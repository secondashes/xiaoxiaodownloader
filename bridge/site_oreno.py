# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Oreno3D / EroMMDTube。

由 gui_bridge.py 按物理顺序拆出（原行区间 10458-11459），
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
# Oreno3D 站点支持 (oreno3d.com，MMD 视频聚合索引站，纯资源站类型)
# ============================
# - 服务端渲染 HTML（Laravel），无需登录，裸请求可访问全部内容
# - 列表: GET /（默认人気排序）?sort=hot|favorites|latest|popularity&page=N
# - 搜索: GET /search?keyword=关键词（可与 sort 组合）
# - 标签: GET /tags/{id}；作者: GET /authors/{id}；标签索引: GET /tags
# - 详情: GET /movies/{id} → "この動画を見る" 按钮 → iwara.tv 视频链接
#   下载/播放复用 Iwara 逻辑（api.iwara.tv 解析最高画质）
# - 视频本体在 iwara，站内仅缩略图（/storage/thumbnails_small/）
ORENO_BASE = "https://oreno3d.com"
EROMMD_BASE = "https://erommdtube.com"
# 四排序（与站点页面上 急上昇/高評価/新着/人気 一一对应）
ORENO_SORTS = {"hot": "急上昇", "favorites": "高評価", "latest": "新着", "popularity": "人気"}

# 两站同库同路由（oreno3d / erommdtube），仅 CSS 选择器不同：一套解析逻辑 + 选择器映射
ORENO_SITES: dict[str, dict] = {
    "oreno3d": {
        "base": ORENO_BASE,
        "label": "Oreno3D",
        "sel_card": "a.box.pop_separate",
        "sel_title": "h2.box-h2",
        "sel_img": "img.main-thumbnail",
        "sel_stats": ".figure-text-in",
        "sel_texts": ".box-text-in",
        "sel_iwara_btn": "a.video-watch-btn2",
        "sel_iwara_fig": None,  # oreno3d 用按钮即可
        "sel_h1_detail": "h1.video-h1",
        "sel_img_detail": "img.video-img",
        "sel_author_link": "section.video-section-tag a[href*='/authors/']",
        # 本视频元数据：标签区(ul.video-tag) + 面包屑(原作/角色)
        "sel_tag_links": "ul.video-tag a[href], ol.breadcrumb a[href]",
        "sel_tag_text": None,
        "sel_stat_text": "div.video-text",
        "sel_comment": "blockquote.video-information-comment",
        "sel_related": "section.g-main-video-related",
        "sel_group_li": "li.group-list-li",
        "sel_group_link": "a.group-list-li-a",
        "sel_group_chara": "div.group-list-li-a-chara",
        "sel_group_number": "div.group-list-li-a-number",
        "sel_pagination": "a.page-link",
    },
    "erommdtube": {
        "base": EROMMD_BASE,
        "label": "EroMMDTube",
        "sel_card": "a.main__list-link",
        "sel_title": "h2.main__list-title",
        "sel_img": "img.main__list-thumbnail",
        "sel_stats": None,  # 统计在 description 文本里
        "sel_texts": None,
        "sel_iwara_btn": None,
        "sel_iwara_fig": "figure.show__figure > a[href*='iwara.tv/video/']",
        "sel_h1_detail": "h1.show__h1",
        "sel_img_detail": "img.show__header-img",
        "sel_author_link": "div.show__authors-link a[href*='/authors/']",
        # 本视频元数据：标签区(含原作/角色/标签混排) + 面包屑
        "sel_tag_links": "ul.show__tag-ul a.show__tag-link, ol.main__breadcrumb a[href]",
        "sel_tag_text": None,
        "sel_stat_text": "ul.show__count li",
        "sel_comment": "blockquote.show__comment-blockquote",
        "sel_related": "section.show__related",
        "sel_group_li": "li.aside__li",
        "sel_group_link": "a.aside__li-link",
        "sel_group_chara": "div.aside__li-chara",
        "sel_group_number": "div.aside__ranking",
        "sel_pagination": "a.main__pagination-link",
    },
}

_oreno_proxy = ""
_erommd_proxy = ""

_oreno_session = requests.Session()
_erommd_session = requests.Session()
for _s in (_oreno_session, _erommd_session):
    _s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })


def _oreno_conf(site_key: str) -> dict:
    return ORENO_SITES.get(site_key) or ORENO_SITES["oreno3d"]


def _oreno_session_of(site_key: str) -> requests.Session:
    return _erommd_session if site_key == "erommdtube" else _oreno_session


def _oreno_site_proxy(site_key: str) -> str:
    return _erommd_proxy if site_key == "erommdtube" else _oreno_proxy


