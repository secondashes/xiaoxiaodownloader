# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Pawchive（搜索/解析/画师子项目/目录规则）。

由 gui_bridge.py 按物理顺序拆出（原行区间 1437-2619），
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
# Pawchive 站点支持 (pawchive.pw)
# ============================
PAWCHIVE_HOST = "https://pawchive.pw"
PAWCHIVE_FILE_HOST = "https://file.pawchive.pw"
PAWCHIVE_IMG_HOST = "https://img.pawchive.pw"
PAWCHIVE_PAGE_SIZE = 50

PAWCHIVE_CREATORS_CACHE = Path("cache") / "pawchive_creators.json"
PAWCHIVE_CREATORS_TTL = 24 * 3600  # 创作者列表缓存有效期（秒）
PAWCHIVE_DOWNLOAD_GAP = 1.0        # 两次下载之间的最小间隔（秒），站点对下载有限速


def is_pawchive_url(url: str) -> bool:
    """判断 URL 是否属于 Pawchive 站点（pawchive.pw 及其子域名）。"""
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    return netloc == "pawchive.pw" or netloc.endswith(".pawchive.pw")


def _pawchive_parse_url(url: str) -> dict | None:
    """解析 Pawchive URL，返回页面信息。

    支持的格式:
      /{service}/user/{user_id}                    画师页（类似相册）
      /{service}/user/{user_id}/post/{post_id}     帖子页（类似单文件）
    """
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]

    if len(parts) >= 3 and parts[1] == "user":
        info = {
            "kind": "artist",
            "service": parts[0],
            "user_id": parts[2],
            "post_id": None,
        }
        if len(parts) >= 5 and parts[3] == "post":
            info["kind"] = "post"
            info["post_id"] = parts[4]
        return info
    return None


# Pawchive 会话（登录后用于收藏等功能；未登录也可用于普通浏览请求）
# 注意：UA 字符串直接写死，不能引用 SEARCH_HEADERS（它定义在文件更靠后的位置）
_pawchive_session = requests.Session()
_pawchive_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": PAWCHIVE_HOST + "/",
})
_pawchive_username: str | None = None


def _pawchive_username_now() -> str:
    """当前用户名（跨模块读取入口）。"""
    return _pawchive_username or ""

# 下载节流（站点对下载有限速，控制请求频率避免被封）
_pawchive_download_lock = asyncio.Lock()
_pawchive_last_download_time = 0.0


async def _pawchive_throttle_download() -> None:
    """确保两次 Pawchive 下载请求之间至少间隔 PAWCHIVE_DOWNLOAD_GAP 秒。"""
    global _pawchive_last_download_time
    async with _pawchive_download_lock:
        elapsed = time.monotonic() - _pawchive_last_download_time
        if elapsed < PAWCHIVE_DOWNLOAD_GAP:
            await asyncio.sleep(PAWCHIVE_DOWNLOAD_GAP - elapsed)
        _pawchive_last_download_time = time.monotonic()


def _pawchive_load_session() -> None:
    """启动时恢复已保存的登录会话（加密账号存储）。"""
    global _pawchive_username
    data = _secure_store_read_cred("pawchive")
    for name, value in (data.get("cookies") or {}).items():
        _pawchive_session.cookies.set(name, value)
    _pawchive_username = data.get("username")
    if _pawchive_username:
        logging.info("已恢复 Pawchive 登录会话: %s", _pawchive_username)


def _pawchive_save_session() -> None:
    """持久化登录会话（加密存储）。"""
    cookies = {c.name: c.value for c in _pawchive_session.cookies}
    _secure_store_write_cred("pawchive", {"username": _pawchive_username, "cookies": cookies})


def _pawchive_logged_in() -> bool:
    return bool(_pawchive_session.cookies.get("session"))


async def pawchive_login(username: str, password: str) -> None:
    """登录 pawchive.pw，成功后保存会话 cookie。"""
    global _pawchive_username
    if not username or not password:
        emit({"event": "pawchive_login_result", "success": False, "message": "请输入用户名和密码"})
        return

    def _do_login() -> requests.Response:
        _pawchive_session.cookies.clear()
        # 先访问登录页获取初始 cookie
        _pawchive_session.get(f"{PAWCHIVE_HOST}/account/login", timeout=15)
        return _pawchive_session.post(
            f"{PAWCHIVE_HOST}/account/login",
            data={"username": username, "password": password, "location": "/"},
            timeout=15,
            allow_redirects=False,
        )

    try:
        response = await asyncio.to_thread(_do_login)
        # 登录成功：302 跳转到 /；失败：302 跳回 /account/login
        location = (response.headers.get("location") or "").lower()
        if response.status_code in (302, 303) and "login" not in location and _pawchive_logged_in():
            _pawchive_username = username
            _pawchive_save_session()
            _record_login_ok("pawchive")
            emit({
                "event": "pawchive_login_result",
                "success": True,
                "username": username,
                "message": f"登录成功: {username}",
            })
            logging.info("Pawchive 登录成功: %s", username)
        else:
            _pawchive_username = None
            emit({
                "event": "pawchive_login_result",
                "success": False,
                "message": "登录失败：用户名或密码错误",
            })
            logging.warning("Pawchive 登录失败: %s", username)
    except requests.RequestException as exc:
        emit({
            "event": "pawchive_login_result",
            "success": False,
            "message": f"登录请求失败: {exc}",
            "network_issue": True,
        })
        logging.exception("Pawchive 登录请求失败")
    _emit_login_info()


