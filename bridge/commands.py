# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Download / Search 命令入口。

由 gui_bridge.py 按物理顺序拆出（原行区间 12623-13069），
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
# Download 命令：下载选中文件
# ============================
async def gui_download(url: str, selected_items: list[dict], options: dict) -> None:
    """下载用户选中的文件。"""
    if not selected_items:
        emit({"event": "download_error", "message": "没有选中的文件"})
        return

    logging.info("开始下载: %s, 选中 %d 个文件", url, len(selected_items))
    args = create_args(options)

    try:
        validated_url = normalize_url(url)

        if is_pawchive_url(validated_url):
            # Pawchive：直链永久有效，无需抓取页面；目录按画师名组织
            soup = None
            album_name = await asyncio.to_thread(
                _pawchive_album_name, validated_url, selected_items,
            )
            album_id = None
        elif is_coomer_url(validated_url):
            soup = await fetch_page(validated_url)
            if soup is None:
                emit({"event": "download_error", "message": f"无法获取页面: {validated_url}"})
                return
            # Coomer：相册名取作者名，下载目录按作者组织
            info = _coomer_parse_url(validated_url)
            album_name = (info or {}).get("username") or "Coomer 下载"
            album_id = None
        else:
            soup = await fetch_page(validated_url)
            if soup is None:
                emit({"event": "download_error", "message": f"无法获取页面: {validated_url}"})
                return
            is_album = check_url_type(validated_url)
            album_name = get_album_name(soup)
            album_id = get_album_id(validated_url) if is_album else None

        # 构建相册目录
        # EX 批量下载母文件夹：用搜索词作母文件夹名，每个画廊按其标题分子文件夹
        batch_parent = (options.get("batch_parent_folder") or "").strip()
        if batch_parent:
            # 用母文件夹名作为顶层目录名（album_id 留空避免拼接后缀）
            album_path = build_album_directory(batch_parent, None, options)
        else:
            album_path = build_album_directory(album_name, album_id, options)
        logging.info("下载目录: %s", album_path)

        # 创建速率限制器
        rate_limit = args.rate_limit
        rate_limiter = RateLimiter(rate_limit * KB if rate_limit else None)

        # 创建 session_info
        session_info = SessionInfo(
            args=args,
            bunkr_status={},
            download_path=album_path,
            rate_limiter=rate_limiter,
        )

        live_manager = GuiLiveManager()
        live_manager.add_overall_task(
            album_name or album_id or "下载",
            len(selected_items),
        )

        semaphore = asyncio.Semaphore(MAX_WORKERS)
        max_retries = args.max_retries or MAX_RETRIES

        async def download_one(index: int, item: dict) -> None:
            async with semaphore:
                item_page = item["item_page"]
                filename_hint = item.get("filename", "")

                # 创建任务
                task_id = live_manager.add_task(current_task=index)

                if item.get("site") == "pawchive":
                    # Pawchive：直链永久有效，直接下载（站点对下载有限速，先节流）
                    await _pawchive_throttle_download()
                    download_link = item.get("media_url") or ""
                    filename = item.get("filename") or "pawchive_file"
                    if not download_link.startswith("http"):
                        live_manager.update_log(
                            event="解析失败",
                            details=f"缺少下载直链: {filename_hint}",
                        )
                        emit({
                            "event": "file_complete",
                            "filename": filename_hint,
                            "success": False,
                            "size": item.get("size"),
                        })
                        return
                elif item.get("site") == "coomer":
                    # Coomer：重新抓取帖子页获取新的媒体直链（视频链接带签名会过期）
                    download_link, filename = await get_coomer_download_info(item)
                    if not download_link:
                        live_manager.update_log(
                            event="解析失败",
                            details=f"无法获取下载链接: {filename_hint}",
                        )
                        emit({
                            "event": "file_complete",
                            "filename": filename_hint,
                            "success": False,
                            "size": item.get("size"),
                        })
                        return
                else:
                    # 重新解析下载信息（下载链接可能已过期）
                    item_soup = await fetch_page(item_page)
                    if item_soup is None:
                        live_manager.update_log(
                            event="获取失败",
                            details=f"无法获取文件页面: {filename_hint}",
                        )
                        emit({
                            "event": "file_complete",
                            "filename": filename_hint,
                            "success": False,
                            "size": item.get("size"),
                        })
                        return

                    download_link, filename = await get_download_info(
                        item_page, item_soup, clean_name=args.clean_name,
                    )
                if not download_link:
                    live_manager.update_log(
                        event="解析失败",
                        details=f"无法获取下载链接: {filename_hint}",
                    )
                    emit({
                        "event": "file_complete",
                        "filename": filename_hint,
                        "success": False,
                        "size": item.get("size"),
                    })
                    return

                size = item.get("size")
                live_manager.set_task_info(task_id, filename, size)

                # 构建文件下载路径（Pawchive 专属子文件夹规则 + 按类型分类）
                if item.get("site") == "pawchive":
                    base_dir = _pawchive_build_file_dir(album_path, item, options)
                    file_download_path = build_file_download_path(
                        base_dir, filename, options,
                    )
                else:
                    # EX 批量下载：按"YYYY-MM-画廊标题"分子文件夹（母文件夹已作顶层目录）
                    base_dir = album_path
                    g_title = (item.get("gallery_title") or "").strip()
                    if g_title and batch_parent:
                        g_date = (item.get("post_date") or "")[:7]
                        g_name = sanitize_directory_name(g_title)
                        sub = str(Path(album_path) / (f"{g_date}-{g_name}" if g_date else g_name))
                        Path(sub).mkdir(parents=True, exist_ok=True)
                        base_dir = sub
                    file_download_path = build_file_download_path(
                        base_dir, filename, options,
                    )

                # 创建该文件的 session_info 副本（避免并发修改）
                file_args = args
                if item.get("site") == "pawchive":
                    # Pawchive：站点限流严格，强制单连接下载，避免并行分块触发封锁
                    file_args = Namespace(**vars(args))
                    file_args.connections = 1
                file_session_info = replace(
                    session_info, download_path=file_download_path, args=file_args,
                )

                emit({
                    "event": "file_start",
                    "filename": filename,
                    "index": index,
                    "size": size,
                })

                media_downloader = MediaDownloader(
                    session_info=file_session_info,
                    download_info=DownloadInfo(
                        item_url=item_page,
                        download_link=download_link,
                        filename=filename,
                        task=task_id,
                    ),
                    live_manager=live_manager,
                    retry_config=RetryConfig(
                        retries=max_retries,
                        has_external_retry=False,
                    ),
                )

                failed = await asyncio.to_thread(media_downloader.download)

                emit({
                    "event": "file_complete",
                    "filename": filename,
                    "success": not failed,
                    "size": size,
                })
                if failed:
                    logging.warning("文件下载失败: %s", filename)
                else:
                    logging.info("文件下载完成: %s", filename)
                    # 记录到历史任务
                    final_path = str(Path(file_download_path) / truncate_filename(filename))
                    _add_history_entry({
                        "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                        "filename": filename,
                        "path": final_path,
                        "size": size,
                        "album": album_name or album_id or "下载",
                        "time": datetime.now().isoformat(timespec="seconds"),
                    })

        tasks = [
            download_one(i, item) for i, item in enumerate(selected_items)
        ]
        await asyncio.gather(*tasks)

        live_manager.stop()
        logging.info("下载完成")

    except Exception as exc:
        emit({"event": "download_error", "message": f"下载过程出错: {exc}"})
        logging.exception("下载过程出错")


