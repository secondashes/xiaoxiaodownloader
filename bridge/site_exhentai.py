# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：ExHentai（含磁力链接）。

由 gui_bridge.py 按物理顺序拆出（原行区间 2620-3636），
跨段名字由包加载器注入（见 bridge/__init__.py），勿在本文件内新增对其他子模块的 import。"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
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
from urllib.parse import urlparse
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
# ExHentai 站点支持 (exhentai.org)
# ============================
# 站点特点：
# - 需要 e-hentai 账号 cookie（ipb_member_id + ipb_pass_hash）才能访问
# - igneous 是 exhentai 的通行证，会过期；带着失效的 igneous 访问会被拒（返回空页 + igneous=mystery）
# - 正确做法：请求时不带 igneous，服务器验证账号 cookie 后自动下发新 igneous
# - 图片直链在 *.hath.network，带 keystamp 时效签名，下载时需重新解析图片页
# - 请求过快会触发 509 带宽限制，需严格节流
# - 需要 HTTP 代理访问（站点在国内不可直连）
EXHENTAI_HOST = "https://exhentai.org"
EXHENTAI_GALLERY_PAGE_SIZE = 40    # 画廊页每页缩略图数量
EXHENTAI_REQUEST_INTERVAL = 0.4    # 请求最小间隔（秒），防 509（实测 2.5 req/s 安全）
EXHENTAI_DEFAULT_PROXY = "http://127.0.0.1:10809"

_exhentai_session = requests.Session()
_exhentai_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Referer": EXHENTAI_HOST + "/",
})
_exhentai_proxy: str | None = None
_exhentai_logged_in: bool = False
_exhentai_lock = threading.Lock()


def exhentai_set_proxy(proxy: str | None) -> None:
    """设置 ExHentai 访问代理（如 http://127.0.0.1:10809）。"""
    global _exhentai_proxy
    _exhentai_proxy = (proxy or "").strip() or None
    if _exhentai_proxy:
        _exhentai_session.proxies.update({"http": _exhentai_proxy, "https": _exhentai_proxy})
    else:
        _exhentai_session.proxies.clear()
    logging.info("ExHentai 代理已设置: %s", _exhentai_proxy or "（直连）")


def _exhentai_cookie_str() -> str:
    """把账号 cookie + igneous 拼成 Cookie 请求头（不带失效的 igneous）。"""
    cookies: dict = _exhentai_load_cookies()
    parts = []
    if cookies.get("ipb_member_id"):
        parts.append(f"ipb_member_id={cookies['ipb_member_id']}")
    if cookies.get("ipb_pass_hash"):
        parts.append(f"ipb_pass_hash={cookies['ipb_pass_hash']}")
    if cookies.get("ipb_coppa"):
        parts.append(f"ipb_coppa={cookies['ipb_coppa']}")
    igneous = cookies.get("_igneous")  # 后端自动刷新的 igneous（带下划线前缀区分）
    if igneous:
        parts.append(f"igneous={igneous}")
    return "; ".join(parts)


def _exhentai_save_cookies(cookies: dict) -> None:
    """保存 ExHentai cookie（长期保持登录状态，加密存储）。"""
    data = _exhentai_load_cookies()
    data.update({k: v for k, v in cookies.items() if v})
    data["_saved_at"] = time.time()
    _secure_store_write_cred("exhentai", data)


def _exhentai_load_cookies() -> dict:
    """读取已保存的 ExHentai cookie（加密账号存储）。"""
    return _secure_store_read_cred("exhentai")


def exhentai_set_cookies(cookie_str: str) -> None:
    """前端 webview 登录后同步 cookie 字符串（或用户手动粘贴）。"""
    cookies: dict = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            if name.strip():
                cookies[name.strip()] = value.strip()
    if not cookies.get("ipb_member_id") or not cookies.get("ipb_pass_hash"):
        emit({
            "event": "exhentai_login_result",
            "success": False,
            "message": "Cookie 缺少 ipb_member_id 或 ipb_pass_hash，请确认已在浏览器中登录",
        })
        return
    # 同一账号重新同步：保留 igneous（避免首请求 sadpanda）；
    # 切换账号（member id 变化）：旧账号的 igneous / 用户名一并丢弃
    saved = _exhentai_load_cookies()
    if cookies.get("ipb_member_id") == saved.get("ipb_member_id"):
        saved = {k: v for k, v in saved.items() if k == "_igneous"}
    else:
        saved = {}
    saved.update(cookies)
    _exhentai_save_cookies(saved)
    # 立即验证
    ok, username, msg = _exhentai_check_login()
    if ok:
        _record_login_ok("exhentai")
    emit({
        "event": "exhentai_login_result",
        "success": ok,
        "username": username or cookies.get("ipb_member_id", ""),
        "message": msg,
        "network_issue": (not ok) and _login_network_issue("exhentai"),
    })
    _emit_login_info()


def exhentai_clear_cookies() -> None:
    """清除已保存的 ExHentai 登录信息（加密存储）。"""
    global _exhentai_logged_in
    _secure_store_clear_cred("exhentai")
    _exhentai_logged_in = False
    emit({"event": "exhentai_login_result", "success": False, "logout": True, "username": "", "message": "已退出登录"})
    _emit_login_info()


_exhentai_throttle = _make_throttle(EXHENTAI_REQUEST_INTERVAL, lock=_exhentai_lock)


