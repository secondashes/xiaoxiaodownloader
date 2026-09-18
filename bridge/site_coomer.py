# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Coomer。

由 gui_bridge.py 按物理顺序拆出（原行区间 1090-1436），
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
# Coomer 站点支持 (xxxcoomer.com)
# ============================
COOMER_HOST = "https://xxxcoomer.com"
# 图片扩展名：用于判断媒体直链是否可直接当缩略图展示
COOMER_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")


def is_coomer_url(url: str) -> bool:
    """判断 URL 是否属于 Coomer 站点（xxxcoomer.com 及其子域名）。"""
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    return netloc == "xxxcoomer.com" or netloc.endswith(".xxxcoomer.com")


def _coomer_parse_url(url: str) -> dict | None:
    """解析 Coomer URL，返回页面信息。

    支持的格式:
      /creator/{service}/{user_id}/{username}          作者页（类似相册）
      /post/{post_id}/{user_id}/{service}/{username}   帖子页（类似单文件）
    """
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]

    if len(parts) >= 4 and parts[0] == "creator":
        return {
            "kind": "creator",
            "service": parts[1],
            "user_id": parts[2],
            "username": parts[3],
            "post_id": None,
        }
    if len(parts) >= 5 and parts[0] == "post":
        return {
            "kind": "post",
            "service": parts[3],
            "user_id": parts[2],
            "username": parts[4],
            "post_id": parts[1],
        }
    return None


def _coomer_creator_avatar(user_id: str) -> str:
    """返回作者头像 URL（作为视频等无预览媒体的缩略图兜底）。"""
    return f"{COOMER_HOST}/istorage/{user_id}.jpg"


def _coomer_extract_media_urls(soup: BeautifulSoup) -> list[str]:
    """从帖子页 .post-body 中提取媒体直链（图片 img / 视频 source）。"""
    body = soup.find("div", class_="post-body")
    if body is None:
        return []

    urls: list[str] = []
    for tag in body.find_all(["img", "source"]):
        src = (tag.get("src") or "").strip()
        # 排除作者头像（istorage）等非媒体图片
        if src.startswith("http") and "/istorage/" not in src:
            urls.append(src)
    return urls


def _coomer_post_title(soup: BeautifulSoup) -> str:
    """提取帖子标题（用于生成对用户友好的文件名）。"""
    wrap = soup.find("div", class_="post-wrap")
    h1 = (wrap.find("h1") if wrap else None) or soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _coomer_build_filename(title: str, media_url: str, index: int, total: int) -> str:
    """根据帖子标题和媒体 URL 生成下载文件名。

    优先使用帖子标题（更友好），无标题时退回 URL 文件名；
    一个帖子包含多个文件时追加序号区分。
    """
    media_path = urlparse(media_url).path
    ext = Path(media_path).suffix
    url_name = Path(media_path).stem

    base = remove_invalid_characters(title).strip()
    base = re.sub(r"\s+", " ", base)
    if not base:
        base = url_name
    if len(base) > 80:
        base = base[:80].rstrip()

    if total > 1:
        base = f"{base}_{index}"

    return f"{base}{ext}"


def _coomer_is_image(media_url: str) -> bool:
    """根据扩展名判断媒体是否为图片（图片直链可兼作缩略图）。"""
    return Path(urlparse(media_url).path).suffix.lower() in COOMER_IMAGE_EXTS


