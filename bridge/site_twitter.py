# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Twitter/X（含关注列表/关注管理/关注分类）。

由 gui_bridge.py 按物理顺序拆出（原行区间 3637-5673），
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
from html import escape as html_escape, unescape as html_unescape
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
# Twitter/X 站点支持 (x.com)
# ============================
# 站点特点（参考 X-Spider 项目的实现）：
# - API 走 GraphQL，需要账号 cookie（auth_token + ct0）+ 网页版公开 Bearer Token + X-Csrf-Token
# - 国内需代理访问（x.com / pbs.twimg.com / video.twimg.com 均被墙）
# - 媒体直链（pbs.twimg.com 图片 / video.twimg.com 视频）永久有效、无需 cookie，但下载需走代理
# - 单条推文可用公开的 syndication API（cdn.syndication.twimg.com）免登录解析
TWITTER_HOST = "https://x.com"
TWITTER_REQUEST_INTERVAL = 0.8    # GraphQL 请求最小间隔（秒），顺序请求仍远低于浏览器并发量
TWITTER_DOWNLOAD_INTERVAL = 0.5   # 媒体下载最小间隔（秒）
TWITTER_DEFAULT_PROXY = "http://127.0.0.1:10809"
# 网页版公开 Bearer Token（所有浏览器一致，非机密）
TWITTER_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

_twitter_session = requests.Session()
_twitter_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": TWITTER_HOST + "/",
    "Origin": TWITTER_HOST,
})
_twitter_proxy: str | None = None
_twitter_lock = threading.Lock()

# GraphQL queryId 注册表（X 每隔数周轮换，过期时自动从 fa0311/TwitterInternalAPIDocument
# 权威 JSON（多 CDN 源，免登录）刷新；失败再回退 x.com main.js 抓取）
TWITTER_QIDS_FILE = "cache/twitter_qids.json"
# 参考 RSSHub lib/routes/twitter/api/web-api/gql-id-resolver.ts（2026-08 最新）
# 多源依次尝试：cdn.jsdelivr 国内常被墙 → fastly.jsdelivr → raw.githubusercontent
TWITTER_API_DOC_URLS = (
    "https://cdn.jsdelivr.net/gh/fa0311/TwitterInternalAPIDocument"
    "@master/docs/json/API.json",
    "https://fastly.jsdelivr.net/gh/fa0311/TwitterInternalAPIDocument"
    "@master/docs/json/API.json",
    "https://raw.githubusercontent.com/fa0311/TwitterInternalAPIDocument"
    "/master/docs/json/API.json",
)
# fa0311 master 最新（2026-08 核实）：X 轮换后内置默认值同步更新；
# 递增 SCHEMA 使旧缓存自动失效，避免旧 qid 永久覆盖新默认值
TWITTER_QID_SCHEMA = 2
TWITTER_QID_DEFAULTS = {
    "Viewer": "5XShkXk2oO2J7SYmTu6pvw",
    # RSSHub 最新 fallback（GitHub: DIYgod/RSSHub）
    "UserByScreenName": "Gb-d6r0vxPOADdG62OEBpQ",
    "UserMedia": "VyudDWQnr9vJNw7GasFz2g",
    "TweetDetail": "XMOz5h24KAZ86qKffKTLdQ",
    # 内容搜索（过期时自动刷新）
    "SearchTimeline": "hyPfJYJ_XAtDYoslQc-Rgg",
    "UserByRestId": "xvmVfRLmnr1alc5f2dib0Q",
    # 关注/取关 mutation（v1.1 失效时的 GraphQL 回退，queryId 自动刷新）
    "CreateFollower": "",
    "DeleteFollower": "",
}
_twitter_query_ids: dict = {}


def _twitter_qid(op: str) -> str:
    """取 GraphQL queryId（优先用缓存刷新过的值，无则用内置默认）。"""
    if not _twitter_query_ids:
        _twitter_query_ids.update(TWITTER_QID_DEFAULTS)
        try:
            with open(TWITTER_QIDS_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # 带版本校验：内置默认值更新后旧缓存直接忽略，
            # 避免过期 qid 永久覆盖新默认值（曾导致"打开博主解析不到内容"）
            if isinstance(cached, dict) and cached.get("_schema") == TWITTER_QID_SCHEMA:
                _twitter_query_ids.update(
                    {k: v for k, v in cached.items()
                     if v and not str(k).startswith("_")})
        except (OSError, json.JSONDecodeError):
            pass
    return _twitter_query_ids.get(op) or ""


def _twitter_refresh_qids(include_mutations: bool = False) -> bool:
    """刷新最新 queryId（X 轮换过期后自动恢复）。

    优先从 fa0311/TwitterInternalAPIDocument 权威 JSON 拉取（jsdelivr CDN、
    免登录、结构化数据，参考 RSSHub gql-id-resolver.ts）；失败再回退
    x.com 首页 main.js 正则抓取（需要登录 Cookie）。

    include_mutations=True 时同时刷新 mutation（关注/取关等写操作）的 queryId。
    """
    import re

    updated = False

    # ---- 来源 1：fa0311 权威 API 文档（免登录，多源依次尝试） ----
    for doc_url in TWITTER_API_DOC_URLS:
        try:
            r = requests.get(
                doc_url,
                proxies=_twitter_session.proxies or None, timeout=15,
            )
            if r.status_code != 200:
                continue
            doc = r.json()
            graphql = doc.get("graphql") or {}
            for name in list(TWITTER_QID_DEFAULTS):
                if include_mutations is False and name in ("CreateFollower", "DeleteFollower"):
                    continue
                qid = (graphql.get(name) or {}).get("queryId") or ""
                if qid and re.fullmatch(r"[0-9a-zA-Z_-]{10,30}", qid):
                    _twitter_qid(name)  # 确保已初始化
                    if _twitter_query_ids.get(name) != qid:
                        _twitter_query_ids[name] = qid
                        updated = True
            if any(_twitter_query_ids.get(n) for n in TWITTER_QID_DEFAULTS):
                break  # 本源拉到有效数据，无需尝试后续源
        except (requests.RequestException, ValueError) as exc:
            logging.debug("Twitter 权威 queryId 源 %s 获取失败: %s", doc_url, exc)

    # ---- 来源 2：x.com main.js 正则抓取（回退） ----
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
        }
        # 必须带登录 Cookie：未登录首页不含 main.js 引用，无法提取 queryId
        cookie = _twitter_cookie_str()
        if cookie:
            headers["Cookie"] = cookie
        response = requests.get(
            TWITTER_HOST, headers=headers,
            proxies=_twitter_session.proxies or None, timeout=20,
        )
        m = re.search(
            r'https://abs\.twimg\.com/responsive-web/client-web/main\.[0-9a-f]+\.js',
            response.text,
        )
        if m:
            js = _twitter_session.get(m.group(0), timeout=60).text
            op_types = r'query|mutation' if include_mutations else 'query'
            pairs = re.findall(
                r'queryId:"([^"]{10,30})",operationName:"([^"]+)",operationType:"(?:%s)"' % op_types,
                js,
            )
            for qid, name in pairs:
                if name in TWITTER_QID_DEFAULTS:
                    _twitter_qid(name)  # 确保已初始化
                    if _twitter_query_ids.get(name) != qid:
                        _twitter_query_ids[name] = qid
                        updated = True
    except (requests.RequestException, OSError) as exc:
        logging.warning("刷新 Twitter queryId 失败: %s", exc)

    if updated:
        logging.info("Twitter GraphQL queryId 已刷新: %s",
                     {k: v for k, v in _twitter_query_ids.items()
                      if k in TWITTER_QID_DEFAULTS})
        try:
            Path("cache").mkdir(parents=True, exist_ok=True)
            payload = dict(_twitter_query_ids)
            payload["_schema"] = TWITTER_QID_SCHEMA
            with open(TWITTER_QIDS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return updated


def twitter_set_proxy(proxy: str | None) -> None:
    """设置 Twitter 访问代理（API 和媒体下载都走此代理）。"""
    global _twitter_proxy
    _twitter_proxy = (proxy or "").strip() or None
    if _twitter_proxy:
        _twitter_session.proxies.update({"http": _twitter_proxy, "https": _twitter_proxy})
    else:
        _twitter_session.proxies.clear()
    logging.info("Twitter 代理已设置: %s", _twitter_proxy or "（直连）")


def _twitter_load_cookies() -> dict:
    """读取已保存的 Twitter cookie（加密账号存储）。"""
    return _secure_store_read_cred("twitter")


def _twitter_save_cookies(cookies: dict) -> None:
    """保存 Twitter cookie（长期保持登录状态，加密存储）。"""
    data = dict(cookies)
    data["_saved_at"] = time.time()
    _secure_store_write_cred("twitter", data)


def _twitter_cookie_str() -> str:
    """拼接 API 请求所需的 Cookie 头（auth_token + ct0）。"""
    cookies = _twitter_load_cookies()
    parts = []
    if cookies.get("auth_token"):
        parts.append(f"auth_token={cookies['auth_token']}")
    if cookies.get("ct0"):
        parts.append(f"ct0={cookies['ct0']}")
    return "; ".join(parts)


_twitter_throttle = _make_throttle(TWITTER_REQUEST_INTERVAL, lock=_twitter_lock)


_twitter_throttle_download = _make_throttle(TWITTER_DOWNLOAD_INTERVAL, lock=_twitter_lock)


def _twitter_head_size(media_url: str) -> int | None:
    """HEAD 预取媒体文件大小（用于下载去重的大小对比）。"""
    try:
        _twitter_throttle_download()
        resp = _twitter_session.head(
            media_url, timeout=20, headers={"Referer": TWITTER_HOST + "/"},
        )
        if resp.status_code == 200:
            return int(resp.headers.get("Content-Length") or 0) or None
    except (requests.RequestException, ValueError):
        pass
    return None


def is_twitter_url(url: str) -> bool:
    """判断是否为 Twitter/X 链接（x.com / twitter.com 用户页或推文页）。"""
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    return netloc in ("x.com", "twitter.com", "www.x.com", "www.twitter.com") or \
        netloc.endswith(".x.com") or netloc.endswith(".twitter.com")


def _twitter_parse_url(url: str) -> dict | None:
    """解析 Twitter URL。

    支持的格式：
      https://x.com/{screen_name}            用户主页（解析全部媒体）
      https://x.com/{screen_name}/status/{id}   单条推文
    """
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    if "intent" in parts or "i" == parts[0]:
        return None
    if len(parts) >= 3 and parts[1] == "status":
        try:
            status_id = int(parts[2])
        except ValueError:
            return None
        return {"kind": "status", "screen_name": parts[0], "status_id": str(status_id)}
    if len(parts) == 1:
        return {"kind": "user", "screen_name": parts[0], "status_id": None}
    return None


def _twitter_api_get(query_id: str, endpoint: str, features: dict, variables: dict,
                     extra_params: dict | None = None, use_post: bool = False) -> dict:
    """调用 x.com GraphQL API（带 Bearer + cookie + csrf；queryId 过期 404 时自动刷新重试）。

    use_post=True 时改用 POST 方式（部分端点如 SearchTimeline 对 GET 请求
    强制校验 x-client-transaction-id 头，缺失直接 404；POST 可绕过）。
    """
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise PermissionError("未登录 Twitter，请先在设置中填写 Cookie")
    qid = _twitter_qid(endpoint) or query_id
    params = {
        "features": json.dumps(features),
        "variables": json.dumps(variables),
    }
    if extra_params:
        params.update(extra_params)
    retried = False  # 每次调用最多自动重试一次，防死循环
    while True:
        _twitter_throttle()
        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Cookie": _twitter_cookie_str(),
            "X-Csrf-Token": cookies["ct0"],
            "Referer": TWITTER_HOST + "/",
            "Origin": TWITTER_HOST,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }
        if use_post:
            # POST 方式：variables/features 放请求体（网页端同款结构）
            headers["Content-Type"] = "application/json"
            payload = {"queryId": qid, "variables": variables, "features": features}
            response = _twitter_session.post(
                f"{TWITTER_HOST}/i/api/graphql/{qid}/{endpoint}",
                json=payload, headers=headers, timeout=20,
            )
        else:
            response = _twitter_session.get(
                f"{TWITTER_HOST}/i/api/graphql/{qid}/{endpoint}",
                params=params, headers=headers, timeout=20,
            )
        if response.status_code == 404:
            # queryId 被 X 轮换过期：从 main.js 刷新后重试一次
            if _twitter_refresh_qids():
                new_qid = _twitter_qid(endpoint)
                if new_qid and new_qid != qid:
                    qid = new_qid
                    continue
            raise requests.HTTPError(
                f"404：GraphQL 查询 {endpoint} 不存在（queryId 可能已过期）",
                response=response,
            )
        if response.status_code in (401, 403):
            raise PermissionError("Twitter 登录已失效，请重新填写 Cookie")
        if response.status_code == 429:
            raise PermissionError("Twitter API 被限流，请稍后再试")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            return {}
        # X 轮换 queryId/features 时会返回 200 + {"errors":[...]}（无有效 data）。
        # 刷新 queryId 后必重试一次（即使 qid 未变——errors 也可能是瞬时故障），
        # 避免"打开博主页却解析不到视频图片"
        if payload.get("errors") and not isinstance(payload.get("data"), dict):
            if not retried:
                retried = True
                _twitter_refresh_qids()
                new_qid = _twitter_qid(endpoint)
                if new_qid:
                    qid = new_qid
                    continue
            raise requests.HTTPError(
                f"GraphQL 查询 {endpoint} 返回错误（queryId/features 可能已过期）: "
                + str(payload["errors"])[:200],
                response=response,
            )
        return payload


