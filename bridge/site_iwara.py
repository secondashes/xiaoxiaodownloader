# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Iwara + 增量下载状态。

由 gui_bridge.py 按物理顺序拆出（原行区间 5674-6833），
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
# Iwara 站点支持 (iwara.tv，MMD 视频站)
# ============================
# - API v2: https://api.iwara.tv/（JSON）
# - 登录: POST /user/login {email, password} → Bearer token（约3周有效）
#   媒体 token: POST /user/token（Bearer 用户 token）→ accessToken（约1小时，解析视频源需要）
# - 视频: GET /video/{id} → fileUrl → 带 X-Version 头请求 fileUrl 得画质列表
#   X-Version = sha1("{路径末段}_{expires参数}_{盐}")
#   画质优先级 Source(最高) > 540 > 360，默认下载最高画质
# - 搜索: GET /videos?query=关键词&sort=date&page={n}&limit=32
# - 用户: GET /profile/{username} → user.id → GET /videos?user={id}&sort=date&page={n}
# - 缩略图: https://files.iwara.tv/image/thumbnail/{file.id}/thumbnail-00.jpg
# - 视频直链带 expires 签名会过期：下载时必须重新解析
# - 可选代理（默认直连，国内不稳时可配置）

IWARA_API = "https://api.iwara.tv"
IWARA_SITE_FILE = "cache/iwara_site.json"
IWARA_SALT = "mSvL05GfEmeEmsEYfGCnVpEjYgTJraJN"
IWARA_QUALITY_PREF = {"source": 0, "540": 1, "360": 2, "preview": 3}
# IW站 / AI站（www.iwara.ai = 同一 API + X-Site 请求头区分内容）
IWARA_SITES = {"iwara": "www.iwara.tv", "ai": "www.iwara.ai"}

_iwara_proxy = ""  # 形如 http://127.0.0.1:10809，空 = 直连

_iwara_session = requests.Session()
_iwara_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.iwara.tv",
    "Referer": "https://www.iwara.tv/",
})


def iwara_set_proxy(proxy: str) -> None:
    """设置 Iwara 代理（空 = 直连）。"""
    global _iwara_proxy
    _iwara_proxy = (proxy or "").strip()
    if _iwara_proxy and not _iwara_proxy.startswith(("http://", "https://", "socks5://")):
        _iwara_proxy = "http://" + _iwara_proxy
    proxies = {"http": _iwara_proxy, "https": _iwara_proxy} if _iwara_proxy else None
    _iwara_session.proxies = proxies or {}
    emit({"event": "iwara_proxy_set", "proxy": _iwara_proxy})