def _coomer_extract_post_pages(soup: BeautifulSoup) -> list[str]:
    """从作者页提取所有帖子链接。"""
    posts_list = soup.find("div", class_="posts-list")
    if posts_list is None:
        return []

    links: list[str] = []
    for a in posts_list.find_all("a", class_="view-post", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = COOMER_HOST + href
        if href.startswith("http") and href not in links:
            links.append(href)
    return links


def _coomer_next_page_url(soup: BeautifulSoup) -> str | None:
    """提取作者页底部的下一页链接（分页），无分页时返回 None。"""
    pagination = soup.find("div", class_="pagination-bottom")
    if pagination is None:
        return None

    next_link = pagination.find("a", class_="next")
    if next_link is None:
        return None

    href = (next_link.get("href") or "").strip()
    if not href:
        return None
    if href.startswith("/"):
        href = COOMER_HOST + href
    return href if href.startswith("http") else None


def _coomer_make_items(
    post_page: str,
    media_urls: list[str],
    title: str,
    avatar: str,
) -> list[dict]:
    """把一个帖子的媒体直链转换为文件列表条目。"""
    items: list[dict] = []
    for index, media_url in enumerate(media_urls, 1):
        items.append({
            "filename": _coomer_build_filename(title, media_url, index, len(media_urls)),
            "size": None,
            "item_page": post_page,
            "status": "ok",
            "site": "coomer",
            "media_url": media_url,
            "media_path": urlparse(media_url).path,
            "thumbnail": media_url if _coomer_is_image(media_url) else avatar,
        })
    return items


async def coomer_inspect(url: str, options: dict) -> None:
    """解析 Coomer 作者页/帖子页，返回媒体文件列表。"""
    info = _coomer_parse_url(url)
    if info is None:
        emit({
            "event": "inspect_error",
            "message": "无法识别的 Coomer 链接，请粘贴作者页或帖子页链接",
        })
        return

    avatar = _coomer_creator_avatar(info["user_id"])

    try:
        # ---------- 帖子页：单帖解析 ----------
        if info["kind"] == "post":
            soup = await fetch_page(url)
            if soup is None:
                emit({"event": "inspect_error", "message": f"无法获取页面: {url}"})
                return

            media_urls = _coomer_extract_media_urls(soup)
            if not media_urls:
                emit({"event": "inspect_error", "message": "帖子中没有找到可下载的媒体文件"})
                return

            items = _coomer_make_items(url, media_urls, _coomer_post_title(soup), avatar)
            _apply_cached_thumbnails(items)

            emit({
                "event": "inspect_complete",
                "album_name": info["username"],
                "album_id": f"coomer_{info['service']}_{info['user_id']}",
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Coomer 帖子解析完成: %s (%d 个文件)", url, len(items))
            return

        # ---------- 作者页：遍历分页收集所有帖子 ----------
        identifier = f"coomer_{info['service']}_{info['user_id']}"

        # 命中缓存则直接返回
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or info["username"],
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 Coomer 作者信息: %s (%d 个文件)", identifier, len(items))
            return

        post_pages: list[str] = []
        page_url: str | None = url
        visited: set[str] = set()
        while page_url and page_url not in visited:
            visited.add(page_url)
            soup = await fetch_page(page_url)
            if soup is None:
                break
            for link in _coomer_extract_post_pages(soup):
                if link not in post_pages:
                    post_pages.append(link)
            page_url = _coomer_next_page_url(soup)

        if not post_pages:
            emit({
                "event": "inspect_error",
                "message": "没有找到任何帖子，请确认链接是否正确",
            })
            return

        total = len(post_pages)
        emit({
            "event": "inspect_progress",
            "current": 0,
            "total": total,
            "filename": "",
        })
        logging.info("Coomer 作者 '%s' 共 %d 个帖子", info["username"], total)

        semaphore = asyncio.Semaphore(INSPECT_CONCURRENCY)
        results: list[dict] = []
        completed_count = 0
        count_lock = asyncio.Lock()

        async def resolve_one(post_page: str) -> None:
            nonlocal completed_count
            async with semaphore:
                post_soup = await fetch_page(post_page)
                if post_soup is None:
                    result = {
                        "filename": post_page.rstrip("/").rsplit("/", 1)[-1],
                        "size": None,
                        "item_page": post_page,
                        "status": "fetch_failed",
                        "site": "coomer",
                        "thumbnail": avatar,
                    }
                    results.append(result)
                else:
                    # 纯文字帖子（无媒体）直接跳过，不生成条目
                    media_urls = _coomer_extract_media_urls(post_soup)
                    if media_urls:
                        results.extend(_coomer_make_items(
                            post_page, media_urls, _coomer_post_title(post_soup), avatar,
                        ))

                async with count_lock:
                    completed_count += 1
                    emit({
                        "event": "inspect_progress",
                        "current": completed_count,
                        "total": total,
                        "filename": results[-1]["filename"] if results else "",
                    })

        await asyncio.gather(*(resolve_one(page) for page in post_pages))

        _apply_cached_thumbnails(results)

        # 增量标记：上次下载之后新增的帖子文件标 is_new
        _mark_items_new(identifier, results)

        _save_album_cache(identifier, {
            "album_name": info["username"],
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })

        emit({
            "event": "inspect_complete",
            "album_name": info["username"],
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })
        asyncio.create_task(_cache_thumbnails(results))
        logging.info("Coomer 作者解析完成: %s, 共 %d 个文件", info["username"], len(results))

    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("Coomer 解析过程出错")


async def get_coomer_download_info(item: dict) -> tuple[str | None, str]:
    """为 Coomer 条目解析下载直链，返回 (下载链接, 文件名)。

    视频直链带签名参数（e/hash）会过期，必须重新抓取帖子页获取新链接；
    图片直链永久有效，帖子页抓取失败时可直接回退到解析时保存的直链。
    """
    item_page = item.get("item_page", "")
    filename = item.get("filename", "") or "coomer_file"
    media_path = item.get("media_path", "")
    media_name = Path(media_path).name if media_path else ""

    if item_page:
        soup = await fetch_page(item_page)
        if soup is not None:
            media_urls = _coomer_extract_media_urls(soup)
            # 优先按媒体路径精确匹配（去掉签名参数后的路径）
            for media_url in media_urls:
                if urlparse(media_url).path == media_path:
                    return media_url, filename
            # 路径匹配失败（帖子可能已更新），按文件名兜底
            for media_url in media_urls:
                if Path(urlparse(media_url).path).name == media_name:
                    return media_url, filename
            # 仍匹配失败：帖子只剩一个文件时直接使用
            if len(media_urls) == 1:
                return media_urls[0], filename

    # 回退：图片直链永久有效
    fallback = item.get("media_url", "")
    if fallback.startswith("http"):
        return fallback, filename

    return None, filename