def pawchive_logout() -> None:
    """退出登录，清除会话。"""
    global _pawchive_username
    try:
        _pawchive_session.get(f"{PAWCHIVE_HOST}/account/logout", timeout=10)
    except requests.RequestException:
        pass
    _pawchive_session.cookies.clear()
    _pawchive_username = None
    _secure_store_clear_cred("pawchive")
    emit({"event": "pawchive_login_result", "success": False, "logout": True, "username": "", "message": "已退出登录"})
    logging.info("Pawchive 已退出登录")
    _emit_login_info()


def _pawchive_check_login() -> tuple[bool, str | None, str]:
    """检查 Pawchive 登录状态（用收藏 API 验证会话是否有效）。"""
    if not _pawchive_logged_in():
        return False, None, "未配置 Pawchive 登录信息"
    try:
        response = _pawchive_session.get(f"{PAWCHIVE_HOST}/api/v1/account/favorites", timeout=15)
        if response.status_code == 200:
            return True, _pawchive_username, "Pawchive 登录有效"
        if response.status_code == 401:
            return False, None, "Pawchive 登录已过期，请重新登录"
        return False, None, f"Pawchive 状态异常: HTTP {response.status_code}"
    except requests.RequestException as exc:
        return False, None, f"Pawchive 连接失败: {exc}"


def pawchive_set_cookies(cookie_str: str, username: str = "") -> None:
    """用 cookie 字符串恢复 Pawchive 会话（一键抓取 Cookie / 账号切换用）。"""
    global _pawchive_username
    cookies: dict = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            if name.strip():
                cookies[name.strip()] = value.strip()
    if not cookies.get("session"):
        emit({
            "event": "pawchive_login_result",
            "success": False,
            "message": "Cookie 缺少 session，请确认已在浏览器登录 pawchive.pw",
        })
        return
    _pawchive_session.cookies.clear()
    for name, value in cookies.items():
        _pawchive_session.cookies.set(name, value)
    _pawchive_username = username or ""
    _pawchive_save_session()
    ok, uname, msg = _pawchive_check_login()
    if ok:
        _record_login_ok("pawchive")
        if uname:
            _pawchive_username = uname
            _pawchive_save_session()
    emit({
        "event": "pawchive_login_result",
        "success": ok,
        "username": (uname if ok else _pawchive_username) or "",
        "message": msg,
        "network_issue": (not ok) and _login_network_issue("pawchive"),
    })
    _emit_login_info()


