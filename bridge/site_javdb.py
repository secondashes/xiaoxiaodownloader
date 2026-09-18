# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：JavDB（含标签词库/热搜/目录导航）。

由 gui_bridge.py 按物理顺序拆出（原行区间 17419-18427），
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
# JavDB（javdb.com，X 站类型：webview 登录抓 cookie + HTML 解析）
# ============================
# 登录：Electron webview（partition persist:javdb）打开 javdb 登录页，
#       用户输入邮箱密码（Cloudflare 人机验证在 webview 内完成），登录成功后抓 cookie；
#       "记住此装置"勾选后 cookie 约 7 天有效（机器七天登录），失效提示重新登录。
# 搜索：GET /search?q={关键词}&f=all（番号 / 标题 / 演员均可）
# 详情：GET /v/{id} → 标题 / 封面 / 标签 / 预览图 / 磁力链接
# 下载：封面 + 预览图直链下载；磁力链接一键复制（交给外部种子客户端）
JAVDB_BASE = "https://javdb.com"
JAVDB_LOGIN_URL = "https://javdb.com/login/"

_javdb_proxy = "http://127.0.0.1:10809"
_javdb_username = ""


def _javdb_username_now() -> str:
    """当前用户名（跨模块读取入口）。"""
    return _javdb_username or ""
# curl_cffi（Chrome TLS 指纹模拟）：JavDB 的 Cloudflare 对 python-requests 的 TLS 指纹
# 直接 403 质询（/search、/users 等路径无论带不带 cookie 都拦），必须用与 webview 同源
# 的 Chrome 指纹 + cf_clearance 才能通过。优先从项目 _pylibs 目录加载（本地免安装），
# 正式环境 pip install curl_cffi 亦可
_PYLIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pylibs")
if os.path.isdir(_PYLIBS) and _PYLIBS not in sys.path:
    sys.path.insert(0, _PYLIBS)
try:
    from curl_cffi import requests as _curl_requests
except ImportError:
    _curl_requests = None
# chrome124 指纹与 webview（Electron 30 / Chrome 124）一致；缺失时退回 requests（会被 CF 拦）
if _curl_requests is not None:
    _javdb_session = _curl_requests.Session(impersonate="chrome124")
else:
    _javdb_session = requests.Session()
_javdb_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})


def _javdb_load_cred() -> dict:
    """读取 JavDB 登录凭据（cookie + UA 加密存 theme_cache.dat）。"""
    return _secure_store_read_cred("javdb")


def _javdb_save_cred(data: dict) -> None:
    _secure_store_write_cred("javdb", dict(data))


def javdb_set_proxy(proxy: str) -> None:
    """设置 JavDB 代理（国内必须；空 = 直连）。"""
    global _javdb_proxy
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    _javdb_proxy = proxy
    _javdb_session.proxies = {"http": proxy, "https": proxy} if proxy else {}
    emit({"event": "javdb_proxy_set", "proxy": proxy})
    logging.info("JavDB 代理已设置: %s", proxy or "（直连）")


def _javdb_restore_session() -> None:
    """启动时从加密凭据恢复 cookie + UA（cf_clearance 绑定 UA，必须与登录时一致）。"""
    global _javdb_username
    cred = _javdb_load_cred()
    # 去掉 Electron 标记：webview 实际请求用的就是去掉后的 UA（cf_clearance 按此签发）
    ua = re.sub(r"\sElectron/[\d.]+", "", cred.get("user_agent") or "").strip()
    if ua:
        _javdb_session.headers["User-Agent"] = ua
    for name, value in (cred.get("cookies") or {}).items():
        try:
            _javdb_session.cookies.set(name, value, domain=".javdb.com")
        except Exception:
            pass
    # 年龄确认 + 界面语言 cookie（未登录也能用）
    _javdb_session.cookies.set("over18", "1", domain=".javdb.com")
    _javdb_session.cookies.set("locale", "zh", domain=".javdb.com")
    _javdb_username = cred.get("username") or ""


def javdb_set_cookies(cookie_str: str, user_agent: str = "", username: str = "",
                      email: str = "", password: str = "") -> dict:
    """保存 webview 抓取的 cookie（+ 登录时的 UA，cf_clearance 校验用）。

    email/password：webview 登录表单预填的账号密码，随 cookie 一起长期保存，
    下次打开登录页自动回填（用户只需过 Cloudflare + 点登录）。
    """
    cookies = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        idx = pair.find("=")
        if idx <= 0:
            continue
        cookies[pair[:idx].strip()] = pair[idx + 1:].strip()
    cred = {"cookies": cookies, "cookie_str": cookie_str or "",
            "user_agent": user_agent or "", "username": username or "",
            "saved_at": time.time()}
    # 账号密码长期记录（有新值就更新，没有就沿用旧值）
    if email:
        cred["email"] = email
    if password:
        cred["password"] = password
    _javdb_save_cred(cred)
    _javdb_restore_session()
    # 立即验证登录态（推送 site_login_result）
    javdb_check_login()
    return {"ok": True, "count": len(cookies)}


def javdb_check_login(silent: bool = False) -> dict:
    """检查登录态：访问首页，页面有登出链接 = 已登录（cookie 有效期内免验证码）。

    （旧版 /users/home 路径已 404 下线，登录态检测改用首页 href="/logout"）
    cookie 过期（约 7 天"记住装置"期限）→ logged_in=False，提示重新在 webview 登录。
    """
    logged_in = False
    username = ""
    network_issue = False
    cred = _javdb_load_cred()
    if cred.get("cookies"):
        try:
            _javdb_throttle()
            resp = _javdb_session.get(f"{JAVDB_BASE}/", timeout=25,
                                      allow_redirects=False)
            if resp.status_code == 200:
                logged_in = "/logout" in resp.text or "current-user" in resp.text
                # 从导航栏提取真实用户名（保存的凭据里 username 常为空）
                # 2026-09 站点改版：<a href="/users/profile">…<span style="position:relative;"> 用户名 </span>
                # .*? 回溯会先撞上 icon span（内部含 < 导致 [^<] 失配）而自动跳过
                if logged_in:
                    m = (re.search(r'href="/users/profile"[^>]*>.*?<span[^>]*>\s*([^<]{1,40}?)\s*</span>\s*</a>', resp.text, re.S)
                         or re.search(r'href="/users/\d+"[^>]*>\s*<strong[^>]*>([^<]{1,40})</strong>', resp.text))
                    if m:
                        username = html_unescape(m.group(1)).strip()
            elif resp.status_code in (301, 302):
                # 重定向到登录页 = cookie 失效
                logged_in = False
            else:
                network_issue = resp.status_code in (403, 503, 530)
            if logged_in:
                username = username or cred.get("username") or ""
                global _javdb_username
                _javdb_username = username
        except Exception as exc:
            logging.warning("JavDB 登录态检查失败: %s", exc)
            network_issue = True
    else:
        network_issue = False
    result = {"logged_in": logged_in, "username": username,
              "network_issue": network_issue}
    # 静默模式（启动时自动检测）也要推送：前端按 silent 标志抑制提示，
    # 否则界面永远显示"未登录"（cookie 实际有效也看不到）
    emit({"event": "site_login_result", "site": "javdb", "silent": silent,
          "message": "JavDB 登录态检查（网络异常，结果可能不准）" if network_issue else "",
          **result})
    return result