# GraphQL features 常量（对齐 RSSHub lib/routes/twitter/api/web-api/constants.ts
# 2026-08 最新版；X 对缺失的新 feature 会返回 errors，需保持更新）
# UserByScreenName / Viewer 专属（RSSHub gqlFeatureUser）
_TW_USER_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
# 时间线类查询通用（UserMedia / TweetDetail / SearchTimeline 等，RSSHub gqlFeatureFeed）
_TW_FEED_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}
_TW_MEDIA_FEATURES = dict(_TW_FEED_FEATURES)
_TW_FEATURES = dict(_TW_FEED_FEATURES)
# SearchTimeline：GET 会被 x-client-transaction-id 校验拦截返回 404，必须用 POST 调用
_TW_SEARCH_FEATURES = dict(_TW_FEED_FEATURES)


def _twitter_check_login() -> tuple[bool, str | None, str]:
    """检查 Twitter 登录状态：GraphQL Viewer 查询（返回当前登录用户）。

    旧的 v1.1 verify_credentials 端点已被 X 下线（404），改用 Viewer。
    """
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token"):
        return False, None, "未配置 Twitter 登录信息"
    if not cookies.get("ct0"):
        return False, None, "Cookie 缺少 ct0，请复制完整 Cookie"
    try:
        data = _twitter_api_get(
            _twitter_qid("Viewer"), "Viewer", _TW_USER_FEATURES, {},
        )
        result = ((((data.get("data") or {}).get("viewer") or {})
                   .get("user_results") or {}).get("result")) or {}
        screen_name = ((result.get("core") or {}).get("screen_name")) or ""
        if screen_name:
            return True, screen_name, "Twitter 登录有效"
        return False, None, "Twitter 返回数据异常，请稍后重试"
    except PermissionError as exc:
        return False, None, str(exc)
    except (requests.RequestException, ValueError) as exc:
        return False, None, f"Twitter 连接失败: {exc}（请检查代理设置）"


def twitter_set_cookies(cookie_str: str) -> None:
    """用户手动粘贴 cookie 字符串（auth_token=...; ct0=...），保存并验证。"""
    cookies: dict = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            if name.strip():
                cookies[name.strip()] = value.strip()
    if not cookies.get("auth_token"):
        emit({
            "event": "twitter_login_result",
            "success": False,
            "message": "Cookie 缺少 auth_token，请在浏览器登录 x.com 后复制 Cookie",
        })
        return
    _twitter_save_cookies({k: v for k, v in cookies.items() if k in ("auth_token", "ct0")})
    ok, screen_name, msg = _twitter_check_login()
    if ok and screen_name:
        # 记录账号名（账号档案展示/多账号区分用）
        saved = _twitter_load_cookies()
        saved["screen_name"] = screen_name
        _twitter_save_cookies(saved)
        _record_login_ok("twitter")
    emit({
        "event": "twitter_login_result",
        "success": ok,
        "username": screen_name or "",
        "message": msg,
        "network_issue": (not ok) and _login_network_issue("twitter"),
    })
    _emit_login_info()


def twitter_clear_cookies() -> None:
    """清除已保存的 Twitter 登录信息（加密存储）。"""
    _secure_store_clear_cred("twitter")
    emit({"event": "twitter_login_result", "success": False, "logout": True,
          "username": "", "message": "已退出登录"})
    _emit_login_info()


# ============================
# Twitter 关注列表 / 关注管理 / 关注分类（v1.1 接口，无需 queryId 轮换）
# ============================
TWITTER_FOLLOW_TAGS_FILE = "cache/twitter_follow_tags.json"
TWITTER_FOLLOWS_FILE = "cache/twitter_follows.json"


def _twitter_v11(method: str, path: str, params: dict | None = None) -> dict:
    """调用 x.com v1.1 接口（关注列表/关注操作）。

    v1.1 端点路径稳定（不像 GraphQL 每隔数周轮换 queryId），
    需要 Bearer + Cookie + csrf（ct0）三件套。
    """
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise PermissionError("未登录 Twitter，请先在左侧设置中登录")
    _twitter_throttle()
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER}",
        "Cookie": _twitter_cookie_str(),
        "X-Csrf-Token": cookies["ct0"],
        "Referer": TWITTER_HOST + "/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }
    url = f"{TWITTER_HOST}/i/api/1.1/{path}"
    if method.upper() == "GET":
        response = _twitter_session.get(url, params=params, headers=headers, timeout=20)
    else:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        response = _twitter_session.post(url, data=params, headers=headers, timeout=20)
    if response.status_code in (401, 403):
        raise PermissionError("Twitter 登录已失效，请重新填写 Cookie")
    if response.status_code == 429:
        raise PermissionError("Twitter API 被限流，请稍后再试")
    if response.status_code == 404:
        raise requests.HTTPError(
            f"v1.1 接口 {path} 不可用（X 可能已下线该接口）", response=response,
        )
    response.raise_for_status()
    return response.json()


def _twitter_current_user_id() -> str:
    """获取当前登录用户的 user_id（Viewer GraphQL）。"""
    data = _twitter_api_get(_twitter_qid("Viewer"), "Viewer", _TW_USER_FEATURES, {})
    result = ((((data.get("data") or {}).get("viewer") or {})
              .get("user_results") or {}).get("result")) or {}
    return str(result.get("rest_id") or "")


def _twitter_map_v11_user(user: dict, following: bool | None = None) -> dict:
    """v1.1 用户对象 → 前端展示条目（关注列表卡片）。"""
    screen_name = user.get("screen_name") or ""
    name = user.get("name") or screen_name
    avatar = user.get("profile_image_url_https") or ""
    if avatar:
        avatar = avatar.replace("_normal.", "_400x400.")
    if following is None:
        following = bool(user.get("following"))
    return {
        "album_name": f"{name} (@{screen_name})",
        "album_url": f"{TWITTER_HOST}/{screen_name}",
        "thumbnail": avatar,
        "files": user.get("media_count"),
        "site": "twitter",
        "user_id": str(user.get("id_str") or user.get("id") or ""),
        "screen_name": screen_name,
        "name": name,
        "description": (user.get("description") or "")[:120],
        "followers_count": user.get("followers_count"),
        "friends_count": user.get("friends_count"),
        "statuses_count": user.get("statuses_count"),
        "verified": bool(user.get("verified")),
        "following": following,
    }


