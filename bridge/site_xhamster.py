# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：xHamster。

由 gui_bridge.py 按物理顺序拆出（原行区间 7582-8475），
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
import uuid
from argparse import Namespace
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote, urlparse
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
# xHamster 站点支持 (jp.xhamster.com，三次元视频站)
# ============================
# 域名策略：全部请求严格限定 jp.xhamster.com（日本区），绝不请求主站 xhamster.com
#   （主站会触发内容规范审查/年龄验证墙，返回页面被截断）
# 登录: webview 浏览器登录（OAuth / 邮箱），cookie 存加密凭据库（AP1 框架已通）
# 数据源: 页面内嵌 window.initials = {...} JSON（列表/详情/分类/评论全在里面）
#   * 列表卡片: layoutPage.videoListProps.videoThumbProps / searchResult.videoThumbProps /
#     videoListComponent.videoThumbProps / pagesCategoryComponent.trendingVideoListProps.videoThumbProps
#   * 分页: initials.page / maxPages
#   * 详情: videoModel（id/title/views/votes.up/rating/duration/created/author/categories/tags）
#   * 播放源: xplayerSettings.sources（standard.h264[] 多画质 mp4 + hls.h264 m3u8），
#     URL 为 SSE 十六进制加密串，需 ByteGen 系列伪随机算法 decipher 解密（yt-dlp 同款）
#   * 评论: commentsComponent.commentsList.items[]（含 author/personalInfo/counters）
# 列表: /newest /most-viewed /top-rated（分页 /{page}）
# 搜索: /search/{kw}/{page}（jp 域内搜索，5 种排序 filters.sortSelectorProps）
# 短视频: /search/%20/duration/shortest/{page}（moments 无公开 API，用时长相邻搜索代替）
# 分类: /categories → layoutPage.store.popular.trending.items（热门12）+ assignable 分组;
#   分类列表: /categories/{slug}/{page}
# 消息: /notifications → notificationsModel{gifts,messages,friends,notifications,subscriptions}
#   （未登录 302 → /login）
# 我的: /users/me 301 → /users/profiles/me（跟随重定向从最终 URL 提取用户名）；
#   视频列表 /users/{name}/videos/{page}、收藏 /users/{name}/favorites/videos/{page}
# 下载: mp4 直链（Range 可用），必须 Referer: https://jp.xhamster.com/；CDN 域 xhcdn.com
# 国内必须代理（默认 http://127.0.0.1:10809）

XHAMSTER_BASE = "https://jp.xhamster.com"
XHAMSTER_DEFAULT_PROXY = "http://127.0.0.1:10809"
# 列表排序 → URL 路径（首页筛选；/top-rated 在 jp 域实测 404，最高评分改走 /best）
XHAMSTER_SORTS = {
    "newest": "/newest",
    "views": "/most-viewed",
    "rating": "/best",
    "hd": "/hd",
    "4k": "/4k",
    "vr": "/vr",
}
# 某 path 404 时的候选（jp 域路径偶发改版）
XHAMSTER_SORT_FALLBACKS = {
    "rating": ["/best", "/4k"],
    "hd": ["/hd", "/4k"],
    "4k": ["/4k", "/hd"],
    "vr": ["/vr", "/4k"],
}
# 搜索排序（filters.sortSelectorProps.options）
XHAMSTER_SEARCH_SORTS = ("relevance", "newest", "views", "best", "longest")

_xhamster_proxy = XHAMSTER_DEFAULT_PROXY
_xhamster_username = ""


def _xhamster_username_now() -> str:
    """当前用户名（跨模块读取入口）。"""
    return _xhamster_username or ""


def _xhamster_set_username(v: str) -> None:
    """跨模块写入口（如登出清空）。"""
    global _xhamster_username
    _xhamster_username = v or ""

_xhamster_session = requests.Session()
_xhamster_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
})


def xhamster_set_proxy(proxy: str) -> None:
    """设置代理（空 = 默认代理；xhamster 国内必须代理）。"""
    global _xhamster_proxy
    _xhamster_proxy = (proxy or "").strip() or XHAMSTER_DEFAULT_PROXY
    _xhamster_session.proxies.update({"http": _xhamster_proxy, "https": _xhamster_proxy})


def _xhamster_restore_session() -> None:
    """把保存的登录 cookie 应用到站点请求会话（浏览/搜索自动带会话）。"""
    cookie_str = _generic_cookie_str("xhamster")
    if cookie_str:
        _xhamster_session.headers["Cookie"] = cookie_str
    else:
        _xhamster_session.headers.pop("Cookie", None)


_xhamster_throttle = _make_throttle(0.5)


def _xh_get(path: str, timeout: int = 30) -> requests.Response:
    """GET jp.xhamster.com 页面（自动带节流/代理/登录 cookie）。"""
    url = path if path.startswith("http") else f"{XHAMSTER_BASE}{path}"
    # 防御：链接若指向主站，改写为 jp 域（规范审查墙规避）
    if "//xhamster.com/" in url:
        url = url.replace("//xhamster.com/", "//jp.xhamster.com/", 1)
    _xhamster_throttle()
    return _xhamster_session.get(url, timeout=timeout)


def _xh_initials(html: str) -> dict | None:
    """解析页面内嵌 window.initials = {...} JSON。

    参考 yt-dlp（github.com/yt-dlp/yt-dlp）XHamsterIE 实现：
    - 用正则定位赋值起点 `window.initials = {`，而非裸 find（防止命中
      页面其他位置出现的同名文本导致解析错位/截断）
    - raw_decode 原生处理嵌套 JSON，配 3MB 上限防御异常超大响应
    - 首个匹配点解析失败时继续尝试后续匹配点（页面可能多处出现）
    """
    decoder = json.JSONDecoder()
    for m in re.finditer(r"window\.initials\s*=\s*(\{)", html):
        j = m.end(1) - 1  # 指向 '{'
        try:
            obj, _ = decoder.raw_decode(html[j:j + 3_000_000])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    return None


def _xh_fetch(path: str) -> tuple[dict | None, requests.Response]:
    """GET + initials 解析（返回 None 表示无数据/被拦截）。"""
    r = _xh_get(path)
    if r.status_code != 200:
        raise PermissionError(f"xHamster 返回 HTTP {r.status_code}")
    return _xh_initials(r.text), r


# ---------- 播放源 SSE 解密（yt-dlp 同款 ByteGen 算法） ----------

def _xh_int32(i: int) -> int:
    i &= 0xFFFFFFFF
    return i - 0x100000000 if i >= 0x80000000 else i


class _XhByteGen:
    """xhamster 播放源 URL 解密用的伪随机字节生成器（7 种算法，algo_id 在密文首字节）。"""

    def __init__(self, algo_id: int, seed: int):
        self._a = getattr(self, f"_algo{algo_id}", self._algo2)
        self._s = _xh_int32(seed)

    def _algo1(self, s):
        s = self._s = _xh_int32(s * 1664525 + 1013904223)
        return s

    def _algo2(self, s):
        s = _xh_int32(s ^ (s << 13))
        s = _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 17))
        s = self._s = _xh_int32(s ^ (s << 5))
        return s

    def _algo3(self, s):
        s = _xh_int32(s + 0x9E3779B9)
        s = _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 16))
        s = _xh_int32(s * _xh_int32(0x85EBCA77))
        s = _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 13))
        s = _xh_int32(s * _xh_int32(0xC2B2AE3D))
        return _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 16))

    def _algo4(self, s):
        s = self._s = _xh_int32(s + 0x6D2B79F5)
        s = _xh_int32((s << 7) | ((s & 0xFFFFFFFF) >> 25))
        s = _xh_int32(s + 0x9E3779B9)
        s = _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 11))
        return _xh_int32(s * 0x27D4EB2D)

    def _algo5(self, s):
        s = _xh_int32(s ^ (s << 7))
        s = _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 9))
        s = _xh_int32(s ^ (s << 8))
        s = self._s = _xh_int32(s + 0xA5A5A5A5)
        return s

    def _algo6(self, s):
        s = self._s = _xh_int32(s * _xh_int32(0x2C9277B5) + _xh_int32(0xAC564B05))
        s2 = _xh_int32(s ^ ((s & 0xFFFFFFFF) >> 18))
        shift = (s & 0xFFFFFFFF) >> 27 & 31
        return _xh_int32((s2 & 0xFFFFFFFF) >> shift)

    def _algo7(self, s):
        s = self._s = _xh_int32(s + _xh_int32(0x9E3779B9))
        e = _xh_int32(s ^ (s << 5))
        e = _xh_int32(e * _xh_int32(0x7FEB352D))
        e = _xh_int32(e ^ ((e & 0xFFFFFFFF) >> 15))
        return _xh_int32(e * _xh_int32(0x846CA68B))

    def __next__(self):
        return self._a(self._s) & 0xFF


def _xh_decipher(hexstr: str) -> str:
    """解密播放源 URL（SSE hex 串 → http 直链）。"""
    try:
        data = bytes.fromhex(hexstr)
        seed = int.from_bytes(data[1:5], "little", signed=True)
        g = _XhByteGen(data[0], seed)
        return bytes(b ^ next(g) for b in data[5:]).decode("latin-1")
    except Exception:
        return ""