def _exhentai_fetch(url: str, params: dict | None = None, timeout: int = 25) -> requests.Response:
    """带节流和 cookie 管理的 ExHentai 请求。

    igneous 处理策略：请求带缓存的 igneous；若返回空页（sadpanda/mystery），
    去掉 igneous 重试一次，让服务器重新下发有效 igneous。
    """
    _exhentai_throttle()
    cookie = _exhentai_cookie_str()
    headers = dict(_exhentai_session.headers)
    if cookie:
        headers["Cookie"] = cookie

    response = _exhentai_session.get(url, params=params, timeout=timeout, headers=headers)

    # 509 带宽限制：退避后重试一次
    if response.status_code == 509:
        logging.warning("ExHentai 返回 509（带宽限制），退避 10 秒后重试")
        time.sleep(10)
        _exhentai_throttle()
        response = _exhentai_session.get(url, params=params, timeout=timeout, headers=headers)

    # 检查是否返回了新 igneous（服务器每次都可能刷新）
    new_igneous = None
    for sc in response.headers.get("Set-Cookie", "").split(","):
        m = re.search(r"igneous=(\w+)", sc)
        if m:
            new_igneous = m.group(1)
            break

    if new_igneous == "mystery" or (not response.text and response.status_code == 200):
        # igneous 失效：去掉 igneous 重试，让服务器重新下发
        cookies = _exhentai_load_cookies()
        auth_parts = []
        for key in ("ipb_member_id", "ipb_pass_hash", "ipb_coppa"):
            if cookies.get(key):
                auth_parts.append(f"{key}={cookies[key]}")
        headers["Cookie"] = "; ".join(auth_parts)
        _exhentai_throttle()
        response = _exhentai_session.get(url, params=params, timeout=timeout, headers=headers)
        for sc in response.headers.get("Set-Cookie", "").split(","):
            m = re.search(r"igneous=(\w+)", sc)
            if m:
                new_igneous = m.group(1)
                break
        # 认证失败（依然空页）
        if new_igneous == "mystery" or (not response.text and response.status_code == 200):
            raise PermissionError(
                "ExHentai 登录已失效，请在 ExHentai 页面重新登录（浏览器视图）后重试"
            )

    if new_igneous and new_igneous != "mystery":
        cookies = _exhentai_load_cookies()
        if cookies.get("_igneous") != new_igneous:
            cookies["_igneous"] = new_igneous
            _exhentai_save_cookies(cookies)

    return response


def _exhentai_parse_username(html: str) -> str:
    """从页面 HTML 解析登录用户名（多模式匹配，失败返回空串）。"""
    if not html:
        return ""
    # 1. IPB 论坛顶栏 "Logged in as: <a ...>username</a>"
    m = re.search(r"[Ll]ogged in as[^<]{0,20}<a[^>]*>([^<]{1,50})</a>", html)
    if m:
        return m.group(1).strip()
    # 2. showuser 个人资料链接（论坛顶栏）
    m = re.search(r"showuser=\d+[\"'][^>]*>([^<]{1,50})</a>", html)
    if m:
        return m.group(1).strip()
    # 3. 画廊站顶栏问候 "Hello <a ...>username</a>"
    m = re.search(r"Hello[^<]{0,20}<a[^>]*>([^<]{1,50})</a>", html)
    if m:
        return m.group(1).strip()
    # 4. 画廊站用户页链接 /u/<id>/<name>
    m = re.search(r"href=[\"'](?:https?://[^\"']*)?/u/\d+/([^\"'?#]{1,50})[\"']", html)
    if m:
        return m.group(1).strip()
    return ""


def _exhentai_fetch_username() -> str:
    """从 e-hentai 论坛首页解析用户名（cookie 在论坛域同样有效，IPB userlinks 结构稳定）。"""
    try:
        _exhentai_throttle()
        cookie = _exhentai_cookie_str()
        headers = dict(_exhentai_session.headers)
        if cookie:
            headers["Cookie"] = cookie
        resp = _exhentai_session.get("https://forums.e-hentai.org/", timeout=20, headers=headers)
        if resp.status_code == 200:
            return _exhentai_parse_username(resp.text)
    except requests.RequestException:
        pass
    return ""


def _exhentai_check_login() -> tuple[bool, str | None, str]:
    """检查 ExHentai 登录状态，返回 (是否成功, 用户名, 消息)。"""
    global _exhentai_logged_in
    cookies = _exhentai_load_cookies()
    if not cookies.get("ipb_member_id"):
        return False, None, "未配置 ExHentai 登录信息"
    try:
        response = _exhentai_fetch(EXHENTAI_HOST + "/")
        if response.status_code == 200 and len(response.text) > 5000:
            soup = BeautifulSoup(response.text, "html.parser")
            # 登录后页面顶部有 Favorites/My Uploads 链接
            logged = bool(soup.select_one("a[href*='favorites.php'], #userlinks"))
            _exhentai_logged_in = logged
            if logged:
                # 解析真实用户名（账号卡片/档案展示用），解析不到回退 IPB ID
                username = _exhentai_parse_username(response.text) or _exhentai_fetch_username()
                if not username:
                    username = cookies.get("ipb_member_id", "")
                # 持久化用户名，避免每次重新解析
                if username and cookies.get("_username") != username:
                    cookies["_username"] = username
                    _exhentai_save_cookies(cookies)
                return True, username, "ExHentai 登录有效"
        _exhentai_logged_in = False
        return False, None, "ExHentai 登录已失效，请重新同步 Cookie"
    except PermissionError:
        _exhentai_logged_in = False
        return False, None, "ExHentai 登录已失效，请重新同步 Cookie"
    except requests.RequestException as exc:
        _exhentai_logged_in = False
        return False, None, f"ExHentai 连接失败: {exc}（请检查代理设置）"


def is_exhentai_url(url: str) -> bool:
    """判断是否为 ExHentai 画廊链接。"""
    return bool(re.search(r"(e-hentai|exhentai)\.org/g/\d+/[0-9a-f]+", url, re.I))


