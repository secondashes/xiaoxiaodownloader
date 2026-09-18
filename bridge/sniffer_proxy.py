# -*- coding: utf-8 -*-
"""手动抓取 · 系统代理模式（mitm）——抓取外部浏览器（Chrome/Edge 等）的媒体请求。

与 sniffer.py（应用内嗅探 + 下载提交）互补：本模块提供 res-downloader 同款能力——
本地 mitm HTTP(S) 代理，外部浏览器把系统代理指过来后，其流量经本代理解密嗅探，
媒体响应实时 emit sniff_capture 事件 → 嗅探窗口列表。

组成：
- CA 证书：cache/sniffer_ca/ca.key+ca.crt（首次自动生成，用户点"安装信任证书"进用户信任区）
- 动态叶子证书：per-host 签发并缓存（SNI callback 自动选择）
- 代理服务：每连接一线程；CONNECT 解密 + 明文代理两路；requests 流式转发上游（保留上游 TLS 校验）
- 系统代理开关：写注册表 + WinINET 刷新（关闭时恢复原值）
- 捕获：Content-Type/扩展名识别 video/audio/image/hls，URL 去重

安全约束：捕获仅记录公网 http/https 目标（emit 前校验）；下载提交仍走 sniffer.py 的 sniff_download（同款校验）。
命名：SNIFP_ 前缀唯一（bridge finalize 同名互踩坑；SNIF_ 已被 sniffer.py 使用）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（emit/requests/…）

import asyncio
import ctypes
import ipaddress
import logging
import re
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

# ============================
# 0. 常量 / 状态
# ============================
SNIFP_PROXY_PORT_DEFAULT = 18081
SNIFP_CA_DIR = Path("cache/sniffer_ca")
SNIFP_CA_KEY = SNIFP_CA_DIR / "ca.key"
SNIFP_CA_CRT = SNIFP_CA_DIR / "ca.crt"
SNIFP_LEAF_DIR = SNIFP_CA_DIR / "leaves"

_snifp_server = None          # 服务线程引用（带 _stop_event/_port 属性）
_snifp_lock = threading.RLock()  # RLock：命令 _do 在锁内调用 _snifp_emit 会再次抢锁，Lock（非重入）会自死锁
_snifp_seen_urls = set()      # 捕获去重
_snifp_stats = {"connections": 0, "captured": 0}
_snifp_sysproxy_backup = None  # 开启系统代理前的原值 {"enable":0/1,"server":str}

# 捕获识别表（与主进程 webRequest 监听同规则，双端一致）
# 分片（.ts/.m4s）单列 hlsseg：一个视频要请求上百个分片，归成 video 会把真正的正片
# 挤出前端 MAX_ITEMS 上限（与 gui/electron/main.cjs 的 SNIFFER_SEG_EXT 同口径）。
_SNIFP_SEG_EXT = (".ts", ".m4s")
_SNIFP_VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv")
_SNIFP_AUDIO_EXT = (".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus")
_SNIFP_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp")
_SNIFP_HLS_EXT = (".m3u8", ".mpd")
# 电子书/论文/压缩包：主进程已分类（SNIFFER_DOC_EXT / SNIFFER_ARCHIVE_EXT），此处补齐
_SNIFP_DOC_EXT = (".pdf", ".epub", ".mobi", ".azw", ".azw3", ".djvu",
                  ".doc", ".docx", ".cbr", ".cbz")
_SNIFP_ARCHIVE_EXT = (".zip", ".rar", ".7z", ".tar", ".gz")
_SNIFP_SKIP_EXT = (".js", ".mjs", ".css", ".woff", ".woff2", ".ttf", ".eot",
                   ".html", ".htm", ".xhtml", ".json", ".xml", ".txt", ".wasm")
# 流清单地址特征（URL 里藏着 m3u8/mpd 而非以扩展名结尾的站，如 /nby/m3u8/getM3u8?url=）
_SNIFP_STREAM_HINT = re.compile(r"m3u8|\.mpd", re.I)


def _snifp_emit(payload: dict) -> None:
    """线程安全的 emit（mitm 工作线程 → stdout JSON）。"""
    with _snifp_lock:
        try:
            emit(payload)  # noqa: F821
        except Exception as exc:
            logging.warning("sniffer_proxy emit 失败: %s", exc)


# ============================
# 1. URL 校验（仅公网 http/https，与 sniffer.py 同规则）
# ============================
def _snifp_check_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").strip().lower()
        if not host or host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


def _snifp_classify(url: str, content_type: str) -> str:
    """按扩展名 + Content-Type 归类媒体（js/css/字体/文档排除）。

    分类优先级与 gui/electron/main.cjs attachCaptureListener 保持一致：
    流清单 → 分片（单列） → 文档/压缩包 → 音视频图（content-type 兜底）。
    """
    ct = (content_type or "").lower()
    path = urlparse(url).path.lower()
    if path.endswith(_SNIFP_SKIP_EXT):
        return ""
    if path.endswith(_SNIFP_HLS_EXT) or "mpegurl" in ct or "dash+xml" in ct:
        return "hls"
    # 分片必须早于 video 判定（.ts/.m4s 也在旧 VIDEO_EXT 里，顺序决定归类）
    if path.endswith(_SNIFP_SEG_EXT):
        return "hlsseg"
    if path.endswith(_SNIFP_DOC_EXT) or "application/pdf" in ct:
        return "doc"
    if path.endswith(_SNIFP_ARCHIVE_EXT):
        return "archive"
    if path.endswith(_SNIFP_VIDEO_EXT) or ct.startswith("video/"):
        return "video"
    if path.endswith(_SNIFP_AUDIO_EXT) or ct.startswith("audio/"):
        return "audio"
    if path.endswith(_SNIFP_IMAGE_EXT) or ct.startswith("image/"):
        return "image"
    # 兜底：清单地址藏在查询参数里的站（URL 不含 .m3u8 结尾但路径含 m3u8/mpd）
    if _SNIFP_STREAM_HINT.search(url) and not ct.startswith(("image/", "video/", "audio/")):
        return "hls"
    return ""


def _snifp_capture(url: str, content_type: str, size: int) -> None:
    """媒体命中 → 去重后 emit sniff_capture（嗅探窗口列表实时入列）。"""
    if not _snifp_check_url(url):
        return
    mtype = _snifp_classify(url, content_type)
    if not mtype:
        return
    with _snifp_lock:
        if url in _snifp_seen_urls:
            return
        _snifp_seen_urls.add(url)
        if len(_snifp_seen_urls) > 5000:
            _snifp_seen_urls.clear()
        _snifp_stats["captured"] += 1
    _snifp_emit({
        "event": "sniff_capture",
        "url": url,
        "type": mtype,
        "size": size or 0,
        "page_url": "",
        "ts": int(time.time() * 1000),
    })


# ============================
# 2. CA / 动态叶子证书
# ============================
def _snifp_load_or_create_ca() -> tuple:
    """加载或生成 CA（RSA2048 / CN=小小下载器 Sniffer CA / 10 年）。"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    SNIFP_CA_DIR.mkdir(parents=True, exist_ok=True)
    if SNIFP_CA_KEY.exists() and SNIFP_CA_CRT.exists():
        key = serialization.load_pem_private_key(SNIFP_CA_KEY.read_bytes(), password=None)
        crt = x509.load_pem_x509_certificate(SNIFP_CA_CRT.read_bytes())
        return key, crt
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "小小下载器 Sniffer CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "xiaoxiao-downloader"),
    ])
    crt = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    SNIFP_CA_KEY.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    SNIFP_CA_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
    logging.info("嗅探 CA 已生成: %s", SNIFP_CA_CRT)
    return key, crt


