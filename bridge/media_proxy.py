# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：本地媒体代理（在线播放）+ Coomer 搜索。

由 gui_bridge.py 按物理顺序拆出（原行区间 13070-13763），
跨段名字由包加载器注入（见 bridge/__init__.py），勿在本文件内新增对其他子模块的 import。"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import re
import json
import logging
import os
import random
import re
from html import unescape as html_unescape
import secrets
import shutil
import sys
import threading
import time
from argparse import Namespace
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse, urljoin
import urllib.parse
import urllib.request

import aiohttp
from aiohttp import web as aiohttp_web
import requests
from bs4 import BeautifulSoup

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import (
    DOWNLOAD_HEADERS,
    KB,
    MAX_RETRIES,
    MAX_WORKERS,
    DEFAULT_CONNECTIONS,
    DownloadInfo,
    DownloadInterrupted,
    RetryConfig,
    SessionInfo,
    SkippedReason,
    UrlInfo,
    UrlType,
)
from src.crawlers.crawler_utils import (
    extract_all_album_item_pages,
    get_download_info,
    get_item_download_link,
    get_item_filename,
)
from src.downloaders.download_utils import detect_range_support
from src.downloaders.media_downloader import MediaDownloader
from src.file_utils import (
    create_download_directory,
    format_directory_name,
    remove_invalid_characters,
    sanitize_directory_name,
    truncate_filename,
)
from src.general_utils import fetch_page
from src.rate_limiter import RateLimiter
from src.url_utils import (
    check_url_type,
    get_album_id,
    get_album_name,
    get_host_page,
    get_identifier,
    normalize_url,
)

if TYPE_CHECKING:
    from enum import IntEnum



from . import _state as _state  # noqa: F401  扁平命名空间：注入此前已加载模块的全部名字
_state.apply_prev(globals())

# ============================
# 本地媒体代理（在线播放：带站点 cookie/代理的流式 HTTP 服务，支持 Range 拖动进度条）
# ============================
# 允许代理的域名关键字（防止本服务被滥用为开放代理）
_MEDIA_ALLOWED_KEYWORDS = (
    "bunkr", "coomer", "coomerfans", "fapello", "pawchive", "e-hentai", "exhentai", "ehgt",
    "hath.network", "twimg", "iwara", "hanime", "hembed", "oreno3d",
    "erommdtube", "asmr", "kiko-play", "pximg", "pixiv", "xhcdn", "ahcdn",
    "fc2",
    # 识图（反向图片搜索）结果缩略图来源：走本地代理以自动带 Referer 绕防盗链
    "saucenao", "iqdb", "ascii2d", "danbooru", "gelbooru", "yande",
    "konachan", "sankaku", "soutubot", "trace.moe", "anilist",
    "lenso", "yandex", "zerochan", "artstation", "deviantart",
)
_media_proxy_port: int = 0  # 启动后填充（127.0.0.1 随机端口）


def _media_host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(k in host for k in _MEDIA_ALLOWED_KEYWORDS)


def media_proxy_url(media_url: str) -> str:
    """把远端媒体直链转换为本地代理 URL（前端 <img>/<video> 直接使用）。"""
    if not media_url or not _media_proxy_port:
        return media_url or ""
    if media_url.startswith(("http://127.0.0.1", "thumb://")):
        return media_url
    from urllib.parse import quote
    return f"http://127.0.0.1:{_media_proxy_port}/media?url={quote(media_url, safe='')}"