async def pawchive_get_favorites(fav_type: str = "creator") -> None:
    """获取登录账号的收藏列表（creator=画师 / post=帖子），以搜索结果事件返回。

    每条带 updated（最后更新时间）/ last_imported（重新导入）/ faved_seq（收藏序号），
    前端按这三个键做"最新发布日期/收藏日期/重新导入日期"排序。
    """
    fav_type = "post" if fav_type == "post" else "artist"  # kemono API 实测 type=artist
    title = "我的收藏（帖子）" if fav_type == "post" else "我的收藏"
    emit({"event": "search_start", "query": title, "page": 1})

    def _fetch_api() -> requests.Response:
        return _pawchive_session.get(
            f"{PAWCHIVE_HOST}/api/v1/account/favorites",
            params={"type": fav_type}, timeout=20)

    items: list[dict] = []
    try:
        response = await asyncio.to_thread(_fetch_api)
        if response.status_code == 401:
            emit({"event": "search_error", "message": "登录已过期，请重新登录 Pawchive"})
            return
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                for creator in data:
                    if not isinstance(creator, dict):
                        continue
                    cid = str(creator.get("id") or "")
                    service = creator.get("service") or ""
                    if not cid or not service:
                        continue
                    if fav_type == "post":
                        # 帖子收藏：字段形状防御性映射（账号无帖子收藏，形状随站点波动）
                        uid = str(creator.get("user") or creator.get("uid") or "")
                        if not uid:
                            continue
                        main_file = creator.get("file") or {}
                        thumb_path = main_file.get("path") or ""
                        items.append({
                            "album_name": creator.get("title") or creator.get("name") or cid,
                            "album_url": f"{PAWCHIVE_HOST}/{service}/user/{uid}/post/{cid}",
                            "thumbnail": f"{PAWCHIVE_HOST}/thumbnail/data{thumb_path}" if thumb_path else "",
                            "files": None,
                            "site": "pawchive",
                            "service": service,
                            "updated": creator.get("edited") or creator.get("updated") or "",
                            "last_imported": creator.get("last_imported") or "",
                            "faved_seq": creator.get("faved_seq") or "",
                            "fav_type": "post",
                        })
                        continue
                    items.append({
                        "album_name": creator.get("name") or cid,
                        "album_url": f"{PAWCHIVE_HOST}/{service}/user/{cid}",
                        "thumbnail": f"{PAWCHIVE_HOST}/icons/{service}/{cid}",
                        "files": None,
                        "site": "pawchive",
                        "service": service,
                        # 排序/展示字段（原站收藏页三排序键）
                        "updated": creator.get("updated") or "",
                        "last_imported": creator.get("last_imported") or "",
                        "faved_seq": creator.get("faved_seq") or "",
                        "fav_type": "creator",
                    })
    except (requests.RequestException, ValueError):
        logging.exception("Pawchive 收藏 API 请求失败")


    # API 未返回数据时回退解析 /favorites HTML（SSR 画师卡片）
    if not items and _pawchive_logged_in():
        try:
            response = await asyncio.to_thread(
                lambda: _pawchive_session.get(f"{PAWCHIVE_HOST}/favorites", timeout=20),
            )
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                seen: set[str] = set()
                for link in soup.find_all("a", href=True):
                    href = link.get("href") or ""
                    m = re.match(r"^/([\w-]+)/user/(\d+)/?$", href)
                    if not m:
                        continue
                    service, uid = m.groups()
                    url = f"{PAWCHIVE_HOST}/{service}/user/{uid}"
                    if url in seen:
                        continue
                    seen.add(url)
                    name = link.get_text(strip=True) or uid
                    items.append({
                        "album_name": name,
                        "album_url": url,
                        "thumbnail": f"{PAWCHIVE_HOST}/icons/{service}/{uid}",
                        "files": None,
                        "site": "pawchive",
                        "service": service,
                    })
        except requests.RequestException:
            logging.exception("Pawchive 收藏页解析失败")

    if not items:
        emit({"event": "search_error", "message": "未获取到收藏，请先登录或先在网页上添加收藏"})
        return

    _apply_cached_thumbnails(items)
    emit({
        "event": "search_result",
        "query": "我的收藏",
        "page": 1,
        "total_pages": 1,
        "has_more": False,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 收藏获取完成: %d 个画师", len(items))


async def pawchive_favorite_creator(service: str, user_id: str, unfavorite: bool = False) -> None:
    """关注/取消关注画师（kemono API 实测：POST/DELETE /api/v1/favorites/creator/{service}/{id}）。"""
    service = (service or "").strip()
    user_id = str(user_id or "").strip()
    if not service or not user_id:
        emit({"event": "pa_fav_result", "service": service, "user_id": user_id,
              "favorited": False, "error": "参数缺失"})
        return
    method = "DELETE" if unfavorite else "POST"
    try:
        resp = await asyncio.to_thread(
            _pawchive_session.request, method,
            f"{PAWCHIVE_HOST}/api/v1/favorites/creator/{service}/{user_id}", timeout=20)
        if resp.status_code in (200, 201, 204):
            emit({"event": "pa_fav_result", "service": service, "user_id": user_id,
                  "favorited": not unfavorite})
            logging.info("Pawchive %s 关注 %s/%s -> %s", method, service, user_id, resp.status_code)
        else:
            emit({"event": "pa_fav_result", "service": service, "user_id": user_id,
                  "favorited": False, "error": f"操作失败 HTTP {resp.status_code}"})
    except requests.RequestException as exc:
        emit({"event": "pa_fav_result", "service": service, "user_id": user_id,
              "favorited": False, "error": f"请求失败: {exc}"})


async def pawchive_home(page: int = 1) -> None:
    """PA 主页：全站最新帖子流（/api/v1/posts 每页 50，发布时间倒序）。

    以搜索结果事件返回帖子卡片（点击卡片直接打开帖子详情）。
    """
    page = max(1, int(page or 1))
    emit({"event": "search_start", "query": "主页", "page": page})
    items: list[dict] = []
    try:
        offset = (page - 1) * PAWCHIVE_PAGE_SIZE
        data = await asyncio.to_thread(
            _pawchive_fetch_json, "/api/v1/posts", {"o": offset},
        )
        if isinstance(data, list):
            for post in data:
                if not isinstance(post, dict):
                    continue
                post_id = str(post.get("id") or "")
                user_id = str(post.get("user") or "")
                service = post.get("service") or ""
                if not (post_id and user_id and service):
                    continue
                main_file = post.get("file") or {}
                att_count = len([
                    a for a in (post.get("attachments") or [])
                    if isinstance(a, dict) and a.get("path")
                ])
                items.append({
                    "album_name": post.get("title") or "未命名帖子",
                    "album_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}/post/{post_id}",
                    "thumbnail": (
                        PAWCHIVE_IMG_HOST + "/thumbnail/data" + main_file["path"]
                        if main_file.get("path") else ""
                    ),
                    "files": 1 + att_count if (main_file.get("path") or att_count) else att_count,
                    "site": "pawchive",
                    "service": service,
                })
    except Exception as exc:
        emit({"event": "search_error", "message": f"获取主页内容失败: {exc}"})
        logging.exception("Pawchive 主页获取失败")
        return

    if not items:
        emit({"event": "search_error", "message": "主页没有更多内容了"})
        return

    _apply_cached_thumbnails(items)
    emit({
        "event": "search_result",
        "query": "主页",
        "page": page,
        "total_pages": 0,          # 未知总页数：分页条只显示当前页
        "has_more": len(items) >= PAWCHIVE_PAGE_SIZE,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 主页: 第 %d 页 %d 个帖子", page, len(items))


# ============================
# Pawchive 搜索
# ============================
def _fetch_pawchive_creators() -> list[dict] | None:
    """拉取全量创作者列表（约 12MB），本地缓存 24 小时。"""
    if PAWCHIVE_CREATORS_CACHE.exists():
        try:
            data = json.loads(PAWCHIVE_CREATORS_CACHE.read_text(encoding="utf-8"))
            if time.time() - data.get("fetched_at", 0) < PAWCHIVE_CREATORS_TTL:
                return data.get("creators")
        except (OSError, json.JSONDecodeError):
            pass

    try:
        response = _pawchive_session.get(f"{PAWCHIVE_HOST}/api/v1/creators", timeout=60)
        response.raise_for_status()
        creators = response.json()
        if not isinstance(creators, list):
            return None
        PAWCHIVE_CREATORS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PAWCHIVE_CREATORS_CACHE.write_text(
            json.dumps({"fetched_at": time.time(), "creators": creators}, ensure_ascii=False),
            encoding="utf-8",
        )
        logging.info("Pawchive 创作者列表已更新: %d 个", len(creators))
        return creators
    except (requests.RequestException, ValueError, OSError):
        logging.exception("Pawchive 创作者列表拉取失败")
        return None


async def pawchive_search_artist(query: str, page: int) -> None:
    """画师搜索：本地过滤创作者列表。"""
    emit({"event": "search_start", "query": query, "page": page})
    logging.info("Pawchive 画师搜索: '%s' (第 %d 页)", query, page)

    creators = await asyncio.to_thread(_fetch_pawchive_creators)
    if creators is None:
        emit({"event": "search_error", "message": "无法获取 Pawchive 创作者列表，请稍后重试"})
        return

    q = query.strip().lower()
    matched = [c for c in creators if q in (c.get("name") or "").lower()]

    total_pages = max(1, -(-len(matched) // PAWCHIVE_PAGE_SIZE))
    start = (page - 1) * PAWCHIVE_PAGE_SIZE
    page_creators = matched[start:start + PAWCHIVE_PAGE_SIZE]

    # 收藏集合（type=artist，kemono API 实测）：卡片显示关注状态
    try:
        fav_resp = await asyncio.to_thread(
            _pawchive_session.get, f"{PAWCHIVE_HOST}/api/v1/account/favorites",
            params={"type": "artist"}, timeout=20)
        fav_ids = {f"{c.get('service')}_{c.get('id')}" for c in (fav_resp.json() or [])} if fav_resp.status_code == 200 else set()
    except (requests.RequestException, ValueError):
        fav_ids = set()

    items = [{
        "album_name": c.get("name") or c.get("id"),
        "album_url": f"{PAWCHIVE_HOST}/{c.get('service')}/user/{c.get('id')}",
        "thumbnail": f"{PAWCHIVE_HOST}/icons/{c.get('service')}/{c.get('id')}",
        "files": None,
        "site": "pawchive",
        "service": c.get("service"),
        "user_id": str(c.get("id") or ""),
        "favorited": f"{c.get('service')}_{c.get('id')}" in fav_ids,
    } for c in page_creators]

    _apply_cached_thumbnails(items)
    emit({
        "event": "search_result",
        "query": query,
        "page": page,
        "total_pages": total_pages,
        "total_results": len(matched),
        "has_more": page < total_pages,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 画师搜索完成: '%s' 匹配 %d 个", query, len(matched))


def _fetch_pawchive_tag_page(tag: str, offset: int) -> BeautifulSoup | None:
    """抓取标签搜索结果页（SSR 渲染，每页 50 个）。"""
    response = _pawchive_session.get(
        f"{PAWCHIVE_HOST}/posts",
        params={"tags": tag, "o": offset},
        timeout=20,
    )
    if response.status_code != 200:
        return None
    return BeautifulSoup(response.content, "html.parser")


def _parse_pawchive_post_cards(soup: BeautifulSoup) -> list[dict]:
    """解析 SSR 帖子卡片为搜索结果条目。"""
    items: list[dict] = []
    for card in soup.find_all("article", class_="post-card"):
        link = card.find("a", href=True)
        if link is None:
            continue
        href = (link.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = PAWCHIVE_HOST + href

        header = card.find("header", class_="post-card__header")
        title = header.get_text(strip=True) if header else ""

        thumbnail = ""
        img = card.find("img", class_="post-card__image")
        if img:
            thumbnail = (img.get("src") or "").strip()

        # 附件数提示
        files = None
        footer = card.find("footer")
        if footer:
            m = re.search(r"(\d+)\s+attachments?", footer.get_text())
            if m:
                files = int(m.group(1))

        items.append({
            "album_name": title or "未命名帖子",
            "album_url": href,
            "thumbnail": thumbnail,
            "files": files,
            "site": "pawchive",
        })
    return items


async def pawchive_search_tag(tag: str, page: int) -> None:
    """标签搜索：全站帖子搜索（SSR 分页，每页 50）。"""
    emit({"event": "search_start", "query": tag, "page": page})
    logging.info("Pawchive 标签搜索: '%s' (第 %d 页)", tag, page)

    offset = (page - 1) * PAWCHIVE_PAGE_SIZE
    soup = await asyncio.to_thread(_fetch_pawchive_tag_page, tag, offset)
    if soup is None:
        emit({"event": "search_error", "message": "搜索失败，无法访问 pawchive.pw"})
        return

    items = _parse_pawchive_post_cards(soup)
    _apply_cached_thumbnails(items)
    # 有结果就认为可能还有下一页（末页由前端"加载全部"兜底）
    emit({
        "event": "search_result",
        "query": tag,
        "page": page,
        "total_pages": page + 1 if len(items) >= PAWCHIVE_PAGE_SIZE else page,
        "has_more": len(items) >= PAWCHIVE_PAGE_SIZE,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 标签搜索完成: '%s' 第 %d 页，%d 个结果", tag, page, len(items))


# ============================
# Pawchive 解析 (inspect)
# ============================
def _pawchive_fetch_json(path: str, params: dict | None = None) -> dict | list | None:
    """同步请求 Pawchive API 并返回 JSON。"""
    try:
        response = _pawchive_session.get(
            f"{PAWCHIVE_HOST}{path}", params=params, timeout=30,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def _pawchive_fetch_profile(service: str, user_id: str) -> dict | None:
    """获取画师资料（画师名等）。"""
    data = _pawchive_fetch_json(f"/api/v1/{service}/user/{user_id}/profile")
    return data if isinstance(data, dict) else None


def _pawchive_make_item(
    post: dict,
    file_info: dict,
    artist_name: str,
    service: str,
    user_id: str,
) -> dict:
    """把帖子中的一个文件转换为下载条目（直链永久有效）。"""
    path = file_info.get("path") or ""
    name = file_info.get("name") or Path(path).name
    post_id = str(post.get("id") or "")
    return {
        "filename": name,
        "size": None,
        "item_page": f"{PAWCHIVE_HOST}/{service}/user/{user_id}/post/{post_id}",
        "status": "ok",
        "site": "pawchive",
        "media_url": PAWCHIVE_FILE_HOST + "/data" + path,
        "media_path": path,
        "thumbnail": PAWCHIVE_IMG_HOST + "/thumbnail/data" + path,
        "post_title": post.get("title") or "",
        "post_date": post.get("published") or "",
        "artist": artist_name,
        "service": service,
        "post_id": post_id,
    }


def _pawchive_post_items(post: dict, artist_name: str, service: str, user_id: str) -> list[dict]:
    """帖子 → 文件条目列表（主文件 + 附件）。"""
    items: list[dict] = []
    main_file = post.get("file") or {}
    if main_file.get("path"):
        items.append(_pawchive_make_item(post, main_file, artist_name, service, user_id))
    for att in post.get("attachments") or []:
        if isinstance(att, dict) and att.get("path"):
            items.append(_pawchive_make_item(post, att, artist_name, service, user_id))
    return items


def _pawchive_post_has_attachments(post: dict) -> bool:
    """判断帖子列表数据里的附件信息是否完整（列表 API 有时只给空占位）。"""
    for att in post.get("attachments") or []:
        if isinstance(att, dict) and att.get("path"):
            return True
    return False


async def pawchive_inspect(url: str, options: dict) -> None:
    """解析 Pawchive 画师页/帖子页，返回文件列表。"""
    info = _pawchive_parse_url(url)
    if info is None:
        emit({
            "event": "inspect_error",
            "message": "无法识别的 Pawchive 链接，请粘贴画师页或帖子页链接",
        })
        return

    service = info["service"]
    user_id = info["user_id"]

    try:
        # ---------- 帖子页：单帖解析 ----------
        if info["kind"] == "post":
            post = await asyncio.to_thread(
                _pawchive_fetch_json,
                f"/api/v1/{service}/user/{user_id}/post/{info['post_id']}",
            )
            if not isinstance(post, dict) or not post.get("id"):
                emit({"event": "inspect_error", "message": f"无法获取帖子: {url}"})
                return

            profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
            artist_name = (profile or {}).get("name") or user_id

            items = _pawchive_post_items(post, artist_name, service, user_id)
            if not items:
                emit({"event": "inspect_error", "message": "帖子中没有找到可下载的文件"})
                return

            _apply_cached_thumbnails(items)
            _mark_items_new(f"pawchive_{service}_{user_id}", items)
            emit({
                "event": "inspect_complete",
                "album_name": artist_name,
                "album_id": f"pawchive_{service}_{user_id}",
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Pawchive 帖子解析完成: %s (%d 个文件)", url, len(items))
            return

        # ---------- 画师页：分页拉全部帖子 ----------
        identifier = f"pawchive_{service}_{user_id}"

        # 命中缓存则直接返回
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or user_id,
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 Pawchive 画师信息: %s (%d 个文件)", identifier, len(items))
            return

        profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
        artist_name = (profile or {}).get("name") or user_id

        # 分页拉取帖子列表
        posts: list[dict] = []
        offset = 0
        while True:
            page_data = await asyncio.to_thread(
                _pawchive_fetch_json,
                f"/api/v1/{service}/user/{user_id}/posts",
                {"o": offset},
            )
            if not isinstance(page_data, list) or not page_data:
                break
            posts.extend(page_data)
            if len(page_data) < PAWCHIVE_PAGE_SIZE:
                break
            offset += PAWCHIVE_PAGE_SIZE

        if not posts:
            emit({"event": "inspect_error", "message": "没有找到任何帖子，请确认链接是否正确"})
            return

        total = len(posts)
        emit({
            "event": "inspect_progress",
            "current": 0,
            "total": total,
            "filename": "",
        })
        logging.info("Pawchive 画师 '%s' 共 %d 个帖子", artist_name, total)

        semaphore = asyncio.Semaphore(INSPECT_CONCURRENCY)
        results: list[dict] = []
        completed_count = 0
        count_lock = asyncio.Lock()

        async def resolve_one(post: dict) -> None:
            nonlocal completed_count
            async with semaphore:
                # 列表 API 附件信息完整时直接使用，否则拉帖子详情
                if _pawchive_post_has_attachments(post) or (post.get("file") or {}).get("path"):
                    post_items = _pawchive_post_items(post, artist_name, service, user_id)
                else:
                    detail = await asyncio.to_thread(
                        _pawchive_fetch_json,
                        f"/api/v1/{service}/user/{user_id}/post/{post.get('id')}",
                    )
                    if isinstance(detail, dict):
                        post_items = _pawchive_post_items(detail, artist_name, service, user_id)
                    else:
                        post_items = []

                if post_items:
                    results.extend(post_items)

                async with count_lock:
                    completed_count += 1
                    if completed_count % 10 == 0 or completed_count == total:
                        emit({
                            "event": "inspect_progress",
                            "current": completed_count,
                            "total": total,
                            "filename": post_items[0]["filename"] if post_items else "",
                        })

        await asyncio.gather(*(resolve_one(p) for p in posts))

        _apply_cached_thumbnails(results)

        # 增量标记：上次下载之后新增的帖子文件标 is_new
        _mark_items_new(identifier, results)

        _save_album_cache(identifier, {
            "album_name": artist_name,
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })

        emit({
            "event": "inspect_complete",
            "album_name": artist_name,
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })
        asyncio.create_task(_cache_thumbnails(results))
        logging.info("Pawchive 画师解析完成: %s, 共 %d 个文件", artist_name, len(results))

    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("Pawchive 解析过程出错")


async def pawchive_post_info(url: str) -> None:
    """获取 Pawchive 帖子完整信息（标题/画师/时间/正文/标签/附件预览）。"""
    info = _pawchive_parse_url(url)
    if info is None or info.get("kind") != "post":
        emit({"event": "pa_post_info_error", "message": "无效的 Pawchive 帖子链接"})
        return
    service = info["service"]
    user_id = info["user_id"]
    post_id = info["post_id"]
    try:
        post = await asyncio.to_thread(
            _pawchive_fetch_json,
            f"/api/v1/{service}/user/{user_id}/post/{post_id}",
        )
        if not isinstance(post, dict):
            emit({"event": "pa_post_info_error", "message": "获取帖子信息失败，请稍后重试"})
            return

        # 画师名（帖子 API 通常含 user 字段；缺失时拉 profile）
        artist_name = ""
        if isinstance(post.get("user"), dict):
            artist_name = post["user"].get("name") or ""
        if not artist_name:
            profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
            if profile:
                artist_name = profile.get("name") or ""
        artist_name = artist_name or user_id

        # 标签（Kemono 架构：可能是列表或逗号分隔字符串）
        raw_tags = post.get("tags") or []
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]

        # 附件预览（主文件 + 附件，直链缩略图永久有效）
        previews: list[dict] = []
        for fi in [post.get("file") or {}] + [
            a for a in (post.get("attachments") or []) if isinstance(a, dict)
        ]:
            path = fi.get("path") or ""
            if not path:
                continue
            previews.append({
                "name": fi.get("name") or Path(path).name,
                "thumbnail": PAWCHIVE_IMG_HOST + "/thumbnail/data" + path,
                "media_url": PAWCHIVE_FILE_HOST + "/data" + path,
            })

        _apply_cached_thumbnails(previews)
        emit({
            "event": "pa_post_info",
            "url": url,
            "title": post.get("title") or "未命名帖子",
            "artist": artist_name,
            "artist_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}",
            "posted": (post.get("published") or "")[:10],
            "content": post.get("content") or "",
            "tags": tags,
            "previews": previews,
        })
        asyncio.create_task(_cache_thumbnails(previews))
        logging.info("Pawchive 帖子信息: %s", (post.get("title") or "")[:50])

    except PermissionError as exc:
        emit({"event": "pa_post_info_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "pa_post_info_error", "message": f"获取帖子信息失败: {exc}"})
        logging.exception("Pawchive 帖子信息获取失败")


# ============================
# Pawchive 画师子项目列表（点开画师 → 按日期展示全部帖子）
# ============================
PAWCHIVE_POSTS_CACHE_DIR = Path("cache") / "pawchive_posts"
PAWCHIVE_POSTS_CACHE_TTL = 24 * 60 * 60  # 帖子列表缓存 24 小时


def _pa_posts_cache_path(identifier: str) -> Path:
    return PAWCHIVE_POSTS_CACHE_DIR / f"{identifier}.json"


def _load_pa_posts_cache(identifier: str) -> dict | None:
    path = _pa_posts_cache_path(identifier)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not (isinstance(data, dict) and data.get("posts")):
            return None
        if time.time() - float(data.get("fetched_at") or 0) > PAWCHIVE_POSTS_CACHE_TTL:
            return None
        if data.get("v") != 2:  # v2：帖子带 edited 字段（旧缓存自动失效重拉）
            return None
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _save_pa_posts_cache(identifier: str, data: dict) -> None:
    try:
        PAWCHIVE_POSTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data["fetched_at"] = time.time()
        data["v"] = 2
        _pa_posts_cache_path(identifier).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8",
        )
    except OSError as exc:
        logging.warning("保存 Pawchive 帖子列表缓存失败: %s", exc)


def _pawchive_map_post(post: dict, service: str, user_id: str) -> dict:
    """帖子列表条目 → 子项目卡片数据（含悬浮详情所需信息）。"""
    post_id = str(post.get("id") or "")
    main_file = post.get("file") or {}
    attachments = [a for a in (post.get("attachments") or []) if isinstance(a, dict)]
    file_names = []
    if main_file.get("name") or main_file.get("path"):
        file_names.append(main_file.get("name") or Path(main_file.get("path") or "").name)
    for att in attachments:
        if att.get("path"):
            file_names.append(att.get("name") or Path(att["path"]).name)
    content = (post.get("content") or "").strip()
    return {
        "post_id": post_id,
        "title": post.get("title") or "未命名帖子",
        "published": post.get("published") or "",
        "edited": post.get("edited") or "",
        "content": content[:200],
        "file_count": len(file_names),
        "files": file_names[:20],
        "has_video": any(
            str(n).lower().endswith((".mp4", ".webm", ".mov", ".m4v"))
            for n in file_names
        ),
        "has_archive": any(
            str(n).lower().endswith((".zip", ".rar", ".7z", ".tar", ".gz"))
            for n in file_names
        ),
        "thumbnail": (
            PAWCHIVE_IMG_HOST + "/thumbnail/data" + main_file["path"]
            if main_file.get("path") else ""
        ),
        "post_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}/post/{post_id}",
    }


async def pawchive_artist_posts(url: str) -> None:
    """获取画师全部帖子列表（子项目视图：按发布日期倒序）。"""
    info = _pawchive_parse_url(url)
    if info is None:
        emit({"event": "pa_artist_posts_error", "message": "无法识别的 Pawchive 画师链接"})
        return
    if info.get("kind") != "artist":
        emit({"event": "pa_artist_posts_error", "message": "请粘贴画师主页链接"})
        return

    service = info["service"]
    user_id = info["user_id"]
    identifier = f"pawchive_{service}_{user_id}"

    try:
        # 命中缓存直接返回
        cached = _load_pa_posts_cache(identifier)
        if cached:
            _apply_cached_thumbnails(cached.get("posts") or [])
            emit({
                "event": "pa_artist_posts",
                "url": url,
                "artist": cached.get("artist") or user_id,
                "artist_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}",
                "posts": cached.get("posts") or [],
                "cached": True,
            })
            asyncio.create_task(_cache_thumbnails(cached.get("posts") or []))
            return

        profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
        artist_name = (profile or {}).get("name") or user_id

        # 分页拉取全部帖子（列表 API：每页 50）
        raw_posts: list[dict] = []
        offset = 0
        while True:
            page_data = await asyncio.to_thread(
                _pawchive_fetch_json,
                f"/api/v1/{service}/user/{user_id}/posts",
                {"o": offset},
            )
            if not isinstance(page_data, list) or not page_data:
                break
            raw_posts.extend(page_data)
            if len(page_data) < PAWCHIVE_PAGE_SIZE:
                break
            offset += PAWCHIVE_PAGE_SIZE

        # 列表 API 附件字段可能为空占位：文件数为 0 的帖子拉详情补全
        async def _fill_detail(post: dict) -> dict:
            if not (post.get("file") or {}).get("path") and \
                    not [a for a in (post.get("attachments") or []) if isinstance(a, dict) and a.get("path")]:
                detail = await asyncio.to_thread(
                    _pawchive_fetch_json,
                    f"/api/v1/{service}/user/{user_id}/post/{post.get('id')}",
                )
                if isinstance(detail, dict) and detail.get("id"):
                    return detail
            return post

        semaphore = asyncio.Semaphore(4)

        async def _fill_one(post: dict) -> dict:
            async with semaphore:
                return await _fill_detail(post)

        raw_posts = list(await asyncio.gather(*(_fill_one(p) for p in raw_posts)))

        # 按最后更新时间倒序（画师更新旧帖会顶到最前；无 edited 回退发布日期）
        posts = [_pawchive_map_post(p, service, user_id) for p in raw_posts]
        posts.sort(key=lambda p: p.get("edited") or p.get("published") or "", reverse=True)

        _apply_cached_thumbnails(posts)
        emit({
            "event": "pa_artist_posts",
            "url": url,
            "artist": artist_name,
            "artist_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}",
            "posts": posts,
            "cached": False,
        })
        asyncio.create_task(_cache_thumbnails(posts))
        _save_pa_posts_cache(identifier, {
            "artist": artist_name,
            "posts": posts,
        })
        logging.info("Pawchive 画师帖子列表: %s 共 %d 个帖子", artist_name, len(posts))

    except Exception as exc:
        emit({"event": "pa_artist_posts_error", "message": f"获取帖子列表失败: {exc}"})
        logging.exception("Pawchive 画师帖子列表获取失败")


async def pawchive_download_artist(url: str, options: dict) -> None:
    """右键「下载画师所有内容」：后台解析画师全部帖子的文件并提交一个下载任务。

    与 pawchive_inspect 的画师分支共用抓取逻辑（缓存优先），但不进入前端
    文件列表，直接把全部条目交给下载管理器后台执行。
    """
    info = _pawchive_parse_url(url)
    if info is None:
        emit({"event": "pa_artist_dl_error", "message": "无法识别的 Pawchive 画师链接"})
        return
    if info.get("kind") != "artist":
        emit({"event": "pa_artist_dl_error", "message": "请提供画师主页链接"})
        return

    service = info["service"]
    user_id = info["user_id"]
    identifier = f"pawchive_{service}_{user_id}"

    try:
        # 缓存优先：之前解析过的画师直接复用（右键下载通常发生在浏览过的画师上）
        cached = _load_album_cache(identifier)
        if cached and cached.get("items"):
            artist_name = cached.get("album_name") or user_id
            items = cached.get("items", [])
            logging.info(
                "Pawchive 画师下载（缓存）: %s (%d 个文件)", artist_name, len(items),
            )
        else:
            profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
            artist_name = (profile or {}).get("name") or user_id

            # 分页拉取全部帖子（与 pawchive_inspect 相同）
            posts: list[dict] = []
            offset = 0
            while True:
                page_data = await asyncio.to_thread(
                    _pawchive_fetch_json,
                    f"/api/v1/{service}/user/{user_id}/posts",
                    {"o": offset},
                )
                if not isinstance(page_data, list) or not page_data:
                    break
                posts.extend(page_data)
                if len(page_data) < PAWCHIVE_PAGE_SIZE:
                    break
                offset += PAWCHIVE_PAGE_SIZE

            if not posts:
                emit({"event": "pa_artist_dl_error", "message": "没有找到任何帖子，请确认链接是否正确"})
                return

            total = len(posts)
            emit({
                "event": "pa_artist_dl_progress",
                "current": 0,
                "total": total,
                "artist": artist_name,
            })
            logging.info("Pawchive 画师 '%s' 后台解析: %d 个帖子", artist_name, total)

            semaphore = asyncio.Semaphore(INSPECT_CONCURRENCY)
            results: list[dict] = []
            completed_count = 0
            count_lock = asyncio.Lock()

            async def resolve_one(post: dict) -> None:
                nonlocal completed_count
                async with semaphore:
                    if _pawchive_post_has_attachments(post) or (post.get("file") or {}).get("path"):
                        post_items = _pawchive_post_items(post, artist_name, service, user_id)
                    else:
                        detail = await asyncio.to_thread(
                            _pawchive_fetch_json,
                            f"/api/v1/{service}/user/{user_id}/post/{post.get('id')}",
                        )
                        post_items = (
                            _pawchive_post_items(detail, artist_name, service, user_id)
                            if isinstance(detail, dict) else []
                        )
                    if post_items:
                        results.extend(post_items)
                    async with count_lock:
                        completed_count += 1
                        if completed_count % 10 == 0 or completed_count == total:
                            emit({
                                "event": "pa_artist_dl_progress",
                                "current": completed_count,
                                "total": total,
                                "artist": artist_name,
                            })

            await asyncio.gather(*(resolve_one(p) for p in posts))
            items = results
            _save_album_cache(identifier, {
                "album_name": artist_name,
                "album_id": identifier,
                "is_album": True,
                "items": items,
            })

        if not items:
            emit({"event": "pa_artist_dl_error", "message": "画师没有可下载的文件"})
            return

        # 后台提交下载任务（目录按画师名组织，文件按帖子标题分 子文件夹）
        task_id = download_manager.submit(
            url, items, options, artist_name, identifier,
        )
        download_manager.start(task_id)
        emit({
            "event": "pa_artist_dl_done",
            "artist": artist_name,
            "files": len(items),
            "task_id": task_id,
        })
        logging.info("Pawchive 画师下载任务已提交: %s (%d 个文件)", artist_name, len(items))

    except Exception as exc:
        emit({"event": "pa_artist_dl_error", "message": f"解析画师内容失败: {exc}"})
        logging.exception("Pawchive 画师下载解析失败")


# ============================
# Pawchive 下载目录规则
# ============================
def _render_folder_template(template: str, date: str, title: str, post_id: str = "") -> str:
    """自定义子文件夹模板 → 相对子目录（每站点独立设置，长期持久化）。

    变量：{date}=YYYY-MM、{date_full}=YYYY-MM-DD、{title}=帖子/画廊标题、{id}=帖子ID。
    模板示例："{date}/{title}" → "2026-08/帖子名"；每段自动清洗非法字符。
    """
    if not template or not template.strip():
        return ""
    mapping = {
        "date": (date or "")[:7],
        "date_full": (date or "")[:10],
        "title": title or "",
        "id": post_id or "",
    }
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace("{" + key + "}", value)
    parts = [sanitize_directory_name(seg.strip())[:80] for seg in rendered.split("/")]
    parts = [p for p in parts if p]
    return str(Path(*parts)) if parts else ""


def _pawchive_subfolder(item: dict, options: dict) -> str:
    """Pawchive 专属子文件夹规则（父文件夹为画师名，由相册目录承担）。

    模式 pawchive_subfolder:
      - none:       不建子文件夹
      - date:       按发布月份 YYYY-MM
      - post:       按帖子标题
      - date_post:  "YYYY-MM-帖子标题"（默认，日期并入文件夹名，减少嵌套层级）
    自定义模板 pawchive_folder_template 非空时优先。
    """
    template = (options.get("pawchive_folder_template") or "").strip()
    if template:
        return _render_folder_template(
            template,
            item.get("post_date") or "",
            (item.get("post_title") or "").strip(),
            item.get("post_id") or "",
        )
    mode = options.get("pawchive_subfolder", "date_post")
    parts: list[str] = []
    date = (item.get("post_date") or "")[:7]  # YYYY-MM
    title = sanitize_directory_name((item.get("post_title") or "").strip())[:60]

    if mode == "date" and date:
        parts.append(date)
    elif mode == "post" and title:
        parts.append(title)
    elif mode == "date_post":
        if date and title:
            parts.append(f"{date}-{title}")
        elif date:
            parts.append(date)
        elif title:
            parts.append(title)
    return str(Path(*parts)) if parts else ""


def _pawchive_build_file_dir(album_path: str, item: dict, options: dict) -> str:
    """构建 Pawchive 文件的下载子目录（画师名已作为相册目录）。"""
    sub = _pawchive_subfolder(item, options)
    if not sub:
        return album_path
    directory = str(Path(album_path) / sub)
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
    except OSError:
        return album_path
    return directory


def _pawchive_album_name(url: str, items: list[dict], fallback: str = "Pawchive") -> str:
    """从 URL 或下载条目推断画师名（作为下载目录名）。"""
    info = _pawchive_parse_url(url)
    if info:
        profile = _pawchive_fetch_profile(info["service"], info["user_id"])
        if profile and profile.get("name"):
            return str(profile["name"])
    for item in items:
        if item.get("artist"):
            return str(item["artist"])
    return fallback