def _xh_cipher_url(val) -> str:
    """密文字段 → 直链（明文字段直接返回；解密失败返回空）。

    参考 yt-dlp XHamsterIE._decipher_format_url，支持三种形态：
    1. 明文 http(s) URL：直接返回
    2. 纯 hex 密文（≥12 位）：整体解密
    3. URL 内嵌 hex 段（CDN 格式 /{hex}/{rest} 或 /{hex},{rest}）：
       解密 path 首段后重拼 URL
    """
    val = val or ""
    if isinstance(val, str) and val.startswith("http"):
        try:
            u = urllib.parse.urlsplit(val)
            m = re.match(r"^/([0-9a-fA-F]{12,})([/,].+)$", u.path)
            if m:
                d = _xh_decipher(m.group(1))
                if d:
                    return urllib.parse.urlunsplit(
                        (u.scheme, u.netloc, f"/{d}{m.group(2)}", u.query, u.fragment))
        except Exception:
            pass
        return val
    if isinstance(val, str) and re.fullmatch(r"[0-9a-fA-F]{12,}", val):
        d = _xh_decipher(val)
        return d if d.startswith("http") else ""
    return ""


# ---------- 卡片/评论/详情解析 ----------

def _xh_duration_str(seconds) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _xh_fav_user_card(u: dict) -> dict | None:
    """收藏用户 → 前端卡片（点击进用户主页，不走视频详情）。"""
    if not isinstance(u, dict):
        return None
    name = (u.get("name") or u.get("username") or "").strip()
    page = u.get("pageURL") or u.get("pageUrl") or ""
    slug = _xh_username_from_url(page) or name
    if not slug:
        return None
    return {
        "album_name": name or slug,
        "album_url": page or f"{XHAMSTER_BASE}/users/{slug}",
        "thumbnail": u.get("thumbURL") or u.get("thumbUrl") or "",
        "files": 0,
        "site": "xhamster",
        "video_id": "",
        "author": slug,
        "author_url": page,
        "views": "",
        "likes": "",
        "duration": "",
        "created": "",
        "is_hd": False,
        "kind": "user",
    }


def _xh_cards(init: dict) -> list[dict]:
    """从 initials 提取视频卡片数组（首页/搜索/分类/用户页数据位置不同，逐个尝试；
    收藏/清单等改版页面再全树递归兜底，任意位置找 videoThumbProps）。"""
    for holder in (
        (init.get("layoutPage") or {}).get("videoListProps"),
        init.get("searchResult"),
        init.get("videoListComponent"),
        ((init.get("pagesCategoryComponent") or {}).get("trendingVideoListProps")),
    ):
        arr = (holder or {}).get("videoThumbProps")
        if isinstance(arr, list) and arr:
            return arr
    # 兜底：深度递归找 videoThumbProps（收藏页结构与常规列表不同时会漏抓）
    found: list = []

    def _walk(node, depth: int = 0) -> None:
        if depth > 14 or found:
            return
        if isinstance(node, dict):
            vtp = node.get("videoThumbProps")
            if isinstance(vtp, list) and vtp and isinstance(vtp[0], dict) and (
                    vtp[0].get("pageURL") or vtp[0].get("id")):
                found.append(vtp)
                return
            for v in node.values():
                _walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                _walk(v, depth + 1)

    _walk(init)
    return found[0] if found else []


def _xh_card(c: dict) -> dict | None:
    """列表卡片 → 前端视频卡片。"""
    if not isinstance(c, dict):
        return None
    page_url = c.get("pageURL") or ""
    vid = str(c.get("id") or "")
    if not page_url and not vid:
        return None
    # 视频短码：URL 尾部 -xhXXXX（如 /videos/xxx-xh3qN8v）
    code = ""
    if page_url:
        m = re.search(r"-xh([0-9a-zA-Z]+)$", page_url.rstrip("/").rsplit("/", 1)[-1])
        if m:
            code = m.group(1)
    up = c.get("uploader") or c.get("author") or c.get("channel") or {}
    if not isinstance(up, dict):
        up = {}
    votes = c.get("votes") if isinstance(c.get("votes"), dict) else {}
    created = ""
    ts = c.get("created") or c.get("published") or c.get("publishDate")
    if ts:
        try:
            created = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError, TypeError):
            created = str(ts)[:10] if ts else ""
    views = c.get("views")
    if views in (None, "", 0):
        stats = c.get("stats") if isinstance(c.get("stats"), dict) else {}
        views = c.get("viewCount") or c.get("viewsCount") or stats.get("views")
    likes = votes.get("up") or c.get("likes") or c.get("likeCount") or ""
    is_hd = bool(c.get("isHD") or c.get("isHd") or c.get("hd") or c.get("isUHD") or c.get("is4K"))
    duration_sec = c.get("duration") or c.get("durationSec") or 0
    try:
        duration_sec = int(duration_sec or 0)
    except (TypeError, ValueError):
        duration_sec = 0
    icon = str(c.get("icon") or "").lower()
    vtype = str(c.get("videoType") or "").lower()
    kind = "video"
    if vtype in ("moment", "moments", "short", "shorts") or duration_sec and duration_sec <= 60:
        kind = "short"
    access = ""
    if icon == "friends":
        access = "friends"
    elif icon == "lock":
        access = "private"
    landing = c.get("landing") if isinstance(c.get("landing"), dict) else {}
    author = up.get("name") or up.get("username") or up.get("title") or landing.get("name") or ""
    # 作者链接真实键名是 landing.link（探针 2026-09-09；pageURL/url 均为空）
    author_url = up.get("pageURL") or up.get("pageUrl") or up.get("url") or up.get("link") or ""
    # 搜索结果里的纯用户卡（landing.type=user）：author_url 归一为 /users/{name} 供用户页路由
    if landing.get("type") == "user":
        if author and not author_url:
            author_url = f"{XHAMSTER_BASE}/users/{author}"
        if not page_url and author_url:
            page_url = author_url
        kind = "user"
    return {
        "album_name": c.get("title") or f"xhamster_{code or vid}",
        "album_url": page_url,
        "thumbnail": c.get("thumbURL") or c.get("imageURL") or c.get("thumbUrl") or "",
        "files": 1,
        "site": "xhamster",
        "video_id": code or vid,      # 短码（无则数字 id）
        "author": author,
        "author_url": author_url,
        "views": str(views or ""),
        "likes": str(likes or ""),
        "rating": c.get("rating") or "",
        "duration": _xh_duration_str(duration_sec),
        "duration_sec": duration_sec,
        "created": created,
        "is_hd": is_hd,
        "kind": kind,
        "access": access,
        "numeric_id": vid,
    }


def _xh_card_items(init: dict) -> list[dict]:
    items = []
    for c in _xh_cards(init):
        card = _xh_card(c)
        if card:
            items.append(card)
    return items


def _xh_has_more(init: dict, n_items: int) -> bool:
    """分页判断：maxPages 可用时按页数，否则按满页数量（搜索页 maxPages 常缺失）。"""
    max_pages = init.get("maxPages")
    page = init.get("page") or 1
    if isinstance(max_pages, (int, float)) and max_pages:
        return page < int(max_pages)
    return n_items >= 36


def _xh_emit_list(event: str, init: dict, **extra) -> int:
    """列表页通用输出：卡片 + 缩略图缓存 + 分页。"""
    items = _xh_card_items(init)
    _apply_cached_thumbnails(items)
    asyncio.get_event_loop().create_task(_cache_thumbnails(items))
    payload = {"event": event, "items": items,
               "page": init.get("page") or 1,
               "has_more": _xh_has_more(init, len(items))}
    payload.update(extra)
    emit(payload)
    return len(items)


def _xh_parse_comments(init: dict) -> tuple[list[dict], int]:
    """评论解析：commentsComponent.commentsList.items[]。"""
    lst = ((init.get("commentsComponent") or {}).get("commentsList")) or {}
    items: list[dict] = []
    for it in (lst.get("items") or []):
        if not isinstance(it, dict):
            continue
        au = it.get("author") or {}
        info = au.get("personalInfo") or {}
        geo = info.get("geo") or {}
        created = ""
        if it.get("created"):
            try:
                created = datetime.fromtimestamp(int(it["created"])).strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError, OverflowError):
                created = ""
        items.append({
            "id": str(it.get("id") or ""),
            "author": au.get("name") or "",
            "avatar": au.get("thumbUrl") or "",
            "author_url": au.get("pageUrl") or "",
            "text": it.get("text") or "",
            "created": created,
            "likes": it.get("likes") or 0,
            "country": geo.get("countryName") or "",
            "is_verified": bool(au.get("isVerified")),
            "vip": bool(au.get("isVip")),
            "reply_to": it.get("replyToUserName") or "",
        })
    counters = lst.get("counters") or {}
    total = counters.get("total")
    return items, int(total) if isinstance(total, (int, float)) else len(items)