def _media_route(url: str) -> tuple[dict, str | None, str | None]:
    """按域名选择 headers / cookie / 代理（与缩略图缓存同套路）。"""
    headers = {"User-Agent": DOWNLOAD_HEADERS.get("User-Agent", "Mozilla/5.0")}
    netloc = urlparse(url).netloc.lower()
    if netloc:
        headers["Referer"] = f"https://{netloc}/"
    cookie = None
    proxy = None
    # Twitter 媒体（pbs.twimg.com / video.twimg.com）：国内必须走代理
    if "twimg" in netloc:
        proxy = _twitter_proxy
    # Iwara 文件（files.iwara.tv / jade·welt·robin.iwara.tv）：按设置走代理；
    # 未配置专属代理时回退系统代理 —— 视频文件 CDN 直连超时（"无法播放媒体"根因），
    # 而 API 域名直连可达，行为对齐 asmr 分支的既有修复；带上登录 token（私密视频需要）
    elif "iwara" in netloc:
        proxy = _iwara_proxy or (_system_proxies() or [None])[0]
        token = _iwara_load_token().get("user_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    # Fapello（fapello.com / content 直链）：必须代理
    elif "fapello" in netloc:
        try:
            proxy = _fapello_session.proxies.get("https") or None  # noqa: F821
        except Exception:
            proxy = "http://127.0.0.1:10809"
    # CoomerFans（coomerfans.com / img*.coomerfans.com）：PoW 会话 cookie + 代理
    elif "coomerfans" in netloc:
        try:
            proxy = _coomerfans_session.proxies.get("https") or None  # noqa: F821
            cookie = "; ".join(f"{c.name}={c.value}" for c in _coomerfans_session.cookies) or None  # noqa: F821
        except Exception:
            proxy = "http://127.0.0.1:10809"
            cookie = None
    # Coomer.st（coomer.st / *.coomer.st）：必须代理 + Accept 反扒头（跨段取 coomerst 会话代理）
    elif "coomer.st" in netloc:
        try:
            proxy = _coomerst_session.proxies.get("https") or None  # noqa: F821
        except Exception:
            proxy = "http://127.0.0.1:10809"
        headers["Accept"] = "text/css"
    # ExHentai 图片（exhentai.org / e-hentai.org / *.hath.network）：必须带账号 cookie + 代理
    elif any(k in netloc for k in ("exhentai", "e-hentai", "ehgt", "hath.network")):
        cookie = _exhentai_cookie_str() or None
        proxy = _exhentai_proxy
    # Pawchive 数据域名（file.pawchive.pw / img.pawchive.pw）：带会话 cookie（部分内容需登录）
    elif "pawchive" in netloc:
        cookie = "; ".join(f"{c.name}={c.value}" for c in _pawchive_session.cookies) or None
    # Hanime1 媒体（vdownload.hembed.com / hanime1.me）：带代理 + Referer
    elif "hanime" in netloc or "hembed" in netloc:
        proxy = _hanime_proxy or None
        headers["Referer"] = f"{HANIME_BASE}/"
    # Pixiv 图片（i.pximg.net）：必须带 Referer: pixiv.net（否则 403），国内走代理
    elif "pximg" in netloc or "pixiv" in netloc:
        proxy = _pixiv_proxy or None
        headers["Referer"] = f"{PIXIV_BASE}/"
    # Oreno3D（oreno3d.com / *.oreno3d.com）：按设置走代理
    elif "oreno3d" in netloc:
        proxy = _oreno_proxy or None
    # EroMMDTube（erommdtube.com）：按设置走代理
    elif "erommdtube" in netloc:
        proxy = _erommd_proxy or None
    # xHamster 媒体（video-h.xhcdn.com / ic-*.xhcdn.com / *.ahcdn.com）：直连挂起（国内），
    # 按设置走 X 站代理 —— 对齐 hanime 分支套路（2026-09-09 播放超时根因）；
    # Accept-Encoding=identity：m3u8 需明文（handler 不转发 Content-Encoding，gzip 体 hls.js 解不了）
    # ahcdn：短视频 HLS variant/分片域名（2026-09-10 实测 ip*.ahcdn.com）
    elif "xhcdn" in netloc or "ahcdn" in netloc or "xhamster" in netloc:
        proxy = _xhamster_proxy or None
        headers["Accept-Encoding"] = "identity"
    # FC2 媒体（video.fc2.com / vip-videoprem*.fc2.com / video-thumbnail*.fc2.com）：
    # 国内需代理，按设置走 FC2 代理（2026-09-10 接入；经函数取值避免跨模块 stale）；
    # 带 FC2 会话 cookie（m3u8/分片接口校验会话，游客也可但登录内容需要）
    elif "fc2" in netloc:
        proxy = fc2_proxy() or None
        headers["Referer"] = "https://video.fc2.com/"
        # m3u8 需明文（handler 不转发 Content-Encoding，gzip 体重写/hls.js 都解不了）；
        # FC2 HLS 是 /api/v3/videoplay/... 无 .m3u8 后缀，靠 Content-Type=mpegurl 命中重写
        headers["Accept-Encoding"] = "identity"
        try:
            cookie = fc2_cookie_header()
            if cookie and urlparse(url).path.startswith("/api/"):
                # 播放 API 带 PHPSESSID（游客/过期会话）会被判 401（site_fc2 对照实验）——
                # 与 _fc2_play_urls 同策略：API 请求剥离会话 cookie 匿名优先
                keep = [p for p in cookie.split("; ")
                        if p and p.split("=", 1)[0] not in ("PHPSESSID", "FCSID")]
                cookie = "; ".join(keep) or "_ac=1; GDPRCHECK=true"
            if cookie:
                headers["Cookie"] = cookie
        except Exception:
            pass
    # ASMR 音声（api.asmr-200.com / *.kiko-play-niptan.one 等）：按设置走代理；
    # 未配置专属代理时回退系统代理 —— requests 会读 Windows 注册表系统代理而
    # aiohttp 不会，api 域名 DNS 被污染时直连超时（试听失败根因），行为对齐浏览器
    elif "asmr" in netloc or "kiko-play" in netloc:
        proxy = _asmr_proxy or (_system_proxies() or [None])[0]
    if cookie:
        headers["Cookie"] = cookie
    return headers, cookie, proxy


def _asmr_media_stream_sync(url: str, headers: dict, range_header: str | None):
    """用 _asmr_session（requests）打开 ASMR 媒体流。

    ASMR 播放不走 aiohttp 转发的原因：aiohttp 只认环境变量代理而不读 Windows
    注册表系统代理，且经代理的长流存在中途断流问题；_asmr_session（requests，
    自动读系统代理、与 API/下载同通道）实测最稳。
    """
    h = dict(headers)
    if range_header:
        h["Range"] = range_header
    return _asmr_session.get(url, headers=h, stream=True, timeout=(10, 60))


async def _asmr_stream_response(request: "aiohttp.web.Request", url: str,
                                headers: dict, range_header: str | None):
    """ASMR 媒体代理：requests 流式转发到本地响应（支持 Range 拖动进度条）。"""
    web = aiohttp_web
    try:
        resp = await asyncio.to_thread(_asmr_media_stream_sync, url, headers, range_header)
    except Exception as exc:
        return web.Response(status=502, text=f"转发失败: {exc}")
    if resp.status_code >= 400:
        resp.close()
        return web.Response(status=resp.status_code, text="远端返回错误")
    stream = web.StreamResponse(status=resp.status_code,
                                reason=resp.reason if resp.status_code != 200 else "OK")
    # 渲染进程（file:// 源）fetch 文本类资源（如音声字幕）需要 CORS 头；127.0.0.1 随机端口，放开无风险
    stream.headers["Access-Control-Allow-Origin"] = "*"
    for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
        v = resp.headers.get(h)
        if v:
            stream.headers[h] = v
    await stream.prepare(request)
    loop = asyncio.get_running_loop()
    try:
        it = resp.iter_content(64 * 1024)
        while True:
            chunk = await loop.run_in_executor(None, next, it, None)
            if not chunk:
                break
            await stream.write(chunk)
        await stream.write_eof()
    except Exception:
        # 客户端暂停/拖动进度条会主动断开连接，属正常现象
        pass
    finally:
        resp.close()
    return stream


async def _media_proxy_handler(request: "aiohttp.web.Request") -> "aiohttp.web.StreamResponse":
    """GET /media?url=<远端媒体直链>：流式转发（支持 Range，视频可拖动进度条）。"""
    web = aiohttp_web
    url = request.query.get("url") or ""
    if not url.startswith(("http://", "https://")) or not _media_host_allowed(urlparse(url).netloc):
        return web.Response(status=403, text="不允许的媒体地址")
    headers, _, proxy = _media_route(url)
    # 透传 Range（视频拖动进度条必需）
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header
    netloc = urlparse(url).netloc.lower()
    # ASMR 音声：走 requests 通道（系统代理 + 与 API/下载同路），避开 aiohttp 代理链路断流
    if "asmr" in netloc or "kiko-play" in netloc:
        return await _asmr_stream_response(request, url, headers, range_header)
    try:
        # auto_decompress=False：按原始字节流转发，Content-Length 才能对得上。
        # 共享连接池（此前每请求新建 session，几十张缩略图并发 = 几十次完整 TLS
        # 握手 → 慢 + 上游连接风暴，Pixiv 图片大量加载失败）
        session = _get_media_session()
        upstream = None
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                upstream = await session.get(
                    url, headers=headers, proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=60),
                    allow_redirects=True,
                )
                break
            except (aiohttp.ClientConnectorError, aiohttp.ServerTimeoutError) as exc:
                # 上游连接失败重试一次（连接池换新连接）；客户端中途断开
                # （Cannot write to closing transport）属正常取消，不重试
                last_exc = exc
                if _attempt:
                    raise
                await asyncio.sleep(0.4)
        if upstream is None:
            raise RuntimeError(f"上游连接失败: {last_exc}")
        if upstream.status >= 400:
            await upstream.release()
            return web.Response(status=upstream.status, text="远端返回错误")
        # HLS 播放列表：把相对 URI 重写为「代理绝对地址」——hls.js 会把相对地址
        # 解析到 127.0.0.1 代理路径下而非原站，导致 levelLoadError（2026-09-09 X 站播放根因）
        ctype = (upstream.headers.get("Content-Type") or "").lower()
        if "mpegurl" in ctype or url.split("?")[0].lower().endswith(".m3u8"):
            raw = await upstream.read()
            await upstream.release()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", "ignore")
            base = str(upstream.url)
            out = []
            for line in text.splitlines():
                ls = line.strip()
                if ls.startswith("#"):
                    m = re.search(r'URI="([^"]+)"', ls)
                    if m:
                        absu = urljoin(base, m.group(1))
                        ls = ls.replace(m.group(1), f"/media?url={urllib.parse.quote(absu, safe='')}")
                    out.append(ls)
                elif ls:
                    absu = urljoin(base, ls)
                    out.append(f"/media?url={urllib.parse.quote(absu, safe='')}")
                else:
                    out.append(ls)
            return web.Response(
                status=200,
                body=(chr(10).join(out) + chr(10)).encode("utf-8"),
                headers={"Content-Type": "application/vnd.apple.mpegurl",
                         "Access-Control-Allow-Origin": "*"},
            )
        stream = web.StreamResponse(
            status=upstream.status,
            reason=upstream.reason if upstream.status != 200 else "OK",
        )
        stream.headers["Access-Control-Allow-Origin"] = "*"
        for h in ("Content-Type", "Content-Length", "Content-Range",
                  "Accept-Ranges", "ETag", "Last-Modified"):
            v = upstream.headers.get(h)
            if v:
                stream.headers[h] = v
        await stream.prepare(request)
        try:
            async for chunk in upstream.content.iter_chunked(256 * 1024):
                await stream.write(chunk)
        finally:
            await stream.write_eof()
            upstream.release()
        return stream
    except Exception as exc:
        logging.debug("媒体代理转发失败 %s: %s", url, exc)
        return web.Response(status=502, text=f"转发失败: {exc}")


