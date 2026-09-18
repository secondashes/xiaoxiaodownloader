# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：ASMR。

由 gui_bridge.py 按物理顺序拆出（原行区间 11460-12134），
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
# asmr-100.com（音声站，Kikoeru 系统，API 网关 + 多域名容灾）
# ============================
# - API：https://api.asmr-200.com（可容灾切换 api.asmr.one / api.asmr-100.com / api.asmr-300.com，token 互通）
# - 登录：POST /api/auth/me {name, password}（勿带 Authorization 头）→ JWT（365 天）
# - 热门：POST /api/recommender/popular {page, pageSize}（勿传空数组参数，会 400）
# - 列表：GET /api/works（order/sort/page/pageSize/subtitle，支持 circleId/tagId/vaId 筛选）
# - 详情：GET /api/work/{id}；音轨树：GET /api/tracks/{id}?v=2（folder/audio/text 三种节点）
# - 音频：GET /api/media/stream/{workId}/{fileId}（播放）/api/media/download/{workId}/{fileId}（下载）
#   → 匿名可用、无签名、支持 Range 断点续传
# - 收藏：PUT /api/review {work_id, progress:"marked"} / DELETE /api/review?work_id=
# - 收藏列表：GET /api/review?filter=marked
ASMR_API_BASES = [
    "https://api.asmr-200.com",
    "https://api.asmr.one",
    "https://api.asmr-100.com",
    "https://api.asmr-300.com",
]
ASMR_SITE = "https://asmr-100.com"
ASMR_ORDERS = {
    "release": "发售日", "create_date": "最新入库", "dl_count": "下载量",
    "price": "价格", "rate_average_2dp": "评分", "review_count": "评论数",
}

_asmr_proxy = ""
_asmr_token = ""
_asmr_username = ""


def _asmr_state() -> dict:
    """当前登录态（跨模块读取入口；本模块内直接用全局名即可）。"""
    return {"token": _asmr_token, "username": _asmr_username}


def _asmr_username_now() -> str:
    """当前用户名（跨模块读取入口；重构第二批拆分时缺失，accounts._site_username 会调用）。"""
    return _asmr_username or ""


def _asmr_set_state(token: str, username: str) -> None:
    """跨模块写入口（账号档案恢复等）：重绑定本模块登录态全局。"""
    global _asmr_token, _asmr_username
    _asmr_token = token or ""
    _asmr_username = username or ""
_asmr_api_base = ASMR_API_BASES[0]
_asmr_session = requests.Session()
_asmr_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Origin": ASMR_SITE,
    "Referer": ASMR_SITE + "/",
})


def asmr_set_proxy(proxy: str) -> None:
    """设置 ASMR 站代理（空 = 直连）。"""
    global _asmr_proxy
    _asmr_proxy = (proxy or "").strip()
    if _asmr_proxy and not _asmr_proxy.startswith(("http://", "https://", "socks5://")):
        _asmr_proxy = "http://" + _asmr_proxy
    proxies = {"http": _asmr_proxy, "https": _asmr_proxy} if _asmr_proxy else {}
    _asmr_session.proxies = proxies
    emit({"event": "asmr_proxy_set", "proxy": _asmr_proxy})


_asmr_throttle = _make_throttle(0.3)


def _asmr_load_cred() -> dict:
    return _secure_store_read_cred("asmr")


def _asmr_save_cred(cred: dict) -> None:
    _secure_store_write_cred("asmr", cred)


def _asmr_auth_headers() -> dict:
    if _asmr_token:
        return {"Authorization": f"Bearer {_asmr_token}"}
    return {}