def javdb_logout() -> None:
    """退出登录（清除本地凭据）。"""
    global _javdb_username
    _secure_store_clear_cred("javdb")
    _javdb_username = ""
    _javdb_session.cookies.clear()
    emit({"event": "site_login_result", "site": "javdb", "logged_in": False,
          "username": "", "logout": True})


_javdb_throttle = _make_throttle(1.0)


def _javdb_soup(path: str, params: dict | None = None) -> "BeautifulSoup":
    """GET 页面并返回 BeautifulSoup；Cloudflare 拦截时给出中文提示。"""
    _javdb_throttle()
    resp = _javdb_session.get(f"{JAVDB_BASE}{path}", params=params, timeout=25)
    if resp.status_code == 404:
        raise FileNotFoundError("页面不存在（链接可能已失效）")
    if resp.status_code in (403, 503, 530):
        hint = "" if _curl_requests is not None else "（本机缺少 curl_cffi 库，无法模拟浏览器指纹，请 pip install curl_cffi 后重试）"
        raise PermissionError(
            f"触发 Cloudflare 拦截{hint}：请在左侧重新登录 JavDB（webview 内完成人机验证后点确定抓取新 cookie）")
    if resp.status_code != 200:
        raise PermissionError(f"JavDB 返回 HTTP {resp.status_code}")
    return BeautifulSoup(resp.text, "html.parser")


def _javdb_img_src(img) -> str:
    """图片地址（懒加载 data-src 优先，其次 src）。"""
    if img is None:
        return ""
    return img.get("data-src") or img.get("src") or ""


def _javdb_abs(u: str) -> str:
    """相对 URL 转绝对。"""
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return JAVDB_BASE + u
    return u


def _javdb_parse_cards(soup: "BeautifulSoup") -> list[dict]:
    """解析搜索结果卡片（.movie-list .item）→ 统一卡片字段。"""
    items: list[dict] = []
    for it in soup.select(".movie-list .item"):
        a = it.find("a", href=True)
        if not a:
            continue
        href = _javdb_abs(a.get("href") or "")
        if "/v/" not in href:
            continue
        title_el = it.select_one(".video-title strong") or it.select_one(".video-title")
        title = title_el.get_text(strip=True) if title_el else ""
        # 番号（.meta 第一个 span 或 title 前缀）
        code = ""
        meta_spans = it.select(".meta span")
        if meta_spans:
            code = meta_spans[0].get_text(strip=True)
        if not code and title:
            m = re.match(r"^([A-Za-z]{2,6}-\d{2,5})", title)
            if m:
                code = m.group(1)
        # 评分 / 日期 / 标签
        score = (it.select_one(".score") or {}).get_text(strip=True) if it.select_one(".score") else ""
        date = ""
        for sp in meta_spans[1:]:
            if re.search(r"\d{4}-\d{2}-\d{2}", sp.get_text(strip=True)):
                date = sp.get_text(strip=True)
                break
        tags = [t.get_text(strip=True) for t in it.select(".tag")]
        cover = _javdb_img_src(it.select_one(".cover img") or it.find("img"))
        thumb = _javdb_abs(cover)
        # 标题去掉番号前缀展示
        display = title
        album_name = f"[{code}] {title}" if code and not title.startswith(code) else (title or code)
        items.append({
            "album_name": album_name or href.rsplit("/", 1)[-1],
            "album_url": href,
            "cover_url": thumb,
            "thumbnail": thumb,
            "code": code,
            "title": display,
            "score": score,
            "date": date,
            "tags": tags,
            "duration": (it.select_one(".duration") or {}).get_text(strip=True) if it.select_one(".duration") else "",
        })
    return items


# JavDB 搜索类型（f= 参数）：影片/演员/系列/片商/导演/番号/标签
_JAVDB_SEARCH_FIELDS = ("all", "actor", "series", "maker", "director", "coded", "tag")