_media_session: "aiohttp.ClientSession | None" = None


def _get_media_session() -> "aiohttp.ClientSession":
    """共享媒体转发连接池（keep-alive 复用 TLS 连接；每请求新建 session 的
    时代几十张缩略图并发 = 几十次完整握手，Pixiv 图片大量加载失败）。"""
    global _media_session
    if _media_session is None or _media_session.closed:
        _media_session = aiohttp.ClientSession(
            auto_decompress=False,
            connector=aiohttp.TCPConnector(
                limit=48, limit_per_host=24, ttl_dns_cache=300,
                enable_cleanup_closed=True,
            ),
        )
    return _media_session


async def start_media_proxy() -> int:
    """启动本地媒体代理（127.0.0.1 随机端口），并通知前端端口。"""
    global _media_proxy_port
    if _media_proxy_port:
        return _media_proxy_port
    app = aiohttp_web.Application()
    app.router.add_get("/media", _media_proxy_handler)
    runner = aiohttp_web.AppRunner(app, access_log=None)
    await runner.setup()
    site = aiohttp_web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    addresses = runner.addresses or [("127.0.0.1", 0)]
    _media_proxy_port = int(addresses[0][1])
    logging.info("媒体代理已启动: http://127.0.0.1:%d/media", _media_proxy_port)
    emit({"event": "media_proxy_ready", "port": _media_proxy_port})
    return _media_proxy_port