_SNIFP_CA = None          # (key, crt) 惰性
_SNIFP_LEAF_CACHE = {}    # host -> cert_path (pem)
_SNIFP_LEAF_LOCK = threading.Lock()


def _snifp_leaf_for_host(host: str) -> str:
    """为域名签发叶子证书（缓存到 cache/sniffer_ca/leaves/<host>.pem）。"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    with _SNIFP_LEAF_LOCK:
        if host in _SNIFP_LEAF_CACHE:
            return _SNIFP_LEAF_CACHE[host]
        ca_key, ca_crt = _SNIFP_CA
        SNIFP_LEAF_DIR.mkdir(parents=True, exist_ok=True)
        out = SNIFP_LEAF_DIR / f"{host}.pem"   # key+cert 合并 PEM（load_cert_chain 直用）
        if not out.exists():
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, host),
            ])
            crt = (
                x509.CertificateBuilder()
                .subject_name(subject).issuer_name(ca_crt.subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
                .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=825))
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
                .sign(ca_key, hashes.SHA256())
            )
            out.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                ) + crt.public_bytes(serialization.Encoding.PEM)
            )
        _SNIFP_LEAF_CACHE[host] = str(out)
        return str(out)


_SNIFP_SERVER_CTX = None


def _snifp_server_ssl_context() -> ssl.SSLContext:
    """服务端 TLS 上下文：SNI 回调按域名动态出证书；只提供 http/1.1（避免 h2 协商差异）。"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
    ctx.set_alpn_protocols(["http/1.1"])

    def _sni(sock, server_name, ctx_):
        try:
            path = _snifp_leaf_for_host(server_name)
            ctx_.load_cert_chain(path)
        except Exception as exc:
            logging.warning("SNI 证书签发失败 %s: %s", server_name, exc)
        return None

    ctx.sni_callback = _sni
    return ctx