def _load_twitter_follow_tags() -> list[dict]:
    """读取关注分类（母子 tag）：[{"name": 母类, "children": [子类, ...]}]。"""
    try:
        data = json.loads(Path(TWITTER_FOLLOW_TAGS_FILE).read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [p for p in data if isinstance(p, dict) and p.get("name")]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_twitter_follow_tags(tags: list[dict]) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(TWITTER_FOLLOW_TAGS_FILE).write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError as exc:
        logging.warning("保存关注分类失败: %s", exc)


def _emit_twitter_follow_tags() -> None:
    emit({"event": "twitter_follow_tags", "tags": _load_twitter_follow_tags()})


def _load_twitter_follows() -> dict:
    """读取已归类的关注链接：{user_id: {screen_name, name, avatar, url, parent, child, saved_at}}。"""
    try:
        data = json.loads(Path(TWITTER_FOLLOWS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_twitter_follows(follows: dict) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(TWITTER_FOLLOWS_FILE).write_text(
            json.dumps(follows, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError as exc:
        logging.warning("保存关注归类失败: %s", exc)


def _emit_twitter_follows() -> None:
    follows = _load_twitter_follows()
    tags = _load_twitter_follow_tags()
    valid = set()
    for p in tags:
        valid.add(p["name"])
        for c in p.get("children") or []:
            valid.add(f"{p['name']}/{c}")
    items = []
    for uid, entry in follows.items():
        tag = entry.get("parent") or ""
        if entry.get("child"):
            tag = f"{tag}/{entry['child']}" if tag else entry["child"]
        items.append({
            "user_id": uid,
            "screen_name": entry.get("screen_name") or "",
            "name": entry.get("name") or "",
            "album_url": entry.get("url") or "",
            "thumbnail": entry.get("avatar") or "",
            "parent": entry.get("parent") or "",
            "child": entry.get("child") or "",
            "tag": tag,
            "saved_at": entry.get("saved_at"),
        })
    items.sort(key=lambda x: (x["parent"], x["child"], x["screen_name"].lower()))
    emit({"event": "twitter_follows", "items": items})


TWITTER_USER_LISTS_DIR = "cache/twitter_user_lists"
TWITTER_BROWSE_CACHE_FILE = "cache/twitter_browse_cache.json"


def _twitter_user_list_cache_path(mode: str, screen_name: str) -> Path:
    """关注列表缓存路径（按 模式+用户 区分；自己用 self）。"""
    key = (screen_name or "self").strip().lstrip("@").replace("/", "_") or "self"
    return Path(TWITTER_USER_LISTS_DIR) / f"{mode}_{key}.json"


def _load_twitter_user_list(mode: str, screen_name: str) -> dict | None:
    try:
        data = json.loads(
            _twitter_user_list_cache_path(mode, screen_name).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_twitter_user_list(mode: str, screen_name: str, payload: dict) -> None:
    try:
        Path(TWITTER_USER_LISTS_DIR).mkdir(parents=True, exist_ok=True)
        _twitter_user_list_cache_path(mode, screen_name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logging.warning("保存 Twitter 关注列表缓存失败: %s", exc)


async def twitter_follow_list(mode: str, cursor: str = "",
                              screen_name: str = "") -> None:
    """拉取关注列表（我关注的人/关注我的人/指定用户的）。

    mode: "following"=关注列表 / "followers"=关注我的人。
    screen_name: 指定用户（空 = 当前登录用户）。
    v1.1 friends/list / followers/list，每页最多 200 人，cursor 翻页。
    首页结果缓存到 cache/twitter_user_lists/；重新打开时：
      1) 先显示缓存（界面立即有内容）
      2) 完整刷新：翻页拉取全部（上限 10 页防限流），与缓存对比后重建缓存
         （新增/取消关注的人员都会体现），追加加载的页也会合并进缓存。
    """
    emit({"event": "twitter_follow_loading", "mode": mode, "loading": True})
    label = "关注我的人" if mode == "followers" else "关注列表"
    if screen_name:
        label = f"@{screen_name.lstrip('@')} 的{label}"
    # ---------- 我的分类：与左侧「分类管理」同一数据源（follow_tags/follows 存储） ----------
    # 此前 follows 落进 else 被当 following 拉全量关注列表，显示与左侧分类管理对不上。
    # 现改为直接从归类存储构建「已归类用户」列表：分类 chip、成员与左侧面板完全同源。
    if mode == "follows":
        try:
            tags = _load_twitter_follow_tags()
            follows = _load_twitter_follows()
            valid_parents = {p.get("name") for p in tags if p.get("name")}
            items: list[dict] = []
            for uid, rec in follows.items():
                parent = rec.get("parent") or ""
                child = rec.get("child") or ""
                # 归类已被删除的母类/子类的用户不显示（与左侧面板口径一致）
                if parent not in valid_parents:
                    continue
                if child and child not in [c for p2 in tags
                                           if p2.get("name") == parent
                                           for c in (p2.get("children") or [])]:
                    continue
                name = rec.get("name") or rec.get("screen_name") or uid
                handle = rec.get("screen_name") or ""
                avatar = rec.get("avatar") or ""
                home = rec.get("url") or (f"https://x.com/{handle}" if handle else "")
                items.append({
                    "user_id": str(uid),
                    "screen_name": handle,
                    "name": name,
                    "album_name": name,
                    "avatar": avatar,
                    "thumbnail": avatar,
                    "url": home,
                    "album_url": home,
                    "files": 0,
                    "bio": "",
                    "follow_tag": f"{parent}/{child}".strip("/"),
                    "has_tag": True,
                    "saved_at": rec.get("saved_at") or 0,
                })
            items.sort(key=lambda x: x.get("saved_at") or 0, reverse=True)
            _apply_cached_thumbnails(items)
            asyncio.create_task(_cache_thumbnails(items))
            emit({
                "event": "twitter_follow_list",
                "mode": "follows",
                "label": "我的分类（已归类的关注）",
                "items": items,
                "next_cursor": "",
                "has_more": False,
                "append": False,
            })
        except Exception as exc:
            logging.exception("我的分类构建失败")
            emit({"event": "twitter_follow_list", "mode": "follows", "items": [],
                  "next_cursor": "", "has_more": False, "append": False,
                  "error": f"构建我的分类失败: {exc}"})
        finally:
            emit({"event": "twitter_follow_loading", "mode": "follows", "loading": False})
        return
    # 先发缓存（仅首页），让界面立即有内容
    if not cursor:
        cached = _load_twitter_user_list(mode, screen_name)
        if cached and cached.get("items"):
            items = list(cached["items"])
            _apply_cached_thumbnails(items)
            emit({"event": "twitter_follow_list", "mode": mode, "label": label,
                  "items": items, "next_cursor": cached.get("next_cursor") or "",
                  "has_more": bool(cached.get("has_more")), "append": False,
                  "cached": True})
    try:
        if mode == "followers":
            path = "followers/list.json"
        else:
            mode, path = "following", "friends/list.json"

        def _apply_tags(items: list[dict]) -> None:
            # 合并已归类的分类 tag（卡片上显示）
            follows = _load_twitter_follows()
            for it in items:
                saved = follows.get(it["user_id"])
                if saved:
                    it["follow_tag"] = f"{saved.get('parent') or ''}/{saved.get('child') or ''}".strip("/")
                    it["has_tag"] = True

        if cursor:
            # ---------- 追加加载（cursor 翻页），同时把新页合并进缓存 ----------
            params: dict = {"count": 200, "skip_status": True, "include_user_entities": False}
            if screen_name:
                params["screen_name"] = screen_name.lstrip("@")
            params["cursor"] = cursor
            data = await asyncio.to_thread(_twitter_v11, "GET", path, params)
            users = data.get("users") or []
            items = [_twitter_map_v11_user(u) for u in users]
            _apply_tags(items)
            next_cursor = str(data.get("next_cursor") or "")
            has_more = bool(next_cursor and next_cursor != "0")
            # 合并进缓存：重新打开时能看到全部已加载过的人
            cached = _load_twitter_user_list(mode, screen_name) or {}
            merged = list(cached.get("items") or [])
            ids = {str(i.get("user_id")) for i in merged}
            for it in items:
                if str(it["user_id"]) not in ids:
                    merged.append(it)
            _save_twitter_user_list(mode, screen_name, {
                "items": merged, "next_cursor": next_cursor if has_more else "",
                "has_more": has_more, "updated_at": time.time(),
            })
            if items:
                _apply_cached_thumbnails(items)
                asyncio.create_task(_cache_thumbnails(items))
            emit({
                "event": "twitter_follow_list",
                "mode": mode,
                "label": label,
                "items": items,
                "next_cursor": next_cursor if has_more else "",
                "has_more": has_more,
                "append": True,
            })
        else:
            # ---------- 重新打开：完整刷新（翻页拉全部，上限 10 页防限流），对比缓存增删 ----------
            all_items: list[dict] = []
            cur = ""
            seen_ids = set()
            for _page in range(10):
                params = {"count": 200, "skip_status": True, "include_user_entities": False}
                if screen_name:
                    params["screen_name"] = screen_name.lstrip("@")
                if cur:
                    params["cursor"] = cur
                data = await asyncio.to_thread(_twitter_v11, "GET", path, params)
                users = data.get("users") or []
                if not users:
                    break
                for u in users:
                    it = _twitter_map_v11_user(u)
                    if str(it["user_id"]) not in seen_ids:
                        seen_ids.add(str(it["user_id"]))
                        all_items.append(it)
                cur = str(data.get("next_cursor") or "")
                if not cur or cur == "0":
                    break
            _apply_tags(all_items)
            has_more = bool(cur and cur != "0")
            next_cursor = cur if has_more else ""
            # 对比旧缓存：统计新增/移除的人员数（写日志 + 事件带差异信息）
            old = _load_twitter_user_list(mode, screen_name) or {}
            old_ids = {str(i.get("user_id")) for i in (old.get("items") or [])}
            new_ids = {str(i.get("user_id")) for i in all_items}
            added = len(new_ids - old_ids)
            removed = len(old_ids - new_ids)
            if old_ids:
                logging.info("Twitter %s 刷新完成: 新增 %d 人, 移除 %d 人", mode, added, removed)
            if all_items:
                _apply_cached_thumbnails(all_items)
                asyncio.create_task(_cache_thumbnails(all_items))
            _save_twitter_user_list(mode, screen_name, {
                "items": all_items, "next_cursor": next_cursor,
                "has_more": has_more, "updated_at": time.time(),
            })
            emit({
                "event": "twitter_follow_list",
                "mode": mode,
                "label": label,
                "items": all_items,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "append": False,
                "added": added,
                "removed": removed,
            })
    except PermissionError as exc:
        emit({"event": "twitter_follow_list", "mode": mode, "items": [],
              "next_cursor": "", "has_more": False, "append": bool(cursor),
              "error": str(exc)})
    except Exception as exc:
        logging.exception("Twitter 关注列表获取失败")
        msg = f"获取关注列表失败: {exc}（请检查登录状态与代理）"
        # 已展示缓存时不报错误横幅，只记日志
        if cursor or not _load_twitter_user_list(mode, screen_name):
            emit({"event": "twitter_follow_list", "mode": mode, "items": [],
                  "next_cursor": "", "has_more": False, "append": bool(cursor),
                  "error": msg})
        else:
            emit({"event": "twitter_follow_list", "mode": mode, "items": [],
                  "next_cursor": "", "has_more": False, "append": True, "refresh_failed": msg})
    finally:
        emit({"event": "twitter_follow_loading", "mode": mode, "loading": False})


async def twitter_browse(offset: int = 0) -> None:
    """浏览模式：聚合我关注博主的最近媒体更新（类似 X 首页时间线）。

    取关注列表（首页缓存），逐个拉 UserMedia 最新一页，每人最多取 2 条，
    按推文时间倒序合并成信息流。结果缓存到 cache/twitter_browse_cache.json，
    重新点击时先显示缓存再后台刷新。
    offset > 0 时为"加载更多"：跳过已拉取的博主，只追加新内容（append 模式）。
    """
    cached = None
    try:
        data = json.loads(Path(TWITTER_BROWSE_CACHE_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("items"):
            cached = data
    except (OSError, json.JSONDecodeError):
        pass
    if cached and not offset:
        items = list(cached["items"])
        _apply_cached_thumbnails(
            [m for it in items for m in it.get("media") or []] or items)
        emit({"event": "twitter_browse_feed", "items": items,
              "updated_at": cached.get("updated_at"), "cached": True})

    emit({"event": "twitter_browse_loading", "loading": True, "offset": offset})
    try:
        # 1. 关注列表（优先用缓存避免重复请求；缓存不足时再拉一页）
        follow_cache = _load_twitter_user_list("following", "")
        if follow_cache and follow_cache.get("items") and (
                offset == 0 or len(follow_cache.get("items") or []) > offset):
            users = list(follow_cache["items"])
        else:
            data = await asyncio.to_thread(
                _twitter_v11, "GET", "friends/list.json",
                {"count": 200, "skip_status": True, "include_user_entities": False},
            )
            users = [_twitter_map_v11_user(u) for u in (data.get("users") or [])]
            _save_twitter_user_list("following", "", {
                "items": users, "next_cursor": str(data.get("next_cursor") or ""),
                "has_more": bool(data.get("next_cursor")), "updated_at": time.time(),
            })
        if not users:
            emit({"event": "twitter_browse_feed", "items": [], "updated_at": time.time()})
            return
        # 有推文的博主优先；offset 为已拉取人数，每批 30 人（节流 1.2s/请求）
        candidates = [u for u in users if (u.get("statuses_count") or 0) > 0]
        candidates = candidates or users
        candidates = candidates[offset:offset + 30]
        has_more = (offset + 30) < len([u for u in users if (u.get("statuses_count") or 0) > 0] or users)
        total = len(candidates)
        if not candidates:
            emit({"event": "twitter_browse_feed", "items": [],
                  "updated_at": time.time(), "append": True, "no_more": True})
            return
        feed: list[dict] = []
        done = 0
        for u in candidates:
            user_id = str(u.get("user_id") or "")
            if not user_id:
                continue
            try:
                variables = {
                    "userId": user_id, "count": 20,
                    "includePromotedContent": False,
                    "withClientEventToken": False, "withBirdwatchNotes": False,
                    "withVoice": True, "withV2Timeline": True,
                }
                data = await asyncio.to_thread(
                    _twitter_api_get,
                    _twitter_qid("UserMedia"), "UserMedia",
                    _TW_MEDIA_FEATURES, variables,
                )
                instructions = _tw_user_instructions(data)
                posts = _twitter_extract_posts(instructions)[:2]  # 每人最多 2 条
                for post in posts:
                    legacy = post.get("legacy") or {}
                    if legacy.get("retweeted_status_result"):
                        continue
                    medias = legacy.get("entities", {}).get("media") or []
                    media_items = []
                    for idx, m in enumerate(medias, start=1):
                        mtype = m.get("type")
                        media_url, thumb = "", ""
                        if mtype == "photo":
                            base = m.get("media_url_https") or ""
                            media_url = f"{base}?name=orig" if base else ""
                            thumb = f"{base}?name=small" if base else ""
                        elif mtype in ("video", "animated_gif"):
                            variants = (m.get("video_info") or {}).get("variants") or []
                            mp4s = [v for v in variants
                                    if v.get("content_type") == "video/mp4" and v.get("url")]
                            if mp4s:
                                media_url = max(mp4s, key=lambda v: v.get("bitrate") or 0)["url"]
                            elif variants:
                                media_url = variants[0].get("url") or ""
                            thumb = m.get("media_url_https") or ""
                        if media_url:
                            media_items.append({
                                "media_url": media_url,
                                "thumbnail": thumb,
                                "type": "video" if mtype != "photo" else "photo",
                                "index": idx,
                            })
                    if not media_items:
                        continue
                    created_at = legacy.get("created_at") or ""
                    post_date = ""
                    if created_at:
                        try:
                            post_date = datetime.strptime(
                                created_at, "%a %b %d %H:%M:%S %z %Y",
                            ).strftime("%Y-%m-%d %H:%M")
                        except ValueError:
                            pass
                    tweet_id = post.get("rest_id") or legacy.get("id_str") or ""
                    feed.append({
                        "tweet_id": tweet_id,
                        "item_page": f"{TWITTER_HOST}/{u.get('screen_name')}/status/{tweet_id}",
                        "text": (legacy.get("full_text") or "").strip()[:200],
                        "post_date": post_date,
                        "created_ts": _tw_created_ts(created_at),
                        "user": {
                            "user_id": user_id,
                            "screen_name": u.get("screen_name") or "",
                            "name": u.get("name") or "",
                            "thumbnail": u.get("thumbnail") or "",
                            "album_url": u.get("album_url") or "",
                            "following": u.get("following"),
                        },
                        "media": media_items,
                    })
            except Exception as exc:
                logging.debug("浏览模式拉取 @%s 失败: %s", u.get("screen_name"), exc)
            finally:
                done += 1
                emit({"event": "twitter_browse_progress", "done": done, "total": total})
        # 按发布时间倒序（无时间的排最后）；追加模式合并旧缓存后统一排序
        feed.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
        if offset:
            # 加载更多：与旧缓存合并去重（按推文 id）
            old = (cached or {}).get("items") or []
            seen_ids = {t.get("tweet_id") for t in feed}
            merged = list(feed)
            for t in old:
                if t.get("tweet_id") not in seen_ids:
                    seen_ids.add(t.get("tweet_id"))
                    merged.append(t)
            merged.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
            feed = merged
        feed = feed[:600]
        if feed:
            _apply_cached_thumbnails([m for it in feed for m in it["media"]])
            asyncio.create_task(_cache_thumbnails(
                [m for it in feed for m in it["media"]]))
        updated_at = time.time()
        try:
            Path("cache").mkdir(parents=True, exist_ok=True)
            Path(TWITTER_BROWSE_CACHE_FILE).write_text(
                json.dumps({"items": feed, "updated_at": updated_at,
                            "offset": offset + total},
                           ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logging.warning("保存浏览模式缓存失败: %s", exc)
        emit({"event": "twitter_browse_feed", "items": feed,
              "updated_at": updated_at, "append": bool(offset),
              "has_more": has_more, "next_offset": offset + total})
    except PermissionError as exc:
        emit({"event": "twitter_browse_feed", "items": [], "error": str(exc)})
    except Exception as exc:
        logging.exception("Twitter 浏览模式失败")
        emit({"event": "twitter_browse_feed", "items": [],
              "error": f"获取最近更新失败: {exc}（请检查登录状态与代理）"})
    finally:
        emit({"event": "twitter_browse_loading", "loading": False})


def _tw_created_ts(created_at: str) -> int:
    """推文 created_at 文本 → Unix 时间戳（失败返回 0）。"""
    if not created_at:
        return 0
    try:
        return int(datetime.strptime(
            created_at, "%a %b %d %H:%M:%S %z %Y").timestamp())
    except ValueError:
        return 0


def twitter_clear_cache() -> None:
    """清除 Twitter 专属缓存（保留登录 Cookie 与关注分类数据）。

    清理项：queryId 缓存 / 关注列表缓存 / 浏览模式缓存 / 用户媒体解析缓存。
    """
    removed = 0
    targets: list[Path] = [
        Path("cache/twitter_qids.json"),
        Path(TWITTER_BROWSE_CACHE_FILE),
    ]
    # 关注列表缓存目录
    lists_dir = Path(TWITTER_USER_LISTS_DIR)
    if lists_dir.is_dir():
        targets.extend(p for p in lists_dir.iterdir() if p.is_file())
    # 用户媒体解析缓存（identifier 以 twitter_ 开头）
    albums_dir = Path(ALBUM_CACHE_DIR)
    if albums_dir.is_dir():
        targets.extend(p for p in albums_dir.glob("twitter_*.json"))
    for p in targets:
        try:
            if p.exists():
                p.unlink()
                removed += 1
        except OSError:
            pass
    emit({"event": "twitter_cache_cleared", "removed": removed,
          "message": f"已清除 Twitter 缓存（{removed} 项）；登录信息与关注分类已保留"})


async def twitter_follow(user_id: str, screen_name: str = "") -> None:
    """关注用户（v1.1 friendships/create；失败时回退 GraphQL CreateFollower）。"""
    try:
        data = await asyncio.to_thread(
            _twitter_v11, "POST", "friendships/create.json", {"user_id": user_id},
        )
        ok = bool(data.get("following"))
        msg = f"已关注 @{data.get('screen_name') or screen_name or user_id}"
    except requests.HTTPError:
        # v1.1 接口不可用时的 GraphQL 回退（queryId 自动刷新）
        try:
            data = await asyncio.to_thread(
                _twitter_api_post, "CreateFollower", "CreateFollower",
                {"user_id": user_id},
            )
            ok = bool(((data.get("data") or {}).get("create_follower") or {})
                      .get("following"))
            msg = f"已关注 @{screen_name or user_id}"
        except Exception as exc:
            emit({"event": "twitter_follow_result", "user_id": user_id,
                  "screen_name": screen_name, "success": False, "following": False,
                  "message": f"关注失败: {exc}"})
            return
    except PermissionError as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": False,
              "message": str(exc)})
        return
    except Exception as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": False,
              "message": f"关注失败: {exc}"})
        return
    emit({"event": "twitter_follow_result", "user_id": user_id,
          "screen_name": screen_name, "success": True, "following": True,
          "message": msg})


async def twitter_unfollow(user_id: str, screen_name: str = "") -> None:
    """取消关注用户（v1.1 friendships/destroy；失败时回退 GraphQL DeleteFollower）。"""
    try:
        data = await asyncio.to_thread(
            _twitter_v11, "POST", "friendships/destroy.json", {"user_id": user_id},
        )
        ok = not bool(data.get("following"))
        msg = f"已取消关注 @{data.get('screen_name') or screen_name or user_id}"
    except requests.HTTPError:
        try:
            data = await asyncio.to_thread(
                _twitter_api_post, "DeleteFollower", "DeleteFollower",
                {"user_id": user_id},
            )
            ok = True
            msg = f"已取消关注 @{screen_name or user_id}"
        except Exception as exc:
            emit({"event": "twitter_follow_result", "user_id": user_id,
                  "screen_name": screen_name, "success": False, "following": True,
                  "message": f"取消关注失败: {exc}"})
            return
    except PermissionError as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": True,
              "message": str(exc)})
        return
    except Exception as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": True,
              "message": f"取消关注失败: {exc}"})
        return
    emit({"event": "twitter_follow_result", "user_id": user_id,
          "screen_name": screen_name, "success": True, "following": False,
          "message": msg})


def _twitter_api_post(query_id: str, endpoint: str, variables: dict,
                      features: dict | None = None) -> dict:
    """调用 x.com GraphQL mutation（POST，用于关注/取关等写操作）。"""
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise PermissionError("未登录 Twitter，请先在设置中填写 Cookie")
    qid = _twitter_qid(endpoint) or query_id
    if not qid or not re.fullmatch(r"[0-9a-zA-Z_-]{10,30}", qid or ""):
        # mutation 的 queryId 未缓存（默认值为空），先从 main.js 抓取
        _twitter_refresh_qids(True)
        qid = _twitter_qid(endpoint) or query_id
    if not qid:
        raise requests.HTTPError(f"未找到 GraphQL 操作 {endpoint} 的 queryId")
    body = {"variables": variables, "queryId": qid}
    if features:
        body["features"] = features
    retried = False  # 每次调用最多自动重试一次，防死循环
    while True:
        _twitter_throttle()
        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Cookie": _twitter_cookie_str(),
            "X-Csrf-Token": cookies["ct0"],
            "Content-Type": "application/json",
            "Referer": TWITTER_HOST + "/",
        }
        response = _twitter_session.post(
            f"{TWITTER_HOST}/i/api/graphql/{qid}/{endpoint}",
            json=body, headers=headers, timeout=20,
        )
        if response.status_code == 404:
            if not retried:
                retried = True
                if _twitter_refresh_qids(True):
                    new_qid = _twitter_qid(endpoint)
                    if new_qid and new_qid != qid:
                        qid = new_qid
                        body["queryId"] = qid
                        continue
            raise requests.HTTPError(
                f"404：GraphQL 操作 {endpoint} 不存在（queryId 可能已过期）",
                response=response,
            )
        if response.status_code in (401, 403):
            raise PermissionError("Twitter 登录已失效，请重新填写 Cookie")
        if response.status_code == 429:
            raise PermissionError("Twitter API 被限流，请稍后再试")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            return {}
        # 同 GET：200 + errors（无 data）时刷新 queryId 后必重试一次
        # （即使 qid 未变——errors 也可能是瞬时故障；body 独立保存避免被响应覆盖）
        if payload.get("errors") and not isinstance(payload.get("data"), dict):
            if not retried:
                retried = True
                _twitter_refresh_qids(True)
                new_qid = _twitter_qid(endpoint)
                if new_qid:
                    qid = new_qid
                    body["queryId"] = qid
                    continue
            raise requests.HTTPError(
                f"GraphQL 操作 {endpoint} 返回错误（queryId 可能已过期）: "
                + str(payload["errors"])[:200],
                response=response,
            )
        return payload


def _twitter_add_follow_tag(parent: str, child: str = "") -> None:
    """新增关注分类（母类，或已有母类下加子类）。"""
    parent = (parent or "").strip()
    child = (child or "").strip()
    if not parent and not child:
        emit({"event": "account_error", "message": "分类名不能为空"})
        return
    tags = _load_twitter_follow_tags()
    names = {t["name"] for t in tags}
    if not parent:
        emit({"event": "account_error", "message": "请先填写母类名"})
        return
    if not child:
        if parent in names:
            emit({"event": "account_error", "message": f"母类「{parent}」已存在"})
            return
        tags.append({"name": parent, "children": []})
        _save_twitter_follow_tags(tags)
        _emit_twitter_follow_tags()
        emit({"event": "account_saved", "message": f"已新增母类「{parent}」"})
        return
    for t in tags:
        if t["name"] == parent:
            if child not in (t.get("children") or []):
                t.setdefault("children", []).append(child)
                _save_twitter_follow_tags(tags)
                _emit_twitter_follow_tags()
                emit({"event": "account_saved", "message": f"「{parent}」下已新增子类「{child}」"})
            else:
                emit({"event": "account_error", "message": f"子类「{child}」已存在"})
            return
    tags.append({"name": parent, "children": [child]})
    _save_twitter_follow_tags(tags)
    _emit_twitter_follow_tags()
    emit({"event": "account_saved", "message": f"已新增分类「{parent}/{child}」"})


def _twitter_delete_follow_tag(parent: str, child: str = "") -> None:
    """删除关注分类（母类或子类）。删除母类时其下子类一并删除。"""
    tags = _load_twitter_follow_tags()
    if not child:
        new_tags = [t for t in tags if t["name"] != parent]
        if len(new_tags) == len(tags):
            emit({"event": "account_error", "message": f"母类「{parent}」不存在"})
            return
        _save_twitter_follow_tags(new_tags)
        _emit_twitter_follow_tags()
        emit({"event": "account_saved", "message": f"已删除母类「{parent}」"})
        return
    for t in tags:
        if t["name"] == parent:
            children = t.get("children") or []
            if child not in children:
                emit({"event": "account_error", "message": f"子类「{child}」不存在"})
                return
            t["children"] = [c for c in children if c != child]
            _save_twitter_follow_tags(tags)
            _emit_twitter_follow_tags()
            emit({"event": "account_saved", "message": f"已删除「{parent}/{child}」"})
            return
    emit({"event": "account_error", "message": f"母类「{parent}」不存在"})


def _twitter_set_follow_tag(user: dict, parent: str, child: str) -> None:
    """保存/更新关注用户的分类归属（parent 为空 = 移除归类）。"""
    follows = _load_twitter_follows()
    user_id = str(user.get("user_id") or "")
    if not user_id:
        emit({"event": "account_error", "message": "缺少用户信息，无法归类"})
        return
    parent = (parent or "").strip()
    child = (child or "").strip()
    if not parent:
        if follows.pop(user_id, None) is not None:
            _save_twitter_follows(follows)
            _emit_twitter_follows()
            emit({"event": "account_saved",
                  "message": f"已移除 @{user.get('screen_name') or ''} 的分类"})
        else:
            emit({"event": "account_error", "message": "该用户尚未归类"})
        return
    # 校验分类存在（不存在则自动创建，方便快速录入）
    tags = _load_twitter_follow_tags()
    entry = next((t for t in tags if t["name"] == parent), None)
    if entry is None:
        tags.append({"name": parent, "children": [child] if child else []})
        _save_twitter_follow_tags(tags)
        _emit_twitter_follow_tags()
    elif child and child not in (entry.get("children") or []):
        entry.setdefault("children", []).append(child)
        _save_twitter_follow_tags(tags)
        _emit_twitter_follow_tags()
    avatar = user.get("thumbnail") or user.get("avatar") or ""
    if avatar and "_400x400" in avatar:
        avatar = avatar.replace("_400x400.", "_normal.")
    follows[user_id] = {
        "screen_name": user.get("screen_name") or "",
        "name": user.get("name") or "",
        "avatar": avatar,
        "url": user.get("album_url") or f"{TWITTER_HOST}/{user.get('screen_name', '')}",
        "parent": parent,
        "child": child,
        "saved_at": time.time(),
    }
    _save_twitter_follows(follows)
    _emit_twitter_follows()
    tag_text = f"{parent}/{child}" if child else parent
    emit({"event": "account_saved",
          "message": f"已将 @{user.get('screen_name') or ''} 归类到「{tag_text}」"})


def _tw_user_instructions(data: dict) -> list:
    """从 UserMedia/UserTweets 响应提取 timeline instructions（三级回退）。

    X 新旧版本响应路径不同，参考 RSSHub lib/routes/twitter/utils.ts
    paginationTweets：result.timeline_v2.timeline（新）/
    result.timeline.timeline（旧）/ result.timeline.timeline_v2（过渡）。
    """
    result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
    timeline = ((result.get("timeline_v2") or {}).get("timeline")
                or (result.get("timeline") or {}).get("timeline")
                or (result.get("timeline") or {}).get("timeline_v2"))
    instructions = (timeline or {}).get("instructions")
    return instructions if isinstance(instructions, list) else []


def _twitter_extract_posts(instructions: list) -> list[dict]:
    """从 GraphQL timeline instructions 中提取推文 result 列表。"""
    posts: list[dict] = []

    def _unwrap(result: dict | None) -> dict | None:
        """解包推文结果：TweetWithVisibilityResults 需取 .tweet（X-Spider 同款）。"""
        if not result:
            return None
        if result.get("__typename") == "TweetWithVisibilityResults":
            return result.get("tweet") or result
        return result

    for inst in instructions or []:
        if inst.get("type") not in ("TimelineAddEntries", "TimelineAddToModule"):
            continue
        entries = inst.get("entries") or []
        # TimelineAddToModule：线程追加（moduleItems）
        if not entries and inst.get("moduleItems"):
            for mi in inst["moduleItems"]:
                r = _unwrap((mi.get("item", {}).get("itemContent", {})
                             .get("tweet_results", {}).get("result")))
                if r:
                    posts.append(r)
            continue
        for entry in entries:
            entry_id = entry.get("entryId", "")
            content = entry.get("content", {})
            if entry_id.startswith("tweet-"):
                r = _unwrap(content.get("itemContent", {})
                            .get("tweet_results", {}).get("result"))
                if r:
                    posts.append(r)
            elif entry_id.startswith(("profile-conversation", "conversationthread")):
                # 线程中的多条推文（TimelineTimelineModule）
                for it in content.get("items", []):
                    r = _unwrap((it.get("item", {}).get("itemContent", {})
                                 .get("tweet_results", {}).get("result")))
                    if r:
                        posts.append(r)
            elif content.get("items"):
                # 模块条目：线程（conversationthread / TimelineTimelineModule）与
                # X 新版 UserMedia 网格（profile-grid-0 / TimelineModule，
                # RSSHub 优先取此结构），items 同构：item.itemContent.tweet_results
                for it in content.get("items", []):
                    r = _unwrap((it.get("item", {}).get("itemContent", {})
                                 .get("tweet_results", {}).get("result")))
                    if r:
                        posts.append(r)
    return posts


def _twitter_filename(post_date: str, title: str, tweet_id: str, idx: int, ext: str) -> str:
    """X 文件名规则：发帖日期_帖子内容_序号.ext（无内容回退推文ID）。"""
    safe_title = sanitize_directory_name((title or "").strip())[:40]
    if post_date and safe_title:
        return f"{post_date}_{safe_title}_{idx:02d}.{ext}"
    if post_date and tweet_id:
        return f"{post_date}_{tweet_id}_{idx:02d}.{ext}"
    if tweet_id:
        return f"{tweet_id}_{idx:02d}.{ext}"
    return f"twitter_{int(time.time())}_{idx:02d}.{ext}"


def _twitter_map_tweet(result: dict) -> list[dict]:
    """把单条推文的 GraphQL result 转成下载条目（跳过转推/无媒体）。

    图片取 orig 原图质量；视频取最高码率 mp4。
    文件名：发帖日期_帖子内容_序号.ext（目录：用户名/图片|视频）。
    """
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet") or result
    legacy = result.get("legacy") or {}
    # 跳过转推（原推会在自己的时间线里出现）
    if legacy.get("retweeted_status_result"):
        return []
    medias = legacy.get("entities", {}).get("media") or []
    if not medias:
        return []

    tweet_id = result.get("rest_id") or legacy.get("id_str") or ""
    screen_name = ((result.get("core", {}).get("user_results", {})
                    .get("result", {}).get("legacy", {}) or {}).get("screen_name")) or ""
    full_text = (legacy.get("full_text") or "").strip()
    created_at = legacy.get("created_at") or ""
    post_date = ""
    if created_at:
        try:
            post_date = datetime.strptime(
                created_at, "%a %b %d %H:%M:%S %z %Y",
            ).strftime("%Y-%m-%d")
        except ValueError:
            pass

    items: list[dict] = []
    for idx, m in enumerate(medias, start=1):
        mtype = m.get("type")
        media_url = ""
        ext = "jpg"
        thumb = m.get("media_url_https") or ""
        if mtype == "photo":
            base = m.get("media_url_https") or ""
            if base:
                ext = base.rsplit(".", 1)[-1].lower() if "." in base else "jpg"
                if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                    ext = "jpg"
                # X-Spider 同款：URL 本身带扩展名，只加 name 参数（orig=原图）
                media_url = f"{base}?name=orig"
                thumb = f"{base}?name=small"
        elif mtype in ("video", "animated_gif"):
            variants = (m.get("video_info") or {}).get("variants") or []
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bitrate") or 0)
                media_url = best["url"]
                ext = "mp4"
            elif variants:
                media_url = variants[0].get("url") or ""
                ext = "webm"
        if not media_url:
            continue
        filename = _twitter_filename(post_date, full_text, tweet_id, idx, ext)
        items.append({
            "filename": filename,
            "size": None,
            "item_page": f"https://x.com/{screen_name}/status/{tweet_id}" if screen_name else "",
            "status": "pending",
            "site": "twitter",
            "media_url": media_url,
            "thumbnail": thumb,
            "post_date": post_date,
            "post_title": full_text[:80],
            "post_id": tweet_id,
            "media_type": "video" if mtype in ("video", "animated_gif") else "photo",
        })
    return items


async def twitter_search(query: str) -> None:
    """X 搜索：
    - "@用户名"（仅限博主）→ 验证用户后直接解析 TA 的全部媒体（下载内容）；
    - 其他任意关键词 → SearchTimeline 内容搜索，返回带媒体的推文卡片。
    """
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "请输入搜索内容（关键词，或 @用户名）"})
        return
    emit({"event": "search_start", "query": query, "page": 1})

    # ---------- 仅限博主（@用户名）：直接解析该博主的全部媒体 ----------
    if query.startswith("@"):
        await _twitter_search_user(query.lstrip("@"))
        return

    # ---------- 内容搜索：SearchTimeline ----------
    try:
        raw_query = f"{query} filter:media"  # 只搜带媒体的内容（本工具用于下载）
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("SearchTimeline"), "SearchTimeline",
            _TW_SEARCH_FEATURES,
            {
                "rawQuery": raw_query,
                "count": 20,
                "querySource": "typed_query",
                "product": "Top",
            },
            None,
            True,  # use_post：GET 会被 x-client-transaction-id 校验拦截 404
        )
        instructions = ((((data.get("data") or {}).get("search_by_raw_query") or {})
                        .get("search_timeline") or {}).get("timeline")
                       or {}).get("instructions") or []
        posts = _twitter_extract_posts(instructions)
        items: list[dict] = []
        for post in posts:
            mapped = _twitter_map_tweet(post)
            if not mapped:
                continue
            first = mapped[0]
            user = post.get("core", {}).get("user_results", {}).get("result") or {}
            user_legacy = user.get("legacy") or {}
            screen_name = user_legacy.get("screen_name") or ""
            text = (post.get("legacy", {}).get("full_text") or "").strip()
            # 卡片标题：作者 + 推文摘要
            snippet = text.split("https://t.co/")[0].strip()[:40]
            tweet_id = post.get("rest_id") or ""
            items.append({
                "album_name": f"@{screen_name}: {snippet}" if snippet else f"@{screen_name} 的推文",
                "album_url": f"{TWITTER_HOST}/{screen_name}/status/{tweet_id}",
                "thumbnail": first.get("thumbnail") or "",
                "files": len(mapped),
                "site": "twitter",
                "post_date": first.get("post_date") or "",
            })
        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": query,
            "page": 1,
            "total_pages": 1,
            "total_results": len(items),
            "has_more": False,
            "items": items,
        })
        if items:
            asyncio.create_task(_cache_thumbnails(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"搜索出错: {exc}（需登录后才能进行内容搜索）"})
        logging.exception("Twitter 内容搜索出错")