async def resolve_media_url(item: dict) -> None:
    """解析条目的媒体直链（在线播放用）。

    - Coomer/Pawchive/Twitter/Iwara：条目已带 media_url，直接返回
    - Bunkr：item_page 是文件页，走签名 API 懒解析直链
    - ExHentai：item_page 是图片页，解析 #img 直链
    成功后发 media_url_resolved 事件，前端把直链换成本地代理地址播放。
    """
    item_page = str(item.get("item_page") or "")
    media_url = str(item.get("media_url") or "")
    site = str(item.get("site") or "")
    event = {"event": "media_url_resolved", "item_page": item_page,
             "media_url": "", "success": False, "message": ""}
    try:
        if media_url:
            event.update({"media_url": media_url, "success": True})
            emit(event)
            return
        netloc = urlparse(item_page).netloc.lower()
        if "bunkr" in netloc:
            # Bunkr 文件页：签名 API 返回直链（与下载流程同一套解析）
            async with aiohttp.ClientSession() as session:
                link = await get_item_download_link(session, item_page)
            if link:
                event.update({"media_url": link, "success": True})
            else:
                event["message"] = "未能解析 Bunkr 直链（页面可能需要重新解析）"
        elif any(k in netloc for k in ("exhentai", "e-hentai")):
            def _ex_resolve() -> str:
                resp = _exhentai_fetch(item_page)
                soup = BeautifulSoup(resp.text, "html.parser")
                img = soup.select_one("#img")
                src = (img.get("src") or "") if img else ""
                return src if src.startswith("http") else ""
            link = await asyncio.to_thread(_ex_resolve)
            if link:
                event.update({"media_url": link, "success": True})
            else:
                event["message"] = "未能解析图片直链（登录可能已失效）"
        else:
            event["message"] = "该条目没有可播放的直链"
    except Exception as exc:
        event["message"] = f"解析失败: {exc}"
    emit(event)