# ============================
# Search 命令：搜索 Bunkr 相册
# ============================
SEARCH_ENDPOINT = "https://balbums.st/"

# 完整浏览器请求头，模拟真实浏览器访问，降低被识别为爬虫的概率
SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Referer": "https://balbums.st/",
}

# 复用 session：保持 cookie 和连接池，避免每次请求都重新握手
_search_session = requests.Session()
_search_session.headers.update(SEARCH_HEADERS)

# Coomer 搜索专用 session：Referer 指向站点自身（复用 balbums.st 的 Referer 会被拦截）
_coomer_session = requests.Session()
_coomer_session.headers.update({
    "User-Agent": SEARCH_HEADERS["User-Agent"],
    "Accept": SEARCH_HEADERS["Accept"],
    "Accept-Language": SEARCH_HEADERS["Accept-Language"],
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Referer": COOMER_HOST + "/",
})

# 请求节流参数
_SEARCH_MIN_INTERVAL = 0.8   # 两次请求之间的最小间隔（秒）
_SEARCH_MAX_RETRIES = 3      # 最大重试次数
_SEARCH_TIMEOUT = 15         # 单次请求超时（秒）

_search_lock = threading.Lock()


_throttle_search = _make_throttle(_SEARCH_MIN_INTERVAL, lock=_search_lock)