def _xh_parse_detail(init: dict, page_url: str) -> dict:
    """详情页解析：元数据 + 播放源（mp4 多画质 + hls）+ 评论。"""
    vm = init.get("videoModel") or {}
    if not vm and "/shorts/" in page_url:
        # /shorts/ 短视频页无 videoModel：标题/日期/作者在 layoutPage.momentProps（实测 2026-09-10）
        mp = (init.get("layoutPage") or {}).get("momentProps") or {}
        if isinstance(mp, dict) and mp:
            pub = (mp.get("commentsTarget") or {}).get("publisher") or {}
            vm = {"title": mp.get("title") or "", "id": mp.get("id") or "",
                  "created": mp.get("created") or "",
                  "author": {"name": pub.get("name") or "",
                             "pageURL": pub.get("pageUrl") or "",
                             "thumbUrl": pub.get("thumbUrl") or ""}}
        kind_short_page = True
    else:
        kind_short_page = False
    author = vm.get("author") or {}
    created = ""
    if vm.get("created"):
        try:
            created = datetime.fromtimestamp(int(vm["created"])).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            created = ""
    votes = vm.get("votes") if isinstance(vm.get("votes"), dict) else {}
    # 播放源解密（standard.h264[] mp4 + hls）
    sources = ((init.get("xplayerSettings") or {}).get("sources")) or {}
    mp4_list: list[dict] = []
    for e in ((sources.get("standard") or {}).get("h264") or []):
        if not isinstance(e, dict):
            continue
        url = _xh_cipher_url(e.get("url")) or _xh_cipher_url(e.get("fallback"))
        if url:
            mp4_list.append({"quality": str(e.get("quality") or ""), "url": url})

    def _quality_key(item: dict) -> int:
        m = re.search(r"(\d+)", item.get("quality") or "")
        return int(m.group(1)) if m else 0

    mp4_list.sort(key=_quality_key, reverse=True)
    hls = ""
    for key in ("hls",):
        h = ((sources.get(key) or {}).get("h264")) or {}
        if isinstance(h, dict):
            hls = _xh_cipher_url(h.get("url")) or _xh_cipher_url(h.get("fallback"))
        elif isinstance(h, list):
            for e in h:
                hls = _xh_cipher_url((e or {}).get("url")) or _xh_cipher_url((e or {}).get("fallback"))
                if hls:
                    break
        if hls:
            break
    comments, comment_count = _xh_parse_comments(init)
    m = re.search(r"-xh([0-9a-zA-Z]+)$", page_url.rstrip("/").rsplit("/", 1)[-1]) if page_url else None
    sub = ((init.get("subscriptionComponent") or {}).get("subscribeButtonsProps")
           or {}).get("subscribeButtonProps") or {}
    if not isinstance(sub, dict):
        sub = {}
    duration_sec = vm.get("duration") or 0
    try:
        duration_sec = int(duration_sec or 0)
    except (TypeError, ValueError):
        duration_sec = 0
    kind = "short" if duration_sec and duration_sec <= 60 else "video"
    if kind_short_page:
        kind = "short"
    author_slug = _xh_username_from_url(author.get("pageURL") or "") or (author.get("name") or "")
    cl = ((init.get("commentsComponent") or {}).get("commentsList")) or {}
    target = cl.get("target") if isinstance(cl.get("target"), dict) else {}
    deny = cl.get("denyWriteComment")
    # 标签：改版后 videoModel.tags/categories 常为空，回退 videoTagsComponent.tags（探针 2026-09-09）
    tags = [t.get("name") or "" for t in (vm.get("tags") or [])
            if isinstance(t, dict) and t.get("name")]
    if not tags:
        tags = [t.get("name") or "" for t in ((init.get("videoTagsComponent") or {}).get("tags") or [])
                if isinstance(t, dict) and t.get("name")]
    return {
        "album_name": vm.get("title") or f"xhamster_{vm.get('id') or ''}",
        "album_url": page_url,
        "thumbnail": vm.get("thumbURL") or vm.get("imageURL") or "",
        "files": 1,
        "site": "xhamster",
        "video_id": (m.group(1) if m else "") or str(vm.get("id") or ""),
        "numeric_id": str(vm.get("id") or target.get("id") or ""),
        "author": author.get("name") or (init.get("subscriptionComponent") or {}).get("name") or "",
        "author_url": author.get("pageURL") or (init.get("subscriptionComponent") or {}).get("link") or "",
        "author_slug": author_slug,
        "author_id": str(author.get("id") or sub.get("id") or ""),
        "author_avatar": author.get("thumbUrl") or author.get("thumbURL")
                         or (init.get("subscriptionComponent") or {}).get("thumbUrl") or "",
        "author_intro": "",
        "subscribed": bool(sub.get("subscribed")),
        "subscribers": sub.get("subscribers") or 0,
        "author_videos": (init.get("subscriptionComponent") or {}).get("videos") or 0,
        "views": str(vm.get("views") or ""),
        "likes": str(votes.get("up") or ""),
        "rating": vm.get("rating") or "",
        "duration": _xh_duration_str(duration_sec),
        "created": created,
        "is_hd": bool(vm.get("isHD")),
        "kind": kind,
        "categories": [c.get("name") or "" for c in (vm.get("categories") or [])
                       if isinstance(c, dict) and c.get("name")],
        "tags": tags,
        "mp4_list": mp4_list,
        "hls_url": hls,
        "video_url": (mp4_list[0]["url"] if mp4_list else "") or hls,
        "comments": comments,
        "comment_count": comment_count,
        "comment_entity_type": target.get("type") or "video",
        "comment_entity_id": str(target.get("id") or vm.get("id") or ""),
        "comment_can_write": deny is not True,
        "related": _xh_card_items(init)[:24],
    }


# ---------- 登录态 / 用户名 ----------

_XH_USERNAME_BLOCKLIST = {
    "me", "profiles", "login", "user", "users", "xhamster", "blog", "photos",
    "videos", "favorites", "edit", "settings",
}


def _xh_username_from_url(val: str) -> str:
    """从 /users|channels|pornstars|creators/{slug} 提取 slug（作者页三形态，探针 2026-09-09）。"""
    if not isinstance(val, str) or not val:
        return ""
    m = re.search(r"/(?:users|channels|pornstars|creators)/(?:profiles/)?([A-Za-z0-9_.-]+)(?:[/?#]|$)", val)
    if not m:
        return ""
    name = m.group(1).strip()
    if name.lower() in _XH_USERNAME_BLOCKLIST:
        return ""
    return name


def _xh_username_from_init(init: dict) -> str:
    """从 initials 已知登录节点取用户名（避免全树误命中评论作者）。"""
    if not isinstance(init, dict):
        return ""
    header = ((init.get("layout") or {}).get("headerWrapperProps") or {}).get("headerDesktopProps") or {}
    user_head = (header.get("userHeadProps") or {}).get("user") or {}
    candidates = [
        ((init.get("urls") or {}).get("myProfile")),
        (header.get("a11yNavUrls") or {}).get("profile"),
        user_head.get("pageURL") or user_head.get("pageUrl"),
        user_head.get("name") or user_head.get("username"),
        ((init.get("commentsComponent") or {}).get("authorizedUser") or {}).get("pageURL"),
        ((init.get("commentsComponent") or {}).get("authorizedUser") or {}).get("name"),
        (init.get("profile") or {}).get("pageURL"),
        (init.get("profile") or {}).get("name"),
        (init.get("authorModel") or {}).get("pageURL"),
        (init.get("authorModel") or {}).get("name"),
        (init.get("displayUserModel") or {}).get("pageURL"),
        (init.get("displayUserModel") or {}).get("name"),
    ]
    for val in candidates:
        name = _xh_username_from_url(val) if isinstance(val, str) and "/" in val else (
            val.strip() if isinstance(val, str) else "")
        if name and name.lower() not in _XH_USERNAME_BLOCKLIST and "@" not in name:
            return name
    return ""


def _xhamster_username_from_page(html: str) -> str:
    """从页面 initials JSON 提取当前登录用户名。"""
    return _xh_username_from_init(_xh_initials(html) or {})


def _xhamster_fetch_username() -> str:
    """登录用户名：/users/me 301 → /users/{name}（取最终 URL）；X 改版 301 到
    /users/profiles/me 时从页面 JSON 提取。"""
    global _xhamster_username
    if _xhamster_username:
        return _xhamster_username
    try:
        r = _xh_get("/users/me", timeout=20)
        name = _xh_username_from_url(r.url) or _xhamster_username_from_page(r.text)
        if not name:
            # /users/profiles/me 的 displayUserModel.name 是 "me"，改拉收藏页拿真实 slug
            r2 = _xh_get("/my/favorites/videos", timeout=20)
            if "/login" not in r2.url:
                name = _xhamster_username_from_page(r2.text)
        if name:
            _xhamster_username = name
            # 持久化（登录卡片展示 + 下次启动免网络恢复）
            cred = _generic_load_cookies("xhamster")
            if cred and cred.get("username") != _xhamster_username:
                cred["username"] = _xhamster_username
                _secure_store_write_cred("xhamster", cred)
            return _xhamster_username
    except Exception as exc:
        logging.debug("xHamster 用户名获取失败: %s", exc)
    return ""