def _load_thumbnail_index() -> dict:
    """读取缩略图索引，返回 {文件名: 原始URL}。"""
    try:
        with Path(THUMBNAIL_INDEX_FILE).open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_thumbnail_index(index: dict) -> None:
    """保存缩略图索引。"""
    try:
        Path(THUMBNAIL_INDEX_FILE).parent.mkdir(parents=True, exist_ok=True)
        with Path(THUMBNAIL_INDEX_FILE).open("w", encoding="utf-8") as file:
            json.dump(index, file, ensure_ascii=False)
    except OSError as exc:
        logging.warning("保存缩略图索引失败: %s", exc)


def _thumbnail_cache_path(url: str) -> Path:
    """根据缩略图 URL 生成本地缓存文件路径。"""
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
        ext = ".jpg"
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return Path(THUMBNAIL_CACHE_DIR) / f"{digest}{ext}"


# 缩略图下载请求头：带上浏览器 UA 和 Referer，避免被 CDN 判为爬虫拒绝
THUMB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://bunkr.cr/",
}


def _is_valid_image(data: bytes) -> bool:
    """通过文件头（魔数）判断下载内容是否为有效图片，避免写入破损文件。"""
    if not data:
        return False
    if data[:3] == b"\xff\xd8\xff":                    # JPEG
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":               # PNG
        return True
    if data[:4] == b"GIF8":                            # GIF
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WebP
        return True
    head = data[:512].lstrip()
    if b"<svg" in head or b"<?xml" in head:  # SVG
        return True
    return False


def _is_valid_cache_file(path: Path) -> bool:
    """检查已缓存缩略图文件头是否为有效图片。"""
    try:
        with path.open("rb") as file:
            return _is_valid_image(file.read(512))
    except OSError:
        return False


def _extract_item_thumbnail(item_soup: BeautifulSoup) -> str | None:
    """从单个文件页面提取缩略图 URL（og:image，视频和图片都适用）。"""
    if item_soup is None:
        return None
    meta = item_soup.find("meta", property="og:image")
    if meta is None:
        return None
    url = (meta.get("content") or "").strip()
    if not url:
        return None
    # 协议相对 URL（//cdn...）补全为 https
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith("http") else None


def _apply_cached_thumbnails(items: list[dict]) -> None:
    """把已缓存到本地的缩略图替换为 thumb://local/ 路径，加快重复查看速度。"""
    for item in items:
        url = item.get("thumbnail", "")
        if not url:
            continue
        # 兼容旧格式 thumb://<name>，迁移为 thumb://local/<name>
        if url.startswith("thumb://") and not url.startswith("thumb://local/"):
            item["thumbnail"] = "thumb://local/" + url[len("thumb://"):]
            continue
        if not url.startswith("http"):
            continue
        cache_path = _thumbnail_cache_path(url)
        if cache_path.exists() and _is_valid_cache_file(cache_path):
            item["thumbnail"] = f"thumb://local/{cache_path.name}"