async def javdb_search(query: str, page: int = 1, field: str = "all") -> None:
    """JavDB 搜索。GET /search?q=...&f={field}（all 影片 / actor 演员 / series 系列 /
    maker 片商 / director 导演 / coded 番号 / tag 标签）"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    field = (field or "all").strip() or "all"
    if field not in _JAVDB_SEARCH_FIELDS:
        field = "all"
    emit({"event": "search_start", "query": query, "page": page})
    try:
        page = max(1, page or 1)
        soup = await asyncio.to_thread(
            _javdb_soup, "/search", {"q": query, "f": field, "page": page})
        items = _javdb_parse_cards(soup)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        # 分页（javdb 用 <a class="pagination-next"> / 最后一页链接判断）
        has_more = bool(soup.select_one("a.pagination-next:not(.is-disabled)"))
        emit({"event": "search_result", "query": query, "site": "javdb",
              "field": field,
              "items": items, "page": page, "has_more": has_more,
              "total_pages": 0, "total_results": len(items)})
        logging.info("JavDB 搜索 '%s'(f=%s) 第 %d 页: %d 个结果", query, field, page, len(items))
    except Exception as exc:
        msg = str(exc)
        hint = ""
        if "Cloudflare" in msg:
            hint = "（请在左侧重新登录 JavDB 刷新 cookie）"
        elif "ProxyError" in msg or "timed out" in msg or "Connection" in msg:
            hint = "（请检查 JavDB 代理设置，国内必须代理）"
        emit({"event": "search_error", "message": f"JavDB 搜索失败: {msg}{hint}"})


def _javdb_parse_detail(soup: "BeautifulSoup", vid: str) -> dict:
    """解析视频详情页 /v/{id}：标题/封面/信息/标签/预览图/磁力。"""
    title_el = soup.select_one("h2.title.current-item") or soup.select_one("h2.title") or soup.select_one(".video-title")
    title = title_el.get_text(strip=True) if title_el else vid
    cover = _javdb_img_src(soup.select_one(".column-video-cover img") or soup.select_one(".cover img"))
    code = ""
    info: dict[str, str] = {}
    # 信息面板（识别码/日期/时长/导演/片商/系列…）
    for block in soup.select(".movie-panel-info .panel-block"):
        strong = block.find("strong")
        if not strong:
            continue
        key = strong.get_text(strip=True).rstrip("：:")
        value = block.get_text(" ", strip=True).replace(strong.get_text(strip=True), "", 1).strip()
        if key in ("識別碼", "识别码", "ID"):
            code = value
        elif key and value and key not in ("演員", "演员", "類別", "类别", "標籤", "标签"):
            info[key] = value
    # 标签 / 演员（演员带主页链接，详情页可点击进入演员全部作品）
    tags = [a.get_text(strip=True) for a in soup.select(".movie-panel-info a[href*='/tags/']")]
    actors = [a.get_text(strip=True) for a in soup.select(".movie-panel-info a[href*='/actors/']")]
    actor_links = [
        {"name": a.get_text(strip=True), "url": _javdb_abs(a.get("href") or "")}
        for a in soup.select(".movie-panel-info a[href*='/actors/']")
        if a.get("href")
    ]
    # 预览图（需登录才可见）
    previews = []
    for a in soup.select(".preview-images a.tile-item"):
        img = a.find("img")
        if img:
            previews.append(_javdb_abs(_javdb_img_src(img)))
    # 磁力链接（含名称/大小/日期/字幕标签）
    magnets = []
    for it in soup.select("#magnets .item"):
        a = it.select_one("a[href^='magnet:']")
        if not a:
            continue
        name_el = it.select_one(".magnet-name .name")
        # meta 容器与子 span 都收集（站点两种结构并存：独立 meta div / 单 meta 多 span）
        meta_texts: list[str] = []
        for t in it.select(".magnet-name .meta"):
            txt = t.get_text(strip=True)
            if txt:
                meta_texts.append(txt)
            for sp in t.select("span"):
                sp_txt = sp.get_text(strip=True)
                if sp_txt and sp_txt != txt:
                    meta_texts.append(sp_txt)
        size = ""
        date = ""
        for t in meta_texts:
            if re.search(r"^\d+(\.\d+)?\s*(GB|MB|KB|TB)$", t, re.I):
                size = t
            elif re.search(r"\d{4}-\d{2}-\d{2}", t):
                date = t
        magnet_tags = [t.get_text(strip=True) for t in it.select(".magnet-name .tags .tag")]
        magnets.append({
            "name": name_el.get_text(strip=True) if name_el else (a.get("href") or "")[:60],
            "link": a.get("href") or "",
            "size": size,
            "date": date,
            "tags": magnet_tags,
        })
    return {
        "video_id": vid,
        "title": title,
        "code": code,
        "cover": _javdb_abs(cover),
        "info": info,
        "tags": tags,
        "actors": actors,
        "actor_links": actor_links,
        "previews": previews,
        "magnets": magnets,
        "url": f"{JAVDB_BASE}/v/{vid}",
    }


def _javdb_download_image_sync(url: str, cache_path: "Path") -> bool:
    """用 JavDB 会话下载图片到缩略图缓存目录（带登录 cookie 与代理，绕开前端网络环境差异）。"""
    resp = _javdb_session.get(url, timeout=20)
    if resp.status_code == 200 and _is_valid_image(resp.content):
        cache_path.write_bytes(resp.content)
        return True
    return False


async def _javdb_localize_images(detail: dict) -> None:
    """封面+预览图下载到本地缓存，替换为 thumb://local/ 路径。

    站点图床（c0.jdbstatic.com）在部分用户网络/代理环境下前端直载报错，
    后端经会话（cookie+代理）下载后走本地 thumb 协议展示，绕开 cookie/代理/防盗链差异。
    下载失败的条目保留原 URL。
    """
    urls: list[str] = []
    if (detail.get("cover") or "").startswith("http"):
        urls.append(detail["cover"])
    urls.extend(u for u in (detail.get("previews") or []) if u.startswith("http"))
    if not urls:
        return
    Path(THUMBNAIL_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(5)

    async def one(u: str) -> str:
        cache_path = _thumbnail_cache_path(u)
        if cache_path.exists() and _is_valid_cache_file(cache_path):
            return f"thumb://local/{cache_path.name}"
        try:
            async with sem:
                ok = await asyncio.to_thread(_javdb_download_image_sync, u, cache_path)
            return f"thumb://local/{cache_path.name}" if ok else u
        except Exception:  # noqa: BLE001
            return u

    results = list(await asyncio.gather(*(one(u) for u in urls)))
    if (detail.get("cover") or "").startswith("http"):
        detail["cover"] = results.pop(0)
    detail["previews"] = results


async def javdb_video_info(url: str) -> None:
    """视频详情页解析（标题/封面/标签/预览图/磁力列表）。"""
    m = re.search(r"javdb\.com/(?:zh/)?v/([0-9a-zA-Z]+)", url or "")
    if not m:
        emit({"event": "javdb_video_detail", "error": "无法识别的 JavDB 链接（支持 /v/{id}）"})
        return
    vid = m.group(1)
    emit({"event": "javdb_detail_loading", "loading": True})
    try:
        soup = await asyncio.to_thread(_javdb_soup, f"/v/{vid}", None)
        detail = _javdb_parse_detail(soup, vid)
        # 封面+预览图本地化（thumb:// 展示，下载失败的保留原 URL）
        await _javdb_localize_images(detail)
        if not detail["magnets"] and not detail["previews"] and not detail["cover"]:
            emit({"event": "javdb_video_detail",
                  "error": "解析结果为空（可能未登录：预览图与部分磁力需登录后可见，请在左侧登录 JavDB）"})
            return
        emit({"event": "javdb_video_detail", "video": detail})
        logging.info("JavDB 详情解析完成: %s (%d 磁力 / %d 预览图)", vid, len(detail["magnets"]), len(detail["previews"]))
    except Exception as exc:
        msg = str(exc)
        hint = "（请重新登录 JavDB 刷新 cookie）" if "Cloudflare" in msg else "（请检查网络或代理设置）"
        emit({"event": "javdb_video_detail", "error": f"JavDB 解析失败: {msg}{hint}"})
    finally:
        emit({"event": "javdb_detail_loading", "loading": False})


async def javdb_download_images(url: str, options: dict) -> None:
    """下载封面 + 全部预览图（直链下载，磁力链接需外部种子客户端）。"""
    m = re.search(r"javdb\.com/(?:zh/)?v/([0-9a-zA-Z]+)", url or "")
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 JavDB 链接"})
        return
    vid = m.group(1)
    try:
        soup = await asyncio.to_thread(_javdb_soup, f"/v/{vid}", None)
        detail = _javdb_parse_detail(soup, vid)
        code = detail.get("code") or vid
        items: list[dict] = []
        if detail.get("cover"):
            items.append({
                "filename": "cover.jpg",
                "size": None,
                "item_page": detail["url"],
                "status": "ok",
                "thumbnail": "",
                "media_url": detail["cover"],
                "site": "javdb",
            })
        for i, pv in enumerate(detail.get("previews") or [], 1):
            items.append({
                "filename": f"preview_{i:02d}.jpg",
                "size": None,
                "item_page": detail["url"],
                "status": "ok",
                "thumbnail": "",
                "media_url": pv,
                "site": "javdb",
            })
        if not items:
            emit({"event": "inspect_error",
                  "message": "没有可下载的图片（预览图需登录后可见）"})
            return
        # 逐个直链下载（走通用下载管理器，带进度）
        task_id = download_manager.submit(
            detail["url"], items, options,
            f"JavDB {code}", f"javdb_{vid}",
        )
        download_manager.start(task_id)
        emit({"event": "inspect_complete",
              "album_name": f"JavDB {code}（{len(items)} 张图片，任务已提交）",
              "album_id": f"javdb_{vid}",
              "is_album": True,
              "items": items})
        logging.info("JavDB 图片下载已提交: %s (%d 张)", vid, len(items))
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"JavDB 解析失败: {exc}"})


async def javdb_batch_download(urls: list, options: dict) -> None:
    """批量下载多个视频的封面+预览图（逐个解析，每个视频单独一个下载任务）。

    options["batch_parent_folder"] 非空时：任务文件夹 = 母文件夹名，
    每个视频按 <番号>/ 子文件夹归档（与 EX 批量下载归档规则一致）。
    """
    urls = [str(u).strip() for u in (urls or []) if str(u).strip()]
    total = len(urls)
    done = 0
    failed: list[str] = []
    parent = (options.get("batch_parent_folder") or "").strip()

    def _progress(done_: int, msg: str) -> None:
        emit({"event": "javdb_batch_progress", "done": done_, "total": total, "message": msg})

    if not total:
        _progress(0, "请先勾选要下载的视频")
        emit({"event": "javdb_batch_done", "done": 0, "total": 0, "failed": []})
        return

    try:
        for u in urls:
            m = re.search(r"javdb\.com/(?:zh/)?v/([0-9a-zA-Z]+)", u)
            if not m:
                failed.append(f"{u}（无法识别链接）")
                done += 1
                continue
            vid = m.group(1)
            _progress(done, f"正在解析 {vid} ...")
            try:
                soup = await asyncio.to_thread(_javdb_soup, f"/v/{vid}", None)
                detail = _javdb_parse_detail(soup, vid)
                code = detail.get("code") or vid
                items: list[dict] = []
                if detail.get("cover"):
                    items.append({
                        "filename": f"{code}/cover.jpg",
                        "size": None, "item_page": detail["url"], "status": "ok",
                        "thumbnail": "", "media_url": detail["cover"], "site": "javdb",
                    })
                for i, pv in enumerate(detail.get("previews") or [], 1):
                    items.append({
                        "filename": f"{code}/preview_{i:02d}.jpg",
                        "size": None, "item_page": detail["url"], "status": "ok",
                        "thumbnail": "", "media_url": pv, "site": "javdb",
                    })
                if not items:
                    failed.append(f"{code}（无图片，预览图需登录后可见）")
                else:
                    task_id = download_manager.submit(
                        detail["url"], items, options,
                        parent or f"JavDB {code}", f"javdb_{vid}",
                    )
                    download_manager.start(task_id)
                    logging.info("JavDB 批量下载：已提交 %s（%d 张图）", code, len(items))
            except Exception as exc:
                failed.append(f"{vid}（{exc}）")
                logging.exception("JavDB 批量下载解析失败: %s", vid)
            done += 1
            _progress(done, f"{done}/{total} 完成")

        summary = f"JavDB 批量下载已提交：{done}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "javdb_batch_done", "done": done, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "javdb_batch_done", "done": done, "total": total, "failed": failed,
              "message": f"批量下载中断: {exc}"})
        logging.exception("JavDB 批量下载出错")


def is_javdb_url(url: str) -> bool:
    """判断是否为 JavDB 链接（/v/{id} 详情页）。"""
    return bool(re.search(r"javdb\.com/(?:zh/)?v/[0-9a-zA-Z]+", url or "", re.I))


async def _javdb_emit_list(soup: "BeautifulSoup", label: str, page: int,
                           extra_items: list | None = None) -> None:
    """把 JavDB 列表页（首页/演员页）解析成搜索卡片流，复用 search_result 事件通道。"""
    items = extra_items if extra_items is not None else _javdb_parse_cards(soup)
    _apply_cached_thumbnails(items)
    asyncio.create_task(_cache_thumbnails(items))
    has_more = bool(soup.select_one("a.pagination-next:not(.is-disabled)"))
    emit({"event": "search_result", "query": label, "site": "javdb",
          "items": items, "page": page, "has_more": has_more,
          "total_pages": 0, "total_results": len(items)})
    logging.info("JavDB 列表「%s」第 %d 页: %d 个结果", label, page, len(items))


async def javdb_home(page: int = 1) -> None:
    """JavDB 首页最新影片（无需搜索关键词，浏览器进入站点即有内容可看）。GET /?page=N"""
    page = max(1, page or 1)
    emit({"event": "search_start", "query": "最新影片", "page": page})
    try:
        soup = await asyncio.to_thread(
            _javdb_soup, "/", {"page": page} if page > 1 else None)
        items = _javdb_parse_cards(soup)
        if not items:
            raise RuntimeError("首页没有解析到影片卡片（站点结构可能变化，或被 Cloudflare 拦截）")
        await _javdb_emit_list(soup, "最新影片", page, items)
    except Exception as exc:
        msg = str(exc)
        hint = ""
        if "Cloudflare" in msg:
            hint = "（请在左侧重新登录 JavDB 刷新 cookie）"
        elif "ProxyError" in msg or "timed out" in msg or "Connection" in msg:
            hint = "（请检查 JavDB 代理设置，国内必须代理）"
        emit({"event": "search_error", "message": f"JavDB 最新影片获取失败: {msg}{hint}"})


async def javdb_actor(url: str, page: int = 1) -> None:
    """演员主页全部作品（详情页点演员名进入）。GET /actors/{id}?page=N"""
    m = re.search(r"javdb\.com/(?:zh/)?actors/([0-9a-zA-Z]+)", url or "")
    if not m:
        emit({"event": "search_error", "message": "无法识别的 JavDB 演员链接"})
        return
    page = max(1, page or 1)
    emit({"event": "search_start", "query": "演员作品", "page": page})
    try:
        soup = await asyncio.to_thread(
            _javdb_soup, f"/actors/{m.group(1)}", {"page": page} if page > 1 else None)
        # 演员名（页面标题 strong，取不到就用链接 id）
        name = ""
        name_el = soup.select_one("h2.title strong") or soup.select_one("strong.current-actor")
        if name_el:
            name = name_el.get_text(strip=True)
        label = f"演员:{name or m.group(1)}"
        items = _javdb_parse_cards(soup)
        if not items:
            raise RuntimeError("该演员页没有解析到影片卡片（可能无作品或被拦截）")
        await _javdb_emit_list(soup, label, page, items)
    except Exception as exc:
        msg = str(exc)
        hint = "（请在左侧重新登录 JavDB 刷新 cookie）" if "Cloudflare" in msg else ""
        emit({"event": "search_error", "message": f"JavDB 演员页获取失败: {msg}{hint}"})


# ============================
# JavDB 标签词库 / 热搜 / 目录导航（类别·排行榜·演员·系列·片商）
# 词库文本按项目内 javdb-tags-内容页.txt 离线制作（不联网抓取站点排版）
# ============================

def _javdb_split_tags(s: str) -> list:
    """词表按空白切分并去重（保持首次出现顺序，避免重复 chip）。"""
    seen, out = set(), []
    for t in s.split():
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _g(key: str, label: str, s: str) -> dict:
    return {"key": key, "label": label, "tags": _javdb_split_tags(s)}


def _javdb_years(min_year: int) -> list:
    """年份筛选项：校验系统时间生成（当前年份超过 2026 时自动扩展到当前年）。"""
    top = max(time.localtime().tm_year, 2026)
    return [str(y) for y in range(top, min_year - 1, -1)]


_JAVDB_DURATION_TAGS = "全部 45分鍾以內 45-90分鍾 90-120分鍾 120分鍾以上"

# 五大模式：有码 / 无码 / 欧美 / FC2 / 动漫
# vft 为类别列表 /{key} 的过滤参数（1=含磁鏈，Google 索引证实）；None = 走站内搜索
JAVDB_TAG_MODES = [
    {
        "key": "censored", "label": "有码", "vft": 1,
        "groups": [
            _g("basic", "基本", "全部 可播放 中字可播放 含磁鏈 含字幕 單體影片 含預覽圖 含預覽視頻"),
            _g("year", "年份", "全部 " + " ".join(_javdb_years(2001))),
            _g("theme", "主題", "全部 淫亂真實 出軌 強姦 亂倫 溫泉 女同性戀 企畫 戀腿癖 獵豔 偷窺 洗澡 其他戀物癖 處女 性愛 學校作品 妄想 M男 跳舞 戀物癖 戀乳癖 惡作劇 運動 倒追 女同接吻 美容院 奴隸 白天出軌 流汗 性騷擾 情侶 爛醉如泥的 魔鬼系 處男 殘忍畫面 性感的 曬黑 雙性人 全裸 正太控 觸手 正常 奇異的 蠻橫嬌羞 性轉換·女體化 男同性戀 韓國 形象俱樂部 友誼 亞洲 暗黑系 天賦 被外國人幹 刺青紋身 黑白配 絕頂高潮 純欲 經歷告白 濕身"),
            _g("role", "角色", "全部 高中女生 美少女 已婚婦女 藝人 姐姐 各種職業 蕩婦 母親 辣妹 妓女 新娘，年輕妻子 女教師 白人 婆婆 女大學生 偶像 明星臉 大小姐 秘書 護士 角色扮演者 賽車女郎 家教 黑人演員 妹妹 寡婦 女醫生 老闆娘，女主人 女主播 其他學生 模特兒 格鬥家 展場女孩 禮儀小姐 女檢察官 講師 服務生 伴侶 車掌小姐 女兒 年輕女孩 公主 童年朋友 飛特族 亞洲女演員 痴漢 御宅族 老太婆 老年男性 拉拉隊 媽媽的朋友 養女 女王"),
            _g("costume", "服裝", "全部 眼鏡 角色扮演 內衣 制服 水手服 泳裝 和服，喪服 連褲襪 女傭 運動短褲 女戰士 校服 制服外套 裸體圍裙 女忍者 身體意識 OL 貓耳女 短裙 學校泳裝 迷你裙 浴衣 猥褻穿著 緊身衣 娃娃 蘿莉角色扮演 女裝人妖 絲襪、過膝襪 泡泡襪 空中小姐 旗袍 兔女郎 女祭司 動畫人物 迷你裙警察 修女 COSPLAY服飾 高跟鞋 靴子"),
            _g("body", "體型", "全部 熟女 巨乳 蘿莉塔 無毛 美臀 苗條 美乳 巨大陰莖 胖女人 平胸 素人 高挑 孕婦 大屁股 瘦小身型 變性者 肌肉 超乳 美腳 多毛"),
            _g("action", "行爲", "全部 乳交 中出 多P 69 淫語 女上位 自慰 顏射 潮吹 口交 舔陰 肛門・肛交 手指插入 手淫 深喉 放尿 足交 按摩 吞精 母乳 濫交 接吻 拳交 飲尿 騎乗位 排便 食糞 剃毛 二穴同入 兩女一男 兩男兩女 兩男一女 打屁股 約會 不穿內褲 不穿胸罩 後入 瑜伽·健身 白眼失神 搔癢"),
            _g("play", "玩法", "全部 凌辱 捆綁 緊縛 輪姦 玩具 SM 戶外 乳液 羞恥 女優按摩棒 拘束 調教 立即口交 跳蛋 監禁 按摩棒 插入異物 灌腸 藥物 露出 汽車性愛 催眠 鴨嘴 糞便 脫衣 子宮頸 導尿 蒙面・面罩 唾液敷面 乳釘、穿孔、乳環 口球 輔助自慰 夫妻交換 假陽具 鼻鉤 蠟燭 站立後入"),
            _g("category", "類別", "全部 單體作品 首次亮相 故事集 經典 戀愛 VR 感謝祭 給女性觀眾 無碼流出 4K 無碼破解 綜藝 精選綜合 國外進口 4小時以上作品 戲劇 成人電影 介紹影片 第一人稱攝影 薄馬賽克 數位馬賽克 投稿 業餘 紀錄片 去背影片 獨立製作 主觀視角 戰鬥行動 特效 16小時以上作品 局部特寫 重印版 歷史劇 寫真偶像 3D 原作改編 訪問 教學 恐怖 西洋片 科幻 行動 綜合短篇 滑稽模仿 男性 冒險 模擬 愛好，文化 懸疑 R-15 美少女電影 感官作品 觸摸打字 素人作品 HDTV 心理驚悚 養尊處優 共演"),
            _g("duration", "時長", _JAVDB_DURATION_TAGS),
        ],
    },
    {
        "key": "uncensored", "label": "无码", "vft": 1,
        "groups": [
            _g("basic", "基本", "全部 可播放 中字可播放 含磁鏈 含字幕 單體影片 含預覽圖"),
            _g("year", "年份", "全部 " + " ".join(_javdb_years(2007))),
            _g("theme", "主題", "全部 肛交 束縛 顏射 中出 二穴同插 輪姦 女同性戀 無套內射 捆綁 乳液 與外國人玩 立即口交 1v1性交 淫蕩手淫 深喉 淋浴沐浴 M字開腿 淫語 打手槍 足交 泡泡浴 跳舞 背後插入 潮吹 3P 迷你裙 性奴 首次亮相 左右口交 奧斯曼株式會社 女體料理 龜甲捆綁 站立性交 騎乘位 背部騎乘位 車站性交 乳交 粉紅 跳 口塞 第一人稱視角(POV) 口爆/吞精 浪叫 戶外 露出 公共場所 出軌 亂倫 汽車性愛 電車痴漢 南國度假地 在他人面前 假陽具 顏面騎乘 立即騎乘 口交 腔鏡 69 濫交 玩具 偷窺 旅行 按摩 其他 口爆 尿失禁 戀物癖 搭訕 妊娠 母乳 舔"),
            _g("role", "角色", "全部 M男 痴女與M男 巨乳爆乳 和服 熟女 美少女 美乳 痴女 白虎 美女 曬黑 苗條 貧乳 太太 捲髮 美腳 漂亮屁股 眼鏡娘 美穴 淫亂S女 M女 人妻 素人 辣妹 精緻身材 混血美女 高挑身材 短髮 變性人 肉肉女 女學生 姐姐 女大學生 單純 幼妻"),
            _g("costume", "服裝", "全部 角色扮演 製服 OL 護士 女傭 婚紗禮服 泳裝 女醫生 濕透 雪白皮膚 漁網褲襪 播音員 蘿莉 西方時 女主角 運動裝 女教師 比基尼 家庭教師 空姐 體育Cosplay 女子高生製服 學校泳裝 連褲襪 高跟鞋"),
            _g("other", "其他", "全部 人氣標題 惡搞 戲劇 店長推薦 知名女優 最新影片 動漫 獨占影片 復古 金發 寫真 正在上映 懷舊 精品收藏 DVD已售罄 週排名第一的作品 2018暢銷Top100"),
            _g("duration", "時長", _JAVDB_DURATION_TAGS),
        ],
    },
    {
        "key": "western", "label": "欧美", "vft": 1,
        "groups": [
            _g("basic", "基本", "全部 可播放 中字可播放 含磁鏈 含字幕 含預覽圖 含預覽視頻"),
            _g("year", "年份", "全部 " + " ".join(_javdb_years(2004))),
            _g("theme", "主題", "全部 按摩 騙色 按摩油 女同性戀 成熟妈妈 綠帽男 採訪 跨種族 亞洲人 拉丁美女 奇聞趣事 運動健身 第一人稱視角 情侶幻想 婚禮 汽車 戀物癖 微變態 SM 派對 芭蕾 人體彩繪 業餘 聖誕 萬聖節 感恩節 復活節 瑜伽 足球 保姆 桑拿 軍事 遊戲 歐洲人 俄國人"),
            _g("body", "體型", "全部 褐髮 貧乳 巨乳 金髮 陰毛 紅頭髮 大屁股 黑髮 藍色眼晴 大陰莖 黑人美女 自然乳房 小個子美女 曬痕 瘦女孩 白虎 豐滿 曲線身材 勻稱身材 雪白皮膚 曬黑皮膚 小屁股 翹臀 修剪的陰毛 紋身/穿孔 大號美女 肌肉發達 短髮 比基尼直線"),
            _g("action", "行爲", "全部 打飛機 口交 舔陰 背入式 騎乘位 站立抽插 傳教士 俯臥後入式 顏射 69 射精 側躺後入 內射 乳交 3P 前吞後入 肛交 雙插 深喉 兩男一女 手淫 潮吹 站立背入式 兩男兩女 舔肛 4P 兩女一男 顏面騎乘 肛門擴張 接吻 打屁股 群交 肛交轉口交 多男對一女 肛門射精 旁觀 偷窺 打樁式 蕾絲剪刀式 電動馬鞍 緊縛 玩具 傳教剪刀式 粗暴性愛 調教 足交 小便 吞精 精液交換 脫衣舞 疊屁股 換妻 拳交 口塞器 流汗"),
            _g("costume", "服裝", "全部 蕾絲 高跟鞋 絲襪 吊帶 比基尼 眼鏡 眼罩 制服 牛仔褲 膠乳 靴子 緊身衣 吊襪腰帶 背心 裙子 短裙 短褲 綁腿 太陽鏡 帽子 襯衫 睡衣 內褲 牛仔短褲"),
            _g("location", "地點", "全部 戶外 學校 浴室 海灘 泳池 辦公室 車庫 停車場 船 酒吧 餐廳 廚房 室內 浴缸 酒店房間 監獄 更衣室 醫院 公園 圖書館 劇院 尋歡洞 臥室 客廳"),
            _g("role", "角色", "全部 少女 醫生/護士 性愛專家 熟女 媽媽 女抖S 抖M 妻子 拉拉隊長 廚師 罪犯 醫生 消防隊員 女童子軍 救生員 女傭 維修工 水管工 警察 囚犯 水手 女學生 女戰士 特務 老師 女服務員 秘書 女商人 法官 律師 空姐 老闆 繼女 角色扮演 女友 女神"),
            _g("other", "其他", "全部 獨占 幕後花絮 粉絲作品"),
            _g("duration", "時長", _JAVDB_DURATION_TAGS),
        ],
    },
    {
        "key": "fc2", "label": "FC2", "vft": None, "fallback_q": "FC2",
        "groups": [
            _g("basic", "基本", "全部 可播放 含磁鏈 含預覽圖"),
            _g("year", "年份", "全部 " + " ".join(_javdb_years(2010))),
            _g("tag", "标签", "全部 家庭主婦 美少女 自拍 年輕 露出 電車 騎乘位 高清 3P 妻子出軌 吞精 手淫 按摩 視頻聊天 美女 人妻 口內射精 女大學生 人母 字幕 泳衣 無套性交 童顔 車內性愛 金發 母乳 肛交 曬黑 模特兒 SM 偶像 成人 日本動漫 原作 男同 角色扮演 苗條 私人攝影 白虎 戀物癖 口交 辦公室美女 女同 內褲 內射 制服 可愛 巨乳 流出 海外 無碼 熟女 素人 美乳"),
            _g("duration", "時長", _JAVDB_DURATION_TAGS),
        ],
    },
    {
        "key": "anime", "label": "动漫", "vft": None, "fallback_q": "動漫",
        "groups": [
            _g("basic", "基本", "全部 可播放 可下載 含字幕 含預覽圖 含預覽視頻"),
            _g("year", "年份", "全部 " + " ".join(_javdb_years(2004))),
            _g("theme", "主題", "全部 動作/戰鬥 冒險 機器人 淫亂真實 科幻小說 SM 汽車性愛 學校作品 企劃 亂倫 懸疑 歷史劇 運動 其他戀物癖 暗黑系 內衣 幻想 恐怖 男同性戀 妄想 浪漫喜劇 亂交 女同性戀 戀愛 3D 遊戲"),
            _g("role", "角色", "全部 偶像/名人 姐妹 女服務員 OL 母親 女主人 兒時的朋友 千金小姐 姐姐 公主 洗澡 女教師 女戰士 格鬥家 導師 護士 岳母 辣妹 女忍者 修女 各種職業 熟女 女醫生 女主播 女大學生 女學生 其他學生 啦啦隊員 痴女 蠻橫嬌羞 偷窺 孕婦 閨蜜 新娘 秘書 人妻 美少女 寡婦 養母/養女 女傭 戶外露出 少妻"),
            _g("action", "行爲", "全部 肛門 猥褻 喝尿 手淫 玩具 監禁 灌腸 顏射 騎乘位 鬼畜 舔陰 拘束 吞精 潮吹 69 捆綁/束縛 羞恥 觸手 糞便 打手槍 體內射精 屈辱 按摩棒 乳交 口交 集體顏射 放尿 母乳 跳蛋 多P"),
            _g("body", "體型", "全部 巨乳 處女 正太控 苗條 貧乳/微乳 雙性人 瘦小身型 眼鏡"),
            _g("costume", "服裝", "全部 圍裙 校服 學校泳裝 角色扮演 水手套裝 制服 體操 褲襪緊身衣 緊縛 女祭司 泳裝 迷你裙 內衣 日本衣服和浴衣 貓耳女"),
            _g("other", "其他", "全部 高清 精選綜合"),
            _g("duration", "時長", _JAVDB_DURATION_TAGS),
        ],
    },
]

# 热搜关键词（按词库常用标签离线整理，避免联网抓取触发审查）
JAVDB_HOT_KEYWORDS = [
    "中出", "人妻", "女教師", "痴女", "巨乳", "美少女", "潮吹", "顏射",
    "角色扮演", "制服", "單體作品", "深喉", "足交", "女同性戀", "素人",
    "熟女", "蘿莉塔", "溫泉", "女傭", "偷窺", "苗條", "白虎", "4K", "動漫",
]


def javdb_tags_vocab() -> None:
    """下发标签词库（5 模式分组词表），前端据此渲染「标签页」内容。"""
    emit({"event": "javdb_tags_vocab", "modes": JAVDB_TAG_MODES})


def javdb_hot_search() -> None:
    """下发热搜关键词（离线词表）。"""
    emit({"event": "javdb_hot_search", "keywords": JAVDB_HOT_KEYWORDS})


# 目录导航：演员 / 系列 / 片商（列表页解析站内链接目录）
_JAVDB_DIR_KINDS = {"actors": "演员", "series": "系列", "makers": "片商"}


def _javdb_login_wall(soup: "BeautifulSoup") -> bool:
    """检测登录墙页面（未登录访问 /tags、/fc2、/users 等受限分区时站点渲染登入提示页）。"""
    title = soup.title.get_text(strip=True) if soup.title else ""
    if "登入" in title or "登錄" in title:
        return True
    text = soup.get_text(" ", strip=True)[:600]
    return "需要登入" in text or "需要登錄" in text or "請先登入" in text


async def javdb_directory(kind: str, page: int = 1, params: str = "") -> None:
    """JavDB 目录页（GET /actors|/series|/makers[/{censored|uncensored|western}]?page=N），解析名称+链接列表。

    kind 可带类型子路径（actors/censored 等，站点导航 HTML 实测为子路径而非 vft 参数）。
    params: 附加查询参数（保留兼容旧调用）。
    """
    parts = [p for p in (kind or "").strip("/").split("/") if p]
    if not parts or parts[0] not in _JAVDB_DIR_KINDS:
        emit({"event": "search_error", "message": f"未知的 JavDB 目录类型: {kind}"})
        return
    base = parts[0]
    sub = parts[1] if len(parts) > 1 else ""
    path = f"/{base}" + (f"/{sub}" if sub else "")
    page = max(1, page or 1)
    query = dict(parse_qsl((params or "").lstrip("?"))) if params else {}
    if page > 1:
        query["page"] = str(page)
    label = _JAVDB_DIR_KINDS[base] + ("·" + sub if sub else "")
    emit({"event": "search_start", "query": f"{label}目录", "page": page})
    try:
        soup = await asyncio.to_thread(_javdb_soup, path, query or None)
        if _javdb_login_wall(soup):
            raise RuntimeError("该目录需要登录后才能查看（凭据可能已过期，请在左侧重新登录 JavDB）")
        prefix = f"/{base}/"
        items, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = a["href"] or ""
            if not href.startswith(prefix):
                continue
            name = a.get_text(strip=True)
            slug = href[len(prefix):].split("?")[0].strip("/")
            if not name or not slug or slug in seen:
                continue
            seen.add(slug)
            items.append({"name": name, "url": f"{JAVDB_BASE}/{base}/{slug}"})
        if not items:
            raise RuntimeError("目录页没有解析到条目（站点结构可能变化，或被 Cloudflare 拦截）")
        has_more = bool(soup.select_one("a.pagination-next:not(.is-disabled)"))
        emit({"event": "javdb_directory", "kind": path.strip("/"), "label": label,
              "items": items, "page": page, "has_more": has_more, "params": params or ""})
        logging.info("JavDB %s目录 第 %d 页: %d 项", path, page, len(items))
    except Exception as exc:
        msg = str(exc)
        hint = "（请在左侧重新登录 JavDB 刷新 cookie）" if "Cloudflare" in msg else ""
        emit({"event": "search_error", "message": f"JavDB {label}目录获取失败: {msg}{hint}"})


async def javdb_open_url(url: str, label: str = "", page: int = 1) -> None:
    """打开任意 JavDB 影片列表页（类别 /censored 等、排行榜 /rankings/movies、年份筛选等），解析成卡片流。"""
    page = max(1, page or 1)
    raw = (url or "").strip()
    if not raw:
        emit({"event": "search_error", "message": "JavDB 列表链接为空"})
        return
    parsed = urlparse(raw if raw.startswith("http") else JAVDB_BASE + "/" + raw.lstrip("/"))
    path = parsed.path or "/"
    params = {k: v for k, v in urllib.parse.parse_qsl(parsed.query)}
    if page > 1:
        params["page"] = str(page)
    label = (label or "JavDB 列表").strip()
    emit({"event": "search_start", "query": label, "page": page})
    try:
        soup = await asyncio.to_thread(_javdb_soup, path, params or None)
        items = _javdb_parse_cards(soup)
        if not items:
            # 登录墙检测：/tags、/fc2、/users 等分区未登录时渲染登入提示页（0 卡片）
            if _javdb_login_wall(soup):
                raise RuntimeError("该页面需要登录后才能查看（凭据可能已过期，请在左侧重新登录 JavDB）")
            raise RuntimeError("列表页没有解析到影片卡片（站点结构可能变化，或被 Cloudflare 拦截）")
        await _javdb_emit_list(soup, label, page, items)
    except Exception as exc:
        msg = str(exc)
        hint = ""
        if "Cloudflare" in msg:
            hint = "（请在左侧重新登录 JavDB 刷新 cookie）"
        elif "ProxyError" in msg or "timed out" in msg or "Connection" in msg:
            hint = "（请检查 JavDB 代理设置，国内必须代理）"
        emit({"event": "search_error", "message": f"JavDB 列表获取失败: {msg}{hint}"})


def _spawn_bg_task(coro) -> "asyncio.Task":
    """把长耗时协程丢后台执行，避免阻塞命令循环（解析/搜索排队表现为转圈卡死）。"""
    task = asyncio.create_task(coro)

    def _on_done(fut: "asyncio.Task") -> None:
        if not fut.cancelled() and fut.exception():
            logging.error("后台任务失败: %s", fut.exception(), exc_info=fut.exception())

    task.add_done_callback(_on_done)
    return task


# 通用 webview OAuth 站点（xhamster/pornhub/xvideos）凭据存取（AP1 阶段）
# cookie 字符串存 theme_cache.dat 的 creds[site]，具体 check_login/搜索/解析待 AP2/AP3/AP4 填充
_GENERIC_OAUTH_SITES = ("xhamster", "pornhub", "xvideos", "google", "oreno3d", "erommdtube", "fc2")


def _generic_save_cookies(site: str, cookie_str: str) -> dict:
    """保存 webview 抓取的 cookie 字符串到加密凭据库。"""
    if site not in _GENERIC_OAUTH_SITES:
        return {"ok": False, "error": f"未知站点: {site}"}
    # 解析 cookie 字符串为 dict
    cookies = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        idx = pair.find("=")
        if idx <= 0:
            continue
        cookies[pair[:idx].strip()] = pair[idx + 1:].strip()
    cred = {"cookies": cookies, "cookie_str": cookie_str, "saved_at": time.time()}
    _secure_store_write_cred(site, cred)
    return {"ok": True, "count": len(cookies)}


def _generic_load_cookies(site: str) -> dict:
    """读取站点 cookie 凭据。"""
    if site not in _GENERIC_OAUTH_SITES:
        return {}
    return _secure_store_read_cred(site)


def _generic_cookie_str(site: str) -> str:
    """读取站点 cookie 字符串。"""
    return _generic_load_cookies(site).get("cookie_str") or ""


def _generic_check_login(site: str, silent: bool = False) -> dict:
    """通用登录态检查。

    - google：会话 cookie 严格判定（SID/HSID/SSID + SAPISID）
    - oreno3d/erommdtube：cookie 存在 + 网络验证（带保存的 cookie 请求站点首页，
      HTTP 200 = 会话有效；网络异常时降级为 cookie 存在判定，避免误报未登录）
    - 其余站：cookie 存在即视为已登录
    """
    cred = _generic_load_cookies(site)
    cookies = cred.get("cookies") or {}
    if site == "google":
        has_auth = _google_has_auth(cookies)
        username = cred.get("email") or ""
    elif site in ("oreno3d", "erommdtube"):
        has_auth = bool(cookies) and _oreno_session_valid(site)
        username = cred.get("email") or ""
    else:
        has_auth = bool(cookies)
        username = cred.get("username") or ""  # AP2/AP4 时填充实际用户名提取
    # 静默模式（启动时自动检测）也要推送：前端按 silent 标志抑制提示
    emit({
        "event": "site_login_result",
        "site": site,
        "silent": silent,
        "logged_in": has_auth,
        "username": username,
        "cookie_count": len(cookies),
    })
    return {"logged_in": has_auth, "username": username, "cookie_count": len(cookies)}


def _generic_logout(site: str) -> None:
    """通用退出登录（清缓存凭据）。"""
    _secure_store_clear_cred(site)
    emit({
        "event": "site_login_result",
        "site": site,
        "logged_in": False,
        "username": "",
        "cookie_count": 0,
        "logout": True,
    })


# 通用账号密码保存（全站登录套件：加密存本机，供登录表单回填与内置浏览器预填）
_SITE_SAVE_CRED_SITES = (
    "pawchive", "twitter", "exhentai", "iwara", "hanime", "pixiv", "asmr",
    "xhamster", "pornhub", "xvideos", "javdb", "google",
    "oreno3d", "erommdtube", "fc2",
)
# 各站账号字段名（asmr 用 username，其余用 email）
_SITE_CRED_USER_FIELD = {s: "email" for s in _SITE_SAVE_CRED_SITES}
_SITE_CRED_USER_FIELD["asmr"] = "username"


def site_save_cred(site: str, email: str, password: str) -> None:
    """通用账号密码保存（加密存本机；不发起登录，仅凭据入库 + 登录表单回填）。

    - iwara / asmr / hanime：保存的密码供 token 失效时自动重登
    - twitter / exhentai / xhamster / pornhub / xvideos：供内置浏览器登录页自动预填
    - 保存后各站登录状态不变（cookie/token 独立判定）
    """
    site = (site or "").strip()
    if site not in _SITE_SAVE_CRED_SITES:
        emit({"event": "site_login_result", "site": site, "logged_in": False,
              "message": f"未知站点: {site}"})
        return
    email = (email or "").strip()
    if not email:
        emit({"event": "site_login_result", "site": site, "logged_in": False,
              "message": "请输入账号（邮箱/用户名）"})
        return
    cred = _secure_store_read_cred(site)
    user_field = _SITE_CRED_USER_FIELD.get(site, "email")
    cred[user_field] = email
    if password:
        cred["password"] = password
    cred["cred_saved_at"] = time.time()
    _secure_store_write_cred(site, cred)
    logged_in = _site_logged_in_quick(site, cred)
    emit({
        "event": "site_login_result",
        "site": site,
        "logged_in": logged_in,
        "username": email,
        "message": "账号密码已保存（加密存本机）",
    })
    logging.info("%s 凭据已保存: %s", site, email)
    _emit_login_info()


def _site_logged_in_quick(site: str, cred: dict) -> bool:
    """保存凭据后快速判定当前登录状态（不发网络请求，按已有会话/token/cookie 判断）。"""
    try:
        if site == "iwara":
            return bool(cred.get("user_token"))
        if site == "asmr":
            return bool(cred.get("token"))
        if site == "hanime":
            return bool(cred.get("cookies"))
        if site in ("oreno3d", "erommdtube", "xhamster", "pornhub", "xvideos", "google"):
            return bool(cred.get("cookies"))
        if site == "twitter":
            return bool(_twitter_load_cookies().get("auth_token"))
        if site == "exhentai":
            return bool(_exhentai_load_cookies().get("ipb_member_id"))
        if site == "pawchive":
            return bool({c.name: c.value for c in _pawchive_session.cookies}.get("session"))
        if site == "javdb":
            return bool(cred.get("cookies"))
    except Exception:
        pass
    return False