def _asmr_api(
    method: str,
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
    auth: bool = True,
) -> dict | list:
    """ASMR API 请求（JSON），多域名容灾：主域名失败依次切换备用域名。"""
    global _asmr_api_base
    headers = dict(_asmr_session.headers)
    if auth and _asmr_token:
        headers["Authorization"] = f"Bearer {_asmr_token}"
    bases = [_asmr_api_base] + [b for b in ASMR_API_BASES if b != _asmr_api_base]
    last_exc: Exception | None = None
    for base in bases:
        _asmr_throttle()
        try:
            resp = _asmr_session.request(
                method, f"{base}{path}", json=json_body, params=params,
                headers=headers, timeout=30,
            )
            if resp.status_code in (200, 201):
                _asmr_api_base = base
                return resp.json() if resp.content else {}
            last_exc = PermissionError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            # 401 = token 失效，切换域名无意义
            if resp.status_code == 401:
                break
        except requests.RequestException as exc:
            last_exc = exc
    raise last_exc or PermissionError("ASMR API 请求失败")


def _asmr_work_card(w: dict) -> dict:
    """API work 对象 → 前端作品卡片。"""
    tags = [t.get("name") or t.get("i18n", {}).get("zh-cn") or "" for t in (w.get("tags") or [])]
    vas = [v.get("name") or "" for v in (w.get("vas") or [])]
    return {
        "album_name": w.get("title") or "",
        "album_url": f"{ASMR_SITE}/work/{w.get('id')}",
        "thumbnail": w.get("mainCoverUrl") or "",
        "files": (w.get("duration") and 1) or 1,
        "site": "asmr",
        "video_id": str(w.get("id") or ""),
        "author": w.get("name") or "",  # 社团名
        "circle_id": str(w.get("circle_id") or ""),
        "views": w.get("dl_count"),
        "likes": w.get("rate_average_2dp"),
        "rating": w.get("rate_average_2dp"),
        "price": w.get("price"),
        "nsfw": bool(w.get("nsfw")),
        "duration": w.get("duration"),  # 分钟
        "has_subtitle": bool(w.get("has_subtitle")),
        "post_date": (w.get("release") or "")[:10],
        "source_id": w.get("source_id") or "",
        "tags": [t for t in tags if t],
        "vas": [v for v in vas if v],
        "review_count": w.get("review_count"),
    }


def asmr_login(name: str, password: str, silent: bool = False) -> None:
    """登录 ASMR 站（用户名+密码 → JWT，365 天有效）。"""
    global _asmr_token, _asmr_username
    name = (name or "").strip()
    password = password or ""
    if not name or not password:
        if not silent:
            emit({"event": "asmr_login_result", "success": False, "message": "请输入用户名和密码"})
        return
    try:
        _asmr_throttle()
        # 登录请求勿带 Authorization 头
        resp = _asmr_session.post(
            f"{_asmr_api_base}/api/auth/me",
            json={"name": name, "password": password}, timeout=30,
        )
        if resp.status_code != 200:
            msg = "用户名或密码错误" if resp.status_code in (401, 422) else f"登录失败（HTTP {resp.status_code}）"
            emit({"event": "asmr_login_result", "success": False, "message": msg,
                  "network_issue": resp.status_code >= 500})
            return
        data = resp.json()
        token = data.get("token") or ""
        user = data.get("user") or {}
        if not token or not user.get("loggedIn"):
            emit({"event": "asmr_login_result", "success": False, "message": "登录失败（服务器未返回有效 token）"})
            return
        _asmr_token = token
        _asmr_username = user.get("name") or name
        # token + 密码一起加密持久化（失效自动重登）
        _asmr_save_cred({"token": token, "username": _asmr_username, "password": password})
        emit({"event": "asmr_login_result", "success": True, "silent": silent,
              "username": _asmr_username, "message": f"已登录：{_asmr_username}"})
        _emit_login_info()
        logging.info("ASMR 登录成功: %s", _asmr_username)
    except requests.RequestException as exc:
        emit({"event": "asmr_login_result", "success": False, "network_issue": True,
              "silent": silent, "message": f"网络错误：登录请求失败（{exc}），请检查网络或代理设置"})
    except Exception as exc:
        emit({"event": "asmr_login_result", "success": False, "network_issue": True,
              "silent": silent, "message": f"登录出错：{exc}"})


def asmr_logout() -> None:
    """退出登录（清除本地 token）。"""
    global _asmr_token, _asmr_username
    _asmr_token = ""
    _asmr_username = ""
    _secure_store_clear_cred("asmr")
    emit({"event": "asmr_login_result", "success": True, "logout": True, "username": "",
          "message": "已退出登录"})
    _emit_login_info()