def oreno_set_proxy(proxy: str, site_key: str = "oreno3d") -> None:
    """设置 Oreno3D / EroMMDTube 代理（空 = 直连）。"""
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    global _oreno_proxy, _erommd_proxy
    if site_key == "erommdtube":
        _erommd_proxy = proxy
    else:
        _oreno_proxy = proxy
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    _oreno_session_of(site_key).proxies = proxies
    emit({"event": "oreno_proxy_set", "proxy": proxy, "site_key": site_key})


def _oreno_apply_saved_cookies(site_key: str) -> None:
    """把加密凭据库保存的登录 cookie 应用到站点请求会话（浏览/搜索自动带会话）。"""
    cookie_str = _generic_cookie_str(site_key)
    if not cookie_str:
        return
    sess = _oreno_session_of(site_key)
    try:
        sess.cookies.clear()
    except Exception:
        pass
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        try:
            sess.cookies.set(name.strip(), value.strip())
        except Exception:
            continue


def _oreno_session_valid(site_key: str) -> bool:
    """O3D / E站 登录会话验证：把保存的 cookie 应用到站点会话并请求首页。

    HTTP 200 = 会话有效（Cloudflare 验证已过 / cookie 未过期）；
    网络异常（超时/代理不可用）返回 True 降级处理，避免误报未登录。
    """
    try:
        if not _generic_cookie_str(site_key):
            return False
        _oreno_apply_saved_cookies(site_key)
        _oreno_throttle()
        resp = _oreno_session_of(site_key).get(f"{_oreno_conf(site_key)['base']}/", timeout=12)
        return resp.status_code == 200
    except Exception:
        # 网络问题无法验证：降级为"有效"（cookie 存在即认为已登录）
        logging.exception("%s 登录会话网络验证失败（降级为 cookie 存在判定）", site_key)
        return True


def oreno_save_cred(site_key: str, email: str, password: str) -> None:
    """保存 O3D / E站 账号密码（加密存储，供内置浏览器登录时自动预填）。"""
    site_key = "erommdtube" if site_key == "erommdtube" else "oreno3d"
    label = _oreno_conf(site_key)["label"]
    email = (email or "").strip()
    if not email:
        emit({"event": "site_login_result", "site": site_key, "logged_in": False,
              "message": f"请输入 {label} 账号（邮箱/用户名）"})
        return
    cred = _secure_store_read_cred(site_key)
    cred["email"] = email
    if password:
        cred["password"] = password
    cred["cred_saved_at"] = time.time()
    _secure_store_write_cred(site_key, cred)
    cookies = cred.get("cookies") or {}
    logged_in = bool(cookies) and _oreno_session_valid(site_key)
    emit({
        "event": "site_login_result",
        "site": site_key,
        "logged_in": logged_in,
        "username": email,
        "cookie_count": len(cookies),
        "message": f"{label} 账号密码已保存" + ("（会话 cookie 有效）" if logged_in else "（尚未登录，可打开内置浏览器登录）"),
    })
    logging.info("%s 凭据已保存: %s", label, email)
    _emit_login_info()


_oreno_throttle = _make_throttle(0.5)


def _oreno_soup(path: str, params: dict | None = None, site_key: str = "oreno3d") -> BeautifulSoup:
    conf = _oreno_conf(site_key)
    _oreno_throttle()
    resp = _oreno_session_of(site_key).get(f"{conf['base']}{path}", params=params, timeout=25)
    if resp.status_code != 200:
        raise PermissionError(f"{conf['label']} 返回 HTTP {resp.status_code}")
    return BeautifulSoup(resp.text, "html.parser")


def _oreno_link_text(a) -> str:
    """链接纯文本（剔除 <i class="material-icons">face/local_offer 等图标文字）。"""
    parts = []
    for s in a.find_all(string=True):
        if s.parent and s.parent.name == "i":
            continue
        parts.append(str(s))
    return "".join(parts).strip()


