# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：BT 下载（磁力链接 / .torrent）—— aria2 集成。

选型：aria2（https://github.com/aria2/aria2，GPL-2.0，Motrix 等产品的下载内核）。
单 exe + JSON-RPC 完备（进度/暂停/续传/文件列表），与 download_manager 任务体系对接最自然。

架构：
- aria2c 进程 lazy 启动（首个 BT 任务时拉起，常驻；后端进程退出时 kill）
- RPC：POST http://127.0.0.1:<port>/jsonrpc（token 鉴权，每会话随机 secret）
- 磁力：addUri(["magnet:?..."])；.torrent：后端先 GET 种子文件 → base64 → addTorrent
- 进度：1s 轮询 tellStatus → live_manager 进度条（下载管理通用 UI）
- 暂停/继续/取消：worker 轮询 task.status 变化 → aria2 forcePause/unpause/remove
- seed-time=0：下载完成即停（不保种）
- 目录：world=surface 落「表世界保存位置」（web_surface_root），里世界落 Downloads
  （album_path 由 download_manager 按既有规则构建，aria2 options.dir 指向它）
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import secrets as _secrets
import socket
import subprocess
import sys
import time

import requests

from . import _state as _state  # noqa: F401  扁平命名空间：注入此前已加载模块的全部名字
_state.apply_prev(globals())

# ============================
# aria2 daemon 管理
# ============================

BT_RPC_PORT_BASE = 16800
BT_RPC_SECRET = _secrets.token_hex(8)
_bt_proc: subprocess.Popen | None = None
_bt_port = 0
import threading  # noqa: E402
_bt_lock = threading.RLock()


