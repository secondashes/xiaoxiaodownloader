# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：账号档案 / 登录状态指纹。

由 gui_bridge.py 按物理顺序拆出（原行区间 17351-17418），
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
# 账号档案（多账号记录与切换）+ 登录状态指纹（失效原因判断）
# ============================
LOGIN_STATE_FILE = "cache/login_state.json"


def _load_accounts() -> dict:
    """读取账号档案：{站点: {"active": 档案名, "profiles": {档案名: {label, username, cookie_str, saved_at}}}}。

    存于加密账号存储（根目录伪装文件），长期保存。
    """
    return _secure_store_read_section("accounts")


def _save_accounts(accounts: dict) -> None:
    _secure_store_write_section("accounts", accounts)


def _site_cookie_str(site: str) -> str:
    """站点当前登录 cookie 字符串（展示/复制/档案共用）。"""
    if site == "twitter":
        return _twitter_cookie_str()
    if site == "exhentai":
        return _exhentai_cookie_str()
    if site == "pawchive":
        cookies = {c.name: c.value for c in _pawchive_session.cookies}
        return "; ".join(f"{k}={v}" for k, v in cookies.items())
    if site == "iwara":
        return _iwara_load_token().get("user_token") or ""
    if site == "hanime":
        cookies = _hanime_load_cred().get("cookies") or {}
        return "; ".join(f"{k}={v}" for k, v in cookies.items())
    if site == "pixiv":
        cookies = _pixiv_load_cred().get("cookies") or {}
        return "; ".join(f"{k}={v}" for k, v in cookies.items())
    if site == "asmr":
        return _asmr_load_cred().get("token") or ""
    if site in _GENERIC_OAUTH_SITES:
        return _generic_cookie_str(site)
    if site == "javdb":
        return _javdb_load_cred().get("cookie_str") or ""
    if site == "leakedzone":
        # 过盾会话 cookie（sniffer 系模块注入的 _lz_session；finalize 后调用期可见）
        lz_sess = globals().get("_lz_session")
        if lz_sess is not None:
            return "; ".join(f"{c.name}={c.value}" for c in lz_sess.cookies)
        return ""
    return ""


def _site_username(site: str) -> str:
    """站点当前登录的用户名（不联网，从缓存文件读）。

    各站用户名状态归各站模块所有（拆分后模块间共享的是加载期快照，
    必须走 owner 模块的 *_now() 访问器取实时值）。
    """
    if site == "twitter":
        return _twitter_load_cookies().get("screen_name") or ""
    if site == "exhentai":
        ex = _exhentai_load_cookies()
        return ex.get("_username") or ex.get("ipb_member_id") or ""
    if site == "pawchive":
        return _pawchive_username_now()
    if site == "iwara":
        return _iwara_load_token().get("username") or ""
    if site == "hanime":
        return _hanime_username_now() or (_hanime_load_cred().get("username") or "")
    if site == "pixiv":
        return _pixiv_username_now() or (_pixiv_load_cred().get("username") or "")
    if site == "asmr":
        return _asmr_username_now() or (_asmr_load_cred().get("username") or "")
    if site in _GENERIC_OAUTH_SITES:
        return _generic_load_cookies(site).get("username") or ""
    if site == "javdb":
        return _javdb_username_now() or (_javdb_load_cred().get("username") or "")
    if site == "leakedzone":
        return "已过盾"
    return ""