def iwara_current_site() -> str:
    """读取当前 Iwara 站点（iwara | ai）。"""
    try:
        data = json.loads(Path(IWARA_SITE_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("site") in IWARA_SITES:
            return data["site"]
    except (OSError, json.JSONDecodeError):
        pass
    return "iwara"


def iwara_set_site(site: str) -> None:
    """切换 IW站 / AI站（同一 API，通过 X-Site 请求头区分内容；登录信息共用）。"""
    site = "ai" if str(site) == "ai" else "iwara"
    _iwara_session.headers["X-Site"] = IWARA_SITES[site]
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(IWARA_SITE_FILE).write_text(
            json.dumps({"site": site}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    emit({"event": "iwara_site_changed", "site": site,
          "message": "已切换到 AI 站 (iwara.ai)" if site == "ai" else "已切换到 IW 站 (iwara.tv)"})


# 启动时按持久化的站点初始化请求头
_iwara_session.headers["X-Site"] = IWARA_SITES[iwara_current_site()]


def _iwara_load_token() -> dict:
    """读取已保存的 Iwara 登录信息（加密账号存储，长期保持登录状态）。"""
    return _secure_store_read_cred("iwara")


def _iwara_save_token(data: dict) -> None:
    """保存 Iwara 登录信息（加密存储：user_token 长期有效 + media_token 短期）。"""
    _secure_store_write_cred("iwara", dict(data))


def _iwara_jwt_exp(token: str) -> float:
    """解析 JWT 的 exp 过期时间（解析失败返回 0）。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(__import__("base64").urlsafe_b64decode(payload)).get("exp") or 0)
    except Exception:
        return 0.0


def _iwara_media_token(force: bool = False) -> str:
    """获取媒体 token（约1小时有效，解析视频源列表必需；自动刷新）。"""
    data = _iwara_load_token()
    media = data.get("media_token") or ""
    exp = _iwara_jwt_exp(media)
    if media and not force and exp > time.time() + 120:
        return media
    user_token = data.get("user_token") or ""
    if not user_token:
        return ""
    resp = _iwara_session.post(
        f"{IWARA_API}/user/token", timeout=20,
        headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    media = resp.json().get("accessToken") or ""
    if media:
        data["media_token"] = media
        _iwara_save_token(data)
    return media


def _iwara_auth_headers() -> dict:
    """带媒体 token 的请求头（未登录返回空 dict，公开内容可直接访问）。"""
    try:
        token = _iwara_media_token()
    except Exception:
        token = ""
    return {"Authorization": f"Bearer {token}"} if token else {}


def _iwara_auto_relogin() -> str:
    """用已保存的邮箱密码自动重新登录（token 过期时续期）。成功返回新 token。

    密码与 token 一起加密保存在本地（theme_cache.dat），长期有效；
    token 过期后无需用户重新输入密码。
    """
    data = _iwara_load_token()
    email = data.get("email") or ""
    password = data.get("password") or ""
    if not email or not password:
        return ""
    try:
        resp = _iwara_session.post(
            f"{IWARA_API}/user/login", timeout=20,
            json={"email": email, "password": password},
        )
        payload = resp.json() if resp.content else {}
        token = payload.get("token") or ""
        if token:
            data["user_token"] = token
            data.pop("media_token", None)  # 旧媒体 token 一并失效
            _iwara_save_token(data)
            logging.info("Iwara token 已自动续期（保存的密码重新登录）")
            return token
    except requests.RequestException as exc:
        logging.warning("Iwara 自动续期失败: %s", exc)
    return ""


def _iwara_me_user(me) -> dict:
    """解析 GET /user 的响应（新版 API 返回 {"balance":.., "user":{...}}，旧版直接返回用户对象）。"""
    if not isinstance(me, dict):
        return {}
    if isinstance(me.get("user"), dict):
        return me["user"]
    return me


def iwara_login(email: str, password: str) -> None:
    """Iwara 登录（邮箱 + 密码 → Bearer token 长期保存；密码也加密保存用于自动续期）。"""
    try:
        resp = _iwara_session.post(
            f"{IWARA_API}/user/login", timeout=20,
            json={"email": email, "password": password},
        )
        data = resp.json() if resp.content else {}
        token = data.get("token") or ""
        if not token:
            msg = data.get("message") or "登录失败（账号或密码错误）"
            emit({"event": "iwara_login_result", "success": False, "message": msg})
            return
        # 密码一并加密保存：token 过期后自动用密码续期，长期免登录
        cred = {"user_token": token, "email": email, "password": password}
        # 立即取用户信息验证
        try:
            me = _iwara_me_user(_iwara_session.get(
                f"{IWARA_API}/user", timeout=20,
                headers={"Authorization": f"Bearer {token}"},
            ).json())
            cred.update({
                "user_id": me.get("id") or "",
                "name": me.get("name") or me.get("username") or "",
                "username": me.get("username") or "",
            })
        except Exception:
            pass
        _iwara_save_token(cred)
        _emit_login_info()
        emit({"event": "iwara_login_result", "success": True, "email": email,
              "username": _iwara_load_token().get("username") or email,
              "message": "Iwara 登录成功"})
    except requests.RequestException as exc:
        emit({"event": "iwara_login_result", "success": False,
              "message": f"连接失败: {exc}（国内建议在设置里配置 Iwara 代理）",
              "network_issue": True})


def iwara_logout() -> None:
    """退出 Iwara 登录（清除加密存储中的凭据）。"""
    _secure_store_clear_cred("iwara")
    _emit_login_info()
    emit({"event": "iwara_login_result", "success": False, "logout": True,
          "message": "已退出 Iwara 登录"})


def iwara_check_login(silent: bool = False) -> None:
    """检查 Iwara 登录状态（token 是否有效；过期时用保存的密码自动续期）。"""
    data = _iwara_load_token()
    token = data.get("user_token") or ""
    if not token:
        emit({"event": "iwara_login_result", "success": False, "silent": silent,
              "message": "未登录" if not silent else ""})
        return
    if _iwara_jwt_exp(token) and _iwara_jwt_exp(token) < time.time():
        # token 过期：优先用保存的密码自动续期（长期免登录）
        new_token = _iwara_auto_relogin()
        if new_token:
            data = _iwara_load_token()
            token = new_token
        else:
            emit({"event": "iwara_login_result", "success": False, "silent": silent,
                  "message": "登录已过期，且自动续期失败（未保存密码或密码已更改），请重新登录"})
            return
    try:
        me = _iwara_me_user(_iwara_session.get(
            f"{IWARA_API}/user", timeout=(8, 20),  # 连接超时 8s：直连不通时避免阻塞 20s
            headers={"Authorization": f"Bearer {token}"},
        ).json())
        if me.get("id"):
            data.update({"user_id": me.get("id") or "",
                         "name": me.get("name") or me.get("username") or "",
                         "username": me.get("username") or ""})
            _iwara_save_token(data)
            _emit_login_info()
            emit({"event": "iwara_login_result", "success": True, "silent": silent,
                  "username": me.get("username") or data.get("username") or "",
                  "message": "Iwara 登录有效"})
        else:
            # token 被服务器拒绝：先尝试密码自动续期再重试一次
            new_token = _iwara_auto_relogin()
            if new_token:
                iwara_check_login(silent=silent)
                return
            emit({"event": "iwara_login_result", "success": False, "silent": silent,
                  "message": "登录已失效，请重新登录"})
    except requests.RequestException as exc:
        # 连接异常 = 网络问题（token 未被服务器拒绝），前端保留登录显示，
        # 避免把国内直连超时误报成"登录失效"
        emit({"event": "iwara_login_result", "success": False, "silent": silent,
              "message": f"连接失败: {exc}（请检查网络或代理设置，国内建议配置 Iwara 代理）",
              "network_issue": True})


def is_iwara_url(url: str) -> bool:
    """判断是否为 Iwara 链接（视频页 / 用户主页 / 图片页，含 iwara.ai AI站）。"""
    return bool(re.search(r"iwara\.(tv|ai)/(video|profile|user|image)s?/[A-Za-z0-9_-]+", url, re.I))


def _iwara_api_get(path: str, params: dict | None = None) -> dict | list:
    """Iwara API GET（带登录态 + 节流；401 自动续期重试一次；跨站视频带 X-Site 重试一次）。"""
    _iwara_throttle()
    resp = _iwara_session.get(
        f"{IWARA_API}{path}", params=params, timeout=20,
        headers=_iwara_auth_headers(),
    )
    if resp.status_code == 401:
        # 登录失效：用保存的密码自动续期后重试一次
        if _iwara_auto_relogin():
            _iwara_throttle()
            resp = _iwara_session.get(
                f"{IWARA_API}{path}", params=params, timeout=20,
                headers=_iwara_auth_headers(),
            )
        if resp.status_code == 401:
            raise PermissionError("Iwara 登录已失效（自动续期失败），请在左侧重新登录")
    resp.raise_for_status()
    data = resp.json() if resp.content else {}
    # 2026-09 实测：Iwara 拆分多站点后（如 iwara_ai），旧 ID 跨站查询返回
    # {"message": "errors.differentSite", "siteId": "<归属站>"} 且无正文 ——
    # 按响应给的 siteId 带 X-Site 头重试一次即可取回（oreno3d/erommdtube 转链视频全靠此）
    if isinstance(data, dict) and data.get("message") == "errors.differentSite" and data.get("siteId"):
        headers = dict(_iwara_auth_headers())
        headers["X-Site"] = str(data["siteId"])
        _iwara_throttle()
        resp = _iwara_session.get(
            f"{IWARA_API}{path}", params=params, timeout=20, headers=headers,
        )
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
    return data


_iwara_lock = threading.Lock()


_iwara_throttle = _make_throttle(0.5, lock=_iwara_lock)


def _iwara_avatar_url(u: dict) -> str:
    """API 用户对象 → 头像 URL（avatar.path + 去扩展名文件名；无头像返回空）。"""
    av = u.get("avatar") or {}
    if av.get("name"):
        stem = str(av["name"]).rsplit(".", 1)[0]
        return f"https://www.iwara.tv/image/avatar/{av.get('path')}/{stem}"
    return ""


def _iwara_map_user(u: dict) -> dict:
    """API 用户对象 → 前端用户卡片（关注列表/好友列表/作者信息通用）。"""
    avatar = _iwara_avatar_url(u)
    return {
        "user_id": u.get("id") or "",
        "name": u.get("name") or u.get("username") or "",
        "username": u.get("username") or "",
        "avatar": avatar,
        "thumbnail": avatar,  # 复用缩略图缓存（thumb://local/）
        "bio": "",  # 个人说明（profile 接口才有，列表加载后后台补齐）
        "following": bool(u.get("following")),
        "friend": bool(u.get("friend")),
        "premium": bool(u.get("premium")),
    }


def _iwara_map_video(v: dict) -> dict:
    """API 视频对象 → 前端搜索结果卡片。"""
    user = v.get("user") or {}
    file = v.get("file") or {}
    thumb = ""
    if file.get("id"):
        thumb = f"https://files.iwara.tv/image/thumbnail/{file['id']}/thumbnail-00.jpg"
    author = _iwara_map_user(user)
    return {
        "album_name": v.get("title") or "未命名视频",
        "album_url": f"https://www.iwara.tv/video/{v.get('id')}",
        "thumbnail": thumb,
        "files": 1,
        "site": "iwara",
        "video_id": v.get("id") or "",
        "author": author["name"] or user.get("username") or "",
        "author_id": author["user_id"],
        "author_username": author["username"],
        "author_avatar": author["avatar"],
        "author_following": author["following"],
        "post_date": (v.get("createdAt") or "")[:10],
        "created_at": v.get("createdAt") or "",
        "views": v.get("numViews"),
        "likes": v.get("numLikes"),
        "num_comments": v.get("numComments"),
        "rating": v.get("rating") or "",
        "duration": file.get("duration"),
        "file_size": file.get("size"),
    }


def _iwara_my_user_id() -> str:
    """获取当前登录用户的 user_id（优先缓存，缺则调 /user 并缓存）。"""
    data = _iwara_load_token()
    uid = data.get("user_id") or ""
    if uid:
        return uid
    token = data.get("user_token") or ""
    if not token:
        return ""
    try:
        me = _iwara_me_user(_iwara_session.get(
            f"{IWARA_API}/user", timeout=(8, 20),  # 连接超时 8s：直连不通时避免阻塞 20s
            headers={"Authorization": f"Bearer {token}"},
        ).json())
        uid = me.get("id") or ""
        if uid:
            data.update({"user_id": uid, "name": me.get("name") or "",
                         "username": me.get("username") or ""})
            _iwara_save_token(data)
        return uid
    except requests.RequestException:
        return ""


def _iwara_map_comment(c: dict) -> dict:
    """评论对象 → 前端评论卡片。"""
    return {
        "id": c.get("id") or "",
        "body": c.get("body") or "",
        "num_replies": c.get("numReplies") or 0,
        "created_at": c.get("createdAt") or "",
        "user": _iwara_map_user(c.get("user") or {}),
    }


async def iwara_home(page: int = 1, mode: str = "") -> None:
    """Iwara 主页：最近更新的视频（进入站点时自动加载，与官网首页一致）。

    mode='subscribed'：我关注的更新（订阅流，只看已关注作者的最新投稿，需登录）。
    """
    emit({"event": "iwara_home_loading", "loading": True})
    try:
        if mode == "subscribed" and not _iwara_load_token().get("user_token"):
            emit({"event": "iwara_home", "items": [], "page": 1, "has_more": False,
                  "mode": mode, "error": "订阅更新需要登录：请在左侧登录 Iwara 账号"})
            return
        api_page = max(0, (page or 1) - 1)
        params = {"page": api_page, "limit": 32, "sort": "date", "rating": "all"}
        if mode == "subscribed":
            params["subscribed"] = "true"  # 只看已关注用户的视频（订阅流）
        data = await asyncio.to_thread(_iwara_api_get, "/videos", params)
        items = [_iwara_map_video(v) for v in (data.get("results") or [])]
        count = data.get("count") or 0
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "iwara_home", "items": items, "page": max(1, page),
              "has_more": (api_page + 1) * 32 < count, "total": count,
              "mode": mode, "site": iwara_current_site()})
        logging.info("Iwara 主页第 %d 页 (mode=%s): %d 个视频", page, mode or "home", len(items))
    except Exception as exc:
        emit({"event": "iwara_home", "items": [], "page": max(1, page), "has_more": False,
              "mode": mode, "error": f"获取主页内容失败: {exc}（请检查网络或代理设置）"})
        logging.exception("Iwara 主页获取失败")
    finally:
        emit({"event": "iwara_home_loading", "loading": False})


async def iwara_following_list(page: int = 1) -> None:
    """我的关注列表（登录后可用；点用户可查看内容 / 取消关注）。"""
    emit({"event": "iwara_follow_loading", "loading": True})
    data = _iwara_load_token()
    if not data.get("user_token"):
        emit({"event": "iwara_follow_list", "items": [], "page": 1, "has_more": False,
              "error": "未登录：请在左侧登录 Iwara 账号后查看关注列表"})
        emit({"event": "iwara_follow_loading", "loading": False})
        return
    try:
        uid = await asyncio.to_thread(_iwara_my_user_id)
        if not uid:
            emit({"event": "iwara_follow_list", "items": [], "page": 1, "has_more": False,
                  "error": "获取用户信息失败（登录可能已失效）"})
            return
        api_page = max(0, (page or 1) - 1)
        data = await asyncio.to_thread(
            _iwara_api_get, f"/user/{uid}/following",
            {"page": api_page, "limit": 50},
        )
        items = [_iwara_map_user(it.get("user") or {}) for it in (data.get("results") or [])]
        count = data.get("count") or 0
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "iwara_follow_list", "items": items, "page": max(1, page),
              "has_more": (api_page + 1) * 50 < count, "total": count,
              "site": iwara_current_site()})
        if items:
            asyncio.create_task(_iwara_fill_user_bios(items))  # 后台补齐个人说明
        logging.info("Iwara 关注列表第 %d 页: %d 人", page, len(items))
    except PermissionError as exc:
        emit({"event": "iwara_follow_list", "items": [], "page": max(1, page),
              "has_more": False, "error": str(exc), "site": iwara_current_site()})
    except Exception as exc:
        emit({"event": "iwara_follow_list", "items": [], "page": max(1, page),
              "has_more": False, "error": f"获取关注列表失败: {exc}", "site": iwara_current_site()})
        logging.exception("Iwara 关注列表获取失败")
    finally:
        emit({"event": "iwara_follow_loading", "loading": False})


async def iwara_friend_list(page: int = 1) -> None:
    """我的好友列表（登录后可用）。"""
    emit({"event": "iwara_friend_loading", "loading": True})
    data = _iwara_load_token()
    if not data.get("user_token"):
        emit({"event": "iwara_friend_list", "items": [], "page": 1, "has_more": False,
              "error": "未登录：请在左侧登录 Iwara 账号后查看好友列表"})
        emit({"event": "iwara_friend_loading", "loading": False})
        return
    try:
        uid = await asyncio.to_thread(_iwara_my_user_id)
        if not uid:
            emit({"event": "iwara_friend_list", "items": [], "page": 1, "has_more": False,
                  "error": "获取用户信息失败（登录可能已失效）"})
            return
        api_page = max(0, (page or 1) - 1)
        data = await asyncio.to_thread(
            _iwara_api_get, f"/user/{uid}/friends",
            {"page": api_page, "limit": 50},
        )
        items = [_iwara_map_user(it.get("user") or it.get("friend") or {}) for it in (data.get("results") or [])]
        count = data.get("count") or 0
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "iwara_friend_list", "items": items, "page": max(1, page),
              "has_more": (api_page + 1) * 50 < count, "total": count,
              "site": iwara_current_site()})
        if items:
            asyncio.create_task(_iwara_fill_user_bios(items))  # 后台补齐个人说明
        logging.info("Iwara 好友列表第 %d 页: %d 人", page, len(items))
    except PermissionError as exc:
        emit({"event": "iwara_friend_list", "items": [], "page": max(1, page),
              "has_more": False, "error": str(exc), "site": iwara_current_site()})
    except Exception as exc:
        emit({"event": "iwara_friend_list", "items": [], "page": max(1, page),
              "has_more": False, "error": f"获取好友列表失败: {exc}", "site": iwara_current_site()})
        logging.exception("Iwara 好友列表获取失败")
    finally:
        emit({"event": "iwara_friend_loading", "loading": False})


IWARA_PROFILE_FILE = "cache/iwara_profiles.json"
IWARA_PROFILE_TTL = 7 * 86400  # 个人说明缓存 7 天


def _iwara_load_profiles() -> dict:
    """读取用户个人说明缓存（{username: {"bio": str, "ts": float}}）。"""
    try:
        return json.loads(Path(IWARA_PROFILE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _iwara_cache_profile(username: str, bio: str) -> None:
    """写入单个用户的个人说明缓存。"""
    try:
        data = _iwara_load_profiles()
        data[username] = {"bio": bio, "ts": time.time()}
        Path(IWARA_PROFILE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(IWARA_PROFILE_FILE).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


async def _iwara_fill_user_bios(items: list[dict]) -> None:
    """后台逐个拉取用户 profile，补齐个人说明（body）与缺失头像，渐进推送给前端。

    profile 接口包含 body（个人说明）与完整 user 对象；关注/好友列表接口不含，
    因此列表先展示，个人说明按 0.5s 节流逐个补齐（带本地缓存，7 天内不重复拉）。
    """
    cache_data = _iwara_load_profiles()
    now = time.time()
    for u in items:
        username = (u.get("username") or "").strip()
        if not username:
            continue
        try:
            cached = cache_data.get(username) or {}
            if cached.get("ts", 0) + IWARA_PROFILE_TTL > now:
                bio = cached.get("bio") or ""
            else:
                profile = await asyncio.to_thread(
                    _iwara_api_get, f"/profile/{username}", None)
                bio = str(profile.get("body") or "").strip()
                _iwara_cache_profile(username, bio)
                cache_data[username] = {"bio": bio, "ts": time.time()}
                # 顺带补齐缺失头像（列表接口偶发不带 avatar 字段）
                if not u.get("avatar"):
                    fix = _iwara_avatar_url(profile.get("user") or {})
                    if fix:
                        u["avatar"] = fix
                        u["thumbnail"] = fix
            if bio and (u.get("bio") or "") != bio:
                u["bio"] = bio
                emit({"event": "iwara_user_profile", "username": username,
                      "name": u.get("name") or "", "bio": bio,
                      "avatar": u.get("avatar") or "",
                      "site": iwara_current_site()})
        except Exception as exc:
            logging.debug("Iwara 个人说明获取失败 @%s: %s", username, exc)


def iwara_follow(user_id: str, follow: bool = True) -> None:
    """关注 / 取消关注用户（POST/DELETE /user/{id}/followers）。"""
    data = _iwara_load_token()
    token = data.get("user_token") or ""
    if not token:
        emit({"event": "iwara_follow_result", "user_id": user_id, "success": False,
              "following": follow, "message": "未登录：请先登录 Iwara 账号"})
        return
    try:
        _iwara_throttle()
        method = "POST" if follow else "DELETE"
        resp = _iwara_session.request(
            method, f"{IWARA_API}/user/{user_id}/followers", timeout=20,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code in (200, 201, 204):
            emit({"event": "iwara_follow_result", "user_id": user_id, "success": True,
                  "following": follow,
                  "message": "已关注" if follow else "已取消关注"})
        else:
            msg = ""
            try:
                msg = resp.json().get("message") or ""
            except Exception:
                pass
            emit({"event": "iwara_follow_result", "user_id": user_id, "success": False,
                  "following": not follow,
                  "message": f"操作失败: {resp.status_code} {msg}".strip()})
    except requests.RequestException as exc:
        emit({"event": "iwara_follow_result", "user_id": user_id, "success": False,
              "following": not follow, "message": f"连接失败: {exc}"})


async def iwara_video_detail(video_id: str) -> None:
    """视频详情：完整信息（简介/tags/统计/作者关注状态）+ 首页评论。"""
    emit({"event": "iwara_detail_loading", "loading": True})
    try:
        v = await asyncio.to_thread(_iwara_api_get, f"/video/{video_id}")
        video = _iwara_map_video(v)
        # 可播放直链（fileUrl 签名解析最高画质；协议相对地址 //xxx 补 https:）
        play_url = ""
        try:
            fu = v.get("fileUrl") or ""
            if fu:
                play_url, _mime = await asyncio.to_thread(_iwara_resolve_best_url, fu)
                if play_url.startswith("//"):
                    play_url = "https:" + play_url
        except Exception:
            play_url = ""
        # tag 的 id 即标签名（如 musclegirl），可直接展示与搜索
        video.update({
            "body": v.get("body") or "",
            "tags": [{"id": t.get("id") or "", "name": t.get("id") or "",
                      "type": t.get("type") or "", "sensitive": bool(t.get("sensitive"))}
                     for t in (v.get("tags") or [])],
            "video_url": play_url,
        })
        # 首页评论（最新一页）
        comments = []
        try:
            cdata = await asyncio.to_thread(
                _iwara_api_get, f"/video/{video_id}/comments", {"limit": 20, "page": 0})
            comments = [_iwara_map_comment(c) for c in (cdata.get("results") or [])]
        except Exception:
            pass
        _apply_cached_thumbnails([video])
        _apply_cached_thumbnails([c["user"] for c in comments])
        asyncio.create_task(_cache_thumbnails([video] + [c["user"] for c in comments]))
        emit({"event": "iwara_video_detail", "video": video, "comments": comments,
              "comment_count": v.get("numComments") or 0, "site": iwara_current_site()})
        logging.info("Iwara 视频详情: %s", video_id)
    except PermissionError as exc:
        emit({"event": "iwara_video_detail", "video": None, "comments": [], "error": str(exc),
              "site": iwara_current_site()})
    except Exception as exc:
        emit({"event": "iwara_video_detail", "video": None, "comments": [],
              "error": f"获取视频详情失败: {exc}", "site": iwara_current_site()})
        logging.exception("Iwara 视频详情获取失败")
    finally:
        emit({"event": "iwara_detail_loading", "loading": False})


async def iwara_video_comments(video_id: str, page: int = 1) -> None:
    """视频评论翻页加载。"""
    try:
        api_page = max(0, (page or 1) - 1)
        data = await asyncio.to_thread(
            _iwara_api_get, f"/video/{video_id}/comments",
            {"limit": 20, "page": api_page},
        )
        comments = [_iwara_map_comment(c) for c in (data.get("results") or [])]
        count = data.get("count") or 0
        emit({"event": "iwara_comments", "video_id": video_id, "comments": comments,
              "page": max(1, page), "has_more": (api_page + 1) * 20 < count, "total": count})
    except Exception as exc:
        emit({"event": "iwara_comments", "video_id": video_id, "comments": [],
              "page": max(1, page), "has_more": False, "error": f"获取评论失败: {exc}"})


async def _iwara_collect_user_items(username: str) -> tuple[str, str, list[dict]]:
    """拉取指定用户的全部视频并构建下载条目（返回 作者名, user_id, items）。"""
    profile = await asyncio.to_thread(_iwara_api_get, f"/profile/{username}", None)
    user = profile.get("user") or {}
    user_id = user.get("id") or ""
    if not user_id:
        raise PermissionError(f"找不到 Iwara 用户 @{username}")
    album_name = user.get("name") or username
    video_ids: list[str] = []
    for p in range(20):
        data = await asyncio.to_thread(
            _iwara_api_get, "/videos",
            {"user": user_id, "page": p, "limit": 32, "sort": "date"},
        )
        page_videos = data.get("results") or []
        if not page_videos:
            break
        video_ids.extend(v.get("id") for v in page_videos if v.get("id"))
        if len(page_videos) < 32:
            break
    items = await _iwara_build_items(video_ids)
    return album_name, user_id, items


async def _iwara_build_items(video_ids: list) -> list[dict]:
    """按视频 ID 列表逐个取详情构建下载条目（与单视频解析一致的元数据）。"""
    items: list[dict] = []
    for vid in video_ids:
        try:
            data = await asyncio.to_thread(_iwara_api_get, f"/video/{vid}", None)
        except Exception as exc:
            logging.warning("Iwara 视频 %s 获取失败: %s", vid, exc)
            continue
        if data.get("message") or not data.get("fileUrl"):
            continue
        user = data.get("user") or {}
        file = data.get("file") or {}
        thumb = f"https://files.iwara.tv/image/thumbnail/{file['id']}/thumbnail-00.jpg" if file.get("id") else ""
        title = sanitize_directory_name((data.get("title") or f"iwara_{vid}").strip())
        items.append({
            "filename": f"{title}.mp4",
            "size": None,
            "item_page": f"https://www.iwara.tv/video/{vid}",
            "status": "ok",
            "thumbnail": thumb,
            "media_url": data.get("fileUrl"),
            "site": "iwara",
            "video_id": vid,
            "post_title": data.get("title") or title,
            "post_date": (data.get("createdAt") or "")[:10],
            "artist": user.get("name") or user.get("username") or "",
        })
    return items


async def iwara_batch_download(usernames: list, video_ids: list, options: dict) -> None:
    """批量解析下载：关注/好友列表勾选多个用户（或主页勾选多个视频），逐个解析并提交下载任务。

    - 用户：每个用户单独一个下载任务（目录 = 作者名/...，与其他站点逻辑一致）
    - 视频：所有勾选视频合并为一个任务
    """
    usernames = [str(u).strip().lstrip("@") for u in (usernames or []) if str(u).strip()]
    video_ids = [str(v).strip() for v in (video_ids or []) if str(v).strip()]
    total = len(usernames) + (1 if video_ids else 0)
    done = 0
    failed: list[str] = []

    def _progress(done_: int, msg: str) -> None:
        emit({"event": "iwara_batch_progress", "done": done_, "total": total, "message": msg})

    if not total:
        _progress(0, "请先勾选要下载的用户或视频")
        emit({"event": "iwara_batch_done", "done": 0, "total": 0, "failed": []})
        return

    try:
        for uname in usernames:
            _progress(done, f"正在解析 @{uname} 的全部视频...")
            try:
                album_name, user_id, items = await _iwara_collect_user_items(uname)
                if not items:
                    failed.append(f"@{uname}（无视频）")
                else:
                    task_id = download_manager.submit(
                        f"https://www.iwara.tv/profile/{uname}", items, options,
                        album_name, f"iwara_{user_id}",
                    )
                    download_manager.start(task_id)
                    logging.info("批量下载：@%s 已提交 %d 个视频", uname, len(items))
            except Exception as exc:
                failed.append(f"@{uname}（{exc}）")
                logging.exception("批量下载解析失败: %s", uname)
            done += 1
            _progress(done, f"@{uname} 完成（{done}/{total}）")

        if video_ids:
            _progress(done, f"正在解析勾选的 {len(video_ids)} 个视频...")
            try:
                items = await _iwara_build_items(video_ids)
                if not items:
                    failed.append("勾选的视频（全部解析失败）")
                else:
                    task_id = download_manager.submit(
                        "https://www.iwara.tv/", items, options, "Iwara 批量下载", "iwara_batch",
                    )
                    download_manager.start(task_id)
                    logging.info("批量下载：已提交 %d 个视频", len(items))
            except Exception as exc:
                failed.append(f"勾选的视频（{exc}）")
                logging.exception("批量下载视频解析失败")
            done += 1
            _progress(done, f"视频解析完成（{done}/{total}）")

        summary = f"批量下载已提交：{done}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "iwara_batch_done", "done": done, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "iwara_batch_done", "done": done, "total": total, "failed": failed,
              "message": f"批量下载中断: {exc}"})
        logging.exception("Iwara 批量下载出错")


async def iwara_search(query: str, page: int = 0) -> None:
    """Iwara 视频搜索（关键词 → 视频卡片；@用户名 → 该用户的视频列表）。

    关键词搜索走官方搜索端点 GET /search（/videos 的 query 参数会被服务端忽略，
    之前"搜索成功但结果不对"的根因）。
    注意：type 必须是复数 "videos"（Iwara 官网搜索页就是此参数），
    单数 "video" 或附加 sort/rating 参数会触发服务端 500。
    """
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    try:
        if query.startswith("@"):
            await iwara_user_videos(query.lstrip("@").strip(), page, emit_result=True)
            return
        emit({"event": "search_loading", "loading": True})
        page = max(1, page or 1)
        api_page = page - 1  # 前端页码从 1 开始，API 从 0 开始
        data = await asyncio.to_thread(
            _iwara_api_get, "/search",
            {"query": query, "type": "videos", "page": api_page, "limit": 32},
        )
        raw = data.get("results")
        if isinstance(raw, dict):
            raw = raw.get("video") or raw.get("videos") or []
        if not isinstance(raw, list):
            raw = []
        results = [_iwara_map_video(v) for v in raw]
        count = data.get("count")
        if not isinstance(count, int):
            count = len(results)
        emit({"event": "search_result", "query": query, "site": "iwara",
              "items": results, "page": page,
              "has_more": (page - 1) * 32 + len(results) < count, "total_results": count})
        if results:
            asyncio.create_task(_cache_thumbnails(results))
        logging.info("Iwara 搜索 '%s': %d 个结果", query, len(results))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"Iwara 搜索失败: {exc}（请检查网络或代理设置）"})
        logging.exception("Iwara 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


async def iwara_user_videos(username: str, page: int = 0, emit_result: bool = False) -> None:
    """获取指定用户上传的全部视频（分页）。"""
    try:
        if emit_result:
            emit({"event": "search_loading", "loading": True})
        profile = await asyncio.to_thread(_iwara_api_get, f"/profile/{username}", None)
        user = profile.get("user") or {}
        user_id = user.get("id") or ""
        if not user_id:
            emit({"event": "search_error", "message": f"找不到 Iwara 用户 @{username}"})
            return
        data = await asyncio.to_thread(
            _iwara_api_get, "/videos",
            {"user": user_id, "page": max(0, (page or 1) - 1), "limit": 32, "sort": "date"},
        )
        results = [_iwara_map_video(v) for v in (data.get("results") or [])]
        count = data.get("count") or len(results)
        if emit_result:
            emit({"event": "search_result", "query": f"@{username}", "site": "iwara",
                  "items": results, "page": max(1, page),
                  "has_more": max(0, (page or 1) - 1) + 1 < (count + 31) // 32, "total_results": count,
                  "label": f"@{username} 的视频（{user.get('name') or username}）"})
        else:
            emit({"event": "iwara_user_videos", "username": username,
                  "videos": results, "page": max(0, page),
                  "has_more": max(0, (page or 1) - 1) + 1 < (count + 31) // 32})
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"获取用户视频失败: {exc}"})
        logging.exception("Iwara 用户视频获取失败")
    finally:
        if emit_result:
            emit({"event": "search_loading", "loading": False})


def _iwara_x_version(file_url: str) -> str:
    """计算 fileUrl 的 X-Version 签名（sha1(路径末段_expires_盐)）。"""
    from urllib.parse import parse_qs
    up = urlparse(file_url)
    params = parse_qs(up.query)
    paths = up.path.rstrip("/").split("/")
    expires = (params.get("expires") or [""])[0]
    return hashlib.sha1("_".join((paths[-1], expires, IWARA_SALT)).encode()).hexdigest()


def _system_proxies() -> list[str]:
    """读取系统代理（Windows 注册表/IE 设置，与浏览器同源）。

    用户场景：浏览器走系统代理下载很快，但本程序直连媒体服务器（mikoto.iwara.tv 等）
    会超时。直连失败时自动用系统代理重试，行为对齐浏览器。
    """
    try:
        proxies = urllib.request.getproxies()
        out = []
        for scheme in ("https", "http"):
            url = (proxies.get(scheme) or "").strip()
            if url and url not in out:
                out.append(url)
        return out
    except Exception:
        return []


def _iwara_resolve_best_url(file_url: str) -> tuple[str, str]:
    """解析视频源列表，返回 (最高画质直链, MIME)。画质优先级 Source > 540 > 360。

    健壮性处理（实测踩坑）：
    - 带失效 Bearer token 时 filesq 可能返回 200 + 空体 → 去掉 auth 重试一次
    - 最高画质条目可能没有 src（转码中）→ 依画质优先级逐级回退
    - 直连超时 → 用系统代理（浏览器同源）重试
    """
    if not file_url:
        return "", ""
    headers = {"X-Version": _iwara_x_version(file_url)}
    auth = _iwara_auth_headers()
    if auth:
        headers.update(auth)

    files = None
    last_err: Exception | None = None
    attempts = [(dict(headers), None)]                      # 1. 原样（含 auth）
    attempts.append(({k: v for k, v in headers.items() if k != "Authorization"}, None))  # 2. 去 auth
    for proxy in _system_proxies():                          # 3+. 系统代理
        attempts.append((dict(headers), proxy))
        if len(attempts) >= 4:                               # 最多试 1 个系统代理，避免拖太久
            break

    for req_headers, proxy in attempts:
        try:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            resp = _iwara_session.get(file_url, timeout=20, headers=req_headers, proxies=proxies)
            resp.raise_for_status()
            data = resp.json() if resp.content else []
            if isinstance(data, list) and data:
                files = data
                if proxy:
                    logging.info("视频源解析经系统代理成功: %s", proxy)
                break
            # 200 但空/非列表：换下一种尝试（去 auth / 走代理）
            logging.warning("视频源列表为空 (len=%s, proxy=%s)，尝试其他方式",
                            len(resp.content), proxy or "直连")
        except Exception as exc:
            last_err = exc
            logging.warning("视频源解析失败 (proxy=%s): %s", proxy or "直连", exc)
    if files is None:
        if last_err:
            logging.warning("视频源解析全部失败: %s", last_err)
        return "", ""

    # 按画质优先级排序后逐级回退：最优画质没有 src 时用次优
    ranked = sorted(
        files,
        key=lambda f: IWARA_QUALITY_PREF.get(str(f.get("name") or "").lower(), 9),
    )
    for entry in ranked:
        src = entry.get("src") or {}
        url = src.get("download") or src.get("view") or ""
        # 协议相对 URL（//hime.iwara.tv/...）：浏览器能自动解析，requests 不能 ——
        # 这正是"无法解析视频源"误报的根因，必须补上 https: 前缀
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http"):
            return url, entry.get("type") or "video/mp4"
    return "", ""


def _iwara_video_ext(mime: str) -> str:
    return {"video/mp4": ".mp4", "video/webm": ".webm"}.get(mime, ".mp4")


async def iwara_inspect(url: str, options: dict) -> None:
    """解析 Iwara 视频页 / 用户主页 → 文件列表（视频直链下载时重新解析）。"""
    m_video = re.search(r"iwara\.(?:tv|ai)/video/([A-Za-z0-9_-]+)", url, re.I)
    m_user = re.search(r"iwara\.(?:tv|ai)/(?:profile|user)/([A-Za-z0-9_-]+)", url, re.I)
    if not m_video and not m_user:
        emit({"event": "inspect_error", "message": "无法识别的 Iwara 链接（支持 /video/{id} 与 /profile/{用户名}）"})
        return
    try:
        album_name = ""
        if m_video:
            video_ids = [m_video.group(1)]
        else:
            # 用户主页：翻页拉取全部视频 ID（上限 20 页 = 640 个防滥用）
            username = m_user.group(1)
            profile = await asyncio.to_thread(_iwara_api_get, f"/profile/{username}", None)
            user = profile.get("user") or {}
            user_id = user.get("id") or ""
            if not user_id:
                emit({"event": "inspect_error", "message": f"找不到 Iwara 用户 @{username}"})
                return
            album_name = user.get("name") or username
            emit({"event": "inspect_progress", "current": 0, "total": 0, "filename": f"获取 @{username} 的视频列表..."})
            video_ids = []
            for p in range(20):
                data = await asyncio.to_thread(
                    _iwara_api_get, "/videos",
                    {"user": user_id, "page": p, "limit": 32, "sort": "date"},
                )
                page_videos = data.get("results") or []
                if not page_videos:
                    break
                video_ids.extend(v.get("id") for v in page_videos if v.get("id"))
                if len(page_videos) < 32:
                    break
            if not video_ids:
                emit({"event": "inspect_error", "message": f"@{username} 没有可下载的视频"})
                return

        items: list[dict] = []
        total = len(video_ids)
        emit({"event": "inspect_progress", "current": 0, "total": total, "filename": ""})
        for idx, vid in enumerate(video_ids):
            data = await asyncio.to_thread(_iwara_api_get, f"/video/{vid}", None)
            errmsg = data.get("message")
            if errmsg:
                logging.warning("Iwara 视频 %s 跳过: %s", vid, errmsg)
                continue
            if not data.get("fileUrl"):
                logging.warning("Iwara 视频 %s 无文件源", vid)
                continue
            user = data.get("user") or {}
            file = data.get("file") or {}
            thumb = ""
            if file.get("id"):
                thumb = f"https://files.iwara.tv/image/thumbnail/{file['id']}/thumbnail-00.jpg"
            title = sanitize_directory_name((data.get("title") or f"iwara_{vid}").strip())
            items.append({
                "filename": f"{title}.mp4",
                "size": None,
                "item_page": f"https://www.iwara.tv/video/{vid}",
                "status": "ok",
                "thumbnail": thumb,
                "media_url": data.get("fileUrl"),
                "site": "iwara",
                "video_id": vid,
                "post_title": data.get("title") or title,
                "post_date": (data.get("createdAt") or "")[:10],
                "artist": user.get("name") or user.get("username") or "",
            })
            emit({"event": "inspect_progress", "current": idx + 1, "total": total, "filename": title})
        if not items:
            emit({"event": "inspect_error", "message": "没有解析到可下载的视频（可能为私有或需登录）"})
            return
        album = album_name or items[0].get("artist") or items[0].get("post_title") or "Iwara"
        album_id = f"iwara_{video_ids[0] if m_video else (user_id or '')}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        if m_user:
            _save_album_cache(f"iwara_user_{m_user.group(1)}", {
                "album_name": album, "album_id": album_id,
                "is_album": True, "items": items,
            })
        emit({
            "event": "inspect_complete",
            "album_name": album,
            "album_id": album_id,
            "is_album": True,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("Iwara 解析完成: %s, 共 %d 个视频", album, len(items))
    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"Iwara 解析失败: {exc}（请检查网络或代理设置）"})
        logging.exception("Iwara 解析过程出错")


# ============================
# 增量下载状态（全站点通用）
# ============================
DOWNLOAD_STATE_FILE = "cache/download_state.json"


def _load_download_state() -> dict:
    """读取各相册的下载进度状态。"""
    try:
        with open(DOWNLOAD_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_download_state(state: dict) -> None:
    """保存下载进度状态。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        _atomic_write_json(DOWNLOAD_STATE_FILE, state)
    except OSError as exc:
        logging.warning("保存下载状态失败: %s", exc)


def _mark_items_new(album_id: str | None, items: list[dict]) -> None:
    """给解析出的文件列表标记 is_new / is_downloaded（历史查重 + 增量更新截断）。

    截断日期（latest_post）：该相册上次成功下载的文件里最新的发帖日期。
    - 发帖日期 <= 截断日期 → is_downloaded（视为已处理过，默认不勾选）
    - 发帖日期 >  截断日期 → is_new（新内容，默认勾选下载）
    - item_page 在已下载集合中 → is_downloaded（精确到单文件的查重）
    """
    if not album_id or not items:
        return
    state = _load_download_state()
    album_state = state.get(album_id) or {}
    downloaded = set(album_state.get("downloaded", []))
    cutoff = album_state.get("latest_post") or ""

    new_count = 0
    dup_count = 0
    for item in items:
        key = item.get("item_page", "")
        post_date = item.get("post_date") or ""
        # 截断日期之前的内容统一视为已下载（下次只下载更新）
        is_dl = bool(key) and key in downloaded
        if not is_dl and post_date and cutoff and post_date <= cutoff:
            is_dl = True
        item["is_downloaded"] = is_dl
        item["is_new"] = not is_dl
        if not is_dl:
            new_count += 1
        else:
            dup_count += 1
    if new_count:
        logging.info("增量标记: %s 有 %d 个新文件（截断日期 %s）", album_id, new_count, cutoff or "无")
    if dup_count:
        logging.info("查重标记: %s 有 %d 个文件已下载过", album_id, dup_count)


def _update_download_state(album_id: str | None, items: list[dict]) -> None:
    """下载成功后更新相册的下载进度（记录已下载文件和最后下载时间）。

    只记录 status == "completed" 的文件：失败/跳过的文件不能进 downloaded 集合，
    否则重新解析时会被误标"已下载"且默认不勾选，用户以为下过了实际没有。

    同时记录 latest_post（已下载文件中最新的发帖日期）作为下次增量更新
    的截断日期：重新解析时早于该日期的内容默认不勾选，只下载更新的内容。
    """
    if not album_id or not items:
        return
    ok_items = [i for i in items if i.get("status") == "completed"]
    if not ok_items:
        return
    state = _load_download_state()
    album_state = state.get(album_id) or {"downloaded": [], "last_downloaded": ""}
    downloaded = set(album_state.get("downloaded", []))
    latest_post = album_state.get("latest_post") or ""
    for item in ok_items:
        key = item.get("item_page", "")
        if key:
            downloaded.add(key)
        pd = item.get("post_date") or ""
        if pd and pd > latest_post:
            latest_post = pd
    album_state["downloaded"] = sorted(downloaded)[-3000:]  # 防止无限增长
    album_state["last_downloaded"] = datetime.now().isoformat(timespec="seconds")
    album_state["latest_post"] = latest_post
    state[album_id] = album_state
    _save_download_state(state)
    logging.info("下载状态已更新: %s (本次成功 %d 个，累计 %d 个文件，更新至 %s)",
                 album_id, len(ok_items), len(downloaded), latest_post or "无日期")