def _bt_aria2c_path() -> str:
    """aria2c.exe 定位：打包后 _internal/aria2/（onedir 的 _MEIPASS）、开发态 resources/aria2/。"""
    cands = []
    if getattr(sys, "_MEIPASS", ""):
        cands.append(os.path.join(sys._MEIPASS, "aria2", "aria2c.exe"))
    exe_dir = os.path.dirname(sys.executable)
    cands.append(os.path.join(exe_dir, "aria2", "aria2c.exe"))
    cands.append(os.path.join(exe_dir, "_internal", "aria2", "aria2c.exe"))
    cands.append(os.path.join(os.getcwd(), "resources", "aria2", "aria2c.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return ""


def _bt_free_port() -> int:
    for p in range(BT_RPC_PORT_BASE, BT_RPC_PORT_BASE + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return BT_RPC_PORT_BASE


def _bt_kill_daemon() -> None:
    global _bt_proc
    with _bt_lock:
        if _bt_proc is not None:
            try:
                _bt_proc.kill()
            except Exception:
                pass
            _bt_proc = None


def _bt_ensure_daemon() -> tuple[str, str]:
    """确保 aria2c daemon 在跑，返回 (rpc_base_url, token)。失败抛 RuntimeError。"""
    global _bt_proc, _bt_port
    with _bt_lock:
        if _bt_proc is not None and _bt_proc.poll() is None:
            # 探活
            try:
                _bt_rpc_now(_bt_port, "aria2.getVersion", [], timeout=2)
                return f"http://127.0.0.1:{_bt_port}/jsonrpc", BT_RPC_SECRET
            except Exception:
                try:
                    _bt_proc.kill()
                except Exception:
                    pass
                _bt_proc = None
        exe = _bt_aria2c_path()
        if not exe:
            raise RuntimeError("未找到 aria2c.exe（打包应含 resources/aria2/）")
        _bt_port = _bt_free_port()
        _bt_proc = subprocess.Popen(
            [exe,
             "--enable-rpc", "--rpc-listen-port", str(_bt_port),
             "--rpc-secret", BT_RPC_SECRET,
             "--rpc-listen-all=false",
             "--seed-time=0",              # 下载完成即停，不保种
             "--file-allocation=none",
             "--dht-file-path", os.path.join(os.getcwd(), "cache", "aria2_dht.dat"),
             "--continue", "--max-connection-per-server=16",
             "--split=8", "--bt-max-peers=80",
             "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TinyDownloader/1.0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # 等 RPC 就绪（最多 8s）
        for _ in range(27):
            if _bt_proc.poll() is not None:
                raise RuntimeError(f"aria2c 启动即退出（code={_bt_proc.returncode}）")
            try:
                _bt_rpc_now(_bt_port, "aria2.getVersion", [], timeout=1)
                return f"http://127.0.0.1:{_bt_port}/jsonrpc", BT_RPC_SECRET
            except Exception:
                time.sleep(0.3)
        raise RuntimeError("aria2c RPC 启动超时")


def _bt_rpc_now(port: int, method: str, params: list, timeout: float = 5) -> dict:
    body = {"jsonrpc": "2.0", "id": "bt", "method": method,
            "params": [f"token:{BT_RPC_SECRET}"] + params}
    r = requests.post(f"http://127.0.0.1:{port}/jsonrpc", json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"].get("message") or data["error"])[:200])
    return data.get("result") or {}


def _bt_rpc(method: str, params: list, timeout: float = 10) -> dict:
    port = _bt_port or BT_RPC_PORT_BASE
    return _bt_rpc_now(port, method, params, timeout)


# ============================
# URL 解析与命令入口
# ============================

import re as _re  # noqa: E402

_BTih_RE = _re.compile(r"urn:btih:([a-zA-Z0-9]+)")


def bt_parse(url: str) -> dict:
    """magnet/torrent URL → {"kind":"magnet"|"torrent","btih":...}。非法抛 ValueError。"""
    u = (url or "").strip()
    if u.startswith("magnet:"):
        m = _BTih_RE.search(u)
        if not m:
            raise ValueError("磁力链接缺少 btih（urn:btih:）")
        return {"kind": "magnet", "btih": m.group(1), "raw": u}
    if u.lower().startswith(("http://", "https://")) and ".torrent" in u.lower():
        return {"kind": "torrent", "btih": "", "raw": u}
    raise ValueError("仅支持 magnet: 磁力链接或 .torrent 种子地址")


def _bt_cmd_download(command: dict) -> None:
    """前端「BT 下载」入口：magnet 链接或 .torrent URL → 占位任务 → 启动。"""
    url = (command.get("url") or "").strip()
    album = (command.get("album") or "").strip() or "BT 下载"
    options = command.get("options") or {}
    if command.get("world"):
        options["world"] = command["world"]
    try:
        info = bt_parse(url)
    except ValueError as exc:
        emit({"event": "bt_result", "ok": False, "message": str(exc)})  # noqa: F821
        return
    btih = info["btih"] or f"t{int(time.time())}"
    item = {
        "filename": f"{btih[:16]}.bt",
        "size": None,
        "item_page": url,
        "status": "ok",
        "thumbnail": "",
        "media_url": url,
        "site": "bt",
        "media_type": "bt",
        "post_title": info.get("name") or album,
        "btih": btih,
    }
    # 命令处理循环里 download_manager 可经 finalize 注入直接可达（扁平命名空间）
    task_id = download_manager.submit(  # noqa: F821
        url, [item], options, album, f"bt:{btih[:12]}",
    )
    download_manager.start(task_id)  # noqa: F821
    emit({  # noqa: F821
        "event": "bt_result", "ok": True, "task_id": task_id,
        "btih": btih, "message": "BT 任务已提交，可在下载管理中查看进度",
    })


def _bt_cmd_download_file(command: dict) -> None:
    """前端拖入 .torrent 文件入口：base64 种子内容 → 占位任务 → 启动。

    payload：{b64: <.torrent 文件内容的 base64 字符串>, album: str, world?: str}
    种子内容直接随命令注入任务条目（_bt_torrent_b64），worker 不再发 HTTP 拉取。
    """
    b64 = str(command.get("b64") or "").strip()
    album = (command.get("album") or "").strip() or "BT 下载"
    options = command.get("options") or {}
    if command.get("world"):
        options["world"] = command["world"]
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        emit({"event": "bt_result", "ok": False, "message": "种子文件解码失败（base64 内容无效）"})  # noqa: F821
        return
    # torrent 文件是 bencode 字典，必以 "d" 开头（快速校验，避免把任意文件当种子提交）
    if not raw.startswith(b"d"):
        emit({"event": "bt_result", "ok": False, "message": "不是有效的种子文件"})  # noqa: F821
        return
    # 占位 btih：真实 info-hash 是 info 字典的 sha1，此处仅用作任务分组标识
    btih12 = hashlib.sha1(raw).hexdigest()[:12]
    item = {
        "filename": f"{btih12}.bt",
        "size": None,
        "item_page": "bt:file",
        "status": "ok",
        "thumbnail": "",
        "media_url": "bt:file",
        "site": "bt",
        "media_type": "bt",
        "post_title": album,
        "btih": btih12,
        "_bt_torrent_b64": b64,
    }
    task_id = download_manager.submit(  # noqa: F821
        "bt:file", [item], options, album, f"bt:{btih12}",
    )
    # _task_file_entry 只按 TASK_FILE_FIELDS 白名单构造条目，"_bt_torrent_b64" 会被
    # 丢弃——直接补写进任务文件条目（worker 的 item 就是该条目的引用），
    # 并落盘持久化（重启续传时仍在）
    try:
        t = download_manager.tasks.get(task_id)  # noqa: F821
        if t and t.get("files"):
            t["files"][0]["_bt_torrent_b64"] = b64
            download_manager._save()  # noqa: F821
    except Exception:
        pass
    download_manager.start(task_id)  # noqa: F821
    emit({  # noqa: F821
        "event": "bt_result", "ok": True, "task_id": task_id,
        "btih": btih12, "message": "种子任务已提交，可在下载管理中查看进度",
    })


# ============================
# 下载 worker（download_manager site=="bt" 分支调用）
# ============================

def _bt_poll_sync(item: dict, task: dict, task_id: str, internal_task: int,
                  live_manager, album_path: str) -> tuple[bool, str]:
    """同步轮询 aria2 任务：进度 → live_manager + item.completed；暂停/取消同步到 aria2。

    返回 (True, final_path) 表示完成。失败/取消以异常抛出。
    """
    url = item.get("media_url") or item.get("item_page") or ""
    gid = item.get("_bt_gid") or ""
    last_done = -1.0
    idle = 0
    last_snap = 0.0
    while True:
        time.sleep(1.0)
        status_task = task.get("status")
        if status_task == "cancelled":
            try:
                _bt_rpc("aria2.remove", [[gid]])
            except Exception:
                pass
            raise InterruptedError()
        if status_task == "paused":
            try:
                _bt_rpc("aria2.forcePause", [[gid]])
            except Exception:
                pass
            while task.get("status") == "paused":
                time.sleep(0.8)
            try:
                _bt_rpc("aria2.unpause", [[gid]])
            except Exception:
                pass
            continue
        try:
            s = _bt_rpc("aria2.tellStatus", [[gid],
                        ["status", "totalLength", "completedLength", "downloadSpeed",
                         "errorMessage", "bittorrent", "files"]], timeout=6)
        except Exception as exc:
            logging.warning("BT tellStatus 失败: %s", exc)
            continue
        st = s.get("status") or "active"
        total = float(s.get("totalLength") or 0)
        done = float(s.get("completedLength") or 0)
        speed = float(s.get("downloadSpeed") or 0)
        name = ""
        try:
            name = ((s.get("bittorrent") or {}).get("info") or {}).get("name") or ""
        except Exception:
            name = ""
        if name and str(item.get("filename", "")).endswith(".bt"):
            item["filename"] = f"{name}.bt"
            item["post_title"] = name
        if total > 0:
            pct = round(100.0 * done / total, 1)
            live_manager.update_task(internal_task, pct)
            live_manager.update_log(
                event="BT 进度",
                details=f"{done / 1048576:.1f}/{total / 1048576:.1f}MB · {speed / 1048576:.2f}MB/s")
            now = time.time()
            if now - last_snap > 3:
                item["completed"] = pct
                item["size"] = int(total)
                try:
                    import sys as _sys
                    _dm = _sys.modules["bridge.download_manager"]
                    _dm.download_manager._save()
                    _dm.download_manager.emit_snapshot()
                    last_snap = now
                except Exception:
                    pass
        if st == "active" and done == last_done and speed == 0:
            idle += 1
        else:
            idle = 0
        last_done = done
        if st in ("complete", "finished"):
            files = s.get("files") or []
            paths = [f.get("path") for f in files
                     if f.get("path") and str(f.get("selected", "true")) != "False"]
            if name:
                item["filename"] = name
            item["_final_name"] = name or item.get("filename") or "BT 下载"
            item["_final_path"] = paths[0] if paths else album_path
            item["_bt_files"] = [p for p in paths][:200]
            return True, (paths[0] if paths else album_path)
        if st == "error":
            raise RuntimeError(f"aria2: {(s.get('errorMessage') or 'BT 下载失败')[:180]}")
        # 磁力长时间拿不到元数据/无种子：10 分钟零进展判失败（冷门种常见，可重试）
        if idle > 600:
            raise RuntimeError("BT 任务 10 分钟无进展（无种子或元数据未返回），可稍后重试")


async def bt_download_one(task, item, album_path, task_id, max_retries):
    """BT 下载入口（download_manager site=="bt" 分支）：磁力链接/.torrent → aria2。

    完成/失败/进度沿用 download_manager 通用约定（对齐 site_bilibili.bili_download_one）。
    """
    filename = str(item.get("filename") or "bt_task")
    url = item.get("media_url") or item.get("item_page") or ""
    logging.info("BT worker 启动: url=%s", url[:80])

    live_manager = GuiLiveManager()  # noqa: F821
    live_manager.task_id = task_id
    internal_task = live_manager.add_task()

    def _fail(msg: str) -> None:
        item["status"] = "failed"
        item["error"] = msg[:200]
        task["failed"] = task.get("failed", 0) + 1
        emit({"event": "file_complete", "filename": filename, "success": False,  # noqa: F821
              "task_id": task_id, "error": msg[:160]})
        download_manager._save()  # noqa: F821
        download_manager.emit_snapshot()  # noqa: F821

    item["status"] = "downloading"
    download_manager._save()  # noqa: F821
    download_manager.emit_snapshot()  # noqa: F821

    try:
        # 解析 + 提交到 aria2（阻塞网络，to_thread）
        # bt:file = 拖入 .torrent 注入的 base64 种子（_bt_cmd_download_file），
        # URL 无法过 bt_parse，直接按 torrent 处理
        b64_inline = str(item.get("_bt_torrent_b64") or "")
        if b64_inline:
            info = {"kind": "torrent", "btih": str(item.get("btih") or ""), "raw": url}
        else:
            info = bt_parse(url)
        album_dir = str(album_path)
        os.makedirs(album_dir, exist_ok=True)
        rpc_base, token = _bt_ensure_daemon()
        if info["kind"] == "magnet":
            # aria2 addUri/addTorrent 的 result 直接是 gid 字符串（非 dict）
            gid = str(_bt_rpc("aria2.addUri", [[url], {"dir": album_dir}]))
        else:
            if b64_inline:
                # 种子内容已随命令注入（前端拖入 .torrent 文件场景）——直接解码使用，
                # 不再发 HTTP 拉取；解码/校验异常走通用失败分支
                torrent_raw = base64.b64decode(b64_inline, validate=True)
            else:
                # .torrent URL：拉种子文件（走通用代理，磁力站种子直链常需代理）
                from curl_cffi import requests as _creq
                proxy = "http://127.0.0.1:10809"
                try:
                    cfg = globals().get("_github_proxy_cfg")  # noqa: F821
                    if callable(cfg):
                        proxy = (cfg() or {}).get("proxy") or proxy
                except Exception:
                    pass
                r = _creq.get(url, impersonate="chrome", timeout=60,
                              proxies={"http": proxy, "https": proxy})
                r.raise_for_status()
                torrent_raw = r.content
            if len(torrent_raw) < 20 or not torrent_raw.startswith(b"d"):
                raise RuntimeError("下载到的 .torrent 内容不是有效种子文件")
            # aria2 addTorrent 的 result 直接是 gid 字符串（非 dict）
            gid = str(_bt_rpc("aria2.addTorrent",
                              [base64.b64encode(torrent_raw).decode(), [],
                               {"dir": album_dir}]))
        item["_bt_gid"] = gid
        live_manager.update_log(event="BT 任务", details=f"gid={gid}")

        final_path = await asyncio.to_thread(
            _bt_poll_sync, item, task, task_id, internal_task, live_manager, album_dir)

        item["status"] = "completed"
        item["completed"] = 100
        task["done"] = task.get("done", 0) + 1
        task["completed"] = task.get("completed", 0) + 1
        download_manager._save()  # noqa: F821
        download_manager.emit_snapshot()  # noqa: F821
        emit({"event": "file_complete", "filename": str(item.get("filename")),  # noqa: F821
              "success": True, "task_id": task_id, "path": str(final_path)})
        logging.info("BT 下载完成: %s", final_path)
    except InterruptedError:
        item["status"] = "cancelled" if task.get("status") == "cancelled" else "paused"
        download_manager._save()  # noqa: F821
        download_manager.emit_snapshot()  # noqa: F821
    except Exception as exc:
        import traceback
        logging.warning("BT 下载失败: %s\n%s", exc, traceback.format_exc())
        _fail(str(exc))


# 注册退出清理
import atexit  # noqa: E402
atexit.register(_bt_kill_daemon)


BT_COMMANDS = {
    "bt_download": _bt_cmd_download,
    "bt_download_file": _bt_cmd_download_file,
}