def _fetch_search_page(query: str, page: int, per_page: int) -> BeautifulSoup | None:
    """同步抓取 balbums.st 搜索页，带限流、重试和指数退避。

    反爬虫应对：
    - 完整浏览器请求头 + 复用 session（保持 cookie）
    - 请求节流（最小间隔）
    - 429 限流时等待更久再重试
    - 网络异常时指数退避 + 随机抖动
    """
    _throttle_search()

    params = {
        "search": query,
        "mode": "broad",
        "per": str(per_page),
        "sort": "latest",
        "page": str(page),
    }

    for attempt in range(_SEARCH_MAX_RETRIES):
        try:
            response = _search_session.get(
                SEARCH_ENDPOINT,
                params=params,
                timeout=_SEARCH_TIMEOUT,
            )

            # 429 Too Many Requests：被限流，等待更长时间后重试
            if response.status_code == 429:
                backoff = 2 ** (attempt + 1) + random.uniform(0, 1)
                logging.warning("搜索被限流(429)，%.1f 秒后重试", backoff)
                time.sleep(backoff)
                continue

            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")

        except requests.RequestException as exc:
            logging.warning("搜索请求失败(第 %d/%d 次): %s", attempt + 1, _SEARCH_MAX_RETRIES, exc)
            if attempt < _SEARCH_MAX_RETRIES - 1:
                backoff = 2 ** attempt + random.uniform(0.5, 1.5)
                time.sleep(backoff)

    return None


def _parse_search_results(soup: BeautifulSoup) -> tuple[list[dict], int]:
    """解析搜索结果页，返回 (相册列表, 总页数)。"""
    items: list[dict] = []

    for card in soup.find_all("a", class_="card"):
        album_url = card.get("href", "")
        if not album_url:
            continue

        # 缩略图：优先取真实缩略图（static.scdn.st），否则用占位图标
        thumbnail = "/img/bunkr.svg"
        for img in card.find_all("img"):
            src = img.get("src", "")
            if "static.scdn.st" in src or src.startswith("http"):
                thumbnail = src
                break
        if thumbnail.startswith("/"):
            thumbnail = "https://balbums.st" + thumbnail

        # 相册名
        h3 = card.find("h3")
        album_name = h3.get_text(strip=True) if h3 else ""

        # 文件数
        files = 0
        for span in card.find_all("span"):
            match = re.search(r"(\d+)\s*files?", span.get_text(strip=True), re.IGNORECASE)
            if match:
                files = int(match.group(1))
                break

        items.append({
            "album_name": album_name,
            "album_url": album_url,
            "thumbnail": thumbnail,
            "files": files,
        })

    # 分页：从 "page X of Y" 文本中提取总页数
    text = soup.get_text(" ", strip=True)
    match = re.search(r"page\s+(\d+)\s+of\s+(\d+)", text, re.IGNORECASE)
    total_pages = int(match.group(2)) if match else 1

    return items, total_pages


# 缩略图本地缓存目录
THUMBNAIL_CACHE_DIR = "cache/thumbnails"
# 缩略图索引：记录「本地文件名 -> 原始缩略图 URL」的对应关系
THUMBNAIL_INDEX_FILE = "cache/thumbnails_index.json"
# 缓存体积上限：超过后按最旧文件清理（防止长期使用后缓存过大导致卡顿/不显示）
THUMBNAIL_CACHE_MAX_BYTES = 500 * 1024 * 1024
THUMBNAIL_CACHE_KEEP_BYTES = 400 * 1024 * 1024
_thumb_cleanup_last = 0.0


def _cleanup_thumbnail_cache() -> None:
    """缩略图缓存超过上限时按最旧优先删除（LRU），并同步修剪索引。"""
    global _thumb_cleanup_last
    # 每小时最多执行一次，避免频繁扫描目录
    if time.time() - _thumb_cleanup_last < 3600:
        return
    _thumb_cleanup_last = time.time()

    cache_dir = Path(THUMBNAIL_CACHE_DIR)
    if not cache_dir.exists():
        return
    try:
        entries = []
        total = 0
        for p in cache_dir.iterdir():
            if not p.is_file():
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, p, stat.st_size))
            total += stat.st_size
        if total <= THUMBNAIL_CACHE_MAX_BYTES:
            return

        # 按修改时间从旧到新删除，直到降到保留水位以下
        entries.sort()
        removed: set[str] = set()
        for _, path, size in entries:
            if total <= THUMBNAIL_CACHE_KEEP_BYTES:
                break
            try:
                path.unlink(missing_ok=True)
                removed.add(path.name)
                total -= size
            except OSError:
                continue

        if removed:
            index = _load_thumbnail_index()
            index = {k: v for k, v in index.items() if k not in removed}
            _save_thumbnail_index(index)
            logging.info("缩略图缓存清理: 删除 %d 个最旧文件", len(removed))
    except OSError as exc:
        logging.warning("缩略图缓存清理失败: %s", exc)
