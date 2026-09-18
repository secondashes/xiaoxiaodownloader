# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：历史任务记录。

由 gui_bridge.py 按物理顺序拆出（原行区间 15746-15783），
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
# 历史任务记录
# ============================
HISTORY_FILE = "history.json"
HISTORY_MAX_ENTRIES = 500


def _load_history() -> list[dict]:
    """读取历史记录文件。"""
    try:
        with Path(HISTORY_FILE).open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_history(history: list[dict]) -> None:
    """保存历史记录文件。"""
    try:
        _atomic_write_json(HISTORY_FILE, history)
    except OSError as exc:
        logging.warning("保存历史记录失败: %s", exc)


def _add_history_entry(entry: dict) -> None:
    """在历史记录头部插入一条新记录，并限制最大条数。"""
    history = _load_history()
    history.insert(0, entry)
    _save_history(history[:HISTORY_MAX_ENTRIES])


# ============================
# 用户设置持久化
# ============================
SETTINGS_FILE = "settings.json"