def asmr_check_login(silent: bool = False) -> None:
    """检查登录状态；token 失效时用保存的密码自动重登。"""
    global _asmr_token, _asmr_username
    cred = _asmr_load_cred()
    token = cred.get("token") or ""
    if not token:
        if not silent:
            emit({"event": "asmr_login_result", "success": False, "message": "未登录"})
        return
    _asmr_token = token
    _asmr_username = cred.get("username") or ""
    try:
        data = _asmr_api("GET", "/api/auth/me")
        user = data.get("user") or {}
        if user.get("loggedIn"):
            _asmr_username = user.get("name") or _asmr_username
            emit({"event": "asmr_login_result", "success": True, "silent": silent,
                  "username": _asmr_username})
            _emit_login_info()
            return
    except Exception as exc:
        logging.warning("ASMR 登录检查失败: %s", exc)
    # token 失效 → 用保存的密码重登
    if cred.get("password"):
        asmr_login(cred.get("username") or "", cred.get("password"), silent=True)
    elif not silent:
        emit({"event": "asmr_login_result", "success": False,
              "message": "登录已失效，请重新登录"})


def _asmr_tracks_flatten(nodes: list, parent: str = "") -> list[dict]:
    """音轨树 → 平铺文件列表（保留文件夹相对路径）。"""
    files: list[dict] = []
    for node in nodes or []:
        ntype = node.get("type")
        title = node.get("title") or ""
        if ntype == "folder":
            sub = f"{parent}/{title}" if parent else title
            files.extend(_asmr_tracks_flatten(node.get("children") or [], sub))
        elif ntype in ("audio", "text", "video"):
            hash_ = node.get("hash") or ""
            if not hash_:
                continue
            work_id, file_id = hash_.split("/", 1) if "/" in hash_ else ("", hash_)
            media_url = node.get("mediaDownloadUrl") or (
                f"{_asmr_api_base}/api/media/download/{hash_}")
            if media_url.startswith("//"):
                media_url = "https:" + media_url
            files.append({
                "title": title,
                "path": parent,
                "type": ntype,
                "duration": node.get("duration"),
                "size": node.get("size"),
                "work_id": work_id,
                "file_id": file_id,
                "media_url": media_url,
                "stream_url": f"{_asmr_api_base}/api/media/stream/{hash_}",
            })
    return files