def xhamster_check_login(silent: bool = False) -> dict:
    """xHamster 登录态检查（cookie 存在 + 网络验证 + 用户名提取）。"""
    global _xhamster_username
    cred = _generic_load_cookies("xhamster")
    cookies = cred.get("cookies") or {}
    username = cred.get("username") or ""
    has_auth = bool(cookies)
    network_ok = True
    if has_auth:
        _xhamster_restore_session()
        try:
            name = _xhamster_fetch_username()
            if name:
                username = name
            else:
                # 无用户名也可能只是页面结构变化，带 cookie 访问首页 200 即算有效
                r = _xh_get("/newest", timeout=20)
                network_ok = r.status_code == 200
        except Exception:
            network_ok = False  # 网络异常降级为 cookie 存在判定，避免误报
    else:
        _xhamster_username = ""
    logged_in = has_auth and (network_ok or not cookies)
    emit({
        "event": "site_login_result",
        "site": "xhamster",
        "silent": silent,
        "logged_in": logged_in,
        "username": username,
        "cookie_count": len(cookies),
    })
    return {"logged_in": logged_in, "username": username, "cookie_count": len(cookies)}


# ---------- 浏览（首页/分类/短视频/消息/我的） ----------

async def xhamster_home(page: int = 1, sort: str = "newest") -> None:
    """首页列表（最新/最多播放/最高评分/HD/4K/VR）。"""
    emit({"event": "xhamster_home_loading", "loading": True})
    try:
        page = max(1, page or 1)
        sort = sort or "newest"
        bases = [XHAMSTER_SORTS.get(sort, "/newest")]
        for extra in XHAMSTER_SORT_FALLBACKS.get(sort, []):
            if extra not in bases:
                bases.append(extra)
        init = None
        last_exc = None
        used = bases[0]
        for base_path in bases:
            path = f"{base_path}/{page}" if page > 1 else base_path
            try:
                init, _ = await asyncio.to_thread(_xh_fetch, path)
                if init:
                    used = base_path
                    break
            except Exception as exc:
                last_exc = exc
                init = None
        if not init:
            emit({"event": "xhamster_home", "items": [], "page": page, "has_more": False,
                  "sort": sort, "error": (
                      f"获取首页失败: {last_exc}" if last_exc
                      else "页面数据解析失败（可能被规范审查拦截，请检查代理）"
                  ) + "（请检查网络或 xHamster 代理设置）"})
            return
        n = _xh_emit_list("xhamster_home", init, sort=sort)
        logging.info("xHamster 首页 %s 第 %d 页: %d 个（path=%s）", sort, page, n, used)
    except Exception as exc:
        emit({"event": "xhamster_home", "items": [], "page": page, "has_more": False,
              "sort": sort, "error": f"获取首页失败: {exc}（请检查网络或 xHamster 代理设置）"})
    finally:
        emit({"event": "xhamster_home_loading", "loading": False})


async def xhamster_categories() -> None:
    """分类页：热门分类网格 + 分组分类（layoutPage.store.popular）。"""
    emit({"event": "xhamster_categories_loading", "loading": True})
    try:
        init, _ = await asyncio.to_thread(_xh_fetch, "/categories")
        store = ((init or {}).get("layoutPage") or {}).get("store") or {}
        popular = store.get("popular") or {}
        trending = [
            {"id": c.get("id"), "name": c.get("name") or "", "thumb": c.get("thumb") or "",
             "url": c.get("url") or "", "slug": (c.get("url") or "").rstrip("/").rsplit("/", 1)[-1]}
            for c in (popular.get("trending") or {}).get("items") or [] if isinstance(c, dict)
        ]
        groups = []
        for g in popular.get("assignable") or []:
            if not isinstance(g, dict):
                continue
            groups.append({
                "id": g.get("id") or g.get("name") or "",
                "name": g.get("name") or "",
                "items": [
                    {"id": c.get("id"), "name": c.get("name") or "", "thumb": c.get("thumb") or "",
                     "url": c.get("url") or "",
                     "slug": (c.get("url") or "").rstrip("/").rsplit("/", 1)[-1]}
                    for c in g.get("items") or [] if isinstance(c, dict)
                ],
            })
        # 分类缩略图走本地缓存
        thumbs = [{"thumbnail": c["thumb"]} for c in trending if c.get("thumb")]
        for g in groups:
            thumbs.extend({"thumbnail": c["thumb"]} for c in g["items"] if c.get("thumb"))
        _apply_cached_thumbnails(thumbs)
        asyncio.get_event_loop().create_task(_cache_thumbnails(thumbs))
        emit({"event": "xhamster_categories", "trending": trending, "groups": groups})
        logging.info("xHamster 分类: 热门 %d 个，分组 %d 组", len(trending), len(groups))
    except Exception as exc:
        emit({"event": "xhamster_categories", "trending": [], "groups": [],
              "error": f"获取分类失败: {exc}（请检查网络或 xHamster 代理设置）"})
    finally:
        emit({"event": "xhamster_categories_loading", "loading": False})


async def xhamster_category(slug: str, page: int = 1) -> None:
    """分类列表页（/categories/{slug}/{page}）。"""
    slug = (slug or "").strip().strip("/")
    if not slug:
        emit({"event": "xhamster_category", "items": [], "slug": "", "page": 1,
              "has_more": False, "error": "分类参数为空"})
        return
    emit({"event": "xhamster_category_loading", "loading": True})
    try:
        page = max(1, page or 1)
        path = f"/categories/{slug}" + (f"/{page}" if page > 1 else "")
        init, _ = await asyncio.to_thread(_xh_fetch, path)
        if not init:
            emit({"event": "xhamster_category", "items": [], "slug": slug, "page": page,
                  "has_more": False, "error": "页面数据解析失败"})
            return
        _xh_emit_list("xhamster_category", init, slug=slug)
    except Exception as exc:
        emit({"event": "xhamster_category", "items": [], "slug": slug, "page": page,
              "has_more": False, "error": f"获取分类列表失败: {exc}"})
    finally:
        emit({"event": "xhamster_category_loading", "loading": False})


async def xhamster_shorts(page: int = 1) -> None:
    """短视频：优先 /moments，404 时回退时长最短搜索。"""
    emit({"event": "xhamster_shorts_loading", "loading": True})
    try:
        page = max(1, page or 1)
        suffix = f"/{page}" if page > 1 else ""
        init = None
        last_exc = None
        for path in (f"/moments{suffix}", f"/search/%20/duration/shortest{suffix}"):
            try:
                init, _ = await asyncio.to_thread(_xh_fetch, path)
                if init and _xh_cards(init):
                    break
            except Exception as exc:
                last_exc = exc
                init = None
        if not init:
            emit({"event": "xhamster_shorts", "items": [], "page": page, "has_more": False,
                  "error": f"页面数据解析失败{f'（{last_exc}）' if last_exc else ''}"})
            return
        _xh_emit_list("xhamster_shorts", init)
    except Exception as exc:
        emit({"event": "xhamster_shorts", "items": [], "page": page, "has_more": False,
              "error": f"获取短视频失败: {exc}"})
    finally:
        emit({"event": "xhamster_shorts_loading", "loading": False})