# ============================
# 3. mitm 转发线程（每连接一线程）
# ============================
def _snifp_read_headers(sock) -> tuple[str, dict, bytes]:
    """读一行请求行 + 头（至空行），返回 (请求行, 头dict, 未消费余量字节)。"""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("客户端断开")
        buf += chunk
        if len(buf) > 1 << 20:
            raise ValueError("请求头过大")
    head, rest = buf.split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    request_line = lines[0]
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return request_line, headers, rest


def _snifp_forward(client_sock, method: str, url: str, headers: dict, body: bytes):
    """requests 流式转发 + 嗅探响应。Connection: close 简化协议（浏览器自动并发新连）。

    上游 TLS 校验保持开启（verify 默认 True）——校验失败返回 502，不做降级。
    """
    fwd_headers = {
        k: v for k, v in headers.items()
        if k not in ("proxy-connection", "connection", "keep-alive", "host",
                     "content-length", "transfer-encoding", "accept-encoding",
                     "upgrade-insecure-requests")
    }
    fwd_headers["Accept-Encoding"] = "identity"  # 关压缩：Content-Type/长度直接可见，转发简单
    try:
        resp = requests.request(  # noqa: F821
            method, url, headers=fwd_headers, data=body if body else None,
            stream=True, timeout=(15, 60),
            proxies=_snifp_upstream_proxies(),
        )
    except Exception as exc:
        logging.warning("嗅探上游请求失败 %s %s: %s", method, url[:100], exc)
        try:
            client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except Exception:
            pass
        return

    ctype = resp.headers.get("Content-Type", "")
    try:
        clen = int(resp.headers.get("Content-Length", "0") or 0)
    except ValueError:
        clen = 0
    status_line = f"HTTP/1.1 {resp.status_code} {resp.reason}".encode("iso-8859-1")
    out_headers = ["Connection: close"]
    for k, v in resp.headers.items():
        if k.lower() in ("connection", "keep-alive", "transfer-encoding", "proxy-authenticate",
                         "proxy-connection", "strict-transport-security"):
            continue
        out_headers.append(f"{k}: {v}")
    # 无 Content-Length 时依赖 Connection: close 界定响应结束（不伪声明长度）
    head = status_line + b"\r\n" + "\r\n".join(out_headers).encode("iso-8859-1") + b"\r\n\r\n"
    sent = 0
    try:
        client_sock.sendall(head)
        while True:
            chunk = resp.raw.read(65536, decode_content=False)
            if not chunk:
                break
            client_sock.sendall(chunk)
            sent += len(chunk)
    except Exception as exc:
        logging.debug("嗅探回写中断 %s: %s", url[:80], exc)
    finally:
        resp.close()
    _snifp_capture(url, ctype, clen or sent)


def _snifp_http_session(sock, https: bool):
    """解密后的 HTTP 会话循环（转发声明 Connection: close，逐请求处理后收尾）。"""
    hop_host = ""
    while True:
        try:
            request_line, headers, rest = _snifp_read_headers(sock)
        except Exception:
            return
        parts = request_line.split(" ")
        if len(parts) < 3:
            return
        method, target = parts[0], parts[1]
        if https:
            # 解密隧道内 origin-form：/path?query
            host = headers.get("host") or hop_host
            if not host:
                return
            hop_host = host
            url = f"https://{host}{target}"
        else:
            # 明文代理 absolute-form
            url = target
            host = urlparse(url).netloc
        # 请求体（Content-Length）
        body = rest
        cl = int(headers.get("content-length", "0") or 0)
        while len(body) < cl:
            chunk = sock.recv(65536)
            if not chunk:
                return
            body += chunk
        if cl and len(body) > cl:
            body = body[:cl]
        _snifp_forward(sock, method, url, headers, body)
        # 转发时已声明 Connection: close → 本连接结束
        return


class _PrefilledSock:
    """把已读出的首部字节回放成"可 recv"的伪 socket（透明给 _snifp_read_headers）。"""

    def __init__(self, sock, prefix: bytes):
        self._sock = sock
        self._buf = prefix

    def recv(self, n):
        if self._buf:
            out, self._buf = self._buf[:n], self._buf[n:]
            return out
        return self._sock.recv(n)

    def sendall(self, data):
        return self._sock.sendall(data)

    def settimeout(self, t):
        return self._sock.settimeout(t)

    def close(self):
        return self._sock.close()