def _oreno_parse_card(card: BeautifulSoup, site_key: str = "oreno3d") -> dict | None:
    """列表卡片 → 前端视频卡片（oreno3d: a.box.pop_separate / erommdtube: a.main__list-link）。"""
    conf = _oreno_conf(site_key)
    m = re.search(r"/movies/(\d+)", card.get("href") or "")
    if not m:
        return None
    mid = m.group(1)
    h2 = card.select_one(conf["sel_title"])
    img = card.select_one(conf["sel_img"])
    views = ""
    likes = ""
    author = ""
    tags: list[str] = []
    if site_key == "erommdtube":
        # 统计与作者混在 description 文本：person 作者 / play_arrow 再生 / favorite 数
        desc = card.select_one("div.main__list-description")
        text = desc.get_text("|", strip=True) if desc else ""
        parts = [p.strip() for p in text.split("|") if p.strip()]
        nums = [p for p in parts if re.fullmatch(r"[\d.,]+[km]?", p, re.I)]
        author = parts[0] if parts else ""
        if len(nums) >= 1:
            views = nums[0]
        if len(nums) >= 2:
            likes = nums[1]
        # 标签行（sell icon 后的文本）
        tag_el = card.select_one("div.main__list-tag")
        if tag_el:
            tags = tag_el.get_text(" ", strip=True).split()
    else:
        # 播放数/点赞数（figure-text-in，顺序固定：先播放后点赞）
        stats = [d.get_text(strip=True) for d in card.select(conf["sel_stats"])]
        views = stats[0] if len(stats) > 0 else ""
        likes = stats[1] if len(stats) > 1 else ""
        texts = card.select(conf["sel_texts"])
        author = texts[0].get_text(strip=True) if len(texts) > 0 else ""
        tags = (texts[1].get_text(strip=True) if len(texts) > 1 else "").split()
    thumb = (img.get("src") or "") if img else ""
    if thumb.startswith("/"):
        thumb = _oreno_conf(site_key)["base"] + thumb
    return {
        "album_name": (h2.get_text(strip=True) if h2 else "") or f"{site_key}_{mid}",
        "album_url": f"{_oreno_conf(site_key)['base']}/movies/{mid}",
        "thumbnail": thumb,
        "files": 1,
        "site": "oreno" if site_key == "oreno3d" else "erommd",
        "site_key": site_key,
        "video_id": mid,
        "author": author,
        "views": views,
        "likes": likes,
        "tags": tags,
    }


def _oreno_parse_cards(soup: BeautifulSoup, site_key: str = "oreno3d") -> list[dict]:
    items: list[dict] = []
    for card in soup.select(_oreno_conf(site_key)["sel_card"]):
        item = _oreno_parse_card(card, site_key)
        if item:
            items.append(item)
    return items


def _oreno_has_next(soup: BeautifulSoup, site_key: str = "oreno3d") -> bool:
    if soup.find("a", rel="next"):
        return True
    # erommdtube 分页无 rel=next：看 pagination 里是否有比当前页大的页码/省略号
    links = soup.select(_oreno_conf(site_key)["sel_pagination"])
    for a in links:
        href = a.get("href") or ""
        m = re.search(r"[?&]page=(\d+)", href)
        if m and a.get_text(strip=True) in (">", "»", "次へ", "次"):
            return True
    return False


