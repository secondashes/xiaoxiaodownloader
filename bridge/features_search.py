# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：搜索历史 / 本地收藏 / EX 搜索游标 / 隐藏 tags。

由 gui_bridge.py 按物理顺序拆出（原行区间 12135-12622），
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
# 搜索历史（日常 tags 快速搜索）
# ============================
SEARCH_HISTORY_FILE = "cache/search_history.json"
SEARCH_HISTORY_MAX = 100


def _load_search_history() -> list[dict]:
    """读取搜索历史（最近在前）。"""
    try:
        with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_search_history(history: list[dict]) -> None:
    """保存搜索历史。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[:SEARCH_HISTORY_MAX], f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存搜索历史失败: %s", exc)


def add_search_history(query: str, site: str, search_mode: str = "") -> None:
    """记录一次搜索（同关键词+站点去重，移到最前）。"""
    query = (query or "").strip()
    if not query:
        return
    history = _load_search_history()
    history = [
        h for h in history
        if not (h.get("query") == query and h.get("site") == site)
    ]
    history.insert(0, {
        "query": query,
        "site": site or "bunkr",
        "search_mode": search_mode or "",
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    _save_search_history(history)


def delete_search_history(query: str, site: str) -> None:
    """删除一条搜索历史。"""
    history = _load_search_history()
    history = [
        h for h in history
        if not (h.get("query") == query and h.get("site") == site)
    ]
    _save_search_history(history)


def clear_search_history() -> None:
    """清空搜索历史。"""
    _save_search_history([])


# ============================
# 本地收藏（跨站点快速打开）
# ============================
LOCAL_FAVORITES_FILE = "cache/local_favorites.json"


def _load_local_favorites() -> list[dict]:
    """读取本地收藏列表。"""
    try:
        with open(LOCAL_FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_local_favorites(favorites: list[dict]) -> None:
    """保存本地收藏列表。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(LOCAL_FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存本地收藏失败: %s", exc)


def add_local_favorite(item: dict) -> None:
    """添加本地收藏（作者/画集/标签等，按 URL 去重）。"""
    url = (item.get("url") or item.get("album_url") or "").strip()
    if not url:
        emit({"event": "local_favorites_error", "message": "收藏缺少 URL"})
        return
    favorites = _load_local_favorites()
    if any(f.get("url") == url for f in favorites):
        emit({"event": "local_favorites_saved", "message": "已在收藏中", "duplicate": True})
        return
    favorites.insert(0, {
        "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
        "type": item.get("type", "gallery"),
        "title": item.get("title", "") or url,
        "url": url,
        "site": item.get("site", ""),
        "search_query": item.get("search_query", ""),
        "thumbnail": item.get("thumbnail", ""),
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    _save_local_favorites(favorites)
    emit({"event": "local_favorites_saved", "message": "已收藏到本地"})


def delete_local_favorite(fav_id: str) -> None:
    """删除一条本地收藏。"""
    favorites = _load_local_favorites()
    favorites = [f for f in favorites if f.get("id") != fav_id]
    _save_local_favorites(favorites)
    emit({"event": "local_favorites", "items": favorites})


# ============================
# ExHentai 搜索（画廊关键词搜索，游标分页）
# ============================
# ExHentai 搜索页的 page= 参数无效，翻页必须用 next=<上页最后画廊ID> 游标。
# 游标缓存到 cache/exhentai_cursors.json，支持上一页/下一页/任意跳页（跳页时顺序推进）。
EX_CURSORS_FILE = "cache/exhentai_cursors.json"


def _load_ex_cursors() -> dict:
    """读取游标缓存：{query: {"2": gid, "3": gid, "total_pages": N}}。"""
    try:
        with open(EX_CURSORS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_ex_cursors(data: dict) -> None:
    try:
        os.makedirs("cache", exist_ok=True)
        with open(EX_CURSORS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        logging.exception("ExHentai 游标缓存保存失败")


def _parse_ex_gallery_ids(html: str) -> list[str]:
    """按出现顺序提取页面里的画廊 ID 列表（游标用）。"""
    return re.findall(r"/g/(\d+)/[0-9a-f]+/?", html)


def _parse_ex_search_page(html: str) -> list[dict]:
    """解析搜索结果页的画廊列表（含标题/缩略图/标签/页数/日期/发布者）。"""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    # 直接取所有画廊链接（Minimal/Compact/Extended 布局通用）
    for link in soup.select("a[href*='/g/']"):
        href = (link.get("href") or "")
        if not href.startswith("http") or "/g/" not in href:
            continue
        # 跳过缩略图/广告位等非画廊行链接：画廊链接格式 /g/数字/token/
        if not re.search(r"/g/\d+/[0-9a-f]+/?", href):
            continue

        # 画廊所在行（Extended/Compact 为 tr，Minimal 为 div）
        row = link.find_parent("tr") or link.find_parent("div")

        # 标题：优先 .glink 节点（列表布局的标准标题），否则取链接文本
        title = ""
        if row:
            glink = row.select_one(".glink")
            if glink:
                title = glink.get_text(strip=True)
        if not title:
            title = link.get_text(strip=True) or link.get("title", "")
        if not title:
            title = href.rstrip("/").rsplit("/", 1)[-1]

        # 缩略图（懒加载属性优先）
        thumb = ""
        if row:
            img = row.select_one("img")
            if img:
                thumb = img.get("data-src") or img.get("src") or ""
                if not thumb.startswith("http"):
                    thumb = ""

        # 标签（.gt 节点，title 属性形如 "Artist:xxx"）
        tags: list[str] = []
        if row:
            for gt in row.select(".gt"):
                t = gt.get("title") or gt.get_text(strip=True)
                if t:
                    tags.append(t)

        # 行文本提取：页数 / 发布时间 / 发布者
        pages = ""
        posted = ""
        uploader = ""
        if row:
            row_text = row.get_text(" ", strip=True)
            m = re.search(r"(\d+)\s*pages?", row_text, re.I)
            if m:
                pages = m.group(1)
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", row_text)
            if m:
                posted = m.group(1)
            up = row.select_one("a[href*='/uploader/']")
            if up:
                uploader = up.get_text(strip=True)

        items.append({
            "title": title,
            "album_name": title,
            "album_url": href,
            "url": href,
            "thumbnail": thumb,
            "site": "exhentai",
            "type": "gallery",
            "tags": tags[:8],
            "pages": pages,
            "posted": posted,
            "uploader": uploader,
        })

    # 去重
    seen: set[str] = set()
    return [i for i in items if not (i["url"] in seen or seen.add(i["url"]))]


# ============================
# ExHentai 隐藏 tags（用户手动标记，解析/收藏结果中不显示）
# ============================
EXHENTAI_HIDDEN_TAGS_FILE = "cache/exhentai_hidden_tags.json"


def _load_ex_hidden_tags() -> list[str]:
    """读取隐藏标签列表（长期保存）。"""
    try:
        with open(EXHENTAI_HIDDEN_TAGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data = data.get("tags") or []
            if isinstance(data, list):
                return [str(t).strip() for t in data if str(t).strip()]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_ex_hidden_tags(tags: list[str]) -> None:
    """保存隐藏标签列表。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(EXHENTAI_HIDDEN_TAGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"tags": tags}, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存隐藏标签失败: %s", exc)


def _ex_hidden_tag_matched(item_tag: str, hidden_tags: list[str]) -> bool:
    """判断画廊标签是否命中隐藏列表。

    匹配规则（不区分大小写）：
    - 隐藏 "xxx"        → 命中任何命名空间的 "Namespace:xxx"
    - 隐藏 "female:xxx"  → 仅命中 "female:xxx"
    """
    if not item_tag:
        return False
    t = item_tag.strip().lower()
    for hidden in hidden_tags:
        h = hidden.strip().lower()
        if not h:
            continue
        if t == h or t.endswith(":" + h):
            return True
    return False


def _exhentai_filter_hidden_tags(items: list[dict]) -> tuple[list[dict], int]:
    """过滤结果中包含隐藏标签的画廊，返回 (过滤后列表, 隐藏数量)。"""
    hidden = _load_ex_hidden_tags()
    if not hidden:
        return items, 0
    kept = []
    for item in items:
        tags = item.get("tags") or []
        if any(_ex_hidden_tag_matched(t, hidden) for t in tags):
            continue
        kept.append(item)
    return kept, len(items) - len(kept)


def exhentai_get_hidden_tags() -> None:
    """获取隐藏标签列表。"""
    emit({"event": "ex_hidden_tags", "tags": _load_ex_hidden_tags()})


def exhentai_add_hidden_tag(tag: str) -> None:
    """新增隐藏标签。"""
    tag = (tag or "").strip()
    if not tag:
        emit({"event": "account_error", "message": "标签名不能为空"})
        return
    tags = _load_ex_hidden_tags()
    low = tag.lower()
    if any(t.lower() == low for t in tags):
        emit({"event": "ex_hidden_tags", "tags": tags})
        return
    tags.append(tag)
    _save_ex_hidden_tags(tags)
    emit({"event": "ex_hidden_tags", "tags": tags})
    logging.info("ExHentai 新增隐藏标签: %s", tag)


def exhentai_delete_hidden_tag(tag: str) -> None:
    """删除隐藏标签（× 按钮）。"""
    tag = (tag or "").strip()
    tags = _load_ex_hidden_tags()
    new_tags = [t for t in tags if t.lower() != tag.lower()]
    _save_ex_hidden_tags(new_tags)
    emit({"event": "ex_hidden_tags", "tags": new_tags})
    logging.info("ExHentai 删除隐藏标签: %s", tag)


# ExHentai 搜索分类（f_cats 位掩码：勾选位掩码之和，f_cats = 1023 - 勾选和）
EXHENTAI_CATEGORIES = [
    ("misc", "杂项", 1),
    ("doujinshi", "同人志", 2),
    ("manga", "漫画", 4),
    ("artistcg", "艺术家CG", 8),
    ("gamecg", "游戏CG", 16),
    ("imageset", "图集", 32),
    ("cosplay", "Cosplay", 64),
    ("asianporn", "亚洲色情", 128),
    ("nonh", "非H", 256),
    ("western", "西方", 512),
]


def _exhentai_search_params(query: str, options: dict) -> dict:
    """根据搜索选项构造 EX 搜索 URL 参数（对应原版搜索页的过滤按钮）。"""
    params: dict = {"f_search": query}
    if options is None:
        return params
    # 分类复选（原版 10 个分类；f_cats = 1023 - 勾选位掩码和）
    cats = options.get("exhentai_cats")
    if isinstance(cats, list) and cats:
        bits = sum(bit for key, _, bit in EXHENTAI_CATEGORIES if key in cats)
        if 0 < bits < 1023:
            params["f_cats"] = 1023 - bits
    # 最低评分（2-5 星）
    try:
        mr = int(options.get("exhentai_min_rating") or 0)
    except (TypeError, ValueError):
        mr = 0
    if 2 <= mr <= 5:
        params["f_sr"] = "on"
        params["f_srdd"] = mr
    # 仅显示有种子的画廊
    if options.get("exhentai_torrents_only"):
        params["f_sto"] = "on"
    # 页数范围
    try:
        pmin = int(options.get("exhentai_page_min") or 0)
        pmax = int(options.get("exhentai_page_max") or 0)
    except (TypeError, ValueError):
        pmin = pmax = 0
    if pmin > 0 or pmax > 0:
        params["f_sp"] = "on"
        if pmin > 0:
            params["f_spf"] = pmin
        if pmax > 0:
            params["f_spt"] = pmax
    return params


async def exhentai_popular(page: int = 1) -> None:
    """EX 首页推荐：与主站 exhentai.org 首页相同的最新画廊列表（next 游标分页）。"""
    page = max(1, int(page or 1))
    try:
        emit({"event": "search_start", "query": "EX 推荐", "page": page})
        cursors = _load_ex_cursors()
        entry = cursors.get("__home__", {})
        if not isinstance(entry, dict):
            entry = {}
        pages_map = {int(k): v for k, v in entry.items() if str(k).isdigit()}

        params: dict = {}
        if page > 1:
            cursor = pages_map.get(page)
            if cursor is None:
                # 跳页：从已知最高页顺序推进补齐游标（每页受节流限制）
                cur = max([p2 for p2 in pages_map if p2 < page] or [1])
                while cur < page:
                    p2_params = {"next": pages_map[cur + 1]} if pages_map.get(cur + 1) else {}
                    html_mid = (await asyncio.to_thread(
                        _exhentai_fetch, EXHENTAI_HOST + "/", p2_params)).text
                    gids_mid = _parse_ex_gallery_ids(html_mid)
                    if not gids_mid:
                        break
                    pages_map[cur + 1] = gids_mid[-1]
                    cur += 1
                    _exhentai_throttle()
                cursor = pages_map.get(page)
                if cursor is None:
                    emit({"event": "search_error", "message": f"第 {page} 页不存在或超出结果范围"})
                    return
            params["next"] = cursor
        response = await asyncio.to_thread(_exhentai_fetch, EXHENTAI_HOST + "/", params)
        html = response.text
        items = _parse_ex_search_page(html)
        gids = _parse_ex_gallery_ids(html)
        if gids:
            pages_map[page + 1] = gids[-1]
            entry = {"total_results": 0}
            for p2, gid in sorted(pages_map.items()):
                entry[str(p2)] = gid
            cursors["__home__"] = entry
            _save_ex_cursors(cursors)
        has_next = bool(re.search(r"[?&]next=\d+", html)) and bool(items)
        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": "EX 推荐",
            "page": page,
            "total_pages": page + 1 if has_next else page,
            "total_results": 0,
            "has_more": has_next,
            "items": items,
            "feed_kind": "exhentai_popular",
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 首页推荐 第 %d 页: %d 个画廊", page, len(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "search_error", "message": f"ExHentai 访问失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 首页推荐出错")


async def exhentai_search(query: str, page: int = 1, options: dict | None = None) -> None:
    """ExHentai 画廊关键词搜索（f_search + 过滤选项 + next 游标分页）。

    游标规则：进入第 N 页用 next=<第 N-1 页最后一个画廊的 ID>。
    跳页时从已缓存的最高已知页顺序推进到目标页（每页受节流限制）。
    过滤选项（分类/评分/种子/页数范围）来自 settings，与原版搜索页按钮等效。
    """
    if not query.strip():
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    page = max(1, int(page))
    base_params = _exhentai_search_params(query, options or {})
    try:
        emit({"event": "search_start", "query": query, "page": page})
        cursors = _load_ex_cursors()
        # 游标缓存 key 需包含过滤条件（不同过滤 = 不同结果集）
        filter_key = "&".join(
            f"{k}={v}" for k, v in base_params.items() if k != "f_search"
        )
        key = query.strip().lower() + ("|" + filter_key if filter_key else "")
        entry = cursors.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        # 已知入口游标：{"2": gid, "3": gid, ...}（进入该页所需 next 值）
        pages_map = {int(k): v for k, v in entry.items() if str(k).isdigit()}

        # 起始页：已知游标的最高页（不超过目标页），从它开始顺序抓
        cur = 1
        for p in sorted(pages_map):
            if p <= page:
                cur = max(cur, p)

        html = ""
        items: list[dict] = []
        while cur <= page:
            params: dict = dict(base_params)
            if cur > 1:
                cursor = pages_map.get(cur)
                if cursor is None:
                    break
                params["next"] = cursor
            response = await asyncio.to_thread(_exhentai_fetch, EXHENTAI_HOST + "/", params)
            html = response.text
            gids = _parse_ex_gallery_ids(html)
            if cur == page:
                items = _parse_ex_search_page(html)
                # 记录下一页游标（本页最后一个画廊 ID）
                if gids:
                    pages_map[page + 1] = gids[-1]
                break
            # 中间页：仅记录下一页游标后继续推进
            if not gids:
                break
            pages_map[cur + 1] = gids[-1]
            cur += 1

        if page > 1 and not items and not pages_map.get(page):
            # 目标页不可达（超出结果范围）
            emit({"event": "search_error", "message": f"第 {page} 页不存在或超出结果范围"})
            return

        # 总页数："Found about 225,000 results" / 过滤后 "Found 37 results" → 按每页条数折算
        total_results = entry.get("total_results") or 0
        m = re.search(r"Found (?:about )?([\d,]+) results", html)
        if m:
            try:
                total_results = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        per_page = len(items) or 25
        if total_results > 0:
            total_pages = max(1, -(-total_results // per_page))
        else:
            # 无总数信息：有结果就保守认为还有下一页
            total_pages = page + 1 if items else page

        # 是否有下一页：页面存在 next= 链接即有
        has_next = bool(re.search(r"[?&]next=\d+", html)) and bool(items)

        # 保存游标缓存
        entry = {"total_results": total_results}
        for p, gid in sorted(pages_map.items()):
            entry[str(p)] = gid
        cursors[key] = entry
        _save_ex_cursors(cursors)

        # 隐藏标签过滤（用户手动标记的 tags 不显示）
        items, hidden_count = _exhentai_filter_hidden_tags(items)

        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": query,
            "page": page,
            "total_pages": total_pages,
            "total_results": total_results,
            "has_more": has_next,
            "hidden_count": hidden_count,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 搜索完成: '%s' 第 %d/%d 页，%d 个结果（隐藏 %d）",
                     query, page, total_pages, len(items), hidden_count)

    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "search_error", "message": f"ExHentai 搜索失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 搜索出错")