async def _twitter_search_user(query: str) -> None:
    """@用户名 搜索：验证用户存在后直接解析其全部媒体。"""
    query = (query or "").strip().lstrip("@")
    if not query:
        emit({"event": "search_error", "message": "请输入用户名（如 @xxx）"})
        return
    try:
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("UserByScreenName"), "UserByScreenName",
            _TW_USER_FEATURES,
            {"screen_name": query, "withSafetyModeUserFields": True},
            {"fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})},
        )
        legacy = (((data.get("data") or {}).get("user") or {})
                  .get("result") or {}).get("legacy") or {}
        if not legacy:
            emit({"event": "search_result", "query": f"@{query}", "page": 1,
                  "total_pages": 1, "total_results": 0, "has_more": False, "items": []})
            return
        screen_name = legacy.get("screen_name") or query
        # 仅限博主：直接解析该博主的全部媒体（下载内容）
        await twitter_inspect(f"{TWITTER_HOST}/{screen_name}", dict(DEFAULT_SETTINGS))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"搜索出错: {exc}"})
        logging.exception("Twitter 用户搜索出错")


def _twitter_fetch_syndication(status_id: str) -> dict | None:
    """用公开 syndication API 获取单条推文（免登录）。"""
    try:
        token = int(int(status_id) / 40503) & 0xFFFFFFFF
        response = _twitter_session.get(
            "https://cdn.syndication.twimg.com/tweet-result",
            params={"id": status_id, "lang": "en", "token": str(token)},
            timeout=20,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None


async def twitter_inspect(url: str, options: dict) -> None:
    """解析 Twitter 用户主页（全部媒体）或单条推文，返回文件列表。"""
    info = _twitter_parse_url(url)
    if info is None:
        emit({"event": "inspect_error", "message": "无法识别的 Twitter 链接，请粘贴用户主页或推文链接"})
        return

    try:
        # ---------- 单条推文 ----------
        if info["kind"] == "status":
            items: list[dict] = []
            # 优先 TweetDetail GraphQL（需 cookie，结果与网页一致）
            try:
                data = await asyncio.to_thread(
                    _twitter_api_get,
                    _twitter_qid("TweetDetail"), "TweetDetail",
                    _TW_FEATURES,
                    {
                        "focalTweetId": info["status_id"],
                        "with_rux_injections": False,
                        "rankingMode": "Relevance",
                        "includePromotedContent": True,
                        "withCommunity": True,
                    },
                    {"fieldToggles": json.dumps({
                        "withArticleRichContentState": True,
                        "withArticlePlainText": False,
                        "withGrokAnalyze": False,
                        "withDisallowedReplyControls": False,
                    })},
                )
                instructions = ((data.get("data") or {})
                                .get("threaded_conversation_with_injections")
                                or {}).get("instructions") or []
                # 只取 focal 推文（避免把整条对话串都收进来）
                focal = "tweet-" + info["status_id"]
                for inst in instructions:
                    if inst.get("type") != "TimelineAddEntries":
                        continue
                    for entry in inst.get("entries") or []:
                        if entry.get("entryId") == focal:
                            r = (entry.get("content", {}).get("itemContent", {})
                                 .get("tweet_results", {}).get("result"))
                            if r:
                                items = _twitter_map_tweet(r)
                                break
                    if items:
                        break
            except (PermissionError, requests.RequestException, ValueError):
                pass
            # 回退：公开 syndication API（免登录，部分推文可用）
            if not items:
                data = await asyncio.to_thread(_twitter_fetch_syndication, info["status_id"])
                if data:
                    screen_name = (data.get("user") or {}).get("screen_name") or info["screen_name"]
                    tweet_id = str(data.get("id") or info["status_id"])
                    created = data.get("created_at") or ""
                    post_date = ""
                    if created:
                        try:
                            post_date = datetime.strptime(
                                created, "%a %b %d %H:%M:%S %z %Y",
                            ).strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                    text = (data.get("text") or "").strip()
                    idx = 0
                    for photo in data.get("photos") or []:
                        idx += 1
                        base = photo.get("url") or ""
                        if not base:
                            continue
                        ext = base.rsplit(".", 1)[-1].lower() if "." in base else "jpg"
                        items.append({
                            "filename": _twitter_filename(post_date, text, tweet_id, idx, ext),
                            "size": None,
                            "item_page": f"https://x.com/{screen_name}/status/{tweet_id}",
                            "status": "pending",
                            "site": "twitter",
                            "media_url": f"{base}?name=orig",
                            "thumbnail": f"{base}?name=small",
                            "post_date": post_date,
                            "post_title": text[:80],
                            "post_id": tweet_id,
                            "media_type": "photo",
                        })
                    video = data.get("video") or {}
                    for variant in video.get("variants") or []:
                        src = variant.get("src") or ""
                        if not src or variant.get("type") != "video/mp4":
                            continue
                        idx += 1
                        items.append({
                            "filename": _twitter_filename(post_date, text, tweet_id, idx, "mp4"),
                            "size": None,
                            "item_page": f"https://x.com/{screen_name}/status/{tweet_id}",
                            "status": "pending",
                            "site": "twitter",
                            "media_url": src,
                            "thumbnail": video.get("poster") or "",
                            "post_date": post_date,
                            "post_title": text[:80],
                            "post_id": tweet_id,
                            "media_type": "video",
                        })
            if not items:
                emit({"event": "inspect_error", "message": "推文中没有找到可下载的媒体文件"})
                return
            _apply_cached_thumbnails(items)
            emit({
                "event": "inspect_complete",
                "album_name": info["screen_name"],
                "album_id": f"twitter_status_{info['status_id']}",
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Twitter 推文解析完成: %s (%d 个文件)", url, len(items))
            return

        # ---------- 用户主页：UserMedia 时间线翻页收集全部媒体 ----------
        screen_name = info["screen_name"]
        # 先取用户 ID
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("UserByScreenName"), "UserByScreenName",
            _TW_USER_FEATURES,
            {"screen_name": screen_name, "withSafetyModeUserFields": True},
            {"fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})},
        )
        user_result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
        user_id = user_result.get("rest_id") or ""
        legacy = user_result.get("legacy") or {}
        if not user_id:
            emit({"event": "inspect_error", "message": f"找不到用户 @{screen_name}"})
            return
        display_name = legacy.get("name") or screen_name

        identifier = f"twitter_{user_id}"
        # 命中缓存则直接返回
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or display_name,
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 Twitter 用户信息: %s (%d 个文件)", identifier, len(items))
            return

        all_items: list[dict] = []
        cursor = ""
        seen_media: set[str] = set()
        seen_cursors: set[str] = set()
        # 增量更新截断日期：上次已下载到的最新发帖日期。
        # 时间线从新到旧翻页，翻到早于截断日期即可停止（只拉取更新的内容，
        # 大博主不用每次都把整个时间线翻到底）。
        cutoff = ((_load_download_state().get(identifier) or {}).get("latest_post")) or ""
        if cutoff:
            logging.info("Twitter 增量解析: @%s 截断日期 %s（只拉取更新的内容）", screen_name, cutoff)
        while True:
            variables = {
                "userId": user_id, "count": 20,
                "includePromotedContent": False,
                "withClientEventToken": False, "withBirdwatchNotes": False,
                "withVoice": True, "withV2Timeline": True,
            }
            if cursor:
                variables["cursor"] = cursor
            data = await asyncio.to_thread(
                _twitter_api_get,
                _twitter_qid("UserMedia"), "UserMedia",
                _TW_MEDIA_FEATURES, variables,
            )
            instructions = _tw_user_instructions(data)
            posts = _twitter_extract_posts(instructions)
            new_count = 0
            oldest_date = ""
            for post in posts:
                mapped = _twitter_map_tweet(post)
                for it in mapped:
                    if it["media_url"] not in seen_media:
                        seen_media.add(it["media_url"])
                        all_items.append(it)
                        new_count += 1
                        pd = it.get("post_date") or ""
                        if pd and (not oldest_date or pd < oldest_date):
                            oldest_date = pd
            # 提取底部游标
            next_cursor = ""
            for inst in instructions:
                if inst.get("type") != "TimelineAddEntries":
                    continue
                for entry in inst.get("entries") or []:
                    c = entry.get("content") or {}
                    if c.get("cursorType") == "Bottom" and c.get("value"):
                        next_cursor = c["value"]
            # 翻页终止：无游标 / 游标循环 / 无新内容 / 已翻到截断日期之前
            reached_cutoff = bool(cutoff and oldest_date and oldest_date <= cutoff)
            if reached_cutoff:
                logging.info("Twitter 时间线已翻到截断日期(%s)，停止翻页", cutoff)
            if not next_cursor or next_cursor in seen_cursors or new_count == 0 or reached_cutoff:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            emit({
                "event": "inspect_progress",
                "current": len(all_items),
                "total": len(all_items) + 20,
                "filename": all_items[-1]["filename"] if all_items else "",
            })

        if not all_items:
            emit({"event": "inspect_error", "message": "没有找到任何媒体（用户可能没有图片/视频）"})
            return

        _apply_cached_thumbnails(all_items)
        _mark_items_new(identifier, all_items)
        _save_album_cache(identifier, {
            "album_name": display_name,
            "album_id": identifier,
            "is_album": True,
            "items": all_items,
        })
        emit({
            "event": "inspect_complete",
            "album_name": display_name,
            "album_id": identifier,
            "is_album": True,
            "items": all_items,
        })
        asyncio.create_task(_cache_thumbnails(all_items))
        logging.info("Twitter 用户解析完成: @%s, 共 %d 个文件", screen_name, len(all_items))

    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("Twitter 解析过程出错")


async def _twitter_feed_resolve_user(screen_name: str, user_id: str) -> tuple[str, str, str, dict]:
    """解析博主身份：缺 user_id 时经 UserByScreenName 换取，并带出个人资料。

    返回 (user_id, screen_name, display_name, profile)；解析失败抛
    ValueError（message 可直接给前端）。
    profile 仅在走了 UserByScreenName 时非空：
      {media_count, statuses_count, followers_count, friends_count}。
    """
    screen_name = (screen_name or "").strip().lstrip("@")
    display_name = screen_name
    profile: dict = {}
    if not user_id:
        if not screen_name:
            raise ValueError("缺少博主信息")
        # user_id 缺失时用 UserByScreenName 换取
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("UserByScreenName"), "UserByScreenName",
            _TW_USER_FEATURES,
            {"screen_name": screen_name, "withSafetyModeUserFields": True},
            {"fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})},
        )
        user_result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
        user_id = user_result.get("rest_id") or ""
        legacy_u = user_result.get("legacy") or {}
        screen_name = legacy_u.get("screen_name") or screen_name
        display_name = legacy_u.get("name") or screen_name
        if not user_id:
            raise ValueError(f"找不到用户 @{screen_name}")
        profile = {
            "media_count": legacy_u.get("media_count"),
            "statuses_count": legacy_u.get("statuses_count"),
            "followers_count": legacy_u.get("followers_count"),
            "friends_count": legacy_u.get("friends_count"),
        }
    return user_id, screen_name, display_name, profile


async def _twitter_user_feed_page(user_id: str, screen_name: str,
                                  cursor: str = "") -> tuple[list[dict], str]:
    """拉取 UserMedia 时间线一页并映射为推文卡片（共用内部函数）。

    返回 (cards, next_cursor)；cards 按发布时间倒序，页内按首图 URL 去重，
    卡片自带 media_items（与文件列表同构的下载条目）。
    twitter_user_feed（单页/加载全部）与 twitter_export_html 共用。
    """
    variables = {
        "userId": user_id, "count": 20,
        "includePromotedContent": False,
        "withClientEventToken": False, "withBirdwatchNotes": False,
        "withVoice": True, "withV2Timeline": True,
    }
    if cursor:
        variables["cursor"] = cursor
    data = await asyncio.to_thread(
        _twitter_api_get,
        _twitter_qid("UserMedia"), "UserMedia",
        _TW_MEDIA_FEATURES, variables,
    )
    instructions = _tw_user_instructions(data)
    posts = _twitter_extract_posts(instructions)

    cards: list[dict] = []
    seen_urls: set[str] = set()
    for post in posts:
        legacy = post.get("legacy") or {}
        if legacy.get("retweeted_status_result"):
            continue  # 跳过转推
        media_items = _twitter_map_tweet(post)
        if not media_items:
            continue
        key = media_items[0].get("media_url") or ""
        if key in seen_urls:
            continue  # 跨页/线程重复推文去重
        seen_urls.add(key)
        created_at = legacy.get("created_at") or ""
        post_date = ""
        if created_at:
            try:
                post_date = datetime.strptime(
                    created_at, "%a %b %d %H:%M:%S %z %Y",
                ).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
        tweet_id = post.get("rest_id") or legacy.get("id_str") or ""
        full_text = (legacy.get("full_text") or "").strip()
        cards.append({
            "tweet_id": tweet_id,
            "item_page": media_items[0].get("item_page") or "",
            "text": full_text[:200],
            "post_date": post_date,
            "created_ts": _tw_created_ts(created_at),
            "media": [
                {
                    "media_url": it.get("media_url") or "",
                    "thumbnail": it.get("thumbnail") or "",
                    "type": it.get("media_type") or "photo",
                    "index": idx,
                }
                for idx, it in enumerate(media_items, start=1)
            ],
            # 与文件列表同构的下载条目（含 filename/site/media_url 等）
            "media_items": media_items,
            "user": {"user_id": user_id, "screen_name": screen_name},
        })
    cards.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
    # 提取底部游标（翻页用）
    next_cursor = ""
    for inst in instructions:
        if inst.get("type") != "TimelineAddEntries":
            continue
        for entry in inst.get("entries") or []:
            c = entry.get("content") or {}
            if c.get("cursorType") == "Bottom" and c.get("value"):
                next_cursor = c["value"]
    return cards, next_cursor


async def twitter_user_feed(screen_name: str = "", user_id: str = "",
                            cursor: str = "", load_all: bool = False) -> None:
    """博主内容流：拉取指定博主 UserMedia 时间线（20 条/页带媒体推文）。

    点开博主后前端自动调用，在用户详情页下方直接展示推文卡片
    （缩略图 + 内容），支持 cursor 翻页；卡片自带 media_items（与文件列表
    同构的下载条目），前端可一键批量下载当前已加载的全部媒体。

    load_all=True 为「加载全部」模式：循环翻页（上限 100 页）合并去重后
    一次性回传全部卡片（append=False、has_more=False，带 total_pages/loaded
    计数），期间每页发 twitter_user_feed_progress 进度。首次调用还随包带
    profile（media_count/statuses_count/followers_count/friends_count）。
    """
    emit({"event": "twitter_user_feed_loading", "loading": True})
    try:
        user_id, screen_name, _display_name, profile = await _twitter_feed_resolve_user(
            screen_name, user_id)

        if load_all:
            # 加载全部：翻页合并（tweet_id 去重），上限 100 页防死循环
            all_cards: list[dict] = []
            seen_ids: set[str] = set()
            seen_cursors: set[str] = set()
            cur = ""
            total_pages = 0
            while total_pages < 100:
                cards, next_cursor = await _twitter_user_feed_page(user_id, screen_name, cur)
                total_pages += 1
                for c in cards:
                    tid = c.get("tweet_id") or ""
                    if tid and tid in seen_ids:
                        continue
                    if tid:
                        seen_ids.add(tid)
                    all_cards.append(c)
                emit({
                    "event": "twitter_user_feed_progress",
                    "loaded": len(all_cards),
                    "total_media": sum(len(c.get("media") or []) for c in all_cards),
                })
                if not next_cursor or next_cursor in seen_cursors or not cards:
                    break
                seen_cursors.add(next_cursor)
                cur = next_cursor
            all_cards.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
            if all_cards:
                all_media = [m for c in all_cards for m in c["media"]]
                _apply_cached_thumbnails(all_media)
                asyncio.create_task(_cache_thumbnails(all_media))
            payload = {
                "event": "twitter_user_feed", "items": all_cards,
                "user_id": user_id, "screen_name": screen_name,
                "cursor": "", "has_more": False, "append": False,
                "total_pages": total_pages, "loaded": len(all_cards),
            }
            if profile:
                payload["profile"] = profile
            emit(payload)
            return

        # 常规单页模式（首包带 profile，翻页包不带）
        cards, next_cursor = await _twitter_user_feed_page(user_id, screen_name, cursor)
        if cards:
            all_media = [m for c in cards for m in c["media"]]
            _apply_cached_thumbnails(all_media)
            asyncio.create_task(_cache_thumbnails(all_media))
        payload = {
            "event": "twitter_user_feed", "items": cards,
            "user_id": user_id, "screen_name": screen_name,
            "cursor": next_cursor, "has_more": bool(next_cursor),
            "append": bool(cursor),
        }
        if profile and not cursor:
            payload["profile"] = profile
        emit(payload)
    except PermissionError as exc:
        emit({"event": "twitter_user_feed", "items": [], "error": str(exc)})
    except Exception as exc:
        logging.exception("博主内容流获取失败")
        emit({"event": "twitter_user_feed", "items": [],
              "error": f"获取博主内容失败: {exc}（请检查登录状态与代理）"})
    finally:
        emit({"event": "twitter_user_feed_loading", "loading": False})


# ---- X 博主媒体「全部更新保存」为本地 HTML 相册（增量） ----

_TW_EXPORT_HTML_NAME = "时间线.html"


def _twitter_download_roots() -> list[Path]:
    """候选下载根目录（务实实现，按优先级）。

    与 build_album_directory/create_download_directory 的规则对齐：
      - settings.json 的 custom_path（下载默认落在 custom/Downloads；
        勾选「不建 Downloads 子文件夹」时直接落在 custom）
      - 默认根 Path("Downloads")（后端工作目录相对路径，同 download_manager）
    """
    roots: list[Path] = []
    custom = ""
    try:
        with Path("settings.json").open("r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                custom = (data.get("custom_path") or "").strip()
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    if custom:
        base = Path(custom)
        roots.append(base / "Downloads")
        roots.append(base)
    roots.append(Path("Downloads"))
    uniq: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            uniq.append(root)
    return uniq


def _twitter_export_album_dirs(screen_name: str, display_name: str) -> list[Path]:
    """列出博主下载目录候选（各候选根 × 展示名/handle，含同名前缀变体）。

    相册目录由下载时的 album_name（博主昵称 display_name）决定，落到
    sanitize_directory_name 之后的名字；再 glob 前缀变体兜底
    （如 date_stamp 会在名字后拼 _YYYYMMDD）。
    """
    names: list[str] = []
    for raw in (display_name, screen_name):
        safe = sanitize_directory_name((raw or "").strip())
        if safe and safe not in names:
            names.append(safe)
    dirs: list[Path] = []
    seen: set[str] = set()

    def _push(p: Path) -> None:
        key = str(p)
        if key not in seen:
            seen.add(key)
            dirs.append(p)

    for root in _twitter_download_roots():
        for name in names:
            _push(root / name)
            try:
                for p in sorted(root.glob(f"{name}*")):
                    if p.is_dir():
                        _push(p)
            except (OSError, ValueError):
                continue
    return dirs


def _twitter_export_build_index(album_dirs: list[Path]) -> dict[str, str]:
    """把候选博主目录内全部已落盘文件按文件名建索引（文件名→绝对路径）。"""
    index: dict[str, str] = {}
    for d in album_dirs:
        if not d.is_dir():
            continue
        try:
            for p in d.rglob("*"):
                if p.is_file():
                    index.setdefault(p.name, str(p))
        except OSError:
            continue
    return index


def _twitter_export_media_src(item: dict, file_index: dict[str, str],
                              html_dir: Path) -> tuple[str, bool]:
    """解析一个媒体条目在 HTML 里的 src：本地命中用相对路径，否则远程 URL。

    返回 (src, is_local)。相对路径做 URL 编码（文件名可含空格/中文）。
    """
    filename = (item.get("filename") or "").strip()
    if filename:
        found = file_index.get(filename)
        if found:
            try:
                rel = Path(os.path.relpath(found, str(html_dir))).as_posix()
            except (OSError, ValueError):
                rel = Path(found).name
            return urllib.parse.quote(rel), True
    return item.get("media_url") or item.get("thumbnail") or "", False


def _twitter_export_read_meta_ids(html_path: Path) -> list[str]:
    """读取已有 HTML 相册末尾 tw-export-meta 里的 tweet_ids（增量合并用）。"""
    try:
        text = html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    m = re.search(
        r'<script type="application/json" id="tw-export-meta">(.*?)</script>',
        text, re.S,
    )
    if not m:
        return []
    try:
        data = json.loads(html_unescape(m.group(1)))
        ids = data.get("tweet_ids") or []
        return [str(i) for i in ids if str(i).strip()]
    except (json.JSONDecodeError, ValueError):
        return []


def _twitter_export_card_html(card: dict, display_name: str, screen_name: str,
                              file_index: dict[str, str], html_dir: Path) -> str:
    """渲染单条推文卡片（昵称/@handle、时间、正文、媒体原位排布）。"""
    tweet_id = card.get("tweet_id") or ""
    post_date = card.get("post_date") or ""
    item_page = card.get("item_page") or ""
    who = f"{html_escape(display_name)} (@{html_escape(screen_name)})" if screen_name \
        else html_escape(display_name)
    head = f'<div class="who">{who}</div>'
    sub = f"tweet_id: {html_escape(tweet_id)}"
    if post_date:
        sub += f" · 发布于 {html_escape(post_date)}"
    link_open, link_close = "", ""
    if item_page:
        link_open = f'<a class="link" href="{html_escape(item_page, quote=True)}" target="_blank" rel="noreferrer">'
        link_close = "</a>"
    media_html: list[str] = []
    for it in card.get("media_items") or []:
        src, _local = _twitter_export_media_src(it, file_index, html_dir)
        if not src:
            continue
        esc_src = html_escape(src, quote=True)
        thumb = (it.get("thumbnail") or "").strip()
        poster = (f' poster="{html_escape(thumb, quote=True)}"' if thumb else "")
        if (it.get("media_type") or "photo") == "video":
            media_html.append(
                f'<video controls preload="metadata" src="{esc_src}"{poster}></video>')
        else:
            media_html.append(f'<img loading="lazy" src="{esc_src}" alt="">')
    text = html_escape(card.get("text") or "")
    return (
        f'<article class="card">{link_open}{head}{link_close}'
        f'<div class="sub">{html_escape(sub)}</div>'
        f'<div class="text">{text}</div>'
        f'<div class="media">{"".join(media_html)}</div>'
        f"</article>"
    )


def _twitter_export_render(cards: list[dict], screen_name: str, display_name: str,
                           html_dir: Path, file_index: dict[str, str],
                           old_ids: list[str]) -> str:
    """渲染暗色自包含 HTML 相册全文（含末尾 tw-export-meta 增量数据块）。"""
    cards_html = "".join(
        _twitter_export_card_html(c, display_name, screen_name, file_index, html_dir)
        for c in cards
    )
    # 增量 meta：本次拉到的推文 + 旧 meta 的推文（并集，去重保序）
    merged_ids = [c.get("tweet_id") or "" for c in cards]
    merged_ids += [i for i in old_ids if i not in set(merged_ids)]
    merged_ids = [i for i in merged_ids if i]
    meta_json = json.dumps(
        {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tweet_ids": merged_ids,
        },
        ensure_ascii=False,
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_escape(display_name or screen_name)} · 时间线</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #0d1117; color: #e6edf3;
         font: 15px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }}
  header {{ position: sticky; top: 0; z-index: 2; background: #161b22ee;
            border-bottom: 1px solid #30363d; padding: 14px 20px; }}
  header h1 {{ margin: 0; font-size: 18px; }}
  header p {{ margin: 2px 0 0; color: #8b949e; font-size: 12px; }}
  main {{ max-width: 640px; margin: 0 auto; padding: 16px 12px 60px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px;
           padding: 14px 16px; margin: 14px 0; }}
  .who {{ font-weight: 600; }}
  .who a {{ color: inherit; text-decoration: none; }}
  .sub {{ color: #8b949e; font-size: 12px; margin: 2px 0 6px; }}
  .text {{ white-space: pre-wrap; word-break: break-word; margin: 0 0 10px; }}
  .media {{ display: grid; gap: 8px; }}
  .media img, .media video {{ width: 100%; max-height: 560px; object-fit: contain;
           border-radius: 10px; background: #0d1117; border: 1px solid #21262d; }}
  a.link {{ color: #58a6ff; }}
</style>
</head>
<body>
<header>
  <h1>{html_escape(display_name or screen_name)} · 时间线</h1>
  <p>共 {len(cards)} 条推文 · 本地相册（媒体命中本机文件则离线可看，未命中走远程链接）</p>
</header>
<main>
{cards_html}
</main>
<script type="application/json" id="tw-export-meta">{meta_json}</script>
</body>
</html>
"""


async def twitter_export_html(screen_name: str = "", user_id: str = "") -> None:
    """博主媒体「全部更新保存」：全量拉取时间线生成本地 HTML 相册（增量）。

    流程：循环翻页拉全部（上限 100 页，每页发拉取进度）→ 在博主下载目录
    匹配已落盘媒体（命中用相对 HTML 的本地路径，未命中用远程 media_url）
    → 在博主目录生成/增量重写 时间线.html（暗色自包含页面，旧 meta 的
    tweet_ids 与本次并集合并）。完成后发 twitter_export_done。
    """
    try:
        user_id, screen_name, display_name, _profile = await _twitter_feed_resolve_user(
            screen_name, user_id)

        # ---- 全量拉取（tweet_id 去重，上限 100 页防死循环） ----
        all_cards: list[dict] = []
        seen_ids: set[str] = set()
        seen_cursors: set[str] = set()
        cur = ""
        pages = 0
        while pages < 100:
            cards, next_cursor = await _twitter_user_feed_page(user_id, screen_name, cur)
            pages += 1
            for c in cards:
                tid = c.get("tweet_id") or ""
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                all_cards.append(c)
            emit({"event": "twitter_export_progress",
                  "done": len(all_cards), "phase": "拉取"})
            if not next_cursor or next_cursor in seen_cursors or not cards:
                break
            seen_cursors.add(next_cursor)
            cur = next_cursor
        all_cards.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)

        # ---- 定位博主下载目录：优先已存在的候选，拿不到就建默认目录 ----
        album_dirs = _twitter_export_album_dirs(screen_name, display_name)
        target_dir = next((d for d in album_dirs if d.is_dir()), None)
        existing_html = ""
        if target_dir:
            probe = target_dir / _TW_EXPORT_HTML_NAME
            if probe.exists():
                existing_html = str(probe)
        if target_dir is None:
            fallback_name = sanitize_directory_name(
                screen_name or display_name or f"user_{user_id}") or user_id
            target_dir = _twitter_download_roots()[0] / fallback_name
            target_dir.mkdir(parents=True, exist_ok=True)
        old_ids = _twitter_export_read_meta_ids(Path(existing_html)) if existing_html else []

        # ---- 已落盘媒体索引 + 生成 HTML ----
        index_dirs = list(album_dirs)
        if target_dir not in index_dirs:
            index_dirs.append(target_dir)
        file_index = _twitter_export_build_index(index_dirs)
        emit({"event": "twitter_export_progress",
              "phase": "生成HTML", "done": len(all_cards)})
        html_text = _twitter_export_render(
            all_cards, screen_name, display_name, target_dir, file_index, old_ids)
        out_path = target_dir / _TW_EXPORT_HTML_NAME
        out_path.write_text(html_text, encoding="utf-8")
        old_set = set(old_ids)
        new_count = sum(
            1 for c in all_cards
            if (c.get("tweet_id") or "") and c["tweet_id"] not in old_set
        )
        emit({
            "event": "twitter_export_done", "ok": True,
            "path": str(out_path.resolve()),
            "total": len(all_cards), "new": new_count,
        })
    except Exception as exc:
        logging.exception("Twitter HTML 相册导出失败")
        emit({"event": "twitter_export_done", "ok": False, "error": str(exc)})


def _twitter_subfolder(item: dict, options: dict) -> str:
    """Twitter 专属子文件夹规则（父文件夹为博主名，由相册目录承担）。

    目录结构：博主名/图片 或 博主名/视频（按媒体类型两级，避免嵌套过多）。
    自定义模板 twitter_folder_template 非空时优先（兼容旧设置值）。
    """
    template = (options.get("twitter_folder_template") or "").strip()
    if template:
        return _render_folder_template(
            template,
            item.get("post_date") or "",
            (item.get("post_title") or "").strip(),
            item.get("post_id") or "",
        )
    # twitter_subfolder: media（默认，图片/视频分类）| none（不分类，直接放博主名下）
    mode = options.get("twitter_subfolder", "media")
    if mode == "none":
        return ""
    # media_type 缺失时按扩展名兜底（升级前持久化的旧任务条目无此字段，
    # 此前会全部落入「图片」分支，表现为视频混进图片文件夹）
    ext = Path(item.get("filename") or "").suffix.lower()
    if item.get("media_type") == "video" or ext in (".mp4", ".webm", ".mov", ".m4v"):
        return "视频"
    return "图片"


# ---- X 站 MD5 查重（同一媒体在多条推文重复出现时只保留最早发布的一份） ----
# 会话缓存按博主目录（album_path）隔离；线程锁保护（concurrent_files 并发下载）。
_twitter_md5_sessions: dict[str, dict] = {}
_twitter_md5_lock = threading.Lock()


def _twitter_name_post_date(name: str) -> str:
    """从文件名前缀解析发布日期（X 命名规则 YYYY-MM-DD_标题_序号.ext）。"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_", name)
    return m.group(1) if m else ""


def _twitter_md5_file(path: str, sess: dict) -> str:
    """计算文件 MD5（按路径缓存，避免同一候选重复哈希）。"""
    cached = sess["md5"].get(path)
    if cached is not None:
        return cached
    digest = ""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
    except OSError:
        return ""
    sess["md5"][path] = digest
    return digest


def _twitter_md5_dedup(album_path: str, final_path: str, md5_hex: str,
                       item: dict) -> dict:
    """对刚下载完成的 X 媒体做 MD5 查重（在同博主目录范围内）。

    返回 {"action": "skip"|"replace"|"new", "dup_path", "dup_date"}：
      - replace：当前条目发布更早 → 删除目录里较晚发布的同内容副本，保留当前
      - skip：目录里已有更早（或同级）发布的同内容副本 → 删除当前文件
      - new：无重复，登记后放行
    发布日期优先取条目 post_date，其次解析既有文件名前缀；无日期的既有副本
    只在当前条目有日期时才被替换（避免无日期之间互相顶替）。
    """
    with _twitter_md5_lock:
        sess = _twitter_md5_sessions.get(album_path)
        if sess is None:
            sess = {"sizes": {}, "indexed": False, "added": {}, "md5": {}}
            _twitter_md5_sessions[album_path] = sess
        # 首次查重时扫描博主目录一次，建立「大小→路径」候选索引（存量文件也参与查重；
        # 内容不同大小必不同，MD5 只需对大小完全一致的候选计算）
        if not sess["indexed"]:
            sess["indexed"] = True
            try:
                for p in Path(album_path).rglob("*"):
                    try:
                        if p.is_file() and not p.name.endswith(".part"):
                            sess["sizes"].setdefault(p.stat().st_size, []).append(str(p))
                    except OSError:
                        continue
            except OSError:
                pass
        fp = Path(final_path)
        try:
            fsize = fp.stat().st_size
        except OSError:
            return {"action": "new", "dup_path": "", "dup_date": ""}
        cur_date = (item.get("post_date") or ""
                    or _twitter_name_post_date(fp.name))
        candidates = [p for p in sess["sizes"].get(fsize, []) if p != str(fp)]
        candidates += [p for p in sess["added"] if p != str(fp)]
        for cand in candidates:
            if not Path(cand).exists():
                continue
            if _twitter_md5_file(cand, sess) != md5_hex:
                continue
            cand_date = ((sess["added"].get(cand) or {}).get("post_date")
                         or _twitter_name_post_date(Path(cand).name))
            if cur_date and (not cand_date or cur_date < cand_date):
                # 当前条目发布更早：删除既有较晚副本，保留当前
                try:
                    Path(cand).unlink(missing_ok=True)
                except OSError:
                    pass
                sess["added"].pop(cand, None)
                sess["added"][str(fp)] = {"post_date": cur_date}
                return {"action": "replace", "dup_path": cand, "dup_date": cand_date}
            # 既有副本更早或同级：删除当前，保留既有
            try:
                fp.unlink(missing_ok=True)
            except OSError:
                pass
            return {"action": "skip", "dup_path": cand, "dup_date": cand_date}
        sess["added"][str(fp)] = {"post_date": cur_date}
        sess["sizes"].setdefault(fsize, []).append(str(fp))
        return {"action": "new", "dup_path": "", "dup_date": ""}