async def oreno_home(page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """Oreno3D / EroMMDTube 主页/列表（默认人気排序，四排序可切换，Laravel 分页）。"""
    emit({"event": "oreno_home_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, "/", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_home", "items": items, "page": page,
              "has_more": _oreno_has_next(soup, site_key), "sort": sort,
              "sorts": ORENO_SORTS, "site_key": site_key})
        logging.info("%s 主页第 %d 页 (sort=%s): %d 个视频",
                     _oreno_conf(site_key)["label"], page, sort, len(items))
    except Exception as exc:
        emit({"event": "oreno_home", "items": [], "page": max(1, page), "has_more": False,
              "sort": sort, "site_key": site_key,
              "error": f"获取列表失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 主页获取失败", _oreno_conf(site_key)["label"])
    finally:
        emit({"event": "oreno_home_loading", "loading": False, "site_key": site_key})


async def oreno_search(query: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """Oreno3D / EroMMDTube 关键词搜索（/search?keyword=）。"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        params: dict = {"keyword": query, "page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, "/search", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        site_tag = "oreno" if site_key == "oreno3d" else "erommd"
        emit({"event": "search_result", "query": query, "site": site_tag,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key),
              "sort": sort, "label": query})
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("%s 搜索 '%s': %d 个结果", _oreno_conf(site_key)["label"], query, len(items))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"{_oreno_conf(site_key)['label']} 搜索失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 搜索失败", _oreno_conf(site_key)["label"])
    finally:
        emit({"event": "search_loading", "loading": False})


async def oreno_tag(tag_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """标签页视频列表。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/tags/{tag_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        tag_name = ""
        h1 = soup.find("h1")
        if h1:
            tag_name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "tag", "id": tag_id, "name": tag_name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "tag", "id": tag_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取标签视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_author(author_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """作者页视频列表。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/authors/{author_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        author_name = ""
        h1 = soup.find("h1")
        if h1:
            author_name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "author", "id": author_id, "name": author_name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "author", "id": author_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取作者视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_character(character_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """角色页视频列表（/characters/{id}）。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/characters/{character_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        name = ""
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "character", "id": character_id, "name": name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "character", "id": character_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取角色视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_origin(origin_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """原作页视频列表（/origins/{id}）。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/origins/{origin_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        name = ""
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "origin", "id": origin_id, "name": name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "origin", "id": origin_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取原作视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_characters(site_key: str = "oreno3d") -> None:
    """角色列表（单页全量：人気排序 + 五十音分组均静态内嵌）。"""
    emit({"event": "oreno_chars_loading", "loading": True, "site_key": site_key})
    try:
        soup = await asyncio.to_thread(_oreno_soup, "/characters", None, site_key)
        conf = _oreno_conf(site_key)
        popular: list[dict] = []
        kana_groups: dict[str, list[dict]] = {}
        seen: set[str] = set()
        # 人気区
        for li in soup.select(f"div.sorted-popularity {conf['sel_group_li']}"):
            a = li.select_one(conf["sel_group_link"])
            if not a:
                continue
            m = re.search(r"/characters/(\d+)", a.get("href") or "")
            if not m:
                continue
            cid = m.group(1)
            if cid in seen:
                continue
            seen.add(cid)
            chara_el = a.select_one(conf["sel_group_chara"])
            name = ""
            origin = ""
            if chara_el:
                name = chara_el.get_text(strip=True)
                span = chara_el.find("span")
                if span:
                    origin = span.get_text(strip=True).strip("()")
                    name = chara_el.get_text(strip=True).replace(span.get_text(strip=True), "").strip()
            nums = [d.get_text(strip=True) for d in a.select(conf["sel_group_number"])]
            popular.append({
                "id": cid, "name": name, "origin": origin,
                "rank": nums[0] if nums else "",
                "count": nums[-1] if len(nums) > 1 else "",
            })
        # 五十音区（oreno3d: div.sorted-kana > ul#sort-{行}；erommdtube 同结构）
        for ul in soup.select("div.sorted-kana ul[id]"):
            row = re.sub(r"^sort-", "", ul.get("id") or "")
            for li in ul.select(conf["sel_group_li"]):
                a = li.select_one(conf["sel_group_link"])
                if not a:
                    continue
                m = re.search(r"/characters/(\d+)", a.get("href") or "")
                if not m:
                    continue
                cid = m.group(1)
                chara_el = a.select_one(conf["sel_group_chara"])
                name = ""
                origin = ""
                if chara_el:
                    name = chara_el.get_text(strip=True)
                    span = chara_el.find("span")
                    if span:
                        origin = span.get_text(strip=True).strip("()")
                        name = chara_el.get_text(strip=True).replace(span.get_text(strip=True), "").strip()
                nums = [d.get_text(strip=True) for d in a.select(conf["sel_group_number"])]
                kana_groups.setdefault(row or "?", []).append({
                    "id": cid, "name": name, "origin": origin,
                    "count": nums[-1] if nums else "",
                })
        emit({"event": "oreno_characters", "popular": popular[:300],
              "kana_groups": kana_groups, "site_key": site_key})
        logging.info("%s 角色列表: 人気 %d 个 / %d 个五十音组",
                     conf["label"], len(popular), len(kana_groups))
    except Exception as exc:
        emit({"event": "oreno_characters", "popular": [], "kana_groups": {},
              "site_key": site_key, "error": f"获取角色列表失败: {exc}"})
        logging.exception("角色列表获取失败")
    finally:
        emit({"event": "oreno_chars_loading", "loading": False, "site_key": site_key})


async def oreno_authors_index(page: int = 1, site_key: str = "oreno3d") -> None:
    """人気作者列表（/authors 分页，oreno3d 共约 1919 页）。"""
    emit({"event": "oreno_authors_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        soup = await asyncio.to_thread(_oreno_soup, "/authors", {"page": page}, site_key)
        conf = _oreno_conf(site_key)
        authors: list[dict] = []
        seen: set[str] = set()
        for li in soup.select(conf["sel_group_li"]):
            a = li.select_one(conf["sel_group_link"])
            if not a:
                continue
            m = re.search(r"/authors/(\d+)", a.get("href") or "")
            if not m:
                continue
            aid = m.group(1)
            if aid in seen:
                continue
            seen.add(aid)
            chara_el = a.select_one(conf["sel_group_chara"])
            name = chara_el.get_text(strip=True) if chara_el else a.get_text(strip=True)[:30]
            nums = [d.get_text(strip=True) for d in a.select(conf["sel_group_number"])]
            authors.append({"id": aid, "name": name, "rank": nums[0] if nums else ""})
        # 该页内嵌的作者热门视频（可顺带返回给前端直接看）
        items = _oreno_parse_cards(soup, site_key)
        emit({"event": "oreno_authors", "authors": authors, "items": items, "page": page,
              "has_more": _oreno_has_next(soup, site_key), "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_authors", "authors": [], "items": [], "page": page,
              "has_more": False, "site_key": site_key, "error": f"获取作者列表失败: {exc}"})
    finally:
        emit({"event": "oreno_authors_loading", "loading": False, "site_key": site_key})


def _oreno_fav_path() -> Path:
    return Path("cache/oreno_favorites.json")


def _oreno_fav_load() -> dict:
    """本地收藏（两站通用，按 site_key 分组）：{site_key: {movie_id: 卡片dict}}。"""
    try:
        data = json.loads(_oreno_fav_path().read_text("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _oreno_fav_save(data: dict) -> None:
    _oreno_fav_path().parent.mkdir(parents=True, exist_ok=True)
    _oreno_fav_path().write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


async def oreno_toggle_favorite(movie_id: str, card: dict, site_key: str = "oreno3d") -> None:
    """本地收藏/取消收藏（站点无服务端账号体系，收藏保存在本地）。"""
    try:
        data = _oreno_fav_load()
        group = data.setdefault(site_key, {})
        movie_id = str(movie_id)
        if movie_id in group:
            group.pop(movie_id)
            saved = False
        else:
            card = dict(card or {})
            card["video_id"] = movie_id
            card["site_key"] = site_key
            card["saved_at"] = int(time.time())
            group[movie_id] = card
            saved = True
        _oreno_fav_save(data)
        emit({"event": "oreno_fav_result", "video_id": movie_id, "saved": saved,
              "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_fav_result", "video_id": str(movie_id), "saved": False,
              "site_key": site_key, "error": f"收藏操作失败: {exc}"})


async def oreno_favorites(site_key: str = "oreno3d") -> None:
    """本地收藏列表。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        group = (_oreno_fav_load().get(site_key)) or {}
        items = sorted(group.values(), key=lambda x: -(x.get("saved_at") or 0))
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "favorites", "id": "", "name": "我的收藏",
              "site_key": site_key, "items": items, "page": 1, "has_more": False, "sort": ""})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "favorites", "id": "", "site_key": site_key,
              "items": [], "page": 1, "has_more": False, "error": f"获取收藏失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_tags_index(site_key: str = "oreno3d") -> None:
    """标签列表 + 热门分类组（tag-groups，名称含作品总数）。"""
    emit({"event": "oreno_tags_loading", "loading": True, "site_key": site_key})
    try:
        soup = await asyncio.to_thread(_oreno_soup, "/tags", None, site_key)
        tags: list[dict] = []
        for a in soup.select("a[href^='/tags/']"):
            m = re.search(r"/tags/(\d+)", a.get("href") or "")
            if not m:
                continue
            name = _oreno_link_text(a)
            if name:
                tags.append({"id": m.group(1), "name": name})
        # 去重
        seen = set()
        unique = []
        for t in tags:
            if t["id"] not in seen:
                seen.add(t["id"])
                unique.append(t)
        # 热门分类组：文本形如 "キャラクター設定 5タグ 171477 作品" → 名称 + 作品总数
        groups: list[dict] = []
        for a in soup.select("a[href*='/tag-groups/']"):
            m = re.search(r"/tag-groups/(\d+)", a.get("href") or "")
            if not m:
                continue
            text = " ".join(_oreno_link_text(a).split())
            if not text:
                continue
            cnt = ""
            pm = re.search(r"([\d.,]+)\s*作品", text)
            if pm:
                cnt = pm.group(1)
            # 名称 = 首个 "Nタグ/N作品" 数字段之前的文本
            nm = re.search(r"\s*[\d.,]+\s*(?:タグ|本|作品)", text)
            name = (text[:nm.start()].strip() if nm else "").strip() or text
            groups.append({"id": m.group(1), "name": name, "count": cnt})
        emit({"event": "oreno_tags", "tags": unique[:500], "groups": groups,
              "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_tags", "tags": [], "groups": [], "site_key": site_key,
              "error": f"获取标签列表失败: {exc}"})
    finally:
        emit({"event": "oreno_tags_loading", "loading": False, "site_key": site_key})


async def oreno_tag_group(group_id: str, site_key: str = "oreno3d") -> None:
    """热门分类组内的标签列表（/tag-groups/{id}）。"""
    emit({"event": "oreno_tags_loading", "loading": True, "site_key": site_key})
    try:
        soup = await asyncio.to_thread(
            _oreno_soup, f"/tag-groups/{group_id}", None, site_key)
        h = soup.select_one("h1, h2")
        title = _oreno_link_text(h) if h else f"分类组 {group_id}"
        tags: list[dict] = []
        seen = set()
        for a in soup.select("a[href^='/tags/']"):
            m = re.search(r"/tags/(\d+)", a.get("href") or "")
            if not m or m.group(1) in seen:
                continue
            name = _oreno_link_text(a)
            if name:
                seen.add(m.group(1))
                tags.append({"id": m.group(1), "name": name})
        emit({"event": "oreno_tags", "tags": tags, "groups": [],
              "group_title": title, "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_tags", "tags": [], "groups": [], "site_key": site_key,
              "error": f"获取分类组失败: {exc}"})
    finally:
        emit({"event": "oreno_tags_loading", "loading": False, "site_key": site_key})


def _oreno_extract_iwara_id(soup: BeautifulSoup, site_key: str = "oreno3d") -> str:
    """详情页提取 iwara 视频 ID（oreno3d: a.video-watch-btn2 / erommdtube: figure.show__figure>a）。"""
    conf = _oreno_conf(site_key)
    hrefs: list[str] = []
    btn = soup.select_one(conf["sel_iwara_btn"]) if conf["sel_iwara_btn"] else None
    if btn:
        hrefs.append(btn.get("href") or "")
    if conf["sel_iwara_fig"]:
        fig = soup.select_one(conf["sel_iwara_fig"])
        if fig:
            hrefs.append(fig.get("href") or "")
    for href in hrefs:
        m = re.search(r"iwara\.tv/video/([A-Za-z0-9]+)", href)
        if m:
            return m.group(1)
    m = re.search(r"https?://www\.iwara\.tv/video/([A-Za-z0-9]+)", soup.get_text() or "")
    return m.group(1) if m else ""


async def oreno_detail(movie_id: str, site_key: str = "oreno3d") -> None:
    """视频详情：标题/作者/原作/角色/标签/统计/作者描述(含网盘链接)/相关推荐 + iwara 源。"""
    emit({"event": "oreno_detail_loading", "loading": True, "site_key": site_key})
    try:
        conf = _oreno_conf(site_key)
        soup = await asyncio.to_thread(_oreno_soup, f"/movies/{movie_id}", None, site_key)
        h1 = soup.select_one(conf["sel_h1_detail"])
        img = soup.select_one(conf["sel_img_detail"])
        thumb = (img.get("src") or "") if img else ""
        if thumb.startswith("/"):
            thumb = conf["base"] + thumb
        # 作者（链接内 <i class="material-icons">face</i><div>hadoru</div> → 取 div 或去图标文本）
        author = ""
        author_id = ""
        for a in soup.select(conf["sel_author_link"]):
            div = a.select_one("div.video-center, div.c-txt, span")
            author = (div.get_text(strip=True) if div else _oreno_link_text(a)) or ""
            author = _oreno_link_text(a) if not author else author
            m = re.search(r"/authors/(\d+)", a.get("href") or "")
            if m:
                author_id = m.group(1)
            break
        # 标签 / 原作 / 角色（按 href 前缀区分；名称去掉 material icon 文本；按 id 去重）
        tags: list[dict] = []
        origins: list[dict] = []
        characters: list[dict] = []
        _seen_meta: set[str] = set()
        for a in soup.select(conf["sel_tag_links"]):
            name_el = a.select_one(conf["sel_tag_text"]) if conf["sel_tag_text"] else None
            name = (name_el.get_text(strip=True) if name_el else "") or _oreno_link_text(a)
            href = a.get("href") or ""
            tm = re.search(r"/tags/(\d+)", href)
            om = re.search(r"/origins/(\d+)", href)
            cm = re.search(r"/characters/(\d+)", href)
            mid = (tm or om or cm)
            if not mid or not name:
                continue
            key = f"{mid.re.pattern}|{mid.group(1)}"
            if key in _seen_meta:
                continue
            _seen_meta.add(key)
            if tm:
                tags.append({"id": tm.group(1), "name": name})
            elif om:
                origins.append({"id": om.group(1), "name": name})
            elif cm:
                characters.append({"id": cm.group(1), "name": name})
        # 统计（日期 / 时长 / 观看数 / 点赞数）
        date = ""
        views = ""
        likes = ""
        text_el = soup.select_one(conf["sel_stat_text"])
        if text_el:
            text = text_el.get_text(" ", strip=True)
            dm = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
            if dm:
                date = dm.group(1).replace("/", "-")
        stat_texts = [d.get_text(" ", strip=True) for d in soup.select("div.video-text, div.video-text-in, ul.show__count li")]
        # erommdtube: "投稿日：2018/11/19" / "151032 再生" / "1300 お気に入り"
        for t in stat_texts:
            if not date:
                dm = re.search(r"(?:投稿日|投稿)\s*[：:]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", t)
                if dm:
                    date = dm.group(1).replace("/", "-")
            vm = re.search(r"(?:再生|再生数|閲覧)\s*[：:]?\s*([\d.,]+[km]?)", t) or \
                re.search(r"([\d.,]+[km]?)\s*(?:再生|再生数|閲覧)", t)
            if vm:
                views = vm.group(1)
            lm = re.search(r"(?:お気に入り|ファボ|いいね)\s*[：:]?\s*([\d.,]+[km]?)", t) or \
                re.search(r"([\d.,]+[km]?)\s*(?:お気に入り|ファボ|いいね)", t)
            if lm:
                likes = lm.group(1)
        # oreno3d: video-text 为纯数字序列（日期/时长/再生数/评论标签/收藏数）
        if not views or not likes:
            nums = [t for t in stat_texts if re.fullmatch(r"[\d.,]+[km]?", t)]
            if len(nums) >= 1 and not views:
                views = nums[0]
            if len(nums) >= 2 and not likes:
                likes = nums[1]
        # 作者描述（常含 MEGA/Patreon 等网盘链接）
        comment = ""
        megas: list[str] = []
        bq = soup.select_one(conf["sel_comment"])
        if bq:
            comment = bq.get_text("\n", strip=True)
            for href in re.findall(r"https?://[^\s\"'<>]+", bq.decode() if hasattr(bq, "decode") else str(bq)):
                if any(k in href.lower() for k in ("mega.nz", "mega.co", "patreon", "drive.google", "pixeldrain", "kemono")):
                    megas.append(href)
            if not megas:
                for href in re.findall(r"https?://[^\s\"'<>]+", comment):
                    if any(k in href.lower() for k in ("mega.nz", "mega.co", "patreon", "drive.google", "pixeldrain", "kemono")):
                        megas.append(href)
        iwara_id = _oreno_extract_iwara_id(soup, site_key)
        video = {
            "album_name": (h1.get_text(strip=True) if h1 else "") or f"{site_key}_{movie_id}",
            "album_url": f"{conf['base']}/movies/{movie_id}",
            "video_id": movie_id,
            "site": "oreno" if site_key == "oreno3d" else "erommd",
            "site_key": site_key,
            "thumbnail": thumb,
            "author": author,
            "author_id": author_id,
            "tags": tags,
            "origins": origins,
            "characters": characters,
            "post_date": date,
            "views": views,
            "likes": likes,
            "comment": comment,
            "mega_links": megas,
            "iwara_id": iwara_id,
            "iwara_url": f"https://www.iwara.tv/video/{iwara_id}" if iwara_id else "",
            "related": [],
        }
        # 相关视频推荐（同列表卡片结构）
        related_sec = soup.select_one(conf["sel_related"])
        if related_sec:
            video["related"] = _oreno_parse_cards(related_sec, site_key)[:12]
        # 通过 Iwara API 解析播放直链（最高画质）
        iwara_info: dict = {}
        if iwara_id:
            try:
                data = await asyncio.to_thread(_iwara_api_get, f"/video/{iwara_id}", None)
                fu = data.get("fileUrl") or ""
                if fu:
                    play_url, mime = await asyncio.to_thread(_iwara_resolve_best_url, fu)
                    if play_url.startswith("//"):
                        play_url = "https:" + play_url
                    iwara_info = {
                        "title": data.get("title") or "",
                        "views": data.get("numViews"),
                        "likes": data.get("numLikes"),
                        "duration": (data.get("file") or {}).get("duration"),
                        "video_url": play_url,
                    }
            except Exception as exc:
                logging.warning("%s iwara 源解析失败: %s", conf["label"], exc)
        video.update(iwara_info)
        # 收藏状态（本地）
        video["saved"] = str(movie_id) in ((_oreno_fav_load().get(site_key)) or {})
        _apply_cached_thumbnails([video])
        asyncio.create_task(_cache_thumbnails([video]))
        emit({"event": "oreno_video_detail", "video": video, "site_key": site_key})
        logging.info("%s 视频详情: %s (iwara=%s)", conf["label"], movie_id, iwara_id)
    except Exception as exc:
        emit({"event": "oreno_video_detail", "video": None, "site_key": site_key,
              "error": f"获取视频详情失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 视频详情获取失败", _oreno_conf(site_key)["label"])
    finally:
        emit({"event": "oreno_detail_loading", "loading": False, "site_key": site_key})


async def oreno_batch_download(video_ids: list, options: dict, site_key: str = "oreno3d") -> None:
    """批量下载视频：解析 iwara ID 后复用 Iwara 下载逻辑（最高画质）。"""
    conf = _oreno_conf(site_key)
    video_ids = [str(v).strip() for v in (video_ids or []) if str(v).strip()]
    if not video_ids:
        emit({"event": "oreno_batch_done", "done": 0, "total": 0, "failed": [],
              "site_key": site_key, "message": "请先勾选要下载的视频"})
        return
    total = len(video_ids)
    failed: list[str] = []
    iwara_ids: list[str] = []
    try:
        for i, mid in enumerate(video_ids):
            try:
                soup = await asyncio.to_thread(_oreno_soup, f"/movies/{mid}", None, site_key)
                iwara_id = _oreno_extract_iwara_id(soup, site_key)
                if iwara_id:
                    iwara_ids.append(iwara_id)
                else:
                    failed.append(f"{mid}（未找到 iwara 源）")
            except Exception as exc:
                failed.append(f"{mid}（{exc}）")
            emit({"event": "oreno_batch_progress", "done": i + 1, "total": total,
                  "site_key": site_key, "message": f"解析进度 {i + 1}/{total}"})
        items: list[dict] = []
        if iwara_ids:
            items = await _iwara_build_items(iwara_ids)
        if items:
            task_id = download_manager.submit(
                f"{conf['base']}/", items, options, f"{conf['label']} 批量下载", "oreno_batch",
            )
            download_manager.start(task_id)
        if not items:
            summary = f"全部 {total} 个视频解析失败（源已失效或下架），未创建下载任务"
        else:
            summary = f"批量下载已提交：{len(items)}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed[:4])}{'…' if len(failed) > 4 else ''}"
        emit({"event": "oreno_batch_done", "done": len(items), "total": total,
              "site_key": site_key, "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "oreno_batch_done", "done": 0, "total": total, "site_key": site_key,
              "failed": failed, "message": f"批量下载中断: {exc}"})


def is_hanime_url(url: str) -> bool:
    """判断是否为 Hanime1 链接（视频页 watch?v=）。"""
    return bool(re.search(r"hanime1\.me/watch\?v=\w+", url, re.I))


def is_oreno_url(url: str) -> str | None:
    """判断是否为 Oreno3D / EroMMDTube 链接（/movies/{id}），返回 site_key 或 None。"""
    if re.search(r"oreno3d\.com/movies/\d+", url, re.I):
        return "oreno3d"
    if re.search(r"erommdtube\.com/movies/\d+", url, re.I):
        return "erommdtube"
    return None


def is_asmr_url(url: str) -> bool:
    """判断是否为 ASMR 站链接（asmr-100.com / asmr.one 作品页 /work/{id}）。"""
    return bool(re.search(r"asmr-100\.com/work/\d+|asmr\.one/work/\d+", url, re.I))


async def hanime_inspect(url: str, options: dict) -> None:
    """解析 Hanime1 视频页 → 文件列表（下载时重新解析最高画质直链）。"""
    m = re.search(r"watch\?v=(\w+)", url)
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 Hanime1 链接（支持 /watch?v={id}）"})
        return
    vid = m.group(1)
    try:
        soup = await asyncio.to_thread(_hanime_soup, "/watch", {"v": vid})
        detail = _hanime_parse_detail(soup, vid)
        if not detail["sources"]:
            emit({"event": "inspect_error", "message": "视频没有可用的播放源"})
            return
        title = sanitize_directory_name((detail["title"] or f"hanime_{vid}").strip())
        items = [{
            "filename": f"{title}.mp4",
            "size": None,
            "item_page": f"{HANIME_BASE}/watch?v={vid}",
            "status": "ok",
            "thumbnail": detail.get("thumbnail") or "",
            "media_url": _hanime_best_source(detail["sources"]).get("url") or "",
            "site": "hanime",
            "video_id": vid,
            "post_title": detail["title"] or title,
            "post_date": detail.get("post_date") or "",
            "artist": detail.get("uploader") or "",
        }]
        album_id = f"hanime_{vid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": detail["title"] or f"hanime_{vid}",
            "album_id": album_id,
            "is_album": False,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("Hanime1 解析完成: %s", vid)
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"Hanime1 解析失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 解析过程出错")


async def oreno_inspect(url: str, options: dict) -> None:
    """解析 Oreno3D / EroMMDTube 视频页 → iwara 源文件列表（复用 Iwara 下载逻辑）。"""
    site_key = is_oreno_url(url) or "oreno3d"
    conf = _oreno_conf(site_key)
    m = re.search(r"/movies/(\d+)", url)
    if not m:
        emit({"event": "inspect_error", "message": f"无法识别的 {conf['label']} 链接（支持 /movies/{{id}}）"})
        return
    mid = m.group(1)
    try:
        soup = await asyncio.to_thread(_oreno_soup, f"/movies/{mid}", None, site_key)
        iwara_id = _oreno_extract_iwara_id(soup, site_key)
        if not iwara_id:
            emit({"event": "inspect_error", "message": "该视频没有找到 iwara 源，无法下载"})
            return
        items = await _iwara_build_items([iwara_id])
        if not items:
            emit({"event": "inspect_error", "message": "iwara 源解析失败（视频可能已删除或需登录）"})
            return
        h1 = soup.select_one(conf["sel_h1_detail"])
        album = (h1.get_text(strip=True) if h1 else "") or items[0].get("post_title") or f"{site_key}_{mid}"
        album_id = f"oreno_{mid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": album,
            "album_id": album_id,
            "is_album": False,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("%s 解析完成: %s (iwara=%s)", conf["label"], mid, iwara_id)
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"{conf['label']} 解析失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 解析过程出错", conf["label"])