def _exhentai_parse_gallery_url(url: str) -> dict | None:
    """解析画廊 URL，返回 {gid, token, host}。"""
    m = re.search(r"(https?://(?:e-hentai|exhentai)\.org)/g/(\d+)/([0-9a-f]+)/?", url, re.I)
    if not m:
        return None
    return {"host": m.group(1), "gid": m.group(2), "token": m.group(3)}


def _exhentai_parse_tags(soup: BeautifulSoup) -> dict[str, list[str]]:
    """解析画廊页 tag 表，返回 {分类: [tag, ...]}。"""
    tags: dict[str, list[str]] = {}
    for tr in soup.select("#taglist table tr"):
        tds = tr.select("td")
        if len(tds) < 2:
            continue
        cat = tds[0].get_text(strip=True).rstrip(":").lower()
        values = [a.get_text(strip=True) for a in tds[1].select("a") if a.get_text(strip=True)]
        if cat and values:
            tags[cat] = values
    return tags


def _exhentai_parse_posted_date(soup: BeautifulSoup) -> str:
    """解析画廊发布时间（ISO 格式），解析失败返回空串。"""
    for tr in soup.select("#gdd table tr"):
        text = tr.get_text(" ", strip=True)
        m = re.search(r"Posted:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", text)
        if m:
            return f"{m.group(1)}T{m.group(2)}:00"
    return ""


def _exhentai_artist_folder(tags: dict[str, list[str]], gallery_title: str) -> str:
    """根据画师/社团 tag 推断父文件夹名（同一个画师归到同一文件夹）。"""
    artists = tags.get("artist") or []
    if artists:
        return artists[0]
    groups = tags.get("group") or []
    if groups:
        return groups[0]
    # 无画师/社团 tag：用画廊标题前缀 [社团 (画师)] 提取
    m = re.match(r"\[([^\]]+)\]", gallery_title)
    if m:
        return m.group(1)[:60]
    return "Unknown Artist"


def _exhentai_image_filename(image_url: str, page_no: int, total: int) -> str:
    """从 hath 直链提取文件名；提取失败时用页码命名。"""
    # URL 形如 https://xxx.hath.network:44000/h/<hash>/keystamp=...;fileindex=...;xres=.../name.webp
    m = re.search(r"/([^/?;]+?)(?:\?|$)", image_url)
    name = m.group(1) if m else ""
    if name and Path(name).suffix:
        return name
    return f"page_{page_no:04d}.webp"