def _snifp_handle(conn: socket.socket, addr):
    """连接入口：透明 TLS（WinDivert 改道）/ CONNECT 代理 / 明文代理 三路分发。

    透明模式（抓 QQ/微信等不走系统代理的应用）：首字节 0x16 = TLS ClientHello，
    直接服务端握手（SNI 回调动态出证书），HTTP 层用 Host 头拼目标 URL。
    """
    _snifp_stats["connections"] += 1
    try:
        conn.settimeout(30)
        first = conn.recv(1, socket.MSG_PEEK)
        if first == b"\x16":
            # 透明 TLS：无 CONNECT 行，直接握手进会话（证书由 SNI 回调按域名出）
            conn.settimeout(15)
            tls_sock = _SNIFP_SERVER_CTX.wrap_socket(conn, server_side=True)
            tls_sock.settimeout(30)
            _snifp_http_session(tls_sock, https=True)
            return
        request_line, headers, _rest = _snifp_read_headers(conn)
        parts = request_line.split(" ")
        if len(parts) >= 2 and parts[0].upper() == "CONNECT":
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            conn.settimeout(15)
            tls_sock = _SNIFP_SERVER_CTX.wrap_socket(conn, server_side=True)
            tls_sock.settimeout(30)
            _snifp_http_session(tls_sock, https=True)
        else:
            # 明文 HTTP：把首行+头重新拼给会话处理（absolute-form）
            head = request_line + "\r\n" + "\r\n".join(
                f"{k}: {v}" for k, v in headers.items())
            _snifp_http_session(_PrefilledSock(conn, (head + "\r\n\r\n").encode("iso-8859-1")), https=False)
    except (ssl.SSLError, ConnectionError, socket.timeout, OSError) as exc:
        logging.debug("嗅探连接结束: %s", exc)
    except Exception:
        logging.exception("嗅探连接异常")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _snifp_serve(port: int, stop_event: threading.Event):
    global _SNIFP_SERVER_CTX, _SNIFP_CA
    globals()["_SNIFP_CA"] = _snifp_load_or_create_ca()
    _SNIFP_SERVER_CTX = _snifp_server_ssl_context()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(64)
    srv.settimeout(1.0)
    logging.info("嗅探 mitm 代理已监听 127.0.0.1:%d", port)
    while not stop_event.is_set():
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=_snifp_handle, args=(conn, addr), daemon=True).start()
    srv.close()
    logging.info("嗅探 mitm 代理已停止")


# ============================
# 4. 上游代理 / 系统代理开关
# ============================
_SNIFP_UPSTREAM = "http://127.0.0.1:10809"   # 出口上游（被墙站需要）；off=直连


def _snifp_upstream_proxies() -> dict:
    p = (_SNIFP_UPSTREAM or "").strip()
    if not p or p.lower() == "off":
        return {}
    if not p.startswith(("http://", "https://", "socks5://")):
        p = "http://" + p
    return {"http": p, "https": p}


def _snifp_sysproxy_set(enable: bool, server: str = "") -> dict:
    """写 HKCU Internet Settings + WinINET 刷新；开启前备份原值，关闭时恢复。"""
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    global _snifp_sysproxy_backup
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
        if enable:
            try:
                old_enable, _ = winreg.QueryValueEx(k, "ProxyEnable")
            except OSError:
                old_enable = 0
            try:
                old_server, _ = winreg.QueryValueEx(k, "ProxyServer")
            except OSError:
                old_server = ""
            if _snifp_sysproxy_backup is None:
                _snifp_sysproxy_backup = {"enable": old_enable, "server": old_server}
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
        else:
            bak = _snifp_sysproxy_backup or {"enable": 0, "server": ""}
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, bak["enable"])
            if bak["server"]:
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, bak["server"])
            _snifp_sysproxy_backup = None
    # 广播刷新（InternetSetOption: INTERNET_OPTION_SETTINGS_CHANGED=39 / REFRESH=37）
    wininet = ctypes.windll.wininet
    wininet.InternetSetOptionW(None, 39, None, 0)
    wininet.InternetSetOptionW(None, 37, None, 0)
    return {"ok": True}