async def _cache_thumbnails(items: list[dict]) -> None:
    """后台下载尚未缓存的缩略图到本地。

    只负责落盘，不修改 items（结果已经返回给前端），失败不影响搜索主流程。
    """
    Path(THUMBNAIL_CACHE_DIR).mkdir(parents=True, exist_ok=True)

    pending: list[tuple[str, Path]] = []
    for item in items:
        url = item.get("thumbnail", "")
        if not url.startswith("http"):
            continue
        cache_path = _thumbnail_cache_path(url)
        # 未缓存，或已缓存的破损文件，都重新下载
        if not cache_path.exists() or not _is_valid_cache_file(cache_path):
            pending.append((url, cache_path))

    if not pending:
        return

    async def cache_one(session: aiohttp.ClientSession, url: str, cache_path: Path) -> bool:
        # Referer 跟随缩略图所在站点，避免跨站 Referer 被 CDN 拒绝（Pawchive/Coomer 等）
        headers = dict(THUMB_HEADERS)
        netloc = urlparse(url).netloc
        proxy = None
        if netloc:
            headers["Referer"] = f"https://{netloc}/"
        # ExHentai 系缩略图（exhentai.org/e-hentai.org/ehgt.org，302 跨域到 CDN；
        # hath.network 精灵图缩略图）：用带 cookie + 代理的 requests 会话直接下载
        # （aiohttp 跨域重试/cookie 处理不稳导致缩略图损坏；hath 精灵图必须走代理——
        # 2026-09-13 EX 缩略图改版为 hath 精灵图后加入）
        if netloc.endswith("exhentai.org") or netloc.endswith("e-hentai.org") or netloc.endswith("ehgt.org") or netloc.endswith("hath.network"):
            def _download_ex_thumb() -> bool:
                try:
                    ex_headers = dict(THUMB_HEADERS)
                    ex_headers["Referer"] = f"{EXHENTAI_HOST}/"
                    cookie = _exhentai_cookie_str()
                    if cookie:
                        ex_headers["Cookie"] = cookie
                    resp = _exhentai_session.get(url, timeout=15, headers=ex_headers)
                    if resp.ok and _is_valid_image(resp.content):
                        cache_path.write_bytes(resp.content)
                        return True
                    return False
                except requests.RequestException:
                    return False

            return await asyncio.to_thread(_download_ex_thumb)
        # Twitter/X 缩略图（pbs.twimg.com / video.twimg.com）国内需代理
        if netloc.endswith("twimg.com"):
            proxy = _twitter_proxy
        # ASMR 缩略图（api.asmr-*.com 封面）：与 API 同走 ASMR 代理；
        # 未配置专属代理时回退系统代理 —— aiohttp 不读 Windows 注册表代理，
        # api 域名 DNS 被污染时直连超时，封面全部缓存失败（预览空白根因）
        if "asmr" in netloc:
            proxy = _asmr_proxy or (_system_proxies() or [None])[0]
        # Iwara 缩略图（files.iwara.tv）：专属代理，未配置时回退系统代理
        #（对齐媒体代理的既有修复——files.iwara.tv 直连不通，空代理=全部缓存失败循环）
        if netloc.endswith("iwara.tv"):
            proxy = _iwara_proxy or (_system_proxies() or [None])[0]
        # Hanime1 缩略图（vdownload.hembed.com）国内需代理
        if "hembed" in netloc or "hanime" in netloc:
            proxy = _hanime_proxy or None
            headers["Referer"] = f"{HANIME_BASE}/"
        # Pixiv 缩略图（i.pximg.net）：必须带 Referer: pixiv.net（否则 403），国内走代理
        if "pximg" in netloc or "pixiv" in netloc:
            proxy = _pixiv_proxy or None
            headers["Referer"] = f"{PIXIV_BASE}/"
        # Oreno3D 缩略图（oreno3d.com/storage/...）/ EroMMDTube 缩略图 按设置走代理
        if "oreno3d" in netloc:
            proxy = _oreno_proxy or None
        if "erommdtube" in netloc:
            proxy = _erommd_proxy or None
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=20), headers=headers, proxy=proxy,
            ) as resp:
                if resp.status != 200:
                    logging.debug("缩略图缓存失败 %s: HTTP %s", url, resp.status)
                    return False
                data = await resp.read()
                # 校验文件头，避免把错误页/破损内容写入缓存
                if not _is_valid_image(data):
                    logging.debug("缩略图缓存失败 %s: 内容非有效图片", url)
                    return False
                cache_path.write_bytes(data)
                return True
        except Exception as exc:
            logging.debug("缩略图缓存失败 %s: %s", url, exc)
        return False

    # 共享同一个 session，减少握手开销
    # 并发限制 6：全量并发会触发站点限流/超时，反而批量失败
    sem = asyncio.Semaphore(6)

    async def fetch_one(session: aiohttp.ClientSession, url: str, cache_path: Path) -> bool:
        # 失败自动重试 1 次（弱网/偶发 503 场景，提高缓存成功率）
        for attempt in range(2):
            ok = await cache_one(session, url, cache_path)
            if ok:
                return True
            if attempt == 0:
                await asyncio.sleep(0.8)
        return False

    async with aiohttp.ClientSession() as session:
        async def bounded(url: str, cp: Path) -> bool:
            async with sem:
                return await fetch_one(session, url, cp)

        results = await asyncio.gather(
            *(bounded(url, cp) for url, cp in pending),
        )

    # 更新索引：本地文件名 -> 原始缩略图 URL
    index = _load_thumbnail_index()
    changed = False
    cached_items: list[dict] = []
    for (url, cache_path), ok in zip(pending, results):
        if ok:
            index[cache_path.name] = url
            changed = True
            cached_items.append({
                "url": url,
                "thumbnail": f"thumb://local/{cache_path.name}",
            })
    if changed:
        _save_thumbnail_index(index)

    # 通知前端：哪些缩略图已缓存到本地，前端把还在直连原图的 <img> 换成本地路径
    # （修复：首次查看时原图 URL 直连国内不通 → 一直加载失败；后台缓存完成也无人刷新）
    if cached_items:
        emit({"event": "thumbnails_cached", "items": cached_items})

    # 缓存体积超限时清理最旧的缩略图（节流：每小时最多一次）
    try:
        _cleanup_thumbnail_cache()
    except Exception:
        logging.exception("缩略图缓存清理出错")