async def asmr_popular(page: int = 1, subtitle: bool = False) -> None:
    """热门作品（每页 100，可翻页抓取 100+；可勾选仅带字幕客户端过滤）。"""
    emit({"event": "asmr_list_loading", "loading": True, "view": "popular"})
    try:
        page = max(1, page or 1)
        data = await asyncio.to_thread(
            _asmr_api, "POST", "/api/recommender/popular",
            {"page": page, "pageSize": 100}, None, False,
        )
        works = data.get("works") or data or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        if subtitle:
            items = [i for i in items if i.get("has_subtitle")]
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        pagination = data.get("pagination") or {}
        emit({"event": "asmr_list", "view": "popular", "items": items, "page": page,
              "has_more": page < max(1, (pagination.get("totalCount") or 0) // 100 + 1),
              "label": "热门作品"})
        logging.info("ASMR 热门第 %d 页: %d 个作品", page, len(items))
    except Exception as exc:
        emit({"event": "asmr_list", "view": "popular", "items": [], "page": page,
              "has_more": False, "error": f"获取热门作品失败: {exc}（请检查网络或代理设置）"})
        logging.exception("ASMR 热门获取失败")
    finally:
        emit({"event": "asmr_list_loading", "loading": False, "view": "popular"})


async def asmr_works(
    page: int = 1, order: str = "create_date", sort: str = "desc",
    subtitle: bool = False, circle_id: str = "", tag_id: str = "", va_id: str = "",
    view: str = "works", label: str = "",
) -> None:
    """作品列表（最新入库等排序 + 社团/标签/声优筛选 + 可勾选仅带字幕）。"""
    emit({"event": "asmr_list_loading", "loading": True, "view": view})
    try:
        page = max(1, page or 1)
        params: dict = {
            "page": page, "pageSize": 50,
            "order": order or "create_date", "sort": sort or "desc",
        }
        if subtitle:
            params["subtitle"] = 1
        # 社团/标签/声优筛选必须走 /api/{kind}/{id}/works 专用路由：
        # /api/works 会静默忽略 circleId/tagId/vas 参数（实测恒返回未过滤的最新列表）
        path = "/api/works"
        if circle_id:
            path = f"/api/circles/{circle_id}/works"
        elif tag_id:
            path = f"/api/tags/{tag_id}/works"
        elif va_id:
            path = f"/api/vas/{va_id}/works"
        data = await asyncio.to_thread(_asmr_api, "GET", path, None, params, False)
        works = data.get("works") or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        pagination = data.get("pagination") or {}
        total = pagination.get("totalCount") or 0
        has_more = page * 50 < total
        emit({"event": "asmr_list", "view": view, "items": items, "page": page,
              "has_more": has_more, "total": total, "label": label or "作品列表",
              "orders": ASMR_ORDERS})
    except Exception as exc:
        emit({"event": "asmr_list", "view": view, "items": [], "page": page,
              "has_more": False, "error": f"获取作品列表失败: {exc}"})
        logging.exception("ASMR 作品列表获取失败")
    finally:
        emit({"event": "asmr_list_loading", "loading": False, "view": view})


async def asmr_search(query: str, page: int = 1, subtitle: bool = False) -> None:
    """关键词搜索（支持 RJ 号 / 标题 / 社团名 / 标签）。"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        params: dict = {
            "page": page, "pageSize": 50,
            "orderBy": "create_date", "sort": "desc",
        }
        if subtitle:
            params["subtitle"] = 1
        from urllib.parse import quote
        data = await asyncio.to_thread(
            _asmr_api, "GET", f"/api/search/{quote(query)}", None, params, False)
        works = data.get("works") or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        emit({"event": "search_result", "query": query, "site": "asmr",
              "items": items, "page": page,
              "has_more": page * 50 < (data.get("pagination") or {}).get("totalCount", 0),
              "label": query})
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("ASMR 搜索 '%s': %d 个结果", query, len(items))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"ASMR 搜索失败: {exc}（请检查网络或代理设置）"})
        logging.exception("ASMR 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


async def _asmr_related_tags_fill(work_id: str, tags: list, seed_ids: set) -> None:
    """详情 tags 推荐后台补齐：查到后单独推送 asmr_related_extra（不阻塞详情下发）。

    限流防护：最多查前 4 个不同标签（对齐收藏页推荐口径），凑满 12 条即止。"""
    items: list[dict] = []
    seen_ids = set(seed_ids)
    queried = 0
    try:
        for tag in tags:
            if len(items) >= 12 or queried >= 4:
                break
            if not isinstance(tag, dict) or not tag.get("id"):
                continue
            queried += 1
            rec = await asyncio.to_thread(
                _asmr_api, "GET", f"/api/tags/{tag['id']}/works", None,
                {"order": "release", "sort": "desc",
                 "page": 1, "pageSize": 12}, False)
            for w2 in (rec.get("works") or []):
                wid = str(w2.get("id") or "")
                if wid and wid not in seen_ids:
                    seen_ids.add(wid)
                    items.append(_asmr_work_card(w2))
                    if len(items) >= 12:
                        break
    except Exception:
        logging.debug("ASMR 标签推荐后台补齐失败", exc_info=True)
    if items:
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
    emit({"event": "asmr_related_extra", "work_id": str(work_id),
          "items": items, "failed": not items})


async def asmr_work_detail(work_id: str) -> None:
    """作品详情：元数据 + 音轨树（在线播放走本地媒体代理）+ 收藏状态。"""
    emit({"event": "asmr_detail_loading", "loading": True})
    try:
        work = await asyncio.to_thread(_asmr_api, "GET", f"/api/work/{work_id}", None, None, False)
        try:
            extra = await asyncio.to_thread(
                _asmr_api, "GET", f"/api/workInfo/{work_id}", None, None, False)
            if isinstance(extra, dict):
                work.update({k: v for k, v in extra.items() if k not in work})
        except Exception:
            pass
        tracks = await asyncio.to_thread(
            _asmr_api, "GET", f"/api/tracks/{work_id}", None, {"v": 2}, False)
        files = _asmr_tracks_flatten(tracks if isinstance(tracks, list) else [])
        # 播放/下载地址转本地媒体代理（前端直接用）
        for f in files:
            f["play_url"] = media_proxy_url(f["stream_url"])
        card = _asmr_work_card(work)
        # 中文附加信息
        card.update({
            "description": (work.get("work_attributes") or {}),
            "sam_cover": work.get("samCoverUrl") or "",
            "circle": (work.get("circle") or {}),
            "source_url": work.get("source_url") or "",
            "create_date": (work.get("create_date") or "")[:10],
            "file_count": len(files),
        })
        # 相似作品：同社团结果（仅 1 个请求）随详情立即下发；不足 8 个时 tags 推荐
        # 后台补齐、单独推送 asmr_related_extra——旧实现把逐 tag 串行查询串在详情
        # 关键路径上，十几连发易触发站方限流（一挂全空）且拖慢详情。
        related = []
        try:
            circle_id = str((work.get("circle") or {}).get("id") or "")
            if circle_id:
                rel = await asyncio.to_thread(
                    _asmr_api, "GET", f"/api/circles/{circle_id}/works", None,
                    {"page": 1, "pageSize": 13,
                     "order": "create_date", "sort": "desc"}, False)
                rel_items = [_asmr_work_card(w) for w in (rel.get("works") or [])
                             if isinstance(w, dict) and str(w.get("id")) != str(work_id)]
                related = rel_items[:12]
        except Exception:
            logging.debug("ASMR 同社团相似作品获取失败", exc_info=True)
        related_pending = False
        if len(related) < 8 and any(
                isinstance(t, dict) and t.get("id") for t in (work.get("tags") or [])):
            related_pending = True
            seed_ids = {r["video_id"] for r in related}
            seed_ids.add(str(work_id))
            asyncio.create_task(
                _asmr_related_tags_fill(str(work_id), work.get("tags") or [], seed_ids))

        emit({"event": "asmr_video_detail", "video": card, "files": files,
              "related": related, "related_pending": related_pending,
              "logged_in": bool(_asmr_token)})
        asyncio.create_task(_cache_thumbnails([card]))
        logging.info("ASMR 作品详情: %s (%d 个文件)", work_id, len(files))
    except Exception as exc:
        emit({"event": "asmr_video_detail", "video": None, "files": [],
              "error": f"获取作品详情失败: {exc}（请检查网络或代理设置）"})
        logging.exception("ASMR 作品详情获取失败")
    finally:
        emit({"event": "asmr_detail_loading", "loading": False})


def _asmr_cache_list(kind: str) -> list[dict]:
    """社团/标签/声优全量列表（API 返回全量，本地缓存 7 天）。"""
    cache_file = Path(f"cache/asmr_{kind}.json")
    if cache_file.exists():
        try:
            age = time.time() - cache_file.stat().st_mtime
            if age < 7 * 86400:
                data = json.loads(cache_file.read_text("utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    path = {"circles": "/api/circles/", "tags": "/api/tags/", "vas": "/api/vas/"}[kind]
    data = _asmr_api("GET", path, None, None, False)
    data = data if isinstance(data, list) else []
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return data


async def asmr_browse_index(kind: str) -> None:
    """社团/标签/声优索引（全量，含作品数与多语言名）。"""
    event = {"circles": "asmr_circles", "tags": "asmr_tags", "vas": "asmr_vas"}[kind]
    emit({"event": f"{event}_loading", "loading": True})
    try:
        data = await asyncio.to_thread(_asmr_cache_list, kind)
        out: list[dict] = []
        for item in data:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            i18n = item.get("i18n") or {}
            name = item.get("name") or i18n.get("zh-cn") or i18n.get("en-us") or ""
            if not name:
                continue
            out.append({"id": str(item["id"]), "name": name,
                        "count": item.get("count") or 0})
        out.sort(key=lambda x: -int(x["count"] or 0))
        emit({"event": event, "items": out})
        logging.info("ASMR %s 索引: %d 项", kind, len(out))
    except Exception as exc:
        emit({"event": event, "items": [], "error": f"获取{kind}列表失败: {exc}"})
    finally:
        emit({"event": f"{event}_loading", "loading": False})


async def asmr_toggle_favorite(work_id: str, card: dict) -> None:
    """收藏/取消收藏作品（PUT/DELETE /api/review，需登录）。"""
    try:
        if not _asmr_token:
            emit({"event": "asmr_fav_result", "video_id": str(work_id), "saved": False,
                  "error": "请先登录"})
            return
        # 查询当前是否已收藏（不带 filter：progress=None 的评分条目也算收藏态）
        cur = _asmr_api("GET", "/api/review", None,
                        {"order": "updated_at", "sort": "desc", "page": 1,
                         "pageSize": 100})
        cur_ids = {str(w.get("id")) for w in (cur.get("works") or [])}
        wid = str(work_id)
        if wid in cur_ids:
            _asmr_api("DELETE", "/api/review", None, {"work_id": work_id})
            saved = False
        else:
            _asmr_api("PUT", "/api/review",
                      {"work_id": int(work_id), "rating": 0,
                       "review_text": "", "progress": "marked"})
            saved = True
        emit({"event": "asmr_fav_result", "video_id": wid, "saved": saved})
    except Exception as exc:
        emit({"event": "asmr_fav_result", "video_id": str(work_id), "saved": False,
              "error": f"收藏操作失败: {exc}"})


async def asmr_favorites(page: int = 1) -> None:
    """我的收藏列表（需登录）。"""
    emit({"event": "asmr_list_loading", "loading": True, "view": "favorites"})
    try:
        if not _asmr_token:
            emit({"event": "asmr_list", "view": "favorites", "items": [], "page": 1,
                  "has_more": False, "error": "请先登录"})
            return
        page = max(1, page or 1)
        # 不再带 filter=marked：评分收藏条目 progress 可能为 None 会被服务端滤掉
        # （实测 2026-09-09：账下 1 条 progress=None 的评分，filter=marked 返回 0）
        data = await asyncio.to_thread(
            _asmr_api, "GET", "/api/review",
            None, {"order": "updated_at", "sort": "desc", "page": page,
                   "pageSize": 50})
        works = data.get("works") or []
        # review 接口条目把作品嵌套在 work 键下（实测 2026-09-09），需解包再转卡片
        items = []
        for w in (works if isinstance(works, list) else []):
            if not isinstance(w, dict):
                continue
            work = w.get("work") if isinstance(w.get("work"), dict) else w
            if isinstance(work, dict) and work.get("id"):
                items.append(_asmr_work_card(work))
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        total = (data.get("pagination") or {}).get("totalCount") or 0
        # 收藏页推荐：取收藏作品的 tags，拉十几个相同标签的推荐作品（对齐真实站滚动推荐）
        recommend = []
        try:
            fav_ids = set()
            tag_ids: list = []
            for w in (works if isinstance(works, list) else []):
                if not isinstance(w, dict):
                    continue
                work = w.get("work") if isinstance(w.get("work"), dict) else (w or {})
                if work.get("id"):
                    fav_ids.add(str(work["id"]))
                for t in (work.get("tags") or [])[:3]:
                    tid = t.get("id") if isinstance(t, dict) else None
                    if tid and tid not in tag_ids:
                        tag_ids.append(tid)
            for tid in tag_ids[:4]:
                rec = await asyncio.to_thread(
                    _asmr_api, "GET", f"/api/tags/{tid}/works", None,
                    {"order": "release", "sort": "desc",
                     "page": 1, "pageSize": 12}, False)
                for w2 in (rec.get("works") or []):
                    wid = str(w2.get("id") or "")
                    if wid and wid not in fav_ids:
                        fav_ids.add(wid)
                        recommend.append(_asmr_work_card(w2))
                        if len(recommend) >= 12:
                            break
                if len(recommend) >= 12:
                    break
        except Exception:
            logging.debug("ASMR 收藏推荐获取失败", exc_info=True)
        emit({"event": "asmr_list", "view": "favorites", "items": items, "page": page,
              "has_more": page * 50 < total, "label": "我的收藏", "recommend": recommend})
    except Exception as exc:
        emit({"event": "asmr_list", "view": "favorites", "items": [], "page": page,
              "has_more": False, "error": f"获取收藏失败: {exc}"})
    finally:
        emit({"event": "asmr_list_loading", "loading": False, "view": "favorites"})


async def asmr_batch_download(work_ids: list, options: dict) -> None:
    """批量下载作品（整包）：每个作品遍历音轨树，逐文件下载（保留文件夹结构）。"""
    work_ids = [str(v).strip() for v in (work_ids or []) if str(v).strip()]
    if not work_ids:
        emit({"event": "asmr_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "请先勾选要下载的作品"})
        return
    total = len(work_ids)
    failed: list[str] = []
    submitted = 0
    try:
        for i, wid in enumerate(work_ids):
            try:
                work = await asyncio.to_thread(
                    _asmr_api, "GET", f"/api/work/{wid}", None, None, False)
                tracks = await asyncio.to_thread(
                    _asmr_api, "GET", f"/api/tracks/{wid}", None, {"v": 2}, False)
                files = _asmr_tracks_flatten(tracks if isinstance(tracks, list) else [])
                if not files:
                    failed.append(f"{wid}（无文件）")
                    continue
                title = sanitize_directory_name(
                    (work.get("title") or "").strip() or f"asmr_{wid}")
                rj = work.get("source_id") or ""
                album_name = f"{rj} {title}".strip() if rj else title
                items: list[dict] = []
                for f in files:
                    rel = "/".join(p for p in [f["path"], f["title"]] if p)
                    items.append({
                        "filename": rel,
                        "size": f.get("size"),
                        "item_page": f"{ASMR_SITE}/work/{wid}",
                        "status": "ok",
                        "media_url": f["media_url"],
                        "site": "asmr",
                        "post_title": title,
                        "post_date": (work.get("release") or "")[:10],
                        "artist": work.get("name") or "",
                    })
                task_id = download_manager.submit(
                    f"{ASMR_SITE}/work/{wid}", items, options,
                    album_name, f"asmr_{wid}")
                download_manager.start(task_id)
                submitted += 1
            except Exception as exc:
                failed.append(f"{wid}（{exc}）")
            emit({"event": "asmr_batch_progress", "done": i + 1, "total": total,
                  "message": f"解析进度 {i + 1}/{total}"})
        summary = f"批量下载已提交 {submitted}/{total} 个作品"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "asmr_batch_done", "done": submitted, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "asmr_batch_done", "done": submitted, "total": total,
              "failed": failed, "message": f"批量下载中断: {exc}"})


# 允许下载的 ASMR 媒体域名后缀（media_url 来源为音轨树 mediaDownloadUrl 或 api 端点，防任意 URL 注入）
# 注意：mediaDownloadUrl 现指向 raw.kiko-play-niptan.one（新 CDN），四 asmr 域名保留作 API 端点兜底
_ASMR_MEDIA_HOST_SUFFIXES = (
    ".asmr.one", ".asmr-100.com", ".asmr-200.com", ".asmr-300.com",
    ".kiko-play-niptan.one",
)


def _asmr_media_url_ok(url: str) -> bool:
    try:
        u = urlparse(url)
        if u.scheme != "https" or not u.hostname:
            return False
        host = u.hostname.lower()
        return any(host == s.lstrip(".") or host.endswith(s) for s in _ASMR_MEDIA_HOST_SUFFIXES)
    except Exception:
        return False


async def asmr_file_download(work_id: str, work: dict, files: list, options: dict) -> None:
    """右键下载单个/多个音轨文件（提交下载管理器，保留文件夹相对路径）。"""
    work_id = str(work_id or "").strip()
    work = work if isinstance(work, dict) else {}
    picked = []
    for f in (files or []):
        if not isinstance(f, dict):
            continue
        url = (f.get("media_url") or "").strip()
        if not url or not _asmr_media_url_ok(url):
            # CDN 域名再次迁移时按 hash 回退 API 下载端点（api 域在白名单内）
            wid, fid = f.get("work_id") or "", f.get("file_id") or ""
            if not (wid and fid):
                tail = (f.get("stream_url") or "").partition("/api/media/stream/")[2]
                if "/" in tail:
                    wid, fid = tail.split("/", 1)
            if wid and fid:
                url = f"{_asmr_api_base}/api/media/download/{wid}/{fid}"
            if not url or not _asmr_media_url_ok(url):
                continue
        picked.append(f)
    if not work_id or not picked:
        emit({"event": "message", "level": "error",
              "text": "没有可下载的音轨文件（链接校验失败）"})
        return
    try:
        title = sanitize_directory_name(
            (work.get("title") or "").strip() or f"asmr_{work_id}")
        rj = work.get("source_id") or ""
        album_name = f"{rj} {title}".strip() if rj else title
        items = []
        for f in picked:
            rel = "/".join(p for p in [f.get("path"), f.get("title")] if p)
            items.append({
                "filename": rel,
                "size": f.get("size"),
                "item_page": f"{ASMR_SITE}/work/{work_id}",
                "status": "ok",
                "media_url": f["media_url"],
                "site": "asmr",
                "post_title": title,
                "post_date": (work.get("release") or "")[:10],
                "artist": work.get("name") or "",
            })
        task_id = download_manager.submit(
            f"{ASMR_SITE}/work/{work_id}", items, options,
            album_name, f"asmr_{work_id}_{int(time.time())}")
        download_manager.start(task_id)
        emit({"event": "message", "level": "success",
              "text": f"已提交下载：{len(items)} 个音轨文件"})
        logging.info("ASMR 单文件下载提交: %s %d 个文件", work_id, len(items))
    except Exception as exc:
        emit({"event": "message", "level": "error", "text": f"提交下载失败: {exc}"})
        logging.exception("ASMR 单文件下载失败")


async def asmr_inspect(url: str, options: dict) -> None:
    """解析 ASMR 作品页 → 全部音轨文件列表（在线播放走本地媒体代理）。"""
    m = re.search(r"/work/(\d+)", url)
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 ASMR 链接（支持 /work/{id}）"})
        return
    wid = m.group(1)
    try:
        work = await asyncio.to_thread(_asmr_api, "GET", f"/api/work/{wid}", None, None, False)
        tracks = await asyncio.to_thread(
            _asmr_api, "GET", f"/api/tracks/{wid}", None, {"v": 2}, False)
        files = _asmr_tracks_flatten(tracks if isinstance(tracks, list) else [])
        if not files:
            emit({"event": "inspect_error", "message": "该作品没有可下载的文件"})
            return
        title = sanitize_directory_name((work.get("title") or "").strip() or f"asmr_{wid}")
        rj = work.get("source_id") or ""
        album_name = f"{rj} {title}".strip() if rj else title
        items: list[dict] = []
        for f in files:
            rel = "/".join(p for p in [f["path"], f["title"]] if p)
            items.append({
                "filename": rel,
                "size": f.get("size"),
                "item_page": f"{ASMR_SITE}/work/{wid}",
                "status": "ok",
                "media_url": f["media_url"],
                "play_url": media_proxy_url(f["stream_url"]),
                "site": "asmr",
                "post_title": title,
                "post_date": (work.get("release") or "")[:10],
                "artist": work.get("name") or "",
            })
        album_id = f"asmr_{wid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": album_name,
            "album_id": album_id,
            "is_album": True,
            "items": items,
        })
        logging.info("ASMR 作品解析完成: %s (%d 个文件)", wid, len(items))
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"ASMR 作品解析失败: {exc}（请检查网络或 ASMR 代理设置）"})
        logging.exception("ASMR 作品解析过程出错")