async def xhamster_search(query: str, page: int = 1, sort: str = "") -> None:
    """搜索（jp 域内 /search/{kw}/{page}，不经过主站）。"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_start", "query": query, "page": page})
    try:
        page = max(1, page or 1)
        kw = quote(query, safe="")
        sort = sort if sort in XHAMSTER_SEARCH_SORTS else ""
        if sort and sort != "relevance":
            path = f"/search/{kw}/sort/{sort}" + (f"/{page}" if page > 1 else "")
        else:
            path = f"/search/{kw}" + (f"/{page}" if page > 1 else "")
        init, _ = await asyncio.to_thread(_xh_fetch, path)
        items = _xh_card_items(init or {})
        _apply_cached_thumbnails(items)
        asyncio.get_event_loop().create_task(_cache_thumbnails(items))
        emit({
            "event": "search_result",
            "query": query,
            "site": "xhamster",
            "page": page,
            "total_pages": int((init.get("pagination") or {}).get("maxPages")
                               or init.get("maxPages") or 0) if init else 0,
            "has_more": _xh_has_more(init or {}, len(items)),
            "items": items,
            "sort": sort,
        })
        logging.info("xHamster 搜索 '%s' 第 %d 页: %d 个结果", query, page, len(items))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"xHamster 搜索失败: {exc}（请检查网络或 xHamster 代理设置）"})


async def xhamster_video_detail(page_url: str) -> None:
    """视频详情：元数据 + 播放源（解密 mp4 多画质/hls）+ 评论。"""
    emit({"event": "xhamster_detail_loading", "loading": True})
    try:
        init, r = await asyncio.to_thread(_xh_fetch, page_url)
        # /shorts/ 页无 videoModel，元数据在 layoutPage.momentProps（_xh_parse_detail 已回退）
        if not init or (not init.get("videoModel")
                        and not ((init.get("layoutPage") or {}).get("momentProps"))
                        and "/shorts/" not in (page_url or "")):
            emit({"event": "xhamster_video_detail", "video": None,
                  "error": "视频数据解析失败（可能已下架或需登录）"})
            return
        video = _xh_parse_detail(init, page_url)
        if not video.get("mp4_list") and not video.get("hls_url"):
            emit({"event": "xhamster_video_detail", "video": None,
                  "error": "视频没有可用的播放源（可能需登录或会员）"})
            return
        # 头像/缩略图本地缓存
        avatars = [{"thumbnail": video.get("author_avatar")}] + \
                  [{"thumbnail": c["avatar"]} for c in video["comments"] if c.get("avatar")]
        _apply_cached_thumbnails([video] + avatars)
        asyncio.get_event_loop().create_task(_cache_thumbnails([video] + avatars))
        emit({"event": "xhamster_video_detail", "video": video,
              "comments": video.pop("comments", []),
              "comment_count": video.get("comment_count") or 0})
        logging.info("xHamster 视频详情: %s", video.get("album_name"))
    except Exception as exc:
        emit({"event": "xhamster_video_detail", "video": None,
              "error": f"获取视频详情失败: {exc}（请检查网络或 xHamster 代理设置）"})
    finally:
        emit({"event": "xhamster_detail_loading", "loading": False})


async def xhamster_notifications() -> None:
    """消息中心（/notifications → notificationsModel；未登录 302 → login）。"""
    emit({"event": "xhamster_notifications_loading", "loading": True})
    try:
        r = await asyncio.to_thread(_xh_get, "/notifications")
        if "/login" in r.url:
            emit({"event": "xhamster_notifications", "logged_in": False,
                  "counts": {}, "message": "未登录（点左侧按钮在弹出的浏览器内登录后可查看消息）"})
            return
        if r.status_code != 200:
            emit({"event": "xhamster_notifications", "logged_in": False, "counts": {},
                  "message": f"获取消息失败: HTTP {r.status_code}"})
            return
        init = _xh_initials(r.text) or {}
        counts = init.get("notificationsModel") or {}
        emit({"event": "xhamster_notifications", "logged_in": True, "counts": counts})
    except Exception as exc:
        emit({"event": "xhamster_notifications", "logged_in": False, "counts": {},
              "message": f"获取消息失败: {exc}"})
    finally:
        emit({"event": "xhamster_notifications_loading", "loading": False})


async def xhamster_my(tab: str = "favorites", page: int = 1) -> None:
    """我的关注（登录用户关注列表）。favorites=关注用户（/my/favorites/users）；
    videos 分支保留兼容（我的视频已从 UI 移除 2026-09-10）。"""
    global _xhamster_username
    emit({"event": "xhamster_my_loading", "loading": True})
    try:
        _xhamster_restore_session()
        if not _generic_cookie_str("xhamster"):
            emit({"event": "xhamster_my", "logged_in": False, "items": [], "tab": tab,
                  "page": 1, "has_more": False,
                  "message": "未登录（点左侧按钮在弹出的浏览器内登录后可查看）"})
            return
        username = _xhamster_username or _generic_load_cookies("xhamster").get("username") or ""
        page = max(1, page or 1)
        qs = f"?page={page}" if page > 1 else ""
        if tab == "favorites":
            # 我的关注：只拉关注用户列表（视频收藏混入会污染关注视图，2026-09-10 用户指定）
            paths = [f"/my/favorites/users{qs}"]
        else:
            paths = [f"/my/videos{qs}"]
            if username:
                paths.append(f"/users/{username}/videos/{page}" if page > 1
                             else f"/users/{username}/videos")
        init: dict | None = None
        items: list[dict] = []
        seen: set[str] = set()
        logged_out = False
        for path in paths:
            r = await asyncio.to_thread(_xh_get, path)
            if "/login" in r.url or r.status_code in (401, 403):
                logged_out = True
                continue
            if r.status_code != 200:
                continue
            cur = _xh_initials(r.text) or {}
            if init is None:
                init = cur
            if not username:
                username = _xh_username_from_init(cur)
            for card in _xh_card_items(cur):
                key = card.get("album_url") or card.get("video_id") or ""
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                items.append(card)
            if tab == "favorites":
                for u in (cur.get("favoritesUsersCollection") or []):
                    card = _xh_fav_user_card(u)
                    if not card:
                        continue
                    key = card.get("album_url") or card.get("author") or ""
                    if key and key in seen:
                        continue
                    if key:
                        seen.add(key)
                    items.append(card)
        if logged_out and init is None:
            emit({"event": "xhamster_my", "logged_in": False, "items": [], "tab": tab,
                  "page": page, "has_more": False, "message": "登录已过期，请重新登录"})
            return
        if init is None:
            emit({"event": "xhamster_my", "logged_in": True, "items": [], "tab": tab,
                  "page": page, "has_more": False, "username": username,
                  "message": "页面获取失败（可能已下线或结构变化）"})
            return
        if username:
            _xhamster_username = username
            cred = _generic_load_cookies("xhamster")
            if cred and cred.get("username") != username:
                cred["username"] = username
                _secure_store_write_cred("xhamster", cred)
        _apply_cached_thumbnails(items)
        asyncio.get_event_loop().create_task(_cache_thumbnails(items))
        has_more = False
        if init:
            paging = (init.get("favoritesVideoPaging") if tab == "favorites"
                      else None) or {}
            max_pages = paging.get("maxPages") or init.get("maxPages")
            cur_page = paging.get("active") or init.get("page") or page
            if isinstance(max_pages, (int, float)) and max_pages:
                has_more = int(cur_page or 1) < int(max_pages)
            elif tab != "favorites":
                has_more = _xh_has_more(init, len(items))
        msg = ""
        if not items:
            msg = f"「{'我的关注' if tab == 'favorites' else '我的视频'}」暂无内容"
        emit({"event": "xhamster_my", "logged_in": True, "username": username,
              "items": items, "tab": tab, "page": page,
              "message": msg, "has_more": has_more})
    except Exception as exc:
        emit({"event": "xhamster_my", "logged_in": False, "items": [], "tab": tab,
              "page": page, "has_more": False, "message": f"获取我的列表失败: {exc}"})
    finally:
        emit({"event": "xhamster_my_loading", "loading": False})


def _xh_profile_from_init(init: dict, username: str) -> dict:
    """作者页资料（profile / displayUserModel / subscriptionComponent）。"""
    prof = init.get("profile") or init.get("displayUserModel") or init.get("authorModel") or {}
    if not isinstance(prof, dict):
        prof = {}
    sub = ((init.get("subscriptionComponent") or {}).get("subscribeButtonsProps")
           or {}).get("subscribeButtonProps") or {}
    if not isinstance(sub, dict):
        sub = {}
    rel = str(prof.get("currentUserRelation") or "").lower()
    intro = prof.get("introduction") or ""
    if isinstance(intro, dict):
        intro = intro.get("text") or intro.get("value") or ""
    slug = _xh_username_from_url(prof.get("pageURL") or "") or username
    return {
        "username": slug,
        "name": prof.get("name") or slug,
        "id": str(prof.get("id") or sub.get("id") or init.get("profileId") or ""),
        "avatar": prof.get("thumbURL") or prof.get("thumbUrl") or "",
        "intro": str(intro or "")[:500],
        "subscribed": bool(prof.get("subscribed") if "subscribed" in prof else sub.get("subscribed")),
        "favorite": bool(prof.get("favorite")),
        "relation": rel,
        "is_friend": rel == "friend",
        "can_message": bool(prof.get("canReceiveMessage")),
        "videos_count": (init.get("subscriptionComponent") or {}).get("videos") or 0,
        "subscribers": sub.get("subscribers") or 0,
    }


def _xh_gallery_card(it: dict, author: str = "") -> dict | None:
    """作者画廊列表条目。"""
    if not isinstance(it, dict):
        return None
    page = it.get("pageURL") or it.get("url") or ""
    gid = str(it.get("galleryID") or it.get("id") or "")
    if not page and not gid:
        return None
    icon = str(it.get("iconNamePhp") or it.get("icon") or "").lower()
    access = ""
    if "friend" in icon:
        access = "friends"
    elif "lock" in icon or "private" in icon:
        access = "private"
    if str(it.get("privacy") or "").lower() in ("friends", "friend"):
        access = "friends"
    elif str(it.get("privacy") or "").lower() in ("private", "locked"):
        access = "private"
    n = it.get("imgCount") or it.get("quantity") or it.get("photosCount") or 0
    return {
        "album_name": it.get("title") or it.get("titleLocalized") or f"gallery_{gid}",
        "album_url": page,
        "thumbnail": it.get("thumbURL") or it.get("imageURL") or it.get("previewThumbURL") or "",
        "files": n or 1,
        "site": "xhamster",
        "video_id": gid,
        "author": author or ((it.get("author") or {}).get("name") if isinstance(it.get("author"), dict) else "") or "",
        "author_url": "",
        "views": str(it.get("views") or ""),
        "likes": str(it.get("favorites") or ""),
        "duration": f"{n} 张" if n else "",
        "created": "",
        "is_hd": False,
        "kind": "gallery",
        "access": access,
        "numeric_id": gid,
    }


def _xh_gallery_items(init: dict, author: str = "") -> list[dict]:
    items = []
    arr = ((init.get("contentComponent") or {}).get("items")) or []
    for it in arr:
        card = _xh_gallery_card(it, author)
        if card:
            items.append(card)
    return items


def _xh_parse_gallery(init: dict, page_url: str) -> dict:
    gp = init.get("galleryPage") or {}
    photos = gp.get("photoItems") or []
    info = ((gp.get("infoProps") or {}).get("authorInfoProps")) or {}
    author = info.get("authorName") or ""
    author_url = info.get("authorLink") or ""
    title = ""
    crumbs = ((gp.get("breadCrumbsProps") or {}).get("breadCrumbs")) or []
    if crumbs:
        title = crumbs[-1].get("name") or ""
    if not title:
        title = f"gallery_{gp.get('id') or ''}"
    files = []
    for i, ph in enumerate(photos, 1):
        if not isinstance(ph, dict):
            continue
        src = ph.get("imgSrc") or ""
        if not src:
            continue
        ext = ".jpg"
        if ".png" in src:
            ext = ".png"
        elif ".webp" in src:
            ext = ".webp"
        files.append({
            "filename": f"{i:03d}{ext}",
            "size": None,
            "item_page": ph.get("link") or page_url,
            "status": "ok",
            "thumbnail": src,
            "media_url": src,
            "site": "xhamster",
            "artist": author,
            "post_title": title,
            "media_type": "image",
            "xh_kind": "gallery",
        })
    return {
        "album_name": title,
        "album_url": page_url,
        "thumbnail": (photos[0].get("imgSrc") if photos else "") or "",
        "site": "xhamster",
        "kind": "gallery",
        "author": author,
        "author_url": author_url,
        "files": files,
        "photos_count": gp.get("photosCount") or len(files),
        "page": ((gp.get("paginationProps") or {}).get("currentPageNumber")) or 1,
        "max_pages": ((gp.get("paginationProps") or {}).get("lastPageNumber")) or 1,
    }


def _xh_author_prefix(val: str) -> str:
    """author_url 或显示名 → 作者页路径前缀（探针 2026-09-09 三形态）。

    - /users/{slug}      普通用户（列表在 /videos 子页）
    - /channels/{slug}   频道（裸页即列表；无短视频）
    - /pornstars|creators/{slug}  影人/创作者（裸页即列表；短视频在 {prefix}/shorts）
    纯显示名（无 URL）按 xhamster slug 规则折算到 /users/。
    """
    val = (val or "").strip()
    if not val:
        return ""
    if val.startswith("/"):
        cand = val.split("?")[0].rstrip("/")
        if re.match(r"/(?:users|channels|pornstars|creators)/[A-Za-z0-9_.-]+$", cand):
            return cand
    m = re.search(r"xhamster\.com(/[a-z]+/[A-Za-z0-9_.-]+)", val)
    if m and re.match(r"/(?:users|channels|pornstars|creators)/", m.group(1)):
        return m.group(1).rstrip("/")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", val).strip("-").lower()
    return f"/users/{slug}" if slug else ""


def _xh_moment_card(it: dict) -> dict | None:
    """momentsComponent.videoThumbProps 条目 → 短视频卡片（/shorts/ 链接，竖屏封面）。"""
    if not isinstance(it, dict):
        return None
    page_url = it.get("pageURL") or ""
    vid = str(it.get("id") or "")
    if not page_url and not vid:
        return None
    m = re.search(r"-xh([0-9a-zA-Z]+)$", page_url.rstrip("/").rsplit("/", 1)[-1]) if page_url else None
    return {
        "album_name": it.get("title") or f"xhamster_short_{vid}",
        "album_url": page_url or (f"{XHAMSTER_BASE}/shorts/{vid}" if vid else ""),
        "thumbnail": it.get("imageURL") or it.get("thumbURL") or "",
        "files": 1,
        "site": "xhamster",
        "video_id": (m.group(1) if m else "") or vid,
        "author": "",
        "author_url": "",
        "views": str(it.get("views") or ""),
        "likes": "",
        "rating": "",
        "duration": "",
        "duration_sec": 0,
        "created": "",
        "is_hd": False,
        "kind": "short",
        "access": "",
        "numeric_id": vid,
    }


def _xh_moments_page(init: dict) -> tuple[list[dict], bool]:
    """/shorts 页 init → (moments 卡片列表, has_more)（pagination.pageLinkTemplate 分页）。"""
    mc = (init or {}).get("momentsComponent") or {}
    items = [_xh_moment_card(it)
             for it in ((mc.get("videoListProps") or {}).get("videoThumbProps") or [])]
    items = [c for c in items if c]
    pg = mc.get("pagination") or {}
    try:
        has_more = int(pg.get("currentPageNumber") or 1) < int(pg.get("lastPageNumber") or 0)
    except (TypeError, ValueError):
        has_more = False
    return items, has_more


def _xh_profile_from_bare_page(init: dict, slug: str) -> dict:
    """pornstar/creator/channel 裸页资料（aboutMeComponent；无 profile 键，探针 2026-09-09）。"""
    ab = init.get("aboutMeComponent") if isinstance(init.get("aboutMeComponent"), dict) else {}
    name = ab.get("pornstarUserName") or slug
    intro = str(ab.get("text") or "")
    personal = ab.get("personalInfoList") or []
    # value 可能是 str 也可能是 list（探针实测存在列表值），统一展平
    def _flat(v) -> str:
        if isinstance(v, list):
            return " ".join(str(x) for x in v if x)
        return str(v or "")
    info_line = " · ".join(filter(None, (_flat(p.get("value")) for p in personal
                                         if isinstance(p, dict))))
    if info_line:
        intro = (intro + ("\n" if intro else "") + info_line)[:500]
    return {
        "username": slug,
        "name": name,
        "id": "",
        "avatar": "",
        "intro": intro,
        "subscribed": False,
        "favorite": False,
        "relation": "",
        "is_friend": False,
        "can_message": False,
        "videos_count": 0,
        "subscribers": 0,
    }


def _xh_user_profile_enriched(prefix: str, slug: str, videos_init: dict) -> dict:
    """用户形态资料：videos 页的 profile 键常缺失（实测 drdrej/ayakkyu 均空），
    头像/名字在裸页 displayUserModel 里 —— 合并补齐（2026-09-09）。"""
    profile = _xh_profile_from_init(videos_init or {}, slug)
    if profile.get("avatar"):
        return profile
    try:
        bare, _ = _xh_fetch(prefix)
        p2 = _xh_profile_from_init(bare or {}, slug)
        for k in ("name", "avatar", "intro", "subscribers", "id"):
            if not profile.get(k) and p2.get(k):
                profile[k] = p2[k]
    except Exception:
        pass
    return profile


async def xhamster_user_videos(username: str, page: int = 1, tab: str = "videos") -> None:
    """作者页：视频 / 短视频 / 画廊（支持 users/channels/pornstars/creators 四空间）。"""
    username = (username or "").strip().strip("/")
    prefix = _xh_author_prefix(username)
    if not prefix:
        return
    slug = prefix.rsplit("/", 1)[-1]
    tab = tab if tab in ("videos", "shorts", "galleries") else "videos"
    is_user_space = prefix.startswith("/users/")
    emit({"event": "xhamster_user_loading", "loading": True, "tab": tab})
    try:
        page = max(1, page or 1)
        profile: dict = {}
        items: list[dict] = []
        has_more = False

        if tab == "shorts":
            # 用户空间也有独立短视频页：数据在 videoListComponent.videoThumbProps 顶层
            # （与 creators/pornstars 的 momentsComponent.videoListProps.videoThumbProps 键
            #   路径不同——2026-09-10 真浏览器取证，ayakkyu 实测 45 条与站面计数一致）
            shorts_path = f"{prefix}/shorts" + (f"/{page}" if page > 1 else "")
            try:
                init_s, _ = await asyncio.to_thread(_xh_fetch, shorts_path)
            except Exception:
                init_s = None
            if is_user_space:
                raw = ((init_s or {}).get("videoListComponent") or {}).get("videoThumbProps") or []
            else:
                raw = (((init_s or {}).get("momentsComponent") or {}).get("videoListProps")
                       or {}).get("videoThumbProps") or []
            items = [c for c in (_xh_moment_card(it) for it in raw if isinstance(it, dict)) if c]
            if items:
                if is_user_space:
                    profile = await asyncio.to_thread(_xh_user_profile_enriched, prefix, slug, init_s)
                else:
                    profile = _xh_profile_from_bare_page(init_s or {}, slug)
                for c in items:
                    if not c.get("author"):
                        c["author"] = profile.get("name") or slug
                        c["author_url"] = f"{XHAMSTER_BASE}{prefix}"
                if is_user_space:
                    # 用户空间单页下发全量（实测 45 条=Tab 计数），无翻页
                    has_more = False
                else:
                    # creators/pornstars 空间有真实分页（实测 8 页/48 条），沿用 pagination 判断
                    pg = ((init_s or {}).get("momentsComponent") or {}).get("pagination") or {}
                    try:
                        has_more = int(pg.get("currentPageNumber") or 1) < int(pg.get("lastPageNumber") or 0)
                    except (TypeError, ValueError):
                        has_more = False
            elif is_user_space:
                # 兜底：shorts 页无数据（极少数）→ 退回旧方案，从 videos 列表按时长聚合（≤12 页）
                items = []
                seen_ids = set()
                profile = {}
                for pg_no in range(1, 13):
                    pg_path = f"{prefix}/videos" + (f"/{pg_no}" if pg_no > 1 else "")
                    init, _ = await asyncio.to_thread(_xh_fetch, pg_path)
                    if not init:
                        break
                    if pg_no == 1:
                        profile = await asyncio.to_thread(
                            _xh_user_profile_enriched, prefix, slug, init)
                    cards = _xh_card_items(init)
                    for c in cards:
                        if not c.get("author"):
                            c["author"] = profile.get("name") or slug
                            c["author_url"] = f"{XHAMSTER_BASE}{prefix}"
                    page_shorts = ([c for c in cards if c.get("kind") == "short"]
                                   or [c for c in cards if int(c.get("duration_sec") or 0) <= 90])
                    for c in page_shorts:
                        if c["video_id"] not in seen_ids:
                            seen_ids.add(c["video_id"])
                            items.append(c)
                    if not cards:
                        break
                    max_pages = init.get("maxVideoPages") or init.get("maxPages") or 0
                    try:
                        if pg_no >= int(max_pages or 0):
                            break
                    except (TypeError, ValueError):
                        pass
                has_more = False
            else:
                emit({"event": "xhamster_user_videos", "username": slug, "items": [],
                      "page": page, "has_more": False, "tab": tab, "profile": {},
                      "error": "该作者没有短视频"})
                return
        elif tab == "galleries" and is_user_space:
            path = f"{prefix}/photos" + (f"?page={page}" if page > 1 else "")
            init, _ = await asyncio.to_thread(_xh_fetch, path)
            if not init:
                emit({"event": "xhamster_user_videos", "username": slug, "items": [],
                      "page": page, "has_more": False, "tab": tab, "profile": {},
                      "error": "画廊页解析失败"})
                return
            profile = _xh_profile_from_init(init, slug)
            items = _xh_gallery_items(init, profile.get("name") or slug)
            # /photos?page=N 被站点无视（实测 2026-09-09 返回同内容），无真实翻页 → 不给加载更多
            has_more = False
        else:  # videos
            if is_user_space:
                path = f"{prefix}/videos" + (f"/{page}" if page > 1 else "")
            else:
                path = prefix + (f"?page={page}" if page > 1 else "")
            init, _ = await asyncio.to_thread(_xh_fetch, path)
            if not init:
                emit({"event": "xhamster_user_videos", "username": slug, "items": [],
                      "page": page, "has_more": False, "tab": tab, "profile": {},
                      "error": "页面数据解析失败"})
                return
            if is_user_space:
                profile = await asyncio.to_thread(_xh_user_profile_enriched, prefix, slug, init)
            else:
                profile = _xh_profile_from_bare_page(init, slug)
            cards = _xh_card_items(init)
            for c in cards:
                if not c.get("author"):
                    c["author"] = profile.get("name") or slug
                    c["author_url"] = f"{XHAMSTER_BASE}{prefix}"
            items = [c for c in cards if c.get("kind") != "short"] or cards
            max_pages = init.get("maxVideoPages") or init.get("maxPages") or 0
            try:
                has_more = page < int(max_pages or 0)
            except (TypeError, ValueError):
                has_more = bool(items) and len(items) >= 24
        _apply_cached_thumbnails(items)
        asyncio.get_event_loop().create_task(_cache_thumbnails(items))
        emit({"event": "xhamster_user_videos", "username": slug, "items": items,
              "page": page, "has_more": has_more, "tab": tab, "profile": profile})
    except PermissionError as exc:
        # /shorts 不存在（普通用户/频道无短视频）等 404 场景：给空列表不报错
        emit({"event": "xhamster_user_videos", "username": slug, "items": [],
              "page": page, "has_more": False, "tab": tab,
              "profile": {}, "error": "" if tab == "shorts" else f"获取失败: {exc}"})
    except Exception as exc:
        emit({"event": "xhamster_user_videos", "username": slug, "items": [],
              "page": page, "has_more": False, "tab": tab, "profile": {},
              "error": f"获取用户内容失败: {exc}"})
    finally:
        emit({"event": "xhamster_user_loading", "loading": False, "tab": tab})


# ---------- 解析/批量下载 ----------

def is_xhamster_url(url: str) -> bool:
    return bool(re.search(r"https?://([a-z0-9.-]*\.)?xhamster\.com/", (url or ""), re.I))


async def xhamster_inspect(url: str, options: dict) -> None:
    """解析视频页或画廊 → 文件列表（下载时重新解析直链，密文会过期）。"""
    if not is_xhamster_url(url):
        emit({"event": "inspect_error", "message": "无法识别的 xHamster 链接"})
        return
    try:
        init, _ = await asyncio.to_thread(_xh_fetch, url)
        if init and (init.get("galleryPage") or "/photos/gallery/" in url):
            gal = _xh_parse_gallery(init or {}, url)
            items = gal.get("files") or []
            if not items:
                emit({"event": "inspect_error", "message": "画廊没有可下载的图片"})
                return
            album_id = f"xhamster_gal_{gal.get('album_url') or url}"
            _apply_cached_thumbnails(items)
            _mark_items_new(album_id, items)
            emit({
                "event": "inspect_complete",
                "album_name": gal.get("album_name") or "画廊",
                "album_id": album_id,
                "is_album": True,
                "items": items,
            })
            asyncio.get_event_loop().create_task(_cache_thumbnails(items))
            return
        # /shorts/ 页无 videoModel：走 _xh_parse_detail 的 momentProps 回退
        if not init or (not init.get("videoModel")
                        and not ((init.get("layoutPage") or {}).get("momentProps"))
                        and "/shorts/" not in (url or "")):
            emit({"event": "inspect_error", "message": "视频数据解析失败（可能已下架或需登录）"})
            return
        video = _xh_parse_detail(init, url)
        if not video["mp4_list"] and not video["hls_url"]:
            emit({"event": "inspect_error", "message": "视频没有可用的播放源（可能需登录或会员）"})
            return
        title = sanitize_directory_name((video["album_name"] or "").strip()) or \
            f"xhamster_{video['video_id']}"
        kind = video.get("kind") or "video"
        items = [{
            "filename": f"{title}.mp4",
            "size": None,
            "item_page": url,
            "status": "ok",
            "thumbnail": video.get("thumbnail") or "",
            "media_url": (video["mp4_list"][0]["url"] if video["mp4_list"] else "") or video.get("hls_url") or "",
            "hls_url": video.get("hls_url") or "",
            "site": "xhamster",
            "video_id": video["video_id"],
            "post_title": video["album_name"],
            "post_date": video.get("created") or "",
            "artist": video.get("author") or video.get("author_slug") or "",
            "media_type": "video",
            "xh_kind": kind,
        }]
        album_id = f"xhamster_{video['video_id']}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": video["album_name"],
            "album_id": album_id,
            "is_album": False,
            "items": items,
        })
        asyncio.get_event_loop().create_task(_cache_thumbnails(items))
        logging.info("xHamster 解析完成: %s", video["video_id"])
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"xHamster 解析失败: {exc}（请检查网络或 xHamster 代理设置）"})
        logging.exception("xHamster 解析过程出错")


def _xh_api_call(action: str, request_data: dict, referer: str = "",
                 as_get: bool = False) -> tuple[bool, object]:
    """x-api 动作调用（关注/评论等登录动作的唯一真实通道，2026-09-18 抓包实锤）。

    协议（真浏览器 webRequest 抓包）：
      POST /x-api  body=[{"name": action, "requestData": {...}}]
      Content-Type: text/plain;charset=UTF-8 + X-Requested-With: XMLHttpRequest
      小载荷（<200B）的查询类动作可 GET /x-api?r=<json>；**无需 csrf 头**。
    动作名 = <模型名>Sync / <模型名>Fetch（如 entitySubscriptionModelSync、
      commentModelSync、entityCommentCollectionFetch）。
    TLS 指纹：requests 的 python 指纹会被 Cloudflare 403（空 body），
      必须 curl_cffi 模拟 Chrome（requirements 已有，缺失时退回 requests 尽力而为）。
    返回 (ok, item)：ok=HTTP 200 且 JSON 正常；动作级成败看 item.extras.result。
    """
    _xhamster_restore_session()
    _xhamster_throttle()
    cookie_str = _generic_cookie_str("xhamster")
    if not cookie_str:
        return False, "未登录"
    body = json.dumps([{"name": action, "requestData": request_data}],
                      separators=(",", ":"))
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": XHAMSTER_BASE,
        "Referer": referer or f"{XHAMSTER_BASE}/",
        "Accept": "*/*",
    }
    try:
        r = None
        try:
            from curl_cffi import requests as _creq
            sess = _creq.Session(impersonate="chrome", proxies={
                "http": _xhamster_proxy, "https": _xhamster_proxy})
            sess.headers["Cookie"] = cookie_str
            if as_get and len(body) < 200:
                r = sess.get(f"{XHAMSTER_BASE}/x-api?r={quote(body)}&_={time.time()}",
                             timeout=25, headers=headers)
            else:
                r = sess.post(f"{XHAMSTER_BASE}/x-api", data=body.encode("utf-8"),
                              timeout=25, headers=headers)
        except ImportError:
            r = _xhamster_session.post(
                f"{XHAMSTER_BASE}/x-api", data=body.encode("utf-8"),
                timeout=25, headers=headers)
    except Exception as exc:
        return False, f"请求失败: {exc}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    try:
        data = r.json()
    except Exception:
        return False, f"响应非 JSON: {str(getattr(r, 'text', ''))[:120]}"
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return False, "响应格式异常"
    return True, data[0]


def _xh_api_result(ok: bool, item: object) -> tuple[bool, str]:
    """动作级判定：extras.result is True 才算成功；返回 (成功, 错误消息)。"""
    if not ok:
        return False, str(item)
    extras = (item or {}).get("extras") or {}
    if extras.get("result") is True:
        return True, ""
    return False, extras.get("errorMessage") or "动作未生效"


async def xhamster_subscribe(user_id: str = "", username: str = "", subscribe: bool = True) -> None:
    """关注 / 取消关注（x-api entitySubscriptionModelSync，2026-09-18 抓包实锤）。

    协议：requestData={"model":{"entityModel":"userModel","entityID":<数字id>,"state":bool}}；
    真浏览器往返验证（state=false→页面 subscribed=false，state=true→恢复）。
    user_id 必须是数字 id（作者页 profile.id / 详情 author_id）。
    """
    user_id = str(user_id or "").strip()
    username = (username or "").strip().strip("/")
    try:
        _xhamster_restore_session()
        if not _generic_cookie_str("xhamster"):
            emit({"event": "xhamster_subscribe_result", "ok": False,
                  "message": "未登录，无法关注"})
            return
        if not user_id.isdigit():
            # 频道/影人裸页没有 profile.id（实测），订阅模型名也未验证——明确告知不硬造
            emit({"event": "xhamster_subscribe_result", "ok": False,
                  "username": username, "user_id": user_id,
                  "subscribed": not subscribe,
                  "message": "该作者页没有可用的数字 id，暂不支持一键关注"})
            return
        ok, item = await asyncio.to_thread(
            _xh_api_call, "entitySubscriptionModelSync",
            {"model": {"entityModel": "userModel",
                       "entityID": int(user_id), "state": bool(subscribe)}},
            f"{XHAMSTER_BASE}/users/{username}" if username else "")
        good, err = _xh_api_result(ok, item)
        if good:
            emit({"event": "xhamster_subscribe_result", "ok": True,
                  "username": username, "user_id": user_id,
                  "subscribed": bool(subscribe),
                  "message": "已关注" if subscribe else "已取消关注"})
        else:
            # 失败：前端会把 subscribed 拨回原状态（not subscribe = 点击前的状态）
            emit({"event": "xhamster_subscribe_result", "ok": False,
                  "username": username, "user_id": user_id,
                  "subscribed": not subscribe,
                  "message": f"关注操作未生效（{err}）"})
    except Exception as exc:
        emit({"event": "xhamster_subscribe_result", "ok": False, "username": username,
              "user_id": user_id, "subscribed": not subscribe,
              "message": f"关注失败: {exc}"})


async def xhamster_add_comment(entity_type: str, entity_id: str, text: str,
                               page_url: str = "") -> None:
    """视频下发表评论。"""
    text = (text or "").strip()
    entity_id = str(entity_id or "").strip()
    entity_type = (entity_type or "video").strip() or "video"
    if not text:
        emit({"event": "xhamster_comment_result", "ok": False, "message": "评论内容为空"})
        return
    try:
        _xhamster_restore_session()
        if not _generic_cookie_str("xhamster"):
            emit({"event": "xhamster_comment_result", "ok": False, "message": "未登录，无法评论"})
            return
        payload = {"text": text, "entity": {"type": entity_type, "id": int(entity_id) if entity_id.isdigit() else entity_id}}
        last_err = ""
        ok = False
        for path in (
            "/api/front/comments",
            "/api/front/comment",
            f"/api/front/{entity_type}s/{entity_id}/comments",
        ):
            try:
                await asyncio.to_thread(_xh_api_post, path, payload)
                ok = True
                break
            except Exception as exc:
                last_err = str(exc)
        if ok and page_url:
            await xhamster_video_detail(page_url)
        emit({"event": "xhamster_comment_result", "ok": ok,
              "message": "评论已发布" if ok else f"评论接口未通（{last_err}）"})
    except Exception as exc:
        emit({"event": "xhamster_comment_result", "ok": False, "message": f"发表评论失败: {exc}"})


def _xh_kind_folder(kind: str) -> str:
    return {"short": "短视频", "gallery": "画廊", "image": "画廊"}.get(kind or "", "视频")


def _xh_batch_item_from_card(card: dict, init: dict | None, page_url: str) -> list[dict]:
    """卡片/详情 → 下载条目（视频一条，画廊多图）。"""
    if "/photos/gallery/" in page_url or (init or {}).get("galleryPage"):
        gal = _xh_parse_gallery(init or {}, page_url)
        files = gal.get("files") or []
        artist = gal.get("author") or card.get("author") or ""
        for f in files:
            f["artist"] = artist
            f["xh_kind"] = "gallery"
            f["media_type"] = "image"
        return files
    video = _xh_parse_detail(init or {}, page_url)
    # /shorts/ 页 videoModel 的 title/id 均空 → 详情标题退化为占位 "xhamster_"，
    # 此时应回退卡片标题（列表/短视频 Tab 带真实 title）
    v_title = sanitize_directory_name((video.get("album_name") or "").strip())
    if not v_title or re.fullmatch(r"xhamster_?", v_title):
        v_title = ""
    title = v_title or sanitize_directory_name((card.get("album_name") or "").strip()) or \
        f"xhamster_{video.get('video_id') or ''}"
    kind = card.get("kind") or video.get("kind") or "video"
    if kind not in ("video", "short", "gallery"):
        kind = "short" if int(video.get("duration") and 0 or video.get("duration_sec") or 0) <= 60 else "video"
    return [{
        "filename": f"{title}.mp4",
        "size": None,
        "item_page": page_url,
        "status": "ok",
        "thumbnail": video.get("thumbnail") or card.get("thumbnail") or "",
        "media_url": ((video.get("mp4_list") or [{}])[0].get("url") if video.get("mp4_list") else "") or video.get("hls_url") or "",
        "hls_url": video.get("hls_url") or "",
        "site": "xhamster",
        "video_id": video.get("video_id") or "",
        "post_title": video.get("album_name") or title,
        "post_date": video.get("created") or "",
        "artist": video.get("author") or card.get("author") or "",
        "media_type": "video",
        "xh_kind": kind,
    }]


async def xhamster_batch_download(page_urls: list, options: dict,
                                  items: list | None = None) -> None:
    """批量下载：视频/短视频/画廊。目录 作者名/视频|短视频|画廊/文件。"""
    cards = [it for it in (items or []) if isinstance(it, dict) and it.get("album_url")]
    if not cards:
        page_urls = [u.strip() for u in (page_urls or []) if u.strip()]
        cards = [{"album_url": u, "kind": "video"} for u in page_urls]
    cards = [c for c in cards if c.get("kind") != "user" and c.get("album_url")]
    if not cards:
        emit({"event": "xhamster_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "请先勾选要下载的视频或画廊"})
        return
    total = len(cards)
    failed: list[str] = []
    out: list[dict] = []
    # 占位式批量：先立即创建空任务（下载管理面板秒见），解析中增量并入，完成后统一启动
    task_album_id = f"xhamster_batch:{int(time.time() * 1000)}"
    task_id = download_manager.submit(
        f"{XHAMSTER_BASE}/", [], options, "xHamster 批量下载", task_album_id,
    )
    emit({"event": "xhamster_batch_progress", "done": 0, "total": total,
          "message": f"正在解析 {total} 个条目..."})
    try:
        for i, card in enumerate(cards):
            purl = card.get("album_url") or ""
            try:
                init, _ = await asyncio.to_thread(_xh_fetch, purl)
                new_items = _xh_batch_item_from_card(card, init, purl)
                out.extend(new_items)
                if new_items:
                    download_manager.submit(
                        f"{XHAMSTER_BASE}/", new_items, options,
                        "xHamster 批量下载", task_album_id,
                    )
            except Exception as exc:
                failed.append(f"{purl.rsplit('/', 1)[-1][:40]}（{exc}）")
                logging.warning("xHamster 批量解析失败 %s: %s", purl, exc)
            emit({"event": "xhamster_batch_progress", "done": i + 1, "total": total,
                  "message": f"解析进度 {i + 1}/{total}"})
        if out:
            download_manager.start(task_id)
        summary = f"批量下载已提交：{len(out)} 个文件 / {total} 个条目"
        if failed:
            summary += f"；失败：{'、'.join(failed[:6])}"
        emit({"event": "xhamster_batch_done", "done": len(out), "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "xhamster_batch_done", "done": len(out), "total": total,
              "failed": failed, "message": f"批量下载中断: {exc}"})