async def gui_search(query: str, page: int, per_page: int, options: dict) -> None:
    """搜索 Bunkr / Coomer / Pawchive / ExHentai 并返回结果（按设置中的站点切换）。"""
    if not query.strip():
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return

    # 记录搜索历史（日常 tags 快速搜索用）
    add_search_history(query.strip(), options.get("site") or "bunkr", options.get("pawchive_search_mode") or "")

    # 站点切换：Coomer 模式下搜索 xxxcoomer.com 的作者
    if options.get("site") == "coomer":
        await coomer_search(query)
        return

    # 站点切换：Pawchive 模式下区分画师搜索 / 标签搜索
    if options.get("site") == "pawchive":
        if options.get("pawchive_search_mode") == "tag":
            await pawchive_search_tag(query, page)
        else:
            await pawchive_search_artist(query, page)
        return

    # 站点切换：ExHentai 模式下搜索画廊
    if options.get("site") == "exhentai":
        await exhentai_search(query, page, options)
        return

    # 站点切换：Twitter/X 模式下按用户名搜索用户
    if options.get("site") == "twitter":
        await twitter_search(query)
        return

    # 站点切换：Iwara 模式下搜索视频（关键词 / @用户名）
    if options.get("site") == "iwara":
        await iwara_search(query, page)
        return

    # 站点切换：Hanime1 模式下搜索视频（关键词 + 可选分类）
    if options.get("site") == "hanime":
        await hanime_search(
            query, page,
            options.get("hanime_genre") or "",
            options.get("hanime_sort") or "",
        )
        return

    # 站点切换：Pixiv 模式下搜索（插画/漫画、小说、用户三模式）
    if options.get("site") == "pixiv":
        await pixiv_search(query, page, options.get("pixiv_mode") or "",
                           options.get("pixiv_search_type") or "")
        return

    # 站点切换：Oreno3D / EroMMDTube 模式下搜索视频（关键词）
    if options.get("site") in ("oreno3d", "erommdtube"):
        await oreno_search(query, page, options.get("oreno_sort") or "", options.get("site"))
        return

    # 站点切换：ASMR 音声站模式搜索作品（RJ 号 / 标题 / 社团 / 标签）
    if options.get("site") == "asmr":
        await asmr_search(query, page, bool(options.get("asmr_subtitle")))
        return

    # 站点切换：JavDB 模式搜索（番号 / 标题 / 演员，可带搜索类型 f=）
    if options.get("site") == "javdb":
        await javdb_search(query, page, options.get("javdb_field") or "all")
        return

    # 站点切换：xHamster 模式搜索（jp 域内 /search/{kw}，支持排序）
    if options.get("site") == "xhamster":
        await xhamster_search(query, page, options.get("xhamster_sort") or "")
        return

    emit({"event": "search_start", "query": query, "page": page})
    logging.info("开始搜索: '%s' (第 %d 页)", query, page)

    try:
        soup = await asyncio.to_thread(_fetch_search_page, query, page, per_page)
        if soup is None:
            emit({"event": "search_error", "message": "搜索失败，无法访问搜索服务"})
            return

        items, total_pages = _parse_search_results(soup)

        # 已缓存的缩略图直接使用本地 thumb://，加快重复查看速度
        _apply_cached_thumbnails(items)

        emit({
            "event": "search_result",
            "query": query,
            "page": page,
            "total_pages": total_pages,
            "has_more": page < total_pages,
            "items": items,
        })
        logging.info("搜索完成: '%s' 第 %d/%d 页，%d 个结果", query, page, total_pages, len(items))

        # 后台缓存尚未下载的缩略图，不阻塞结果返回；下次重复查看时命中本地缓存
        asyncio.create_task(_cache_thumbnails(items))

    except Exception as exc:
        emit({"event": "search_error", "message": f"搜索出错: {exc}"})
        logging.exception("搜索出错")