# ============================
# 5. GS 命令（async 包装；command_loop 统一 await）
# ============================
async def _snifp_cmd_start(command: dict) -> None:
    def _do():
        with _snifp_lock:
            if _snifp_server and _snifp_server.is_alive():
                port = getattr(_snifp_server, "_port", SNIFP_PROXY_PORT_DEFAULT)
                _snifp_emit({"event": "sniff_proxy_state", "running": True, "port": port,
                             "ca_path": str(SNIFP_CA_CRT)})
                return
            upstream = str(command.get("upstream") or "").strip()
            if upstream:
                globals()["_SNIFP_UPSTREAM"] = upstream
            port = int(command.get("port") or SNIFP_PROXY_PORT_DEFAULT)
            stop_event = threading.Event()
            t = threading.Thread(target=_snifp_serve, args=(port, stop_event), daemon=True)
            t.start()
            t._stop_event = stop_event
            t._port = port
            globals()["_snifp_server"] = t
        time.sleep(0.6)
        srv = globals().get("_snifp_server")
        _snifp_emit({"event": "sniff_proxy_state",
                     "running": bool(srv and srv.is_alive()),
                     "port": getattr(srv, "_port", port) if srv else port,
                     "ca_path": str(SNIFP_CA_CRT)})
    await asyncio.to_thread(_do)


async def _snifp_cmd_stop(command: dict) -> None:
    def _do():
        with _snifp_lock:
            srv = globals().get("_snifp_server")
            if not srv or not srv.is_alive():
                _snifp_emit({"event": "sniff_proxy_state", "running": False, "port": 0})
                return
            srv._stop_event.set()
            globals()["_snifp_server"] = None
        time.sleep(1.2)
        _snifp_emit({"event": "sniff_proxy_state", "running": False, "port": 0})
    await asyncio.to_thread(_do)


async def _snifp_cmd_ca_install(command: dict) -> None:
    def _do():
        _snifp_load_or_create_ca()
        # 用户信任区安装（无需管理员）：certutil -user -addstore Root
        r = subprocess.run(
            ["certutil", "-user", "-addstore", "Root", str(SNIFP_CA_CRT)],
            capture_output=True, text=True, encoding="gbk", errors="replace", timeout=30,
        )
        ok = r.returncode == 0
        msg = "CA 证书已装入用户信任区" if ok else f"安装失败: {str((r.stderr or '') + (r.stdout or ''))[:200]}"
        _snifp_emit({"event": "sniff_ca_result", "ok": ok, "message": msg})
    await asyncio.to_thread(_do)


async def _snifp_cmd_ca_check(command: dict) -> None:
    def _do():
        _snifp_load_or_create_ca()
        r = subprocess.run(
            ["certutil", "-user", "-store", "Root", "小小下载器 Sniffer CA"],
            capture_output=True, text=True, encoding="gbk", errors="replace", timeout=30,
        )
        installed = r.returncode == 0 and "小小下载器 Sniffer CA" in (r.stdout or "")
        _snifp_emit({"event": "sniff_ca_state", "installed": installed,
                     "ca_path": str(SNIFP_CA_CRT)})
    await asyncio.to_thread(_do)


async def _snifp_cmd_sysproxy_on(command: dict) -> None:
    def _do():
        with _snifp_lock:
            srv = globals().get("_snifp_server")
            port = getattr(srv, "_port", SNIFP_PROXY_PORT_DEFAULT) if (srv and srv.is_alive()) else SNIFP_PROXY_PORT_DEFAULT
        r = _snifp_sysproxy_set(True, f"127.0.0.1:{port}")
        _snifp_emit({"event": "sniff_sysproxy_state", "on": True, "port": port, **r})
    await asyncio.to_thread(_do)


async def _snifp_cmd_sysproxy_off(command: dict) -> None:
    def _do():
        r = _snifp_sysproxy_set(False)
        _snifp_emit({"event": "sniff_sysproxy_state", "on": False, **r})
    await asyncio.to_thread(_do)


async def _snifp_cmd_status(command: dict) -> None:
    with _snifp_lock:
        srv = globals().get("_snifp_server")
        running = bool(srv and srv.is_alive())
        port = getattr(srv, "_port", 0) if running else 0
    _snifp_emit({"event": "sniff_proxy_state", "running": running, "port": port,
                 "connections": _snifp_stats["connections"], "captured": _snifp_stats["captured"]})


# 命令表：唯一名，由 bridge/__init__.py 显式并入总表
SNIFP_COMMANDS = {
    "sniff_proxy_start": _snifp_cmd_start,
    "sniff_proxy_stop": _snifp_cmd_stop,
    "sniff_ca_install": _snifp_cmd_ca_install,
    "sniff_ca_check": _snifp_cmd_ca_check,
    "sniff_sysproxy_on": _snifp_cmd_sysproxy_on,
    "sniff_sysproxy_off": _snifp_cmd_sysproxy_off,
    "sniff_proxy_status": _snifp_cmd_status,
}