async def exhentai_inspect(url: str, options: dict) -> None:
    """解析 ExHentai 画廊：标题/tags/日期 + 全部图片直链（增量标记 is_new）。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "inspect_error", "message": "无法识别的 ExHentai 画廊链接（格式: /g/{id}/{token}/）"})
        return

    gallery_key = f"exhentai_{info['gid']}"
    try:
        # ---------- 缓存 ----------
        # 命中后仍需拉画廊首页校验（1 个请求）：旧版 bug 时代的缓存只解析到 20 张
        #（末页误判），数量不足或无 ver 标记的坏缓存直接丢弃重新全量解析
        gallery_url = f"{info['host']}/g/{info['gid']}/{info['token']}/"
        response = await asyncio.to_thread(_exhentai_fetch, gallery_url)
        soup = BeautifulSoup(response.text, "html.parser")
        total_pages_count = 0
        gpc = soup.select_one(".gpc")
        if gpc:
            m = re.search(r"of\s+(\d+)\s+images", gpc.get_text())
            if m:
                total_pages_count = int(m.group(1))

        cached = _load_album_cache(gallery_key)
        cached_items = (cached or {}).get("items", [])
        _cached_with_thumb = sum(
            1 for it in cached_items if str(it.get("thumbnail") or "").strip())
        cache_ok = (
            cached
            and cached.get("ver") == 2
            and cached_items
            and (not total_pages_count or len(cached_items) >= total_pages_count)
            # 2026-09-13：09-12 重写时代产生的缓存不带缩略图（点开详情整页无图）——
            # 数量够也判废，重新全量解析补缩略图
            and _cached_with_thumb * 2 >= len(cached_items)
        )
        if cache_ok:
            items = cached_items
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or gallery_key, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or info["gid"],
                "album_id": cached.get("album_id") or gallery_key,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 ExHentai 画廊信息: %s (%d 个文件)", gallery_key, len(items))
            return
        if cached:
            logging.info("丢弃过期/不完整的 ExHentai 画廊缓存: %s（缓存 %d 张，站方 %d 张）",
                         gallery_key, len(cached_items), total_pages_count)

        # ---------- 画廊元数据（首页已在上面的缓存校验时拉取） ----------
        gn = soup.select_one("#gn")
        gallery_title = gn.get_text(strip=True) if gn else f"Gallery {info['gid']}"
        tags = _exhentai_parse_tags(soup)
        posted_date = _exhentai_parse_posted_date(soup)
        artist_folder = _exhentai_artist_folder(tags, gallery_title)

        # 页数信息（"Showing 1 - 40 of 92 images"）
        total_pages_count = 0
        gpc = soup.select_one(".gpc")
        if gpc:
            m = re.search(r"of\s+(\d+)\s+images", gpc.get_text())
            if m:
                total_pages_count = int(m.group(1))

        # ---------- 翻页收集全部图片页链接（附带画廊缩略图页上的稳定小图） ----------
        # 缩略图（ehgt.org / e-hentai.org 域名，长期有效）用于文件列表展示；
        # 直链（*.hath.network 带 keystamp 时效签名）仅用于下载（下载/预览时懒解析）。
        # 有总页数时并发收集（Semaphore 3，大画廊 53 页从 2 分钟串行压到 ~40s）；
        # 全程发 inspect_progress（此前翻页阶段零反馈，用户看"处理中 0%"以为卡死）。
        def _parse_gdt(sp):
            """缩略图页条目解析 → (图片页URL, 缩略图URL, 偏移元数据)。

            2026-09-13 实测 EX 改版：缩略图为 CSS 精灵图——页面里没有任何 <img>，
            每页共用一张 hath .webp 拼图挂在内层 div 的 background:url()，靠
            background-position 负偏移切片。旧逻辑只找 <img> → 全部 0 缩略图
            （点开详情整页无图）。现提取精灵 URL + 偏移/尺寸，前端按偏移渲染；
            精灵图由缩略图缓存任务落盘为 thumb:// 稳定显示。"""
            out = []
            for a in sp.select("#gdt a"):
                href = a.get("href", "")
                if not href.startswith("http"):
                    continue
                meta: dict = {}
                img_el = a.select_one("img")
                if img_el:
                    thumb = img_el.get("data-src") or img_el.get("src") or ""
                else:
                    thumb = ""
                    div = a.select_one("div[style*='background']")
                    style = (div.get("style") or "") if div else ""
                    mu = re.search(r"url\(([^)]+)\)", style)
                    if mu:
                        mx = re.search(r"-(\d+)px\s+-(\d+)px", style)
                        mw = re.search(r"width:(\d+)px;height:(\d+)px", style)
                        thumb = mu.group(1)
                        meta = {
                            "thumb_x": int(mx.group(1)) if mx else 0,
                            "thumb_y": int(mx.group(2)) if mx else 0,
                            "thumb_w": int(mw.group(1)) if mw else 200,
                            "thumb_h": int(mw.group(2)) if mw else 287,
                        }
                out.append((href, thumb, meta))
            return out

        first_entries = _parse_gdt(soup)
        image_pages = list(first_entries)
        first_page_count = len(first_entries)
        if total_pages_count and first_page_count:
            import math
            total_gallery_pages = max(1, math.ceil(total_pages_count / first_page_count))
            emit({"event": "inspect_progress", "current": 1, "total": total_gallery_pages,
                  "filename": f"正在收集画廊缩略图页（共约 {total_gallery_pages} 页）..."})  # noqa: F821
            if total_gallery_pages > 1:
                sem = asyncio.Semaphore(3)

                async def fetch_gallery_page(pno: int) -> list[tuple[str, str]]:
                    async with sem:
                        try:
                            resp = await asyncio.to_thread(
                                _exhentai_fetch, f"{gallery_url}?p={pno}")
                            sp = BeautifulSoup(resp.text, "html.parser")
                            entries = _parse_gdt(sp)
                        except (requests.RequestException, PermissionError):
                            return []
                        done = total_gallery_pages - (total_gallery_pages - pno)
                        emit({"event": "inspect_progress", "current": pno + 1,
                              "total": total_gallery_pages,
                              "filename": "正在收集画廊缩略图页..."})  # noqa: F821
                        return entries

                page_results = await asyncio.gather(
                    *(fetch_gallery_page(p) for p in range(1, total_gallery_pages)))
                for entries in page_results:
                    image_pages.extend(entries)
        else:
            # 无总页数（gpc 缺失）：逐页串行，按分页条判定末页
            page_no = 0
            while True:
                page_url = gallery_url if page_no == 0 else f"{gallery_url}?p={page_no}"
                if page_no > 0:
                    response = await asyncio.to_thread(_exhentai_fetch, page_url)
                    soup = BeautifulSoup(response.text, "html.parser")
                page_entries = _parse_gdt(soup)
                if not page_entries:
                    break
                image_pages.extend(page_entries)
                emit({"event": "inspect_progress", "current": page_no + 1,
                      "total": 0, "filename": "正在收集画廊缩略图页..."})  # noqa: F821
                has_next = False
                gtb = soup.select_one(".gtb")
                if gtb is not None:
                    pnums = [int(x) for x in re.findall(r'[?&]p=(\d+)', gtb.decode())]
                    if page_no + 1 <= max(pnums or [0]):
                        has_next = True
                elif page_no == 0:
                    has_next = len(page_entries) >= EXHENTAI_GALLERY_PAGE_SIZE
                if not has_next:
                    break
                page_no += 1

        if not image_pages:
            emit({"event": "inspect_error", "message": "画廊中没有找到图片（可能需要登录或画廊已被删除）"})
            return

        # 去重（缩略图页可能重复出现）
        seen = set()
        image_pages = [e for e in image_pages if not (e[0] in seen or seen.add(e[0]))]

        # ---------- 直接以图片页条目出列（不再逐张解析直链） ----------
        # 直链带 keystamp 时效签名，下载时反正要重新解析（resolve_media_url 懒解析
        # item_page → #img）；此前逐张请求图片页，2000 张画廊要发 2000 个请求、
        # 十几分钟起步——用户看到的就是"只解析出前面一点"。
        total = len(image_pages)
        logging.info("ExHentai 画廊 '%s' 共 %d 张图片", gallery_title, total)
        # 文件名消毒（标题可能含 / \ 等非法字符，此前 636 张全因带 / 的标题写盘失败）
        safe_title = sanitize_filename(gallery_title.strip()) or f"gallery_{info['gid']}"
        items: list[dict] = []
        for idx, (page_url, gdt_thumb, gdt_meta) in enumerate(image_pages, 1):
            it = {
                "filename": f"{safe_title}_{idx:04d}.jpg",
                "size": None,
                "item_page": page_url,
                "status": "ok",
                # 展示用稳定缩略图（ehgt.org / hath 精灵图），下载/预览时懒解析直链
                "thumbnail": gdt_thumb,
                "media_url": "",
                "site": "exhentai",
                "post_title": gallery_title,
                "post_date": posted_date,
                "artist": artist_folder,
                "gallery_url": gallery_url,
            }
            it.update(gdt_meta)
            items.append(it)

        if not items:
            emit({"event": "inspect_error", "message": "画廊中没有找到图片（可能需要登录或画廊已被删除）"})
            return

        _apply_cached_thumbnails(items)
        _mark_items_new(gallery_key, items)

        _save_album_cache(gallery_key, {
            "ver": 2,
            "album_name": gallery_title,
            "album_id": gallery_key,
            "is_album": True,
            "items": items,
        })

        emit({
            "event": "inspect_complete",
            "album_name": gallery_title,
            "album_id": gallery_key,
            "is_album": True,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 画廊解析完成: %s, 共 %d 个文件", gallery_title, len(items))

    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "inspect_error", "message": f"ExHentai 访问失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 解析出错")
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("ExHentai 解析过程出错")


# ============================
# ExHentai 磁力链接（torrent）
# ============================
def _bdecode(data: bytes, pos: int = 0):
    """简易 bencode 解码器（解析 .torrent 文件用）。"""
    c = data[pos:pos + 1]
    if c == b"i":
        end = data.index(b"e", pos)
        return int(data[pos + 1:end]), end + 1
    if c == b"l":
        pos += 1
        result = []
        while data[pos:pos + 1] != b"e":
            v, pos = _bdecode(data, pos)
            result.append(v)
        return result, pos + 1
    if c == b"d":
        pos += 1
        result = {}
        while data[pos:pos + 1] != b"e":
            k, pos = _bdecode(data, pos)
            v, pos = _bdecode(data, pos)
            result[k] = v
        return result, pos + 1
    colon = data.index(b":", pos)
    length = int(data[pos:colon])
    start = colon + 1
    return data[start:start + length], start + length


def _torrent_infohash(torrent_data: bytes) -> str | None:
    """从 .torrent 文件字节中提取 infohash（构造磁力链接用）。"""
    try:
        idx = torrent_data.find(b"4:infod")
        if idx < 0:
            idx = torrent_data.find(b"4:infol")
        if idx < 0:
            return None
        pos = idx + 6
        _, end = _bdecode(torrent_data, pos)
        info_bytes = torrent_data[pos:end]
        return hashlib.sha1(info_bytes).hexdigest()
    except (ValueError, IndexError):
        return None


async def exhentai_get_torrents(url: str) -> None:
    """获取画廊的种子列表（弹窗选择用）。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "exhentai_torrents_error", "message": "无效的画廊链接"})
        return
    try:
        response = await asyncio.to_thread(
            _exhentai_fetch,
            f"{EXHENTAI_HOST}/gallerytorrents.php",
            {"gid": info["gid"], "t": info["token"]},
        )
        soup = BeautifulSoup(response.text, "html.parser")

        torrents = []
        # 每个种子一行：.torrent 下载链接 + 名称/大小/做种信息
        forms = soup.select("form")
        rows = soup.select("tr")
        # 通用解析：找所有 .torrent 链接，按行关联信息
        torrent_links = [a for a in soup.select("a[href$='.torrent']")]
        for link in torrent_links:
            href = link.get("href", "")
            if href.startswith("/"):
                href = EXHENTAI_HOST + href
            # 从所在行提取信息
            row = link.find_parent("tr") or link.find_parent("div")
            row_text = row.get_text(" ", strip=True) if row else ""
            size_m = re.search(r"Size:\s*([\d.]+\s*[KMG]?i?B)", row_text)
            posted_m = re.search(r"Posted:\s*([\d-]+\s+[\d:]+)", row_text)
            seeds_m = re.search(r"Seeds:\s*(\d+)", row_text)
            peers_m = re.search(r"Peers:\s*(\d+)", row_text)
            # 种子名：链接文本或行内长文本
            name = link.get_text(strip=True)
            if not name and row:
                # 名称通常是行里最长的文本块
                texts = [t.strip() for t in row.stripped_strings if len(t.strip()) > 8]
                name = texts[0] if texts else "torrent"
            torrents.append({
                "name": name or "torrent",
                "url": href,
                "size": size_m.group(1) if size_m else "",
                "posted": posted_m.group(1) if posted_m else "",
                "seeds": int(seeds_m.group(1)) if seeds_m else 0,
                "peers": int(peers_m.group(1)) if peers_m else 0,
            })

        if not torrents:
            emit({"event": "exhentai_torrents", "torrents": [], "message": "该画廊没有可用的种子"})
            return

        emit({"event": "exhentai_torrents", "torrents": torrents})
        logging.info("ExHentai 种子列表: %d 个", len(torrents))

    except PermissionError as exc:
        emit({"event": "exhentai_torrents_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "exhentai_torrents_error", "message": f"获取种子失败: {exc}"})
        logging.exception("ExHentai 获取种子失败")


async def exhentai_get_magnet(torrent_url: str) -> None:
    """下载 .torrent 文件并解析出磁力链接。"""
    try:
        response = await asyncio.to_thread(_exhentai_fetch, torrent_url)
        if response.status_code != 200 or not response.content[:1] == b"d":
            emit({"event": "exhentai_magnet_error", "message": "种子文件下载失败"})
            return
        infohash = _torrent_infohash(response.content)
        if not infohash:
            emit({"event": "exhentai_magnet_error", "message": "无法解析种子文件"})
            return
        # 从种子文件内提取真实名称（info.name）
        dn = ""
        try:
            data, _ = _bdecode(response.content)
            if isinstance(data, dict):
                info = data.get(b"info")
                if isinstance(info, dict) and info.get(b"name"):
                    dn = info[b"name"].decode("utf-8", "replace")
        except (ValueError, IndexError):
            pass
        magnet = f"magnet:?xt=urn:btih:{infohash}"
        if dn:
            from urllib.parse import quote
            magnet += f"&dn={quote(dn)}"
        magnet += "&tr=http://ehtracker.org/announce"
        emit({"event": "exhentai_magnet", "magnet": magnet, "infohash": infohash, "name": dn})
        logging.info("ExHentai 磁力链接: %s (%s)", infohash, dn)
    except PermissionError as exc:
        emit({"event": "exhentai_magnet_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "exhentai_magnet_error", "message": f"种子下载失败: {exc}"})
        logging.exception("ExHentai 磁力解析失败")


async def exhentai_favorites(page: int = 1) -> None:
    """获取我的收藏列表（favorites.php，next 游标分页，复用搜索结果视图）。"""
    page = max(1, int(page))
    try:
        emit({"event": "search_start", "query": "__ex_favorites__", "page": page})
        cursors = _load_ex_cursors()
        entry = cursors.get("__ex_favorites__", {})
        if not isinstance(entry, dict):
            entry = {}
        pages_map = {int(k): v for k, v in entry.items() if str(k).isdigit()}

        cur = 1
        for p in sorted(pages_map):
            if p <= page:
                cur = max(cur, p)

        html = ""
        items: list[dict] = []
        while cur <= page:
            params: dict = {}
            if cur > 1:
                cursor = pages_map.get(cur)
                if cursor is None:
                    break
                params["next"] = cursor
            response = await asyncio.to_thread(_exhentai_fetch, EXHENTAI_HOST + "/favorites.php", params)
            html = response.text
            gids = _parse_ex_gallery_ids(html)
            if cur == page:
                items = _parse_ex_search_page(html)
                if gids:
                    pages_map[page + 1] = gids[-1]
                break
            if not gids:
                break
            pages_map[cur + 1] = gids[-1]
            cur += 1

        if page > 1 and not items and not pages_map.get(page):
            emit({"event": "search_error", "message": f"收藏第 {page} 页不存在或超出范围"})
            return

        # 收藏页无总数提示："Showing 1 - 25 of 89"（无 about）
        total_results = entry.get("total_results") or 0
        m = re.search(r"(?:of|about)\s+([\d,]+)\s+(?:results|entries)", html)
        if m:
            try:
                total_results = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        per_page = len(items) or 25
        # 无总数提示（单页放得下）时 total_pages=0（未知），分页栏仅靠 has_more 翻页
        total_pages = max(1, -(-total_results // per_page)) if total_results > 0 else 0
        has_next = bool(re.search(r"[?&]next=\d+", html)) and bool(items)

        entry = {"total_results": total_results}
        for p, gid in sorted(pages_map.items()):
            entry[str(p)] = gid
        cursors["__ex_favorites__"] = entry
        _save_ex_cursors(cursors)

        # 隐藏标签过滤（用户手动标记的 tags 不显示）
        items, hidden_count = _exhentai_filter_hidden_tags(items)

        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": "__ex_favorites__",
            "page": page,
            "total_pages": total_pages,
            "total_results": total_results,
            "has_more": has_next,
            "hidden_count": hidden_count,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 我的收藏: 第 %d 页，%d 个（隐藏 %d）", page, len(items), hidden_count)

    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "search_error", "message": f"获取收藏失败: {exc}（请检查登录状态和代理）"})
        logging.exception("ExHentai 收藏获取失败")


def _exhentai_parse_image_entries(soup: BeautifulSoup) -> list[dict]:
    """解析画廊缩略图页的 #gdt：图片页链接 + 稳定缩略图（详情页图片列表用）。"""
    entries = []
    for a in soup.select("#gdt a"):
        page_url = a.get("href", "")
        if not page_url.startswith("http"):
            continue
        img_el = a.select_one("img")
        thumb = ""
        if img_el:
            thumb = img_el.get("data-src") or img_el.get("src") or ""
        entries.append({"page_url": page_url, "thumb": thumb})
    return entries


def _exhentai_gallery_pages(soup: BeautifulSoup) -> int:
    """从分页表 .ptt 解析画廊缩略图页总数。"""
    nums = []
    for td in soup.select(".ptt td"):
        t = td.get_text(strip=True)
        if t.isdigit():
            nums.append(int(t))
    return max(nums) if nums else 1


async def exhentai_gallery_info(url: str) -> None:
    """获取画廊完整信息（标题/上传者/发布时间/父画廊/大小/页数/收藏数/评分/全部分组标签）。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "ex_gallery_info_error", "message": "无效的画廊链接"})
        return
    try:
        gallery_url = f"{info['host']}/g/{info['gid']}/{info['token']}/"
        response = await asyncio.to_thread(_exhentai_fetch, gallery_url)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("#gn")
        title = title.get_text(strip=True) if title else f"Gallery {info['gid']}"
        title_jp = soup.select_one("#gj")
        title_jp = title_jp.get_text(strip=True) if title_jp else ""

        uploader = ""
        gdn = soup.select_one("#gdn a")
        if gdn:
            uploader = gdn.get_text(strip=True)

        posted = ""
        posted_raw = _exhentai_parse_posted_date(soup)
        if posted_raw:
            posted = posted_raw.replace("T", " ")[:16]

        # 元数据表（#gdd）：Parent / Visible / Language / File Size / Length / Favorited
        parent = ""
        visible = ""
        language = ""
        file_size = ""
        length = ""
        favorited = ""
        for tr in soup.select("#gdd tr"):
            label_td = tr.select_one("td.gdt1")
            value_td = tr.select_one("td.gdt2")
            if not label_td or not value_td:
                continue
            label = label_td.get_text(strip=True).rstrip(":").lower()
            value = value_td.get_text(strip=True)
            if label == "parent":
                link = value_td.select_one("a#parent_link") or value_td.select_one("a")
                parent = link.get("href", "") if link else ""
            elif label == "visible":
                visible = value
            elif label == "language":
                language = value
            elif label == "file size":
                file_size = value
            elif label == "length":
                length = value
            elif label == "favorited":
                favorited = value

        # 评分：#rating_label "Average: 4.70" + #rating_count "146"
        rating = ""
        rating_count = ""
        rating_label = soup.select_one("#rating_label")
        if rating_label:
            text = rating_label.get_text(strip=True)
            m = re.search(r"Average:\s*([\d.]+)", text)
            if m:
                rating = m.group(1)
        rating_count_el = soup.select_one("#rating_count")
        if rating_count_el:
            rating_count = rating_count_el.get_text(strip=True)

        # 分组标签（female:/male:/mixed:/artist:/group:/parody: 等）
        tags = _exhentai_parse_tags(soup)

        # 图片列表（缩略图页第 0 页的 #gdt 稳定缩略图，tag 下方展示 + 翻页浏览）
        images = _exhentai_parse_image_entries(soup)
        gallery_pages = _exhentai_gallery_pages(soup)
        image_count = 0
        gpc_text = soup.select_one(".gpc")
        if gpc_text:
            m_cnt = re.search(r"of\s+(\d+)\s+images", gpc_text.get_text())
            if m_cnt:
                image_count = int(m_cnt.group(1))
        if not image_count:
            image_count = len(images)
        if images:
            # 稳定缩略图走本地缓存（ehgt.org 需带 cookie + 代理）
            thumb_items = [{"thumbnail": e["thumb"]} for e in images]
            _apply_cached_thumbnails(thumb_items)
            for e, ti in zip(images, thumb_items):
                if ti.get("thumbnail").startswith("thumb://"):
                    e["thumb"] = ti["thumbnail"]
            asyncio.create_task(_cache_thumbnails(thumb_items))

        # 封面缩略图（同步下载到本地缓存：前端 img 无法带 EX cookie 加载远程封面）
        # 两种形式：#gd1 内 img 标签，或 #gd1 div 的 background:url() 样式
        thumb = ""
        gd1 = soup.select_one("#gd1")
        if gd1:
            img_el = gd1.select_one("img")
            if img_el:
                thumb = img_el.get("data-src") or img_el.get("src") or ""
            else:
                style = gd1.select_one("div").get("style", "") if gd1.select_one("div") else ""
                m_bg = re.search(r"url\((https?://[^)]+)\)", style or "")
                if m_bg:
                    thumb = m_bg.group(1)
        if thumb:
            try:
                cache_path = _thumbnail_cache_path(thumb)
                if not cache_path.exists() or not _is_valid_cache_file(cache_path):
                    Path(THUMBNAIL_CACHE_DIR).mkdir(parents=True, exist_ok=True)
                    headers = dict(THUMB_HEADERS)
                    headers["Referer"] = f"{EXHENTAI_HOST}/"
                    cookie = _exhentai_cookie_str()
                    if cookie:
                        headers["Cookie"] = cookie
                    img_resp = _exhentai_session.get(thumb, timeout=10, headers=headers)
                    if img_resp.ok and img_resp.content[:1] in (b"\xff", b"\x89", b"G"):
                        cache_path.write_bytes(img_resp.content)
                if cache_path.exists() and _is_valid_cache_file(cache_path):
                    thumb = f"thumb://local/{cache_path.name}"
            except requests.RequestException as exc:
                logging.warning("画廊封面下载失败: %s", exc)

        emit({
            "event": "ex_gallery_info",
            "url": gallery_url,
            "title": title,
            "title_jp": title_jp,
            "uploader": uploader,
            "posted": posted,
            "parent": parent,
            "visible": visible,
            "language": language,
            "file_size": file_size,
            "length": length,
            "favorited": favorited,
            "rating": rating,
            "rating_count": rating_count,
            "tags": tags,
            "thumbnail": thumb,
            "images": images,
            "image_count": image_count,
            "gallery_page": 0,
            "gallery_pages": gallery_pages,
        })
        logging.info("ExHentai 画廊信息: %s", title[:50])

    except PermissionError as exc:
        emit({"event": "ex_gallery_info_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "ex_gallery_info_error", "message": f"获取画廊信息失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 画廊信息获取失败")


async def exhentai_gallery_page(url: str, page: int = 0) -> None:
    """画廊详情页图片列表翻页：解析指定缩略图页的 #gdt 稳定缩略图。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "ex_gallery_page_error", "message": "无效的画廊链接"})
        return
    try:
        gallery_url = f"{info['host']}/g/{info['gid']}/{info['token']}/"
        target = gallery_url if page <= 0 else f"{gallery_url}?p={page}"
        response = await asyncio.to_thread(_exhentai_fetch, target)
        soup = BeautifulSoup(response.text, "html.parser")
        images = _exhentai_parse_image_entries(soup)
        gallery_pages = _exhentai_gallery_pages(soup)
        thumb_items = [{"thumbnail": e["thumb"]} for e in images]
        _apply_cached_thumbnails(thumb_items)
        for e, ti in zip(images, thumb_items):
            if ti.get("thumbnail").startswith("thumb://"):
                e["thumb"] = ti["thumbnail"]
        asyncio.create_task(_cache_thumbnails(thumb_items))
        emit({
            "event": "ex_gallery_page",
            "url": gallery_url,
            "page": max(0, page),
            "pages": gallery_pages,
            "images": images,
        })
    except PermissionError as exc:
        emit({"event": "ex_gallery_page_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "ex_gallery_page_error", "message": f"获取画廊图片页失败: {exc}"})
        logging.exception("ExHentai 画廊图片页获取失败")


def _exhentai_image_page_with_nl(page_url: str) -> str:
    """解析图片页，返回带 ?nl=token 的刷新链接（原站"图片加载失败点击刷新"）。

    H@H 节点故障时，带 nl 参数重新请求图片页会换一个节点返回新直链。
    """
    response = _exhentai_fetch(page_url)
    m = re.search(r"nl\(['\"]([^'\"]+)['\"]\)", response.text)
    token = m.group(1) if m else ""
    if not token:
        return page_url
    sep = "&" if "?" in page_url else "?"
    return f"{page_url}{sep}nl={token}"


async def exhentai_reload_image(item_page: str) -> None:
    """刷新失效图片：走原站 nl 链接强制换 H@H 节点，重新解析直链。"""
    if not item_page.startswith("http"):
        emit({"event": "ex_image_reloaded", "item_page": item_page, "media_url": "", "success": False,
              "message": "无效的图片页链接"})
        return

    def _reload() -> str:
        reload_url = _exhentai_image_page_with_nl(item_page)
        resp = _exhentai_fetch(reload_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        img = soup.select_one("#img")
        src = (img.get("src") or "") if img else ""
        return src if src.startswith("http") else ""

    try:
        media_url = await asyncio.to_thread(_reload)
        emit({
            "event": "ex_image_reloaded",
            "item_page": item_page,
            "media_url": media_url,
            "thumbnail": media_url,
            "success": bool(media_url),
            "message": "" if media_url else "刷新失败：未能解析出新直链（登录可能已失效）",
        })
    except Exception as exc:
        emit({
            "event": "ex_image_reloaded",
            "item_page": item_page,
            "media_url": "",
            "success": False,
            "message": f"刷新失败: {exc}",
        })


async def exhentai_torrents(url: str) -> None:
    """画廊种子列表（gallerytorrents.php）：名字/大小/做种数 + btih 磁力链接。

    前端磁力弹窗（RightPanel torrentModal）的数据源——历史重构中该命令与
    App 监听一并丢失，磁链按钮从此点了没反应；本轮按页面实测结构重建。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "ex_torrents_result", "url": url, "torrents": [], "error": "无效的画廊链接"})
        return
    try:
        page = await asyncio.to_thread(
            _exhentai_fetch, f"{info['host']}/gallerytorrents.php?gid={info['gid']}&t={info['token']}")
        torrents: list[dict] = []
        # 每个种子一个 <div style="margin:10px 5px..."> 块：gtid hidden + 下载锚
        # （ehtracker.org/get/{gid}/{hash}.torrent）+ Posted/Size/Seeds 表格
        for block in re.split(r'(?=<div style="margin:10px 5px)', page.text):
            mh = re.search(r'ehtracker\.org/get/\d+/([0-9a-f]{40})\.torrent', block)
            if not mh:
                continue
            h = mh.group(1)
            mn = re.search(r'\.torrent["\'][^>]*>([^<]{1,200})', block)
            ms = re.search(r'Size:</span>\s*([^<]{1,30})', block)
            mse = re.search(r'Seeds:</span>\s*([^<]{1,10})', block)
            mp = re.search(r'Peers:</span>\s*([^<]{1,10})', block)
            md = re.search(r'Downloads:</span>\s*([^<]{1,12})', block)
            mpo = re.search(r'Posted:</span>\s*([^<]{1,24})', block)
            name = (mn.group(1).strip() if mn else "") or f"torrent_{h[:8]}"
            torrents.append({
                "hash": h,
                "name": name,
                "size": ms.group(1).strip() if ms else "",
                "seeds": mse.group(1).strip() if mse else "",
                "peers": mp.group(1).strip() if mp else "",
                "downloads": md.group(1).strip() if md else "",
                "posted": mpo.group(1).strip() if mpo else "",
                "magnet": f"magnet:?xt=urn:btih:{h}&dn={urllib.parse.quote(name)}",
            })
        emit({"event": "ex_torrents_result", "url": url, "torrents": torrents})
    except Exception as exc:
        emit({"event": "ex_torrents_result", "url": url, "torrents": [], "error": f"种子获取失败: {exc}"})


async def exhentai_save_torrent(torrent_url: str, name: str = "") -> None:
    """下载 .torrent 种子文件并保存到 downloads/torrents/。"""
    try:
        response = await asyncio.to_thread(_exhentai_fetch, torrent_url)
        if response.status_code != 200 or not response.content[:1] == b"d":
            emit({"event": "ex_torrent_saved", "success": False, "message": "种子文件下载失败"})
            return
        # 文件名：优先种子内名称，其次传入名称，最后时间戳
        dn = name
        if not dn:
            try:
                data, _ = _bdecode(response.content)
                if isinstance(data, dict):
                    info = data.get(b"info")
                    if isinstance(info, dict) and info.get(b"name"):
                        dn = info[b"name"].decode("utf-8", "replace")
            except (ValueError, IndexError):
                pass
        safe = re.sub(r'[\\/:*?"<>|]', "_", (dn or f"torrent_{int(time.time())}").strip())[:150]
        save_dir = Path("downloads") / "torrents"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"{safe}.torrent"
        save_path.write_bytes(response.content)
        emit({
            "event": "ex_torrent_saved",
            "success": True,
            "path": str(save_path),
            "message": f"种子已保存: {save_path}",
        })
        logging.info("ExHentai 种子已保存: %s", save_path)

    except PermissionError as exc:
        emit({"event": "ex_torrent_saved", "success": False, "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "ex_torrent_saved", "success": False, "message": f"种子下载失败: {exc}"})
        logging.exception("ExHentai 种子保存失败")