# ============================
# Coomer 站点搜索 (xxxcoomer.com)
# ============================
def _fetch_coomer_search_page(query: str) -> BeautifulSoup | None:
    """同步抓取 xxxcoomer.com 作者搜索页，带限流、重试和指数退避。"""
    _throttle_search()

    for attempt in range(_SEARCH_MAX_RETRIES):
        try:
            response = _coomer_session.get(
                COOMER_HOST,
                params={"q": query},
                timeout=_SEARCH_TIMEOUT,
            )

            if response.status_code == 429:
                backoff = 2 ** (attempt + 1) + random.uniform(0, 1)
                logging.warning("Coomer 搜索被限流(429)，%.1f 秒后重试", backoff)
                time.sleep(backoff)
                continue

            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")

        except requests.RequestException as exc:
            logging.warning(
                "Coomer 搜索请求失败(第 %d/%d 次): %s",
                attempt + 1, _SEARCH_MAX_RETRIES, exc,
            )
            if attempt < _SEARCH_MAX_RETRIES - 1:
                backoff = 2 ** attempt + random.uniform(0.5, 1.5)
                time.sleep(backoff)

    return None


def _parse_coomer_search_results(soup: BeautifulSoup) -> list[dict]:
    """解析 Coomer 作者搜索结果页，返回作者卡片列表。"""
    items: list[dict] = []

    for card in soup.find_all("div", class_="thumb"):
        link = card.find("a", href=True)
        if link is None:
            continue

        album_url = (link.get("href") or "").strip()
        if not album_url:
            continue
        if album_url.startswith("/"):
            album_url = COOMER_HOST + album_url

        # 头像缩略图
        thumbnail = ""
        img = card.find("img")
        if img:
            thumbnail = (img.get("src") or "").strip()
        if thumbnail.startswith("/"):
            thumbnail = COOMER_HOST + thumbnail

        # 作者名
        name_tag = card.find("p")
        album_name = name_tag.get_text(strip=True) if name_tag else ""
        if not album_name:
            album_name = album_url.rstrip("/").rsplit("/", 1)[-1]

        items.append({
            "album_name": album_name,
            "album_url": album_url,
            "thumbnail": thumbnail,
            "files": None,  # 搜索结果页不含文件数
            "site": "coomer",
        })

    return items


async def coomer_search(query: str) -> None:
    """搜索 xxxcoomer.com 作者并返回结果。"""
    emit({"event": "search_start", "query": query, "page": 1})
    logging.info("开始搜索 Coomer 作者: '%s'", query)

    try:
        soup = await asyncio.to_thread(_fetch_coomer_search_page, query)
        if soup is None:
            emit({"event": "search_error", "message": "搜索失败，无法访问 xxxcoomer.com"})
            return

        items = _parse_coomer_search_results(soup)

        # 已缓存的头像直接使用本地 thumb://，加快重复查看速度
        _apply_cached_thumbnails(items)

        emit({
            "event": "search_result",
            "query": query,
            "page": 1,
            "total_pages": 1,
            "has_more": False,
            "items": items,
        })
        logging.info("Coomer 搜索完成: '%s'，%d 个结果", query, len(items))

        # 后台缓存尚未下载的头像缩略图
        asyncio.create_task(_cache_thumbnails(items))

    except Exception as exc:
        emit({"event": "search_error", "message": f"搜索出错: {exc}"})
        logging.exception("Coomer 搜索出错")
