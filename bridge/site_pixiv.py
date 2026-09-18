# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Pixiv（含 App API 全功能）。

由 gui_bridge.py 按物理顺序拆出（原行区间 8476-10457），
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
# Pixiv 站点支持 (pixiv.net，插画/漫画/小说站)
# ============================
# 登录: App API Refresh Token 方案（账号密码 + 内置浏览器表单登录已失效，弃用）
#   1) PKCE OAuth: 生成 code_verifier/challenge → 前端 webview 打开
#      app-api.pixiv.net/web/v1/login?code_challenge=...&client=pixiv-android（人机验证在弹窗内完成）
#   2) 登录成功 pixiv 重定向 pixiv://account/login?code=xxx → webview 拦截提取 code
#   3) POST oauth.secure.pixiv.net/auth/token (grant_type=authorization_code, code+code_verifier)
#      → access_token(1小时) + refresh_token(长期) + 用户信息，全部加密保存
#   4) 之后 access_token 过期自动用 refresh_token 续期，长期免登录
#   （Pixiv Android App 公开 client_id/secret，业界通用做法）
# 搜索: 三模式（插画/漫画、小说、用户）
#   - 未登录走 Web ajax（/ajax/search/artworks|novels|users/{kw}，匿名可用）
#   - 登录后优先走 App API（/v1/search/illust|novel|user，offset 分页每页30）
# 浏览: App API（全部需 Bearer token）
#   - 推荐 /v1/illust/recommended | 漫画 content_type=manga | 小说 /v1/novel/recommended | 用户 /v1/user/recommended
#   - 排行榜 /v1/illust/ranking|/v1/novel/ranking?mode=day|week|month
#   - 关注的人更新 /v2/illust/follow | /v1/novel/follow（断点合并缓存 cache/pixiv_follow_feed_*.json）
#   - 收藏 /v1/user/bookmarks/illust|manga|novel?restrict=public|private（年龄限制本地过滤）
#   - 收藏标签 /v1/user/bookmark-tags/illust|novel（书签）
#   - 关注列表 /v1/user/following | 粉丝 /v1/follower/list | 他人收藏 /v1/user/bookmarks/*
#   - 用户页 /v1/user/detail + /v1/user/illusts(type=illust|manga) + /v1/user/novels
# 详情: /v1/illust/detail | /v1/novel/detail（+ /v1/novel/text 小说正文）+ /v1/illust/related（点击懒加载）
# 互动: 点赞 POST /v2/illust|novel/like；收藏 POST /v2/illust|novel/bookmark/add|delete；
#   评论 POST /v1/illust|novel/comment/add|reply|delete；关注 POST /v1/user/follow/add|delete
# 发布: POST /v1/upload/illust（multipart：标题/说明/tags/年龄限制 + 图片文件）
# 下载: i.pximg.net 原图直链永久有效，但必须带 Referer: https://www.pixiv.net/（否则 403）
#   小说下载为 txt 全文（/v1/novel/text）；动图 ugoira 走 zip
# 提醒: Web ajax /ajax/notification（oauth 登录时同时抓取 webview cookie 备用）
# 国内必须代理（默认 http://127.0.0.1:10809）

PIXIV_BASE = "https://www.pixiv.net"
PIXIV_ACCOUNTS = "https://accounts.pixiv.net"
PIXIV_APP_BASE = "https://app-api.pixiv.net"
PIXIV_OAUTH_URL = "https://oauth.secure.pixiv.net/auth/token"
# Pixiv Android App 公开 OAuth 凭据（与 ZipFile/pixiv_auth、pixivpy 等开源实现一致）
PIXIV_CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
PIXIV_CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
# OAuth 授权码换 token 必带的 redirect_uri（登录回跳 callback 页）
PIXIV_OAUTH_REDIRECT_URI = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
PIXIV_HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"
PIXIV_APP_UA = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"
PIXIV_DEFAULT_PROXY = "http://127.0.0.1:10809"
# 用户主页解析的作品数上限（防止大触作者数千作品把解析卡死）
PIXIV_USER_MAX_WORKS = 500
# profile/illusts 批量取详情的单批 id 数
PIXIV_DETAIL_CHUNK = 30
# App API 每页条数（offset 分页）
PIXIV_APP_PER_PAGE = 30

_pixiv_proxy = PIXIV_DEFAULT_PROXY
_pixiv_username = ""


def _pixiv_username_now() -> str:
    """当前用户名（跨模块读取入口）。"""
    return _pixiv_username or ""


def _pixiv_set_username(v: str) -> None:
    """跨模块写入口（账号档案恢复等）。"""
    global _pixiv_username
    _pixiv_username = v or ""
_pixiv_user_id = ""
# App API token 缓存（凭据里的 access_token/refresh_token 为持久层）
_pixiv_access_token = ""
_pixiv_access_expire = 0.0

_pixiv_session = requests.Session()
# 会话创建即应用默认代理：启动期后台登录检查串行排队，pixiv_set_proxy(settings)
# 要 ~75 秒后才轮到——此前会话无代理，启动首屏的 pixiv feed/搜索全部直连超时
_pixiv_session.proxies = {"http": PIXIV_DEFAULT_PROXY, "https": PIXIV_DEFAULT_PROXY}
_pixiv_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
})


def pixiv_set_proxy(proxy: str) -> None:
    """设置 Pixiv 代理（空 = 直连；国内默认走代理）。"""
    global _pixiv_proxy
    _pixiv_proxy = (proxy or "").strip()
    if _pixiv_proxy and not _pixiv_proxy.startswith(("http://", "https://", "socks5://")):
        _pixiv_proxy = "http://" + _pixiv_proxy
    proxies = {"http": _pixiv_proxy, "https": _pixiv_proxy} if _pixiv_proxy else {}
    _pixiv_session.proxies = proxies
    emit({"event": "pixiv_proxy_set", "proxy": _pixiv_proxy})


_pixiv_throttle = _make_throttle(1.0)


def _pixiv_load_cred() -> dict:
    """读取已保存的 Pixiv 登录信息（加密存储：cookies + 邮箱 + 密码）。"""
    return _secure_store_read_cred("pixiv")


def _pixiv_save_cred(data: dict) -> None:
    _secure_store_write_cred("pixiv", dict(data))


def _pixiv_restore_session() -> None:
    """启动时从加密存储恢复会话 cookie。"""
    global _pixiv_username, _pixiv_user_id
    cred = _pixiv_load_cred()
    cookies = cred.get("cookies") or {}
    for name, value in cookies.items():
        try:
            _pixiv_session.cookies.set(name, value, domain=".pixiv.net")
        except Exception:
            pass
    _pixiv_username = cred.get("username") or ""
    _pixiv_user_id = cred.get("user_id") or ""


def _pixiv_sync_cookies(cred: dict) -> dict:
    """把当前会话 cookie 写回凭据（PHPSESSID 等会刷新）。"""
    cred["cookies"] = {c.name: c.value for c in _pixiv_session.cookies}
    return cred


def _pixiv_phpsessid_uid() -> str:
    """从会话 PHPSESSID 提取用户 ID（格式 "用户ID_哈希"；"0_" = 未登录）。"""
    for c in _pixiv_session.cookies:
        if c.name == "PHPSESSID":
            return (c.value.split("_", 1)[0] or "0").strip()
    return ""


def _pixiv_novel_html_to_text(html: str) -> str:
    """pixiv web 小说正文（HTML）→ 纯文本（br/p 转换行、去标签、反转义）。

    注意：[uploadedimage:N] / [pixivimage:ID] / [chapter:] 等方括号标记是
    纯文本的一部分，不会被本函数剥掉（去的是 HTML 标签）。"""
    if not html:
        return ""
    t = re.sub(r"<\s*br\s*/?\s*>", chr(10), html, flags=re.I)
    t = re.sub(r"</p\s*>", chr(10) * 2, t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    import html as _h
    return _h.unescape(t).replace(chr(13) + chr(10), chr(10)).strip()


_NOVEL_MARKER_RE = re.compile(r"\[(uploadedimage:\d+|pixivimage:\d+(?:-\d+)?)\]")


async def _pixiv_novel_embedded_images(d: dict, max_pixivimage: int = 12) -> dict:
    """web /ajax/novel/{id} 响应 → 正文插图映射 {标记: 图片直链}。

    2026-09-13 实测（真站响应字段）：
    - 正文内嵌插图：content 里 [uploadedimage:ID] 标记 ↔ 顶层 textEmbeddedImages
      （键=纯数字 id，值={novelImageId, sl, urls:{original/1200mw/...}}）；
    - 引用站内插画：[pixivimage:ID] 或带页码 [pixivimage:ID-p] →
      /ajax/illust/{ID}/pages 解析原图（p 为 1 起页码）。
    返回键带方括号（如 "[uploadedimage:25434480]"），与正文标记逐字对应。
    """
    embedded: dict = {}
    for k, v in (d.get("textEmbeddedImages") or {}).items():
        # 2026-09-13 实测：值是 {novelImageId, sl, urls:{original/1200mw/480mw/240mw}}
        url = ""
        if isinstance(v, dict):
            urls = v.get("urls") or {}
            url = (urls.get("original") or urls.get("1200mw")
                   or urls.get("480mw") or urls.get("240mw") or "")
        elif isinstance(v, str) and v.startswith("http"):
            url = v
        if url:
            # 键是纯数字 id（正文标记为 [uploadedimage:{id}]）
            marker = f"[uploadedimage:{k}]" if str(k).isdigit() else f"[{k}]"
            embedded[marker] = url
    text = d.get("content") or ""
    seen_illusts: set[str] = set()
    for m in _NOVEL_MARKER_RE.finditer(text):
        tag = m.group(1)
        if not tag.startswith("pixivimage:") or len(embedded) >= 40:
            continue
        illust_id, _, page = tag.split(":", 1)[1].partition("-")
        if illust_id in seen_illusts:
            continue
        if len(seen_illusts) >= max_pixivimage:
            break
        seen_illusts.add(illust_id)
        try:
            pages = await asyncio.to_thread(
                _pixiv_api_get, f"/ajax/illust/{illust_id}/pages")
            url = ""
            if page:
                idx = int(page) - 1
                if 0 <= idx < len(pages or []):
                    url = ((pages[idx].get("urls") or {}).get("original")
                           or (pages[idx].get("urls") or {}).get("large") or "")
            elif pages:
                url = ((pages[0].get("urls") or {}).get("original")
                       or (pages[0].get("urls") or {}).get("large") or "")
            if url:
                embedded[f"[{tag}]"] = url
        except Exception as exc:
            logging.warning("小说插画 pixivimage:%s 解析失败: %s", illust_id, exc)
    return embedded


def _pixiv_web_novel_to_app(d: dict, item_id: str) -> dict:
    """web /ajax/novel/{id} 的 body → 伪 App API 形状（供 _pixiv_app_card 消费）。"""
    tags = d.get("tags") if isinstance(d.get("tags"), dict) else {}
    tag_raw = tags.get("tags") if isinstance(tags, dict) else (tags or [])
    tag_list = [{"tag": t.get("tag") if isinstance(t, dict) else t}
                for t in (tag_raw or [])]
    # 封面字段是 coverUrl（2026-09-13 实测；此前取 d["url"] 恒 None → 封面全空）
    cover = d.get("coverUrl") or d.get("url") or ""
    # 系列连载信息（web 详情形状 seriesNavData {seriesId, title}）
    snav = d.get("seriesNavData") or {}
    return {
        "id": str(d.get("id") or item_id),
        "title": d.get("title") or "",
        "image_urls": {"medium": cover, "large": cover},
        "caption": d.get("description") or d.get("illustComment") or "",
        "create_date": d.get("createDate") or d.get("uploadDate") or "",
        "text_length": d.get("text_length") or d.get("wordCount") or 0,
        "view_count": d.get("viewCount") or 0,
        "total_bookmarks": d.get("bookmarkCount") or 0,
        "x_restrict": d.get("xRestrict") or 0,
        "series": {"id": snav.get("seriesId") or "", "title": snav.get("title") or ""},
        "is_bookmarked": bool(d.get("bookmarkData")),
        "user": {
            "id": d.get("userId") or "",
            "name": d.get("userName") or "",
            "profile_image_urls": {"medium": d.get("userImage") or cover},
        },
        "tags": tag_list,
    }


def _pixiv_web_user_card(d: dict, fallback_uid: str = "") -> dict:
    """web ajax 用户条目（following/followers）→ 前端统一用户卡片。

    2026-09-13 实测 /ajax/user/{uid}/followers 条目字段：
    userId/userName/profileImageUrl/profileImageSmallUrl/illusts/novels/...
    （此前读 image/userImage 恒空 → 粉丝/关注列表头像全部加载失败）"""
    uid = str(d.get("userId") or d.get("id") or fallback_uid or "")
    avatar = (d.get("profileImageUrl") or d.get("profileImageSmallUrl")
              or d.get("image") or d.get("userImage") or "")
    # web 条目的 recent illusts（带 url 的字典列表）→ 近作缩略图
    thumbs = []
    for w in (d.get("illusts") or [])[:3]:
        if isinstance(w, dict):
            t = w.get("url") or ""
            if t:
                thumbs.append(t)
    return {
        "kind": "user", "site": "pixiv",
        "user_id": uid,
        "album_name": d.get("userName") or d.get("name") or "未命名用户",
        "album_url": f"{PIXIV_BASE}/users/{uid}",
        "thumbnail": avatar,
        "avatar": avatar,
        "author": d.get("userName") or d.get("name") or "",
        "author_id": uid,
        "is_followed": bool(d.get("following")) if "following" in d else None,
        "recent_thumbs": thumbs,
    }


def _pixiv_api_get(path: str, params: dict | None = None) -> dict:
    """带节流的 AJAX GET（返回 JSON 的 body 部分；出错抛异常）。"""
    _pixiv_throttle()
    resp = _pixiv_session.get(
        f"{PIXIV_BASE}{path}", params=params, timeout=25,
        headers={
            "Referer": f"{PIXIV_BASE}/",
            "Accept": "application/json",
            "x-user-id": _pixiv_user_id or "",
        },
    )
    if resp.status_code != 200:
        raise PermissionError(f"Pixiv 返回 HTTP {resp.status_code}")
    data = resp.json()
    if data.get("error"):
        msg = (data.get("message") or "")[:200]
        raise PermissionError(f"Pixiv API 错误: {msg or '未知错误'}")
    return data.get("body") or {}


def _pixiv_oauth_state_path() -> Path:
    return Path("cache") / "pixiv_oauth.json"


def pixiv_oauth_start() -> None:
    """PKCE OAuth 第一步：生成 code_verifier/challenge，把登录 URL 发给前端 webview 打开。

    登录页为 app-api.pixiv.net/web/v1/login（Pixiv App 授权页，人机验证在弹窗内完成）；
    登录成功后 Pixiv 重定向 pixiv://account/login?code=xxx，由 webview 拦截提取 code。
    """
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    try:
        Path("cache").mkdir(exist_ok=True)
        _pixiv_oauth_state_path().write_text(
            json.dumps({"verifier": verifier, "created": time.time()}, ensure_ascii=False),
            encoding="utf-8")
    except OSError as exc:
        logging.warning("Pixiv OAuth 状态写入失败: %s", exc)
    url = (f"https://app-api.pixiv.net/web/v1/login"
           f"?code_challenge={challenge}&code_challenge_method=S256&client=pixiv-android")
    emit({"event": "pixiv_oauth_url", "url": url})


def _pixiv_oauth_post(extra: dict) -> dict:
    """POST oauth.secure.pixiv.net/auth/token（换 token；出错抛异常）。

    参数结构对齐 ZipFile/pixiv_auth 权威实现：
    授权码流程必须带 redirect_uri，否则返回 invalid_request。
    """
    data = {
        "client_id": PIXIV_CLIENT_ID,
        "client_secret": PIXIV_CLIENT_SECRET,
        "include_policy": "true",
    }
    data.update(extra)
    resp = requests.post(
        PIXIV_OAUTH_URL, data=data, timeout=30,
        headers={
            "User-Agent": PIXIV_APP_UA,
            "App-OS": "android", "App-Version": "5.0.234",
        },
        proxies=({"http": _pixiv_proxy, "https": _pixiv_proxy} if _pixiv_proxy else None),
    )
    try:
        result = resp.json()
    except ValueError:
        raise PermissionError(f"Pixiv OAuth 返回非 JSON（HTTP {resp.status_code}）")
    if resp.status_code != 200 or result.get("error"):
        # Pixiv 的真实原因在 errors.system.message（如"不正なOAuthクライアントです"=凭据非法），
        # 顶层只有 error=invalid_request，必须挖嵌套字段才能看到有效信息
        sys_err = ((result.get("errors") or {}).get("system") or {})
        msg = (sys_err.get("message") or result.get("error_description")
               or result.get("message") or result.get("error")
               or f"HTTP {resp.status_code}")[:200]
        raise PermissionError(f"Pixiv OAuth 失败: {msg}（code {sys_err.get('code') or resp.status_code}）")
    if not result.get("access_token") or not result.get("refresh_token"):
        raise PermissionError("Pixiv OAuth 未返回 token")
    return result


def pixiv_oauth_complete(code: str, cookie_str: str = "") -> None:
    """PKCE OAuth 第三步：webview 提取的 code + code_verifier 换 access/refresh token。

    登录页本身的 webview cookie 一并保存（提醒/通知等 Web ajax 备用通道）。
    """
    global _pixiv_username, _pixiv_user_id, _pixiv_access_token, _pixiv_access_expire
    try:
        verifier = ""
        try:
            state = json.loads(_pixiv_oauth_state_path().read_text(encoding="utf-8"))
            verifier = state.get("verifier") or ""
        except Exception:
            pass
        if not verifier:
            emit({"event": "pixiv_login_result", "success": False,
                  "message": "登录会话已过期，请重新点击「打开内置浏览器登录」"})
            return
        result = _pixiv_oauth_post({
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": PIXIV_OAUTH_REDIRECT_URI,
        })
        user = result.get("user") or {}
        uid = str(user.get("id") or "")
        username = (user.get("name") or "").strip()
        avatar = (user.get("profile_image_urls") or {}).get("medium") or ""
        cred = _pixiv_load_cred()
        cred.update({
            "access_token": result.get("access_token") or "",
            "refresh_token": result.get("refresh_token") or "",
            "access_expire": time.time() + int(result.get("expires_in") or 3600) - 300,
            "user_id": uid, "username": username, "avatar": avatar,
        })
        # webview cookie 一并保存（Web ajax 通道：通知/提醒等）
        if (cookie_str or "").strip():
            cookies = {}
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    cookies[k.strip()] = v.strip()
            cred["cookies"] = cookies
        _pixiv_save_cred(cred)
        _pixiv_access_token = cred["access_token"]
        _pixiv_access_expire = cred["access_expire"]
        _pixiv_user_id = uid
        _pixiv_username = username
        # 同步 cookie 到请求会话
        _pixiv_session.cookies.clear()
        for name, value in (cred.get("cookies") or {}).items():
            try:
                _pixiv_session.cookies.set(name, value, domain=".pixiv.net")
            except Exception:
                pass
        try:
            _pixiv_oauth_state_path().unlink(missing_ok=True)
        except Exception:
            pass
        _emit_login_info()
        emit({"event": "pixiv_login_result", "success": True, "username": username,
              "user_id": uid, "message": "Pixiv 登录成功（Refresh Token 已长期保存）"})
        logging.info("Pixiv OAuth 登录成功: %s (%s)", username, uid)
    except requests.RequestException as exc:
        emit({"event": "pixiv_login_result", "success": False,
              "message": f"连接失败: {exc}（国内必须在设置里配置 Pixiv 代理）",
              "network_issue": True})
    except Exception as exc:
        emit({"event": "pixiv_login_result", "success": False,
              "message": f"获取 Token 失败: {exc}"})
        logging.exception("Pixiv OAuth 换 token 失败")


def _pixiv_token_refresh() -> None:
    """用 refresh_token 换新的 access_token（1小时一换；refresh_token 长期有效）。"""
    global _pixiv_access_token, _pixiv_access_expire
    cred = _pixiv_load_cred()
    refresh_token = cred.get("refresh_token") or ""
    if not refresh_token:
        raise PermissionError("未登录（无 Refresh Token），请点「打开内置浏览器登录」")
    result = _pixiv_oauth_post({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    _pixiv_access_token = result["access_token"]
    _pixiv_access_expire = time.time() + int(result.get("expires_in") or 3600) - 300
    cred["access_token"] = _pixiv_access_token
    cred["access_expire"] = _pixiv_access_expire
    # OAuth 续期会轮换 refresh_token（返回新值则更新）
    if result.get("refresh_token"):
        cred["refresh_token"] = result["refresh_token"]
    _pixiv_save_cred(cred)


def _pixiv_token_ready() -> bool:
    """token 可用性检查：过期自动用 refresh_token 续期（登录时无感）。"""
    global _pixiv_access_token, _pixiv_access_expire
    cred = _pixiv_load_cred()
    if not _pixiv_access_token:
        _pixiv_access_token = cred.get("access_token") or ""
        try:
            _pixiv_access_expire = float(cred.get("access_expire") or 0)
        except (TypeError, ValueError):
            _pixiv_access_expire = 0.0
    if not cred.get("refresh_token"):
        return False
    if not _pixiv_access_token or time.time() >= _pixiv_access_expire:
        _pixiv_token_refresh()
    return True


def _pixiv_app_api(method: str, path: str, params: dict | None = None,
                   retry: bool = True) -> dict:
    """Pixiv App API 调用（Bearer access_token；过期自动续期，401 重试一次）。

    App API 的 GET 参数走 query string；POST 参数必须放表单 body
    （x-www-form-urlencoded）——此前 POST 也放 query string，写操作
    （点赞/收藏/关注）一律 400 Bad Request。
    """
    if not _pixiv_token_ready():
        raise PermissionError("Pixiv 未登录：请点「打开内置浏览器登录」完成 Refresh Token 登录")
    client_time = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    client_hash = hashlib.md5((client_time + PIXIV_HASH_SECRET).encode()).hexdigest()
    base_params = dict(params or {})
    base_params.setdefault("filter", "for_ios")
    headers = {
        "Authorization": f"Bearer {_pixiv_access_token}",
        "User-Agent": PIXIV_APP_UA,
        "App-OS": "android", "App-Version": "5.0.234",
        "X-Client-Time": client_time,
        "X-Client-Hash": client_hash,
    }
    _pixiv_throttle(0.8)
    if method.upper() == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = _pixiv_session.request(
            method, f"{PIXIV_APP_BASE}{path}", data=base_params,
            headers=headers, timeout=25)
    else:
        resp = _pixiv_session.request(
            method, f"{PIXIV_APP_BASE}{path}", params=base_params,
            headers=headers, timeout=25)
    if resp.status_code == 401 and retry:
        # token 失效 → 强制续期重试一次
        global _pixiv_access_expire
        _pixiv_access_expire = 0.0
        _pixiv_token_refresh()
        return _pixiv_app_api(method, path, params, retry=False)
    if resp.status_code == 404:
        raise PermissionError("接口不存在（404）")
    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = (err.get("error") or {}).get("message") if isinstance(err.get("error"), dict) else (err.get("message") or "")
        except ValueError:
            msg = ""
        raise PermissionError(f"App API HTTP {resp.status_code}: {(msg or resp.text[:120])[:160]}")
    return resp.json()


def _pixiv_fetch_username(uid: str) -> str:
    """拉取用户显示名（ajax/user/{uid}；失败返回空）。"""
    try:
        body = _pixiv_api_get(f"/ajax/user/{uid}")
        return (body.get("name") or "").strip()
    except Exception:
        return ""


def pixiv_set_cookies(cookie_str: str, email: str = "", password: str = "") -> None:
    """更新 Pixiv Web cookie 备用通道（提醒/通知等 Web ajax 用；登录主体为 Refresh Token）。

    OAuth 登录流程会自动带上 webview cookie，此命令一般无需单独调用；
    webview 里重新过验证后可手动确认刷新 cookie。
    """
    try:
        cred = _pixiv_load_cred()
        cookies = {}
        for pair in (cookie_str or "").split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookies[name.strip()] = value.strip()
        if cookies:
            cred["cookies"] = cookies
            _pixiv_session.cookies.clear()
            for name, value in cookies.items():
                try:
                    _pixiv_session.cookies.set(name, value, domain=".pixiv.net")
                except Exception:
                    pass
        if (email or "").strip():
            cred["email"] = email.strip()
        if password:
            cred["password"] = password
        _pixiv_save_cred(cred)
        emit({"event": "pixiv_login_result", "success": True,
              "message": "Pixiv Web cookie 已更新（Refresh Token 登录不受影响）"})
    except Exception as exc:
        logging.exception("Pixiv cookie 保存失败")
        emit({"event": "pixiv_login_result", "success": False,
              "message": f"保存会话失败: {exc}"})


def pixiv_logout() -> None:
    global _pixiv_username, _pixiv_user_id
    _secure_store_clear_cred("pixiv")
    _pixiv_session.cookies.clear()
    _pixiv_username = ""
    _pixiv_user_id = ""
    _emit_login_info()
    emit({"event": "pixiv_login_result", "success": False, "logout": True,
          "message": "已退出 Pixiv 登录"})


def pixiv_check_login(silent: bool = False) -> None:
    """检查 Pixiv 登录状态（有 refresh_token 即视为已登录；顺带静默续期验证有效性）。"""
    global _pixiv_username, _pixiv_user_id
    cred = _pixiv_load_cred()
    if not cred.get("refresh_token"):
        emit({"event": "pixiv_login_result", "success": False, "silent": silent,
              "message": "" if silent else "未登录（点「打开内置浏览器登录」完成 Refresh Token 登录）"})
        return
    try:
        # 有 refresh_token：静默续期一次验证有效性（顺带刷新 access_token）
        _pixiv_token_refresh()
        _pixiv_username = cred.get("username") or ""
        _pixiv_user_id = cred.get("user_id") or ""
        _emit_login_info()
        emit({"event": "pixiv_login_result", "success": True, "silent": silent,
              "username": _pixiv_username, "message": "Pixiv 登录有效"})
    except requests.RequestException as exc:
        emit({"event": "pixiv_login_result", "success": False, "silent": silent,
              "message": f"连接失败: {exc}（请检查网络或 Pixiv 代理设置）",
              "network_issue": True})
    except Exception:
        # refresh_token 失效 → 需重新走内置浏览器 OAuth 登录
        emit({"event": "pixiv_login_result", "success": False, "silent": silent,
              "message": "" if silent else "登录已失效，请重新点「打开内置浏览器登录」"})


def _pixiv_parse_card(d: dict) -> dict:
    """搜索/用户作品卡片数据 → 前端插画卡片。"""
    illust_id = str(d.get("id") or "")
    if not illust_id:
        return {}
    thumb = d.get("url") or ""
    if thumb.startswith("//"):
        thumb = "https:" + thumb
    x_restrict = d.get("xRestrict") or 0
    # 系列连载（漫画/插画系列）：seriesNavData {seriesId, title, seriesType}
    snav = d.get("seriesNavData") or {}
    return {
        "album_name": d.get("title") or f"pixiv_{illust_id}",
        "album_url": f"{PIXIV_BASE}/artworks/{illust_id}",
        "thumbnail": thumb,
        "files": d.get("pageCount") or 1,
        "site": "pixiv",
        "illust_id": illust_id,
        "author": d.get("userName") or "",
        "author_url": f"{PIXIV_BASE}/users/{d.get('userId')}" if d.get("userId") else "",
        "r18": x_restrict in (1, 2),
        "ugoira": d.get("illustType") == 2,
        "posted": (d.get("createDate") or "")[:10],
        # 前端屏蔽标签/作者功能需要（web ajax 卡片 tags 是字符串数组）
        "tags": [str(t) for t in (d.get("tags") or []) if t][:10],
        "series_id": str(snav.get("seriesId") or ""),
        "series_title": str(snav.get("title") or ""),
    }


def _pixiv_app_card(d: dict, kind: str = "illust") -> dict:
    """App API 对象（illust/novel/user）→ 前端统一卡片。

    illust/novel 卡片带互动统计与收藏状态；user 卡片带简介与关注状态。
    """
    user = d.get("user") or {}
    uid = str(user.get("id") or "")
    author = user.get("name") or ""
    avatar = (user.get("profile_image_urls") or {}).get("medium") or ""
    x_restrict = d.get("x_restrict") or 0
    if kind == "user":
        return {
            "kind": "user", "site": "pixiv",
            "user_id": uid, "album_name": author,
            "thumbnail": avatar, "author": author,
            "comment": (user.get("comment") or "")[:120],
            "is_followed": bool(user.get("is_followed")),
            "account": user.get("account") or "",
        }
    if kind == "novel":
        cover = (d.get("image_urls") or {}).get("medium") or ""
        series_obj = d.get("series") if isinstance(d.get("series"), dict) else {}
        return {
            "kind": "novel", "site": "pixiv",
            "novel_id": str(d.get("id") or ""),
            "album_name": d.get("title") or "",
            "album_url": f"{PIXIV_BASE}/novel/show.php?id={d.get('id')}",
            "thumbnail": cover,
            "author": author, "author_url": f"{PIXIV_BASE}/users/{uid}" if uid else "",
            "r18": x_restrict in (1, 2),
            "posted": (d.get("create_date") or "")[:10],
            "words": d.get("text_length") or 0,
            "views": d.get("total_view") or 0,
            "bookmarks": d.get("total_bookmarks") or 0,
            "is_bookmarked": bool(d.get("is_bookmarked")),
            "series": (series_obj.get("title") or "") or ((d.get("series") or "") if isinstance(d.get("series"), str) else ""),
            "series_id": str(series_obj.get("id") or d.get("series_id") or ""),
            "series_title": str(series_obj.get("title") or d.get("series_title") or ""),
            # 前端屏蔽标签/作者功能需要（App API tags 是 [{tag}] 字典数组）
            "tags": [str((t or {}).get("tag") or (t if isinstance(t, str) else ""))
                     for t in (d.get("tags") or []) if t][:10],
        }
    # illust / manga
    thumb = (d.get("image_urls") or {}).get("medium") or ""
    return {
        "kind": "illust", "site": "pixiv",
        "illust_id": str(d.get("id") or ""),
        "album_name": d.get("title") or "",
        "album_url": f"{PIXIV_BASE}/artworks/{d.get('id')}",
        "thumbnail": thumb,
        "files": d.get("page_count") or 1,
        "author": author, "author_url": f"{PIXIV_BASE}/users/{uid}" if uid else "",
        "author_id": uid,
        "r18": x_restrict in (1, 2),
        "ugoira": d.get("type") == "ugoira",
        "manga_type": d.get("type") == "manga",
        "posted": (d.get("create_date") or "")[:10],
        "views": d.get("total_view") or 0,
        "bookmarks": d.get("total_bookmarks") or 0,
        "likes": d.get("total_evaluate") or 0,
        "comments": d.get("total_comments") or 0,
        "is_bookmarked": bool(d.get("is_bookmarked")),
        "avatar": avatar,
        "series": ((d.get("series") or {}).get("title") or ""),
        "tags": [str((t or {}).get("tag") or (t if isinstance(t, str) else ""))
                 for t in (d.get("tags") or []) if t][:10],
    }


def _pixiv_has_token() -> bool:
    return bool(_pixiv_load_cred().get("refresh_token"))


async def pixiv_search(query: str, page: int = 1, mode: str = "", search_type: str = "") -> None:
    """Pixiv 三模式搜索：插画/漫画（默认）、小说、用户。

    登录后优先走 App API（offset 分页，每页 30）；未登录走 Web ajax（每页 60）。
    """
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        mode = mode if mode in ("all", "safe", "r18") else "all"
        search_type = search_type if search_type in ("illust", "novel", "user") else "illust"
        items: list[dict] = []
        total = 0
        per_page = 60
        used_app_api = False

        if search_type == "illust":
            # 插画/漫画混合：Web ajax（与旧版一致，登录与否都可用）
            encoded = urllib.parse.quote(query, safe="")
            body = await asyncio.to_thread(
                _pixiv_api_get, f"/ajax/search/artworks/{encoded}",
                {"word": query, "order": "date_d", "mode": mode, "p": page,
                 "type": "all", "s_mode": "s_tag_full", "lang": "zh"},
            )
            data = (body.get("illustManga") or {}).get("data") or []
            total = int((body.get("illustManga") or {}).get("total") or 0)
            items = [c for c in (_pixiv_parse_card(d) for d in data) if c]
            for c in items:
                c.setdefault("kind", "illust")
        elif _pixiv_has_token():
            # 小说/用户：登录走 App API
            used_app_api = True
            per_page = PIXIV_APP_PER_PAGE
            offset = (page - 1) * PIXIV_APP_PER_PAGE
            path = "/v1/search/novel" if search_type == "novel" else "/v1/search/user"
            result = await asyncio.to_thread(_pixiv_app_api, "GET", path, {
                "word": query, "search_target": "partial_match_for_tags",
                "sort": "date_desc", "offset": offset,
            })
            if search_type == "novel":
                raw = result.get("novels") or []
                if mode == "r18":
                    raw = [d for d in raw if (d.get("x_restrict") or 0) in (1, 2)]
                elif mode == "safe":
                    raw = [d for d in raw if not (d.get("x_restrict") or 0)]
                items = [c for c in (_pixiv_app_card(d, "novel") for d in raw) if c["novel_id"]]
            else:
                raw = result.get("user_previews") or []
                items = [c for c in (_pixiv_app_card(d, "user") for d in raw) if c["user_id"]]
        else:
            # 未登录：小说/用户走 Web ajax
            encoded = urllib.parse.quote(query, safe="")
            if search_type == "novel":
                body = await asyncio.to_thread(
                    _pixiv_api_get, f"/ajax/search/novels/{encoded}",
                    {"word": query, "order": "date_d", "mode": mode, "p": page,
                     "s_mode": "s_tag_full", "lang": "zh"},
                )
                data = (body.get("novels") or {}).get("data") or []
                total = int((body.get("novels") or {}).get("total") or 0)
                for d in data:
                    cover = d.get("url") or ""
                    if cover.startswith("//"):
                        cover = "https:" + cover
                    items.append({
                        "kind": "novel", "site": "pixiv",
                        "novel_id": str(d.get("id") or ""),
                        "album_name": d.get("title") or "",
                        "album_url": f"{PIXIV_BASE}/novel/show.php?id={d.get('id')}",
                        "thumbnail": cover,
                        "author": d.get("userName") or "",
                        "author_url": f"{PIXIV_BASE}/users/{d.get('userId')}" if d.get("userId") else "",
                        "r18": (d.get("xRestrict") or 0) in (1, 2),
                        "posted": (d.get("createDate") or "")[:10],
                        "words": d.get("textLength") or 0,
                        "views": d.get("viewCount") or 0,
                        "bookmarks": d.get("bookmarkCount") or 0,
                    })
            else:
                body = await asyncio.to_thread(
                    _pixiv_api_get, f"/ajax/search/users/{encoded}",
                    {"word": query, "order": "date_d", "p": page, "lang": "zh"},
                )
                data = ((body.get("users") or {}).get("data")) or []
                total = int((body.get("users") or {}).get("total") or 0)
                for d in data:
                    avatar = d.get("image") or ""
                    if avatar.startswith("//"):
                        avatar = "https:" + avatar
                    items.append({
                        "kind": "user", "site": "pixiv",
                        "user_id": str(d.get("userId") or ""),
                        "album_name": d.get("name") or "",
                        "thumbnail": avatar, "author": d.get("name") or "",
                        "comment": (d.get("comment") or "")[:120],
                    })

        # 已缓存的缩略图直接用本地 thumb://（i.pximg.net 直链在 <img> 里会 403）
        _apply_cached_thumbnails(items)
        has_more = False
        total_pages = 0
        if used_app_api:
            # App API 无 total：本页满 30 条即视为有下一页
            has_more = len(items) >= PIXIV_APP_PER_PAGE
            total_pages = page + 1 if has_more else page
        else:
            total_pages = (total + per_page - 1) // per_page if total else 0
            has_more = bool(total) and page * per_page < total
        type_label = {"illust": "插画/漫画", "novel": "小说", "user": "用户"}[search_type]
        mode_label = {"all": "全部", "safe": "全年龄", "r18": "R-18"}.get(mode, "")
        if search_type == "illust" or not used_app_api:
            label = f"{query} · {type_label}" + (f" · {mode_label}" if mode_label and search_type != "user" else "")
        else:
            label = f"{query} · {type_label}"
        emit({
            "event": "search_result", "query": query, "site": "pixiv",
            "items": items, "page": page,
            "total_pages": total_pages, "total_results": total,
            "has_more": has_more, "mode": mode, "search_type": search_type,
            "label": label,
        })
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("Pixiv 搜索 '%s' (type=%s mode=%s page=%d): %d 个结果",
                     query, search_type, mode, page, len(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"Pixiv 搜索失败: {exc}（请检查网络或 Pixiv 代理设置）"})
        logging.exception("Pixiv 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


def is_pixiv_url(url: str) -> bool:
    """判断是否为 Pixiv 链接（作品页 /artworks/{id}、小说页、用户主页 /users/{id}）。"""
    return bool(re.search(r"pixiv\.net/(?:en/)?(?:artworks/\d+|users/\d+|novel/show\.php\?.*id=\d+|member_illust\.php\?.*illust_id=\d+)", url, re.I))


# ============================
# Pixiv App API 功能（feed/排行/关注更新/收藏/用户页/互动/详情/评论/相关/标签/通知/上传）
# ============================

PIXIV_FEED_KINDS: dict[str, tuple[str, dict, str]] = {
    # kind → (App API 路径, 额外参数, 响应列表字段)
    "home":       ("/v1/illust/recommended", {"content_type": "illust", "include_ranking_illusts": "true"}, "illusts"),
    "illust":     ("/v1/illust/recommended", {"content_type": "illust"}, "illusts"),
    "manga":      ("/v1/illust/recommended", {"content_type": "manga"}, "illusts"),
    "novel":      ("/v1/novel/recommended", {"include_ranking_novels": "true"}, "novels"),
    "recommended_user": ("/v1/user/recommended", {}, "user_previews"),
    "rank_illust_day":   ("/v1/illust/ranking", {"mode": "day"}, "illusts"),
    "rank_illust_week":  ("/v1/illust/ranking", {"mode": "week"}, "illusts"),
    "rank_illust_month": ("/v1/illust/ranking", {"mode": "month"}, "illusts"),
    "rank_manga_day":    ("/v1/illust/ranking", {"mode": "day_manga"}, "illusts"),
    "rank_manga_week":   ("/v1/illust/ranking", {"mode": "week_manga"}, "illusts"),
    "rank_manga_month":  ("/v1/illust/ranking", {"mode": "month_manga"}, "illusts"),
    "rank_novel_day":    ("/v1/novel/ranking", {"mode": "day"}, "novels"),
    "rank_novel_week":   ("/v1/novel/ranking", {"mode": "week"}, "novels"),
    "rank_novel_month":  ("/v1/novel/ranking", {"mode": "month"}, "novels"),
}
PIXIV_FEED_LABELS: dict[str, str] = {
    "home": "首页", "illust": "插画", "manga": "漫画", "novel": "小说",
    "recommended_user": "推荐用户",
    "rank_illust_day": "插画日榜", "rank_illust_week": "插画周榜", "rank_illust_month": "插画月榜",
    "rank_manga_day": "漫画日榜", "rank_manga_week": "漫画周榜", "rank_manga_month": "漫画月榜",
    "rank_novel_day": "小说日榜", "rank_novel_week": "小说周榜", "rank_novel_month": "小说月榜",
    "follow_illust": "关注的人更新（插画/漫画）", "follow_novel": "关注的人更新（小说）",
    "bookmark_illust": "我的收藏（插画）", "bookmark_manga": "我的收藏（漫画）", "bookmark_novel": "我的收藏（小说）",
}


def _pixiv_feed_cache_path(content: str) -> Path:
    return Path("cache") / f"pixiv_follow_feed_{content}.json"


def _pixiv_my_tags_path() -> Path:
    return Path("cache") / "pixiv_my_tags.json"


def _pixiv_app_items(result: dict, list_key: str, kind: str) -> list[dict]:
    raw = result.get(list_key) or []
    items = []
    for d in raw:
        items.append(_pixiv_app_card(d, kind))
    return [c for c in items if c.get("album_name") is not None and
            (c.get("illust_id") or c.get("novel_id") or c.get("user_id"))]


async def pixiv_feed(kind: str, page: int = 1) -> None:
    """Pixiv 首页/插画/漫画/小说/推荐用户/排行榜 feed（App API offset 分页）。"""
    kind = kind or "home"
    emit({"event": "search_loading", "loading": True})
    try:
        cfg = PIXIV_FEED_KINDS.get(kind)
        if not cfg:
            emit({"event": "search_error", "message": f"未知内容类型: {kind}"})
            return
        path, extra, list_key = cfg
        page = max(1, page or 1)
        offset = (page - 1) * PIXIV_APP_PER_PAGE
        params = dict(extra)
        if offset:
            params["offset"] = offset
        # 2026-09-13 实测 recommended/ranking 同样支持 offset（首页与 offset=30 首ID不同）；
        # 此前跳过导致推荐/排行榜翻页永远重复第一页
        params.setdefault("offset", offset)
        result = await asyncio.to_thread(_pixiv_app_api, "GET", path, params)
        kind_card = "user" if list_key == "user_previews" else ("novel" if "novel" in list_key else "illust")
        items = _pixiv_app_items(result, list_key, kind_card)
        _apply_cached_thumbnails(items)
        label = PIXIV_FEED_LABELS.get(kind, kind)
        emit({
            "event": "search_result", "query": label, "site": "pixiv",
            "items": items, "page": page,
            "total_pages": page + 1 if len(items) >= PIXIV_APP_PER_PAGE else page,
            "total_results": 0, "has_more": len(items) >= PIXIV_APP_PER_PAGE,
            "feed_kind": kind, "label": label, "search_type": kind_card,
        })
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("Pixiv feed %s page=%d: %d 条", kind, page, len(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"Pixiv 加载失败: {exc}"})
        logging.exception("Pixiv feed 失败 kind=%s", kind)
    finally:
        emit({"event": "search_loading", "loading": False})


async def pixiv_follow_feed(content: str = "illust", refresh: bool = True) -> None:
    """关注的人的最新作品（插画/漫画 或 小说）：断点合并缓存，与 X 站浏览模式同逻辑。

    2026-09-13 修复"只抓一页"：App API 单页仅 30 条 → 顺 next_url 链最多走 8 页
    （240 条，无 next_url 提前停），与缓存按作品 id 去重合并（新的在前，上限 600）。
    缓存持久化 cache/pixiv_follow_feed_{content}.json。
    """
    content = "novel" if content == "novel" else "illust"
    emit({"event": "search_loading", "loading": True})
    try:
        path = "/v1/novel/follow" if content == "novel" else "/v2/illust/follow"
        result = await asyncio.to_thread(_pixiv_app_api, "GET", path, {"restrict": "public"})
        list_key = "novels" if content == "novel" else "illusts"
        kind_card = "novel" if content == "novel" else "illust"
        items = _pixiv_app_items(result, list_key, kind_card)

        cache_path = _pixiv_feed_cache_path(content)
        id_key = "novel_id" if content == "novel" else "illust_id"
        label = PIXIV_FEED_LABELS.get(f"follow_{content}", "关注更新")

        def _merge_and_emit(new_items: list, append: bool) -> list:
            cached: list[dict] = []
            try:
                if cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8")).get("items") or []
            except Exception:
                cached = []
            seen = {c.get(id_key) for c in new_items}
            merged = new_items + [c for c in cached if c.get(id_key) not in seen][:600]
            try:
                cache_path.parent.mkdir(exist_ok=True)
                cache_path.write_text(
                    json.dumps({"items": merged[:600], "updated_at": time.time()}, ensure_ascii=False),
                    encoding="utf-8")
            except OSError:
                pass
            _apply_cached_thumbnails(merged)
            emit({
                "event": "search_result", "query": label, "site": "pixiv",
                "items": merged, "page": 1, "total_pages": 1,
                "total_results": len(merged), "has_more": False,
                "feed_kind": f"follow_{content}", "label": label,
                "search_type": kind_card, "new_count": len(new_items),
                "append": append,
            })
            if merged:
                asyncio.create_task(_cache_thumbnails(merged))
            return merged

        # 阶段 1：首页先发（1-2 秒内界面即有内容；后台化后整段抓完才发，
        # 用户 10-16 秒零反馈以为功能坏了——日志实锤连点两次被防重入挡掉）
        _merge_and_emit(items, append=False)

        # 阶段 2：剩余页后台补齐，追加事件合并（前端按 append 标记去重追加）
        first_result = result

        async def _fetch_rest():
            rest = list(items)
            result_ = first_result
            pages = 1
            while pages < 8:
                next_url = result_.get("next_url") if isinstance(result_, dict) else None
                if not next_url:
                    break
                npath, nparams = _pixiv_parse_next_url(next_url)
                if not npath:
                    break
                try:
                    _pixiv_throttle()
                    result_ = await asyncio.to_thread(_pixiv_app_api, "GET", npath, nparams)
                except Exception:
                    break
                more = _pixiv_app_items(result_, list_key, kind_card)
                if not more:
                    break
                rest = rest + more
                pages += 1
                _merge_and_emit(rest, append=True)
            logging.info("Pixiv 关注更新 %s: 新 %d 条（%d 页）", content, len(rest), pages)

        asyncio.create_task(_fetch_rest())
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc),
              "feed_kind": f"follow_{content}"})
    except Exception as exc:
        emit({"event": "search_error", "message": f"Pixiv 关注更新失败: {exc}",
              "feed_kind": f"follow_{content}"})
        logging.exception("Pixiv follow feed 失败 content=%s", content)
    finally:
        emit({"event": "search_loading", "loading": False})


# 收藏游标分页缓存：App API 的收藏接口忽略 offset 参数（offset=30/60 仍返回第一页），
# 翻页必须跟随响应里的 next_url（内含 max_bookmark_id 游标，已实测有效且 0 重叠）。
# cache_key = uid|content|restrict → {页码: 该页响应的 next_url（""=已到末页）}
_pixiv_bm_cursors: dict[str, dict[int, str]] = {}


def _pixiv_parse_next_url(next_url: str) -> tuple[str, dict]:
    """next_url（绝对或相对均可）→ (path, params)，供 _pixiv_app_api 直接请求。"""
    parts = urllib.parse.urlsplit(next_url or "")
    return parts.path, dict(urllib.parse.parse_qsl(parts.query))


async def _pixiv_bm_walk(cursors: dict[int, str], path: str,
                         first_params: dict, page: int) -> dict | None:
    """游标翻页到第 page 页并返回该页响应（超出末页返回 None）。

    页 1 恒新取（收藏可能新增，清空旧游标）；页 N > 1 从最近缓存页顺序
    跟随 next_url 前进——App API 无 offset 语义，跳页只能顺序走。
    cursors[p] 记录第 p 页响应的 next_url。
    """
    if page <= 1 or not cursors:
        cursors.clear()
        result = await asyncio.to_thread(_pixiv_app_api, "GET", path, dict(first_params))
        cursors[1] = result.get("next_url") or ""
        if page <= 1:
            return result
    cur = max(p for p in cursors if p < page)
    result = None
    while cur < page:
        nu = cursors.get(cur) or ""
        if not nu:
            return None  # 游标耗尽 = 已到末页
        nu_path, nu_params = _pixiv_parse_next_url(nu)
        result = await asyncio.to_thread(_pixiv_app_api, "GET", nu_path, nu_params)
        cur += 1
        cursors[cur] = result.get("next_url") or ""
    return result if cur == page else None


async def pixiv_bookmarks(content: str = "illust", restrict: str = "public",
                          allow_r18: bool = True, page: int = 1, user_id: str = "") -> None:
    """我的收藏 / 他人收藏（插画/漫画/小说；公开/私密过滤 + 年龄限制开关）。"""
    content = content if content in ("illust", "manga", "novel") else "illust"
    restrict = "private" if restrict == "private" else "public"
    emit({"event": "search_loading", "loading": True})
    try:
        uid = user_id or (_pixiv_load_cred().get("user_id") or "")
        if not uid:
            emit({"event": "search_error", "message": "未登录：请先完成 Refresh Token 登录"})
            return
        page = max(1, page or 1)
        path = f"/v1/user/bookmarks/{content}"
        cursors = _pixiv_bm_cursors.setdefault(f"{uid}|{content}|{restrict}", {})
        result = await _pixiv_bm_walk(cursors, path,
                                      {"user_id": uid, "restrict": restrict}, page)
        list_key = "novels" if content == "novel" else "illusts"
        items = _pixiv_app_items(result or {}, list_key,
                                 "novel" if content == "novel" else "illust")
        # 翻页判定：has_more 看响应 next_url 是否还有下一页游标
        #（不能按条数算：R18 过滤后当页可能 <30；也不能用 offset——接口忽略它）
        next_url = (result or {}).get("next_url") or ""
        if not allow_r18:
            items = [c for c in items if not c.get("r18")]
        _apply_cached_thumbnails(items)
        label = PIXIV_FEED_LABELS.get(f"bookmark_{content}", "我的收藏")
        suffix = {"illust": "插画", "manga": "漫画", "novel": "小说"}[content]
        r_label = "私密" if restrict == "private" else "公开"
        emit({
            "event": "search_result", "query": label, "site": "pixiv",
            "items": items, "page": page,
            "total_pages": page + 1 if next_url else page,
            "total_results": 0, "has_more": bool(next_url),
            "feed_kind": f"bookmark_{content}",
            "label": f"{label} · {suffix} · {r_label}" + ("" if allow_r18 else " · 全年龄"),
            "search_type": "novel" if content == "novel" else "illust",
        })
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("Pixiv 收藏 %s/%s page=%d: %d 条", content, restrict, page, len(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"Pixiv 收藏加载失败: {exc}"})
        logging.exception("Pixiv bookmarks 失败 content=%s", content)
    finally:
        emit({"event": "search_loading", "loading": False})


async def pixiv_bookmark_tags(content: str = "illust") -> None:
    """书签：收藏标签列表（点击标签可搜索/查看该标签内容）。"""
    content = content if content in ("illust", "novel") else "illust"
    try:
        uid = _pixiv_load_cred().get("user_id") or ""
        if not uid:
            emit({"event": "pixiv_bookmark_tags_result", "ok": False,
                  "message": "未登录：请先完成 Refresh Token 登录"})
            return
        result = await asyncio.to_thread(_pixiv_app_api, "GET",
                                         f"/v1/user/bookmark-tags/{content}",
                                         {"user_id": uid, "restrict": "public"})
        tags = result.get("bookmark_tags") or []
        emit({"event": "pixiv_bookmark_tags_result", "ok": True, "content": content,
              "tags": [{"name": t.get("name") or "", "count": t.get("count") or 0} for t in tags]})
    except Exception as exc:
        emit({"event": "pixiv_bookmark_tags_result", "ok": False,
              "message": f"收藏标签加载失败: {exc}"})


async def pixiv_user_page(uid: str, page: int = 1, tab: str = "all") -> None:
    """用户主页：用户信息 + 插画/漫画/小说作品列表（可查看他人收藏与关注）。

    tab=all 首屏（三类型各第一页）；tab=illusts/manga/novels 时按页拉对应类型
    （App API offset 分页，30/页）——此前只拉一页 30 条，作者上千作品只能看 30。"""
    emit({"event": "pixiv_user_loading", "loading": True})
    try:
        page = max(1, page or 1)
        tab = tab if tab in ("illusts", "manga", "novels", "all") else "all"
        _type = {"illusts": "illust", "manga": "manga", "novels": "novel"}.get(tab)

        if tab != "all" and page > 1:
            # 翻页：只拉对应类型，不重复拉用户资料（前端追加到已有 userPage）
            offset = (page - 1) * PIXIV_APP_PER_PAGE
            path = "/v1/user/novels" if tab == "novels" else "/v1/user/illusts"
            params = {"user_id": uid, "offset": offset}
            if tab != "novels":
                params["type"] = _type
            result = await asyncio.to_thread(_pixiv_app_api, "GET", path, params)
            list_key = "novels" if tab == "novels" else "illusts"
            items = _pixiv_app_items(result, list_key, "novel" if tab == "novels" else "illust")
            _apply_cached_thumbnails(items)
            asyncio.create_task(_cache_thumbnails(items))
            emit({
                "event": "pixiv_user_result", "user_id": uid, "page": page, "tab": tab,
                "items": items, "has_more": len(items) >= PIXIV_APP_PER_PAGE,
            })
            return

        detail = await asyncio.to_thread(_pixiv_app_api, "GET", "/v1/user/detail", {"user_id": uid})
        user = detail.get("user") or {}
        profile = detail.get("profile") or {}
        # 三类作品各取第一页（前端按 tab 继续分页加载）
        offset = (page - 1) * PIXIV_APP_PER_PAGE
        tasks = {
            "illusts": asyncio.to_thread(_pixiv_app_api, "GET", "/v1/user/illusts",
                                         {"user_id": uid, "type": "illust", "offset": offset}),
            "manga": asyncio.to_thread(_pixiv_app_api, "GET", "/v1/user/illusts",
                                       {"user_id": uid, "type": "manga", "offset": offset}),
            "novels": asyncio.to_thread(_pixiv_app_api, "GET", "/v1/user/novels",
                                        {"user_id": uid, "offset": offset}),
        }
        results = {k: await v for k, v in tasks.items()}
        illusts = _pixiv_app_items(results["illusts"], "illusts", "illust")
        manga = _pixiv_app_items(results["manga"], "illusts", "illust")
        novels = _pixiv_app_items(results["novels"], "novels", "novel")
        all_items = illusts + manga + novels
        if all_items:
            _apply_cached_thumbnails(all_items)
            asyncio.create_task(_cache_thumbnails(all_items))
        totals = {
            "illusts": profile.get("total_illusts") or 0,
            "manga": profile.get("total_manga") or 0,
            "novels": profile.get("total_novels") or 0,
        }
        emit({
            "event": "pixiv_user_result", "user_id": uid, "page": 1, "tab": "all",
            "has_more": {
                "illusts": len(illusts) >= PIXIV_APP_PER_PAGE and offset + len(illusts) < (totals["illusts"] or 0),
                "manga": len(manga) >= PIXIV_APP_PER_PAGE and offset + len(manga) < (totals["manga"] or 0),
                "novels": len(novels) >= PIXIV_APP_PER_PAGE and offset + len(novels) < (totals["novels"] or 0),
            },
            "user": {
                "user_id": str(user.get("id") or uid),
                "name": user.get("name") or "",
                "account": user.get("account") or "",
                "avatar": (user.get("profile_image_urls") or {}).get("medium") or "",
                "comment": user.get("comment") or "",
                "is_followed": bool(user.get("is_followed")),
            },
            "profile": {
                "total_illusts": totals["illusts"],
                "total_manga": totals["manga"],
                "total_novels": totals["novels"],
                "total_following": profile.get("total_following") or 0,
                "total_follower": profile.get("total_follower") or 0,
                "total_illust_bookmarks": profile.get("total_illust_bookmarks") or 0,
                "total_novel_bookmarks": profile.get("total_novel_bookmarks") or 0,
            },
            "illusts": illusts, "manga": manga, "novels": novels,
        })
        logging.info("Pixiv 用户页 %s: 插画 %d / 漫画 %d / 小说 %d",
                     uid, len(illusts), len(manga), len(novels))
    except PermissionError as exc:
        emit({"event": "pixiv_user_result", "error": str(exc)})
    except Exception as exc:
        emit({"event": "pixiv_user_result", "error": f"用户信息加载失败: {exc}"})
        logging.exception("Pixiv 用户页失败 uid=%s", uid)
    finally:
        emit({"event": "pixiv_user_loading", "loading": False})


async def pixiv_user_list(mode: str = "following", uid: str = "", page: int = 1) -> None:
    """关注列表 / 粉丝列表（自己或他人）。"""
    mode = "followers" if mode == "followers" else "following"
    emit({"event": "search_loading", "loading": True})
    try:
        target = uid or (_pixiv_load_cred().get("user_id") or "")
        if not target:
            emit({"event": "search_error", "message": "未登录：请先完成 Refresh Token 登录"})
            return
        page = max(1, page or 1)
        offset = (page - 1) * PIXIV_APP_PER_PAGE
        path = "/v1/follower/list" if mode == "followers" else "/v1/user/following"
        web_mode = "followers" if mode == "followers" else "following"
        web_fallback = False
        try:
            result = await asyncio.to_thread(_pixiv_app_api, "GET", path, {
                "user_id": target, "offset": offset,
            })
            raw = result.get("user_previews") or []
        except PermissionError:
            # App API 端点弃用/受限 → web ajax（关注/粉丝通用）
            web_fallback = True
            wb = await asyncio.to_thread(
                _pixiv_api_get, f"/ajax/user/{target}/{web_mode}",
                {"offset": offset, "limit": PIXIV_APP_PER_PAGE, "lang": "zh"})
            raw = wb.get("users") if isinstance(wb, dict) else []
            if isinstance(raw, dict):
                raw = list(raw.values())
        items = []
        for d in raw:
            if not isinstance(d, dict):
                continue
            if web_fallback:
                # web ajax 条目（userId/userName/image 形状）→ 专用卡片
                items.append(_pixiv_web_user_card(d, target))
                continue
            # app user_preview（内含 user 子对象）→ _pixiv_app_card 自行解包。
            # 此前误传已解包的 user 对象导致内部二次 d.get("user") 全空
            #（卡片 user_id/名称/头像全空 → 前端点击无法进入用户主页）
            card = _pixiv_app_card(d, "user")
            # 带上最近 3 幅作品缩略图（卡片展示）
            thumbs = [((w.get("image_urls") or {}).get("medium") or "")
                      for w in (d.get("illusts") or [])[:3]]
            card["recent_thumbs"] = [t for t in thumbs if t]
            items.append(card)
        _apply_cached_thumbnails(items)
        label = "粉丝列表" if mode == "followers" else "关注列表"
        emit({
            "event": "search_result", "query": label, "site": "pixiv",
            "items": items, "page": page,
            "total_pages": page + 1 if len(items) >= PIXIV_APP_PER_PAGE else page,
            "total_results": 0, "has_more": len(items) >= PIXIV_APP_PER_PAGE,
            "feed_kind": f"userlist_{mode}", "label": label, "search_type": "user",
        })
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("Pixiv %s %s page=%d: %d 人", mode, target, page, len(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"列表加载失败: {exc}"})
        logging.exception("Pixiv user list 失败 mode=%s", mode)
    finally:
        emit({"event": "search_loading", "loading": False})


async def pixiv_detail(kind: str, item_id: str) -> None:
    """作品详情：插画/小说（含小说正文、评论区、统计、收藏状态）。"""
    emit({"event": "pixiv_detail_loading", "loading": True})
    try:
        kind = "novel" if kind == "novel" else "illust"
        if kind == "novel":
            # /v1/novel/detail 已弃用 404（用户实测"点开小说内容消失"）→ 直接走 web
            d = await asyncio.to_thread(_pixiv_api_get, f"/ajax/novel/{item_id}")
            detail = _pixiv_web_novel_to_app(d, item_id)
            detail["novel_text"] = _pixiv_novel_html_to_text(d.get("content") or "")
            # 正文插图解析较慢（每个 [pixivimage] 引用要再请求插画页，最多 12 次）——
            # 内联解析会阻塞命令循环十几秒（期间全部界面点击排队）。改为详情先发
            # （插图空表占位），异步补齐后经 pixiv_novel_images 事件合并（2026-09-13）
            detail["embedded_images"] = {}
            try:
                comments_result = await asyncio.to_thread(
                    _pixiv_app_api, "GET", "/v3/novel/comments",
                    {"novel_id": item_id, "include_total_comments": "true"})
            except Exception:
                comments_result = {}
            card = _pixiv_app_card(detail, "novel")
        else:
            detail = (await asyncio.to_thread(
                _pixiv_app_api, "GET", "/v1/illust/detail", {"illust_id": item_id})).get("illust") or {}
            comments_result = await asyncio.to_thread(
                _pixiv_app_api, "GET", "/v3/illust/comments",
                {"illust_id": item_id, "include_total_comments": "true"})
            card = _pixiv_app_card(detail, "illust")
            # 多页原图（详情页直接展示 + 下载用）
            if int(detail.get("page_count") or 1) > 1 or detail.get("type") == "manga":
                try:
                    pages = (await asyncio.to_thread(
                        _pixiv_app_api, "GET", "/v1/illust/pages",
                        {"illust_id": item_id})).get("pages") or []
                    detail["page_urls"] = [
                        ((p.get("image_urls") or {}).get("large")
                         or (p.get("image_urls") or {}).get("medium") or "")
                        for p in pages]
                    detail["page_originals"] = [
                        ((p.get("image_urls") or {}).get("original") or "") for p in pages]
                except Exception:
                    # App API /v1/illust/pages 对部分作品已 404（端点弃用）——此前详情
                    # 图片区整个为空（"打开后图片没有加载"）。回退 web ajax pages
                    # （登录态 cookie 可看 R-18；regular 经媒体代理加载，original 下载用）
                    try:
                        wb = await asyncio.to_thread(_pixiv_api_get, f"/ajax/illust/{item_id}/pages")
                        plist = wb if isinstance(wb, list) else (wb.get("pages") if isinstance(wb, dict) else []) or []
                        detail["page_urls"] = [
                            ((p.get("urls") or {}).get("regular")
                             or (p.get("urls") or {}).get("large")
                             or (p.get("urls") or {}).get("original") or "")
                            for p in plist]
                        detail["page_originals"] = [
                            ((p.get("urls") or {}).get("original") or "") for p in plist]
                    except Exception:
                        detail["page_urls"] = []
            else:
                detail["page_urls"] = [(detail.get("image_urls") or {}).get("large") or ""]
                detail["page_originals"] = [(detail.get("meta_single_page") or {}).get("original_image_url") or ""]
            # 动图
            if detail.get("type") == "ugoira":
                try:
                    ugoira = await asyncio.to_thread(
                        _pixiv_app_api, "GET", "/v1/ugoira/metadata", {"illust_id": item_id})
                    detail["ugoira_zip"] = (ugoira.get("ugoira_metadata") or {}).get("zip_urls", {}).get("medium") or ""
                except Exception:
                    detail["ugoira_zip"] = ""

        comments = []
        for c in (comments_result.get("comments") or []):
            user = c.get("user") or {}
            parent = c.get("parent_comment") or {}
            comments.append({
                "id": str(c.get("id") or ""),
                "comment": c.get("comment") or "",
                "date": (c.get("date") or "")[:16].replace("T", " "),
                "user_id": str(user.get("id") or ""),
                "user_name": user.get("name") or "",
                "user_avatar": (user.get("profile_image_urls") or {}).get("medium") or "",
                "parent_user": (parent.get("user") or {}).get("name") or "",
                "has_replies": bool(c.get("total_replies")),
            })
        card_all = [card] + ([{"thumbnail": detail.get("novel_text", "")[:0] or card["thumbnail"]}] if kind == "novel" else [])
        _apply_cached_thumbnails(card_all)
        asyncio.create_task(_cache_thumbnails(card_all))
        emit({
            "event": "pixiv_detail_result", "kind": kind, "item_id": str(item_id),
            "detail": card, "raw": detail, "comments": comments,
            "total_comments": comments_result.get("total_comments") or len(comments),
        })
        logging.info("Pixiv 详情 %s %s: %d 评论", kind, item_id, len(comments))

        # 小说正文插图后台补齐（详情已先发，插图到位后经事件合并，不再阻塞命令循环）
        if kind == "novel" and isinstance(d, dict) and d:
            async def _fill_novel_images(nd: dict):
                try:
                    imgs = await _pixiv_novel_embedded_images(nd)
                    if imgs:
                        emit({"event": "pixiv_novel_images", "item_id": str(item_id),
                              "embedded_images": imgs})
                except Exception:
                    pass
            asyncio.create_task(_fill_novel_images(d))

        # 作者的其他作品：后台补齐（不阻塞详情下发——串行多拉一个请求会让详情
        # 慢 1-2 秒，期间前端详情视图是空白）
        aid = str((detail.get("user") or {}).get("id") or "")
        if aid and kind == "illust":
            async def _fill_author_works():
                try:
                    aw = await asyncio.to_thread(
                        _pixiv_app_api, "GET", "/v1/user/illusts",
                        {"user_id": aid, "type": "illust"})
                    works = [w for w in _pixiv_app_items(aw, "illusts", "illust")
                             if str(w.get("illust_id")) != str(item_id)][:12]
                    _apply_cached_thumbnails(works)
                    asyncio.create_task(_cache_thumbnails(works))
                    emit({"event": "pixiv_author_works", "item_id": str(item_id),
                          "works": works})
                except Exception:
                    pass
            asyncio.create_task(_fill_author_works())
    except PermissionError as exc:
        emit({"event": "pixiv_detail_result", "kind": kind, "item_id": str(item_id), "error": str(exc)})
    except Exception as exc:
        emit({"event": "pixiv_detail_result", "kind": kind, "item_id": str(item_id),
              "error": f"详情加载失败: {exc}"})
        logging.exception("Pixiv 详情失败 %s %s", kind, item_id)
    finally:
        emit({"event": "pixiv_detail_loading", "loading": False})


async def pixiv_user_download_all(uid: str, kind: str = "illustmanga", fmt: str = "txt") -> None:
    """下载指定用户的全部作品（占位式任务 + 并发解析）。

    kind: illustmanga（插画+漫画，原图 zip 级）| novel（小说，fmt=txt/doc）。
    doc 格式：封面 + 正文（保留插图位置）HTML 封装，Word/WPS 可直接打开。"""
    uid = str(uid or "").strip()
    if not uid:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "缺少用户 ID"})
        return
    task_album_id = f"pixiv_user_all:{uid}:{kind}:{int(time.time() * 1000)}"
    label = "Pixiv 全部插画/漫画" if kind == "illustmanga" else "Pixiv 全部小说"
    task_id = download_manager.submit(  # noqa: F821
        f"{PIXIV_BASE}/users/{uid}", [], {}, label, task_album_id,
    )

    def _prog(done, total, msg):
        emit({"event": "pixiv_batch_progress", "done": done, "total": total, "message": msg})

    # 收集全部作品 ID（App API 分页；30/页）
    collected: list[dict] = []
    failed: list[str] = []
    if kind == "novel":
        offset = 0
        while True:
            _prog(len(collected), 0, "正在获取小说列表...")
            result = await asyncio.to_thread(
                _pixiv_app_api, "GET", "/v1/user/novels", {"user_id": uid, "offset": offset})
            raw = result.get("novels") or []
            for n in raw:
                collected.append({
                    "kind": "novel", "novel_id": str(n.get("id") or ""),
                    "title": n.get("title") or "",
                    "author": (n.get("user") or {}).get("name") or "",
                    "cover": (n.get("image_urls") or {}).get("medium") or "",
                })
            if len(raw) < PIXIV_APP_PER_PAGE:
                break
            offset += PIXIV_APP_PER_PAGE
    else:
        for t in ("illust", "manga"):
            offset = 0
            while True:
                _prog(len(collected), 0, f"正在获取{'漫画' if t == 'manga' else '插画'}列表...")
                result = await asyncio.to_thread(
                    _pixiv_app_api, "GET", "/v1/user/illusts",
                    {"user_id": uid, "type": t, "offset": offset})
                raw = result.get("illusts") or []
                for w in raw:
                    collected.append({
                        "kind": "illust", "illust_id": str(w.get("id") or ""),
                        "title": w.get("title") or "",
                        "author": ((w.get("user") or {}).get("name")) or "",
                        "cover": ((w.get("image_urls") or {}).get("medium")) or "",
                    })
                if len(raw) < PIXIV_APP_PER_PAGE:
                    break
                offset += PIXIV_APP_PER_PAGE
    total = len(collected)
    if not total:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "该用户没有可下载的作品（或列表未公开）"})
        return

    done = 0
    sem = asyncio.Semaphore(3)

    async def _dl_one(idx: int, it: dict):
        nonlocal done
        async with sem:
            try:
                if it["kind"] == "novel":
                    entry = {
                        "filename": f"{sanitize_directory_name(it['title']) or it['novel_id']}.txt",
                        "size": None, "status": "ok", "media_url": "",
                        "item_page": f"{PIXIV_BASE}/novel/show.php?id={it['novel_id']}",
                        "site": "pixiv", "kind": "novel", "novel_id": it["novel_id"],
                        "post_title": it["title"], "post_date": "",
                        "artist": it["author"] or "pixiv",
                        "media_type": "novel",
                        "pixiv_novel_fmt": fmt,
                    }
                else:
                    entry = {
                        "filename": f"{sanitize_directory_name(it['title']) or it['illust_id']}.zip",
                        "size": None, "status": "ok", "media_url": "",
                        "item_page": f"{PIXIV_BASE}/artworks/{it['illust_id']}",
                        "site": "pixiv", "kind": "illust", "illust_id": it["illust_id"],
                        "post_title": it["title"], "post_date": "",
                        "artist": it["author"] or "pixiv",
                        "media_type": "illust",
                    }
                download_manager.submit(  # noqa: F821
                    f"{PIXIV_BASE}/users/{uid}", [entry], {}, label, task_album_id,
                )
                done += 1
            except Exception as exc:
                failed.append(f"{it}（{exc}）")
            _prog(min(idx, total), total, f"解析进度 {idx}/{total}")

    # 分批并发 3
    for i in range(0, total, 3):
        await asyncio.gather(*(_dl_one(j + 1, it) for j, it in
                               enumerate(collected[i:i + 3], start=i)))
    if done:
        download_manager.start(task_id)  # noqa: F821
    summary = f"下载全部{'小说' if kind == 'novel' else '插画/漫画'}已提交：{done}/{total}"
    if failed:
        summary += f"；失败：{'、'.join(failed[:4])}{'…' if len(failed) > 4 else ''}"
    emit({"event": "pixiv_batch_done", "done": done, "total": total,
          "failed": failed, "message": summary})


async def pixiv_batch_download(items: list, novel_fmt: str = "txt") -> None:
    """通用批量模块（卡片勾选）：勾选的作品逐个加入下载任务。

    条目为"用户主页式"（media_url 空 + illust_id/novel_id）——下载器
    _pixiv_download_one 下载时现场解析原图/小说正文。占位式：先建空任务，
    每个作品轻量详情（web ajax）补标题/作者后立即并入。
    novel_fmt：勾选含小说时的保存格式（txt|docx，前端弹窗选择后透传）。"""
    novel_fmt = "docx" if str(novel_fmt or "").lower() in ("docx", "doc", "word") else "txt"
    items = [it for it in (items or []) if isinstance(it, dict) and (it.get("illust_id") or it.get("novel_id"))]
    if not items:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0,
              "failed": [], "message": "请先勾选要下载的作品"})
        return
    total = len(items)
    task_album_id = f"pixiv_batch:{int(time.time() * 1000)}"
    task_id = download_manager.submit(  # noqa: F821
        f"{PIXIV_BASE}/", [], {}, "Pixiv 批量下载", task_album_id,
    )
    done = 0
    failed: list[str] = []
    for i, it in enumerate(items, 1):
        iid = str(it.get("illust_id") or it.get("novel_id") or "")
        kind = str(it.get("kind") or ("novel" if it.get("novel_id") else "illust"))
        try:
            if kind == "novel":
                d = await asyncio.to_thread(_pixiv_api_get, f"/ajax/novel/{iid}")
                title = d.get("title") or f"novel_{iid}"
                author = d.get("userName") or ""
            else:
                d = await asyncio.to_thread(_pixiv_api_get, f"/ajax/illust/{iid}")
                title = d.get("illustTitle") or f"illust_{iid}"
                author = d.get("userName") or ""
            entry = {
                "filename": f"{sanitize_directory_name(title) or iid}.zip" if kind == "illust" else f"{sanitize_directory_name(title) or iid}.txt",
                "size": None,
                "item_page": f"{PIXIV_BASE}/{('novel/show.php?id=' + iid) if kind == 'novel' else ('artworks/' + iid)}",
                "status": "ok",
                "thumbnail": d.get("coverUrl") or d.get("url") or "",
                "media_url": "",
                "site": "pixiv",
                "illust_id": iid if kind == "illust" else "",
                "novel_id": iid if kind == "novel" else "",
                "kind": kind,
                "post_title": title,
                "post_date": (d.get("createDate") or d.get("updateDate") or "")[:10],
                "artist": author or "pixiv",
                "media_type": "novel" if kind == "novel" else "illust",
                "pixiv_novel_fmt": novel_fmt,
            }
            download_manager.submit(  # noqa: F821
                f"{PIXIV_BASE}/", [entry], {}, "Pixiv 批量下载", task_album_id,
            )
            done += 1
        except Exception as exc:
            failed.append(f"{iid}（{exc}）")
            logging.warning("Pixiv 批量解析失败 %s: %s", iid, exc)
        emit({"event": "pixiv_batch_progress", "done": i, "total": total,
              "message": f"解析进度 {i}/{total}"})
    if done:
        download_manager.start(task_id)  # noqa: F821
    summary = f"批量下载已提交：{done} / {total} 个作品"
    if failed:
        summary += f"；失败：{'、'.join(failed[:6])}"
    emit({"event": "pixiv_batch_done", "done": done, "total": total,
          "failed": failed, "message": summary})


async def pixiv_series_download(series_id: str, kind: str = "novel",
                                novel_fmt: str = "txt",
                                options: dict = None) -> None:
    """下载全部系列（连载：书名目录 + 每话章节文件，下载管理目录一一对应）。

    kind=novel: /ajax/novel/series_content/{id}?limit=30&last_order=N → page.seriesContents
                [{id, title, order}]（2026-09-13 实测；last_order 递增直到取满 total）；
    kind=illust: /ajax/illust/series/{id}?limit=30&last_order=N → illusts [{id, title, ...}]
                 （漫画系列章节）。
    任务目录 = 系列书名（album_name），每话章节文件直接落在里面；
    小说章节格式随 novel_fmt（txt|docx）。
    """
    kind = "illust" if kind == "illust" else "novel"
    series_id = str(series_id or "").strip()
    fmt = "docx" if str(novel_fmt or "").lower() in ("docx", "doc", "word") else "txt"
    options = options or {}
    if not series_id:
        emit({"event": "inspect_error", "message": "缺少系列 ID"})
        return
    emit({"event": "pixiv_batch_progress", "done": 0, "total": 0, "message": "正在获取系列章节..."})
    try:
        chapters: list[dict] = []
        s_title = ""
        last_order = 0
        while len(chapters) < 200:
            if kind == "novel":
                d = await asyncio.to_thread(
                    _pixiv_api_get, f"/ajax/novel/series_content/{series_id}",
                    {"limit": 30, "last_order": last_order, "order_by": "asc"})
                batch = ((d.get("page") or {}).get("seriesContents")) or []
            else:
                d = await asyncio.to_thread(
                    _pixiv_api_get, f"/ajax/illust/series/{series_id}",
                    {"limit": 30, "last_order": last_order})
                batch = d.get("illusts") or []
            s_title = s_title or str(d.get("title") or "")
            if not batch:
                break
            chapters.extend(batch)
            if len(batch) < 30:
                break
            last_order += 30
            _pixiv_throttle()
        if not chapters:
            emit({"event": "inspect_error", "message": "该系列没有可下载的章节"})
            return
        if not s_title:
            # series_content 响应不含书名（2026-09-13 实测）→ 补拉系列元信息
            try:
                _pixiv_throttle()
                if kind == "novel":
                    meta = await asyncio.to_thread(
                        _pixiv_api_get, f"/ajax/novel/series/{series_id}", {"limit": 1})
                else:
                    meta = await asyncio.to_thread(
                        _pixiv_api_get, f"/ajax/illust/series/{series_id}", {"limit": 1})
                s_title = str(meta.get("title") or "")
            except Exception:
                s_title = ""
        s_title = s_title or f"pixiv系列_{series_id}"

        items = []
        for ch in chapters:
            cid = str(ch.get("id") or "")
            if not cid:
                continue
            ctitle = str(ch.get("title") or f"第{ch.get('order') or len(items) + 1}话")
            if kind == "novel":
                items.append({
                    "filename": f"{sanitize_directory_name(ctitle) or cid}.txt",
                    "size": None, "status": "ok", "media_url": "",
                    "item_page": f"{PIXIV_BASE}/novel/show.php?id={cid}",
                    "thumbnail": "", "site": "pixiv", "kind": "novel",
                    "novel_id": cid, "illust_id": "",
                    "post_title": ctitle, "artist": ch.get("userName") or "",
                    "subfolder": "", "pixiv_novel_fmt": fmt,
                    "media_type": "novel",
                })
            else:
                items.append({
                    "filename": "",  # 下载时按页生成（章节名_pN.扩展名）
                    "size": None, "status": "ok", "media_url": "",
                    "item_page": f"{PIXIV_BASE}/artworks/{cid}",
                    "thumbnail": ch.get("url") or "", "site": "pixiv",
                    "kind": "illust", "illust_id": cid, "novel_id": "",
                    "post_title": ctitle, "artist": ch.get("userName") or "",
                    "subfolder": "", "media_type": "illust",
                })
        task_album_id = f"pixiv_series:{series_id}"
        task_id = download_manager.submit(  # noqa: F821
            f"{PIXIV_BASE}/", items, options, s_title, task_album_id,
        )
        download_manager.start(task_id)  # noqa: F821
        emit({"event": "log", "type": "下载",
              "message": f"系列《{s_title}》已提交下载：{len(items)} 话（书名目录 + 每话章节）"})
        logging.info("Pixiv 系列 %s(%s) %s: %d 话", s_title, series_id, kind, len(items))
    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"系列解析失败: {exc}"})
        logging.exception("Pixiv 系列下载失败 %s", series_id)


async def pixiv_related(kind: str, item_id: str) -> None:
    """相关作品（详情页点击「相关作品」按钮后才加载）。"""
    try:
        path = "/v1/novel/related" if kind == "novel" else "/v1/illust/related"
        key_param = "novel_id" if kind == "novel" else "illust_id"
        result = await asyncio.to_thread(_pixiv_app_api, "GET", path, {key_param: item_id})
        list_key = "novels" if kind == "novel" else "illusts"
        items = _pixiv_app_items(result, list_key, "novel" if kind == "novel" else "illust")
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "pixiv_related_result", "kind": kind, "item_id": str(item_id),
              "items": items})
    except Exception as exc:
        # App API /v1/illust/related、/v1/novel/related 已对部分作品 404（端点弃用）——
        # 回退 web：详情 ajax 取首个标签 → 同标签最新作品作相关推荐
        items: list = []
        try:
            detail_path = f"/ajax/novel/{item_id}" if kind == "novel" else f"/ajax/illust/{item_id}"
            d = await asyncio.to_thread(_pixiv_api_get, detail_path)
            # _pixiv_api_get 已剥掉 body 包装；tags 结构 {'authorId',..., 'tags': [{tag}]}
            raw_tags = d.get("tags") if isinstance(d, dict) else None
            if isinstance(raw_tags, dict):
                raw_tags = raw_tags.get("tags") or []
            tags = [t.get("tag") for t in (raw_tags or [])
                    if isinstance(t, dict) and t.get("tag")]
            tag = tags[0] if tags else ""
            if tag:
                encoded = urllib.parse.quote(tag, safe="")
                if kind == "novel":
                    body = await asyncio.to_thread(
                        _pixiv_api_get, f"/ajax/search/novels/{encoded}",
                        {"word": tag, "order": "date_d", "p": 1})
                    data = (body.get("novels") or {}).get("data") or []
                    items = [{
                        "kind": "novel", "site": "pixiv",
                        "novel_id": str(dn.get("id") or ""),
                        "album_name": dn.get("title") or "未命名",
                        "album_url": f"{PIXIV_BASE}/novel/show.php?id={dn.get('id')}",
                        "thumbnail": dn.get("url") or "",
                        "author": dn.get("userName") or "",
                        "author_url": f"{PIXIV_BASE}/users/{dn.get('userId')}",
                        "posted": (dn.get("updateDate") or "")[:10],
                        "views": dn.get("viewCount") or "",
                    } for dn in data if dn.get("id")]
                else:
                    body = await asyncio.to_thread(
                        _pixiv_api_get, f"/ajax/search/artworks/{encoded}",
                        {"word": tag, "order": "date_d", "p": 1,
                         "type": "all", "s_mode": "s_tag_full", "lang": "zh"})
                    data = (body.get("illustManga") or {}).get("data") or []
                    items = [c for c in (_pixiv_parse_card(dn) for dn in data) if c]
                    for c in items:
                        c.setdefault("kind", "illust")
        except Exception:
            pass
        # 剔除作品本身
        key = "novel_id" if kind == "novel" else "illust_id"
        items = [c for c in items if str(c.get(key) or c.get("item_id") or "") != str(item_id)]
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "pixiv_related_result", "kind": kind, "item_id": str(item_id),
              "items": items,
              **({} if items else {"error": f"相关作品加载失败: {exc}"})})


async def pixiv_action(action: str, kind: str, item_id: str, **kw) -> None:
    """互动：点赞 / 收藏 / 取消收藏 / 关注 / 取关 / 发表评论 / 回复 / 删除评论。"""
    kind = "novel" if kind == "novel" else "illust"
    key_param = "novel_id" if kind == "novel" else "illust_id"
    try:
        if action == "like":
            result = await asyncio.to_thread(
                _pixiv_app_api, "POST", f"/v2/{kind}/like", {key_param: item_id})
            seen = (result.get("liked_count") if isinstance(result, dict) else None)
            msg = f"已点赞（like 数 {seen}）" if seen is not None else "已点赞"
        elif action in ("bookmark_add", "bookmark_delete"):
            op = "add" if action == "bookmark_add" else "delete"
            restrict = "private" if kw.get("restrict") == "private" else "public"
            params = {key_param: item_id}
            if op == "add":
                params["restrict"] = restrict
            await asyncio.to_thread(
                _pixiv_app_api, "POST", f"/v2/{kind}/bookmark/{op}", params)
            msg = "已收藏" if op == "add" else "已取消收藏"
        elif action in ("follow", "unfollow"):
            op = "add" if action == "follow" else "delete"
            params = {"user_id": item_id}
            if op == "add":
                params["restrict"] = "private" if kw.get("restrict") == "private" else "public"
            await asyncio.to_thread(_pixiv_app_api, "POST", f"/v1/user/follow/{op}", params)
            msg = "已关注" if op == "add" else "已取消关注"
        elif action == "comment_add":
            text = (kw.get("text") or "").strip()
            if not text:
                raise PermissionError("评论内容为空")
            parent = (kw.get("parent_id") or "").strip()
            # 发评论：先试 add，再试 reply（回复带 parent_comment_id）
            try:
                await asyncio.to_thread(
                    _pixiv_app_api, "POST", f"/v1/{kind}/comment/add",
                    {key_param: item_id, "comment": text,
                     **({"parent_comment_id": parent} if parent else {})})
            except PermissionError as exc:
                if "404" not in str(exc):
                    raise
                await asyncio.to_thread(
                    _pixiv_app_api, "POST", f"/v1/{kind}/comment/reply",
                    {key_param: item_id, "comment": text,
                     **({"parent_comment_id": parent} if parent else {})})
            msg = "评论已发表"
        elif action == "comment_delete":
            comment_id = (kw.get("comment_id") or "").strip()
            if not comment_id:
                raise PermissionError("评论 id 为空")
            try:
                await asyncio.to_thread(
                    _pixiv_app_api, "POST", f"/v1/{kind}/comment/delete",
                    {"comment_id": comment_id})
            except PermissionError as exc:
                if "404" not in str(exc):
                    raise
                await asyncio.to_thread(
                    _pixiv_app_api, "POST", "/v1/comment/delete", {"comment_id": comment_id})
            msg = "评论已删除"
        else:
            raise PermissionError(f"未知操作: {action}")
        emit({"event": "pixiv_action_result", "action": action, "kind": kind,
              "item_id": str(item_id), "ok": True, "message": msg})
        logging.info("Pixiv 互动 %s %s %s", action, kind, item_id)
    except PermissionError as exc:
        emit({"event": "pixiv_action_result", "action": action, "kind": kind,
              "item_id": str(item_id), "ok": False, "message": str(exc)})
    except Exception as exc:
        emit({"event": "pixiv_action_result", "action": action, "kind": kind,
              "item_id": str(item_id), "ok": False, "message": f"操作失败: {exc}"})
        logging.exception("Pixiv 互动失败 %s %s %s", action, kind, item_id)


def _pixiv_record_tag_click(tag: str) -> None:
    """记录常用标签点击（cache/pixiv_my_tags.json，频次排序）。"""
    tag = (tag or "").strip()
    if not tag:
        return
    path = _pixiv_my_tags_path()
    data: dict = {}
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data[tag] = int(data.get(tag) or 0) + 1
    try:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


async def pixiv_tags() -> None:
    """常用标签（账号本地统计）+ 热门标签（trending tags）置顶展示。"""
    try:
        my_tags: list[dict] = []
        try:
            data = json.loads(_pixiv_my_tags_path().read_text(encoding="utf-8"))
            my_tags = [{"name": k, "count": v} for k, v in
                       sorted(data.items(), key=lambda x: -x[1])[:20]]
        except Exception:
            pass
        trending: list[dict] = []
        if _pixiv_has_token():
            try:
                result = await asyncio.to_thread(
                    _pixiv_app_api, "GET", "/v1/trending-tags/illust", {})
                trending = [{"name": t.get("tag") or t.get("name") or "",
                             "translated": (t.get("translated_name") or "")
                             or ((t.get("translated_tag") or {}).get("zh") if isinstance(t.get("translated_tag"), dict) else "")}
                            for t in (result.get("trend_tags") or [])][:30]
            except Exception:
                trending = []
        emit({"event": "pixiv_tags_result", "my_tags": my_tags,
              "trending": [t for t in trending if t["name"]]})
    except Exception as exc:
        emit({"event": "pixiv_tags_result", "my_tags": [], "trending": [],
              "error": str(exc)})


async def pixiv_notification() -> None:
    """提醒（通知）：优先 Web ajax（需 cookie 通道），失败提示走 App API 受限。"""
    try:
        if not _pixiv_has_token():
            emit({"event": "pixiv_notification_result", "ok": False,
                  "message": "未登录：请先完成 Refresh Token 登录"})
            return
        cred = _pixiv_load_cred()
        if not (cred.get("cookies") or {}).get("PHPSESSID"):
            emit({"event": "pixiv_notification_result", "ok": False,
                  "message": "缺少 Web 会话（重新登录一次即可带上，通知功能需 Web cookie）"})
            return
        body = await asyncio.to_thread(_pixiv_api_get, "/ajax/notification", {})
        items = []
        for n in (body.get("items") or [])[:60]:
            items.append({
                "id": str(n.get("id") or ""),
                "type": n.get("type") or "",
                "content": (n.get("content") or "")[:80],
                "user_name": ((n.get("user") or {}).get("name") or ""),
                "user_avatar": ((n.get("user") or {}).get("image") or ""),
                "created": (n.get("created_at") or "")[:16].replace("T", " "),
                "link": n.get("link") or "",
            })
        emit({"event": "pixiv_notification_result", "ok": True, "items": items,
              "unread": body.get("unread") or 0})
    except Exception as exc:
        emit({"event": "pixiv_notification_result", "ok": False,
              "message": f"通知加载失败: {exc}"})


async def pixiv_upload(paths: list[str], title: str, caption: str,
                       tags: list[str], x_restrict: int = 0) -> None:
    """发布作品：POST /v1/upload/illust（multipart：标题/说明/tags/年龄限制 + 图片）。

    App API 上传接口为逆向所得：失败时返回具体报错，便于后续调整格式。
    """
    try:
        if not _pixiv_has_token():
            emit({"event": "pixiv_upload_result", "ok": False,
                  "message": "未登录：请先完成 Refresh Token 登录"})
            return
        files_path = [p for p in (paths or []) if p and Path(p).exists()]
        if not files_path:
            emit({"event": "pixiv_upload_result", "ok": False, "message": "请选择要上传的图片文件"})
            return
        title = (title or "").strip()
        if not title:
            emit({"event": "pixiv_upload_result", "ok": False, "message": "请填写作品标题"})
            return
        tag_list = [t.strip() for t in (tags or []) if t.strip()]
        if not tag_list:
            emit({"event": "pixiv_upload_result", "ok": False, "message": "至少填写一个标签（Pixiv 必填）"})
            return
        if not _pixiv_token_ready():
            raise PermissionError("登录已失效，请重新登录")

        def _do_upload() -> dict:
            client_time = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            client_hash = hashlib.md5((client_time + PIXIV_HASH_SECRET).encode()).hexdigest()
            headers = {
                "Authorization": f"Bearer {_pixiv_access_token}",
                "User-Agent": PIXIV_APP_UA,
                "App-OS": "android", "App-Version": "5.0.234",
                "X-Client-Time": client_time,
                "X-Client-Hash": client_hash,
            }
            form = {
                "title": title, "caption": caption or "",
                "x_restrict": str(int(x_restrict or 0)),
                "restrict": "public",
                "tags": json.dumps([{"name": t} for t in tag_list], ensure_ascii=False),
            }
            multipart = []
            for i, p in enumerate(files_path):
                fh = open(p, "rb")
                multipart.append(("data" if i == 0 else "data_extra", (
                    Path(p).name, fh, "application/octet-stream")))
            _pixiv_throttle()
            resp = _pixiv_session.post(
                f"{PIXIV_APP_BASE}/v1/upload/illust", params={"filter": "for_ios"},
                data=form, files=multipart, headers=headers, timeout=180)
            for _, (_, fh, _) in multipart:
                try:
                    fh.close()
                except Exception:
                    pass
            try:
                return {"status": resp.status_code, "body": resp.json() if resp.text else {}}
            except ValueError:
                return {"status": resp.status_code, "body": {"raw": resp.text[:200]}}

        result = await asyncio.to_thread(_do_upload)
        if result["status"] == 200:
            iid = ((result["body"].get("illust") or {}).get("id")) or ""
            emit({"event": "pixiv_upload_result", "ok": True,
                  "message": f"作品发布成功！" + (f"（作品ID {iid}）" if iid else "")})
            logging.info("Pixiv 上传成功: %s", iid)
        else:
            err = result["body"]
            msg = (err.get("error") or {}).get("message") if isinstance(err.get("error"), dict) else (
                err.get("message") or err.get("raw") or "")
            emit({"event": "pixiv_upload_result", "ok": False,
                  "message": f"发布失败（HTTP {result['status']}）: {str(msg)[:200]}"})
            logging.warning("Pixiv 上传失败: %s", result["body"])
    except PermissionError as exc:
        emit({"event": "pixiv_upload_result", "ok": False, "message": str(exc)})
    except Exception as exc:
        emit({"event": "pixiv_upload_result", "ok": False, "message": f"发布失败: {exc}"})
        logging.exception("Pixiv 上传异常")


async def pixiv_novel_items(novel_id: str, title: str = "", author: str = "",
                            fmt: str = "txt") -> None:
    """单个小说 → 下载条目，走现有文件列表/下载管线。

    fmt: txt（txt 全文 + 封面文件）| docx（单个 Word 文档：封面+正文插图按原位嵌入，
    不再单发封面条目）。/v1/novel/detail 已弃用 404 → web ajax。"""
    fmt = "docx" if str(fmt or "").lower() in ("docx", "doc", "word") else "txt"
    try:
        d = await asyncio.to_thread(_pixiv_api_get, f"/ajax/novel/{novel_id}")
        title = title or d.get("title") or f"pixiv小说_{novel_id}"
        author = author or d.get("userName") or ""
        create_date = (d.get("createDate") or d.get("uploadDate") or "")[:10]
        date_prefix = create_date[:7] if create_date else ""
        sub = f"{date_prefix}-{title}" if date_prefix else title
        cover = d.get("coverUrl") or d.get("url") or ""
        ext = ".docx" if fmt == "docx" else ".txt"
        items = [{
            "filename": f"{sanitize_directory_name(title)}{ext}",
            "size": None,
            "item_page": f"{PIXIV_BASE}/novel/show.php?id={novel_id}",
            "status": "ok",
            "thumbnail": cover,
            "media_url": "",
            "site": "pixiv", "kind": "novel", "novel_id": str(novel_id),
            "post_title": title, "post_date": create_date, "artist": author,
            "subfolder": sanitize_directory_name(sub),
            "pixiv_novel_fmt": fmt,
        }]
        if fmt == "txt" and cover:
            # txt 模式沿用"正文 + 封面文件"两个条目；docx 封面已嵌入文档不再单发
            items.append({
                "filename": f"{sanitize_directory_name(title)}_封面" + Path(urlparse(cover).path).suffix,
                "size": None,
                "item_page": f"{PIXIV_BASE}/novel/show.php?id={novel_id}",
                "status": "ok",
                "thumbnail": cover,
                "media_url": cover,
                "site": "pixiv", "illust_id": "", "novel_id": str(novel_id),
                "post_title": title, "post_date": create_date, "artist": author,
                "subfolder": sanitize_directory_name(sub),
            })
        album_id = f"pixiv_novel_{novel_id}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({"event": "inspect_complete", "album_name": title,
              "album_id": album_id, "is_album": len(items) > 1, "items": items})
        logging.info("Pixiv 小说 %s 解析完成: %d 个文件", novel_id, len(items))
    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"小说解析失败: {exc}"})
        logging.exception("Pixiv 小说解析失败 %s", novel_id)


async def _pixiv_user_novel_items(uid: str) -> tuple[list[dict], str]:
    """解析用户全部小说 → 下载条目列表（不发 inspect 事件，供预览/批量下载复用）。"""
    all_novels: list[dict] = []
    offset = 0
    while True:
        params = {"user_id": uid, "offset": offset} if offset else {"user_id": uid}
        result = await asyncio.to_thread(_pixiv_app_api, "GET", "/v1/user/novels", params)
        batch = result.get("novels") or []
        all_novels.extend(batch)
        if len(batch) < PIXIV_APP_PER_PAGE or len(all_novels) >= PIXIV_USER_MAX_WORKS:
            break
        offset += PIXIV_APP_PER_PAGE
    if not all_novels:
        return [], ""
    author = ((all_novels[0].get("user") or {}).get("name")) or f"pixiv用户_{uid}"
    items = []
    for d in all_novels:
        title = d.get("title") or f"pixiv小说_{d.get('id')}"
        create_date = (d.get("create_date") or "")[:10]
        date_prefix = create_date[:7] if create_date else ""
        sub = f"{date_prefix}-{title}" if date_prefix else title
        items.append({
            "filename": "",  # 下载时生成（标题.txt）
            "size": None,
            "item_page": f"{PIXIV_BASE}/novel/show.php?id={d.get('id')}",
            "status": "ok",
            "thumbnail": (d.get("image_urls") or {}).get("medium") or "",
            "media_url": "",  # 下载时取 /v1/novel/text
            "site": "pixiv", "kind": "novel", "novel_id": str(d.get("id") or ""),
            "post_title": title, "post_date": create_date, "artist": author,
            "subfolder": sanitize_directory_name(sub),
        })
    return items, author


async def pixiv_user_novels(uid: str) -> None:
    """用户全部小说 → 下载条目列表（txt 全文，一键批量下载）。"""
    try:
        emit({"event": "inspect_progress", "current": 0, "total": 0,
              "filename": "获取小说列表..."})
        items, author = await _pixiv_user_novel_items(uid)
        if not items:
            emit({"event": "inspect_error", "message": "该用户没有小说"})
            return
        album_id = f"pixiv_user_novels_{uid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({"event": "inspect_complete", "album_name": f"{author}的小说",
              "album_id": album_id, "is_album": True, "items": items})
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("Pixiv 用户 %s 小说解析完成: %d 篇", uid, len(items))
    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"用户小说解析失败: {exc}"})
        logging.exception("Pixiv 用户小说解析失败 uid=%s", uid)


async def pixiv_batch_download_users(user_ids: list, content: str,
                                     illust_ids: list, novel_ids: list,
                                     options: dict) -> None:
    """Pixiv 批量解析下载（多批次）：关注/粉丝列表勾选多个用户或列表勾选多个作品，
    逐个解析并直接提交下载任务（不经解析预览页）。

    （2026-09-13 由 pixiv_batch_download 改名：该名字曾与卡片勾选版（items 参数）
    同名互相覆盖——Python 后定义者胜，导致 command_loop 按 items 调用时实际走进
    本函数、把条目字典当 user_id 解析 → 任务永远建不出来。现两版各自独立命名。）

    - user_ids + content（illust|novel）：每个用户单独一个下载任务（多批次，
      目录 = 作者名/...，与其他站点批量下载逻辑一致）
    - illust_ids / novel_ids：勾选的作品合并为一个任务
    """
    user_ids = [str(u).strip() for u in (user_ids or []) if str(u).strip()]
    illust_ids = [str(v).strip() for v in (illust_ids or []) if str(v).strip()]
    novel_ids = [str(v).strip() for v in (novel_ids or []) if str(v).strip()]
    content = "novel" if content == "novel" else "illust"
    works_total = 1 if (illust_ids or novel_ids) else 0
    total = len(user_ids) + works_total
    done = 0
    failed: list[str] = []

    def _progress(done_: int, msg: str) -> None:
        emit({"event": "pixiv_batch_progress", "done": done_, "total": total, "message": msg})

    if not total:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "没有可批量下载的内容"})
        return

    try:
        for uid in user_ids:
            label = f"用户 {uid}"
            _progress(done, f"正在解析 {label} 的全部{'小说' if content == 'novel' else '插画/漫画'}...")
            try:
                if content == "novel":
                    items, author = await _pixiv_user_novel_items(uid)
                    album_name = f"{author}的小说" if author else f"pixiv用户_{uid}的小说"
                    album_id = f"pixiv_user_novels_{uid}"
                    src_url = f"{PIXIV_BASE}/users/{uid}/novels"
                else:
                    items, user_name = await _pixiv_user_items(uid)
                    album_name = f"{user_name}的插画漫画" if user_name else f"pixiv用户_{uid}"
                    album_id = f"pixiv_user_{uid}"
                    src_url = f"{PIXIV_BASE}/users/{uid}"
                    label = f"@{user_name or uid}"
                if not items:
                    failed.append(f"{label}（无{'小说' if content == 'novel' else '作品'}）")
                else:
                    _apply_cached_thumbnails(items)
                    task_id = download_manager.submit(src_url, items, options, album_name, album_id)
                    download_manager.start(task_id)
                    logging.info("Pixiv 批量下载：%s 已提交 %d 个文件", label, len(items))
            except Exception as exc:
                failed.append(f"{label}（{exc}）")
                logging.exception("Pixiv 批量下载解析失败 uid=%s", uid)
            done += 1
            _progress(done, f"{label} 完成（{done}/{total}）")

        if illust_ids or novel_ids:
            _progress(done, f"正在解析勾选的 {len(illust_ids) + len(novel_ids)} 个作品...")
            items: list[dict] = []
            try:
                for iid in illust_ids:
                    w_items, _meta = await _pixiv_build_illust_items(iid)
                    items.extend(w_items)
                for nid in novel_ids:
                    # 小说批量：单篇 detail 仅取标题/日期/封面（正文下载时取 /v1/novel/text）
                    detail = (await asyncio.to_thread(
                        _pixiv_app_api, "GET", "/v1/novel/detail", {"novel_id": nid})).get("novel") or {}
                    title = detail.get("title") or f"pixiv小说_{nid}"
                    create_date = (detail.get("create_date") or "")[:10]
                    date_prefix = create_date[:7] if create_date else ""
                    sub = f"{date_prefix}-{title}" if date_prefix else title
                    cover = (detail.get("image_urls") or {}).get("large") or ""
                    items.append({
                        "filename": "", "size": None,
                        "item_page": f"{PIXIV_BASE}/novel/show.php?id={nid}", "status": "ok",
                        "thumbnail": cover, "media_url": "",
                        "site": "pixiv", "kind": "novel", "novel_id": str(nid),
                        "post_title": title, "post_date": create_date,
                        "artist": (detail.get("user") or {}).get("name") or "",
                        "subfolder": sanitize_directory_name(sub),
                    })
                if not items:
                    failed.append("勾选的作品（全部解析失败）")
                else:
                    task_id = download_manager.submit(
                        "https://www.pixiv.net/", items, options, "Pixiv 批量下载", "pixiv_batch")
                    download_manager.start(task_id)
                    logging.info("Pixiv 批量下载：已提交 %d 个作品", len(items))
            except Exception as exc:
                failed.append(f"勾选的作品（{exc}）")
                logging.exception("Pixiv 批量下载作品解析失败")
            done += 1
            _progress(done, f"作品解析完成（{done}/{total}）")

        summary = f"Pixiv 批量下载已提交：{done}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "pixiv_batch_done", "done": done, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "pixiv_batch_done", "done": done, "total": total, "failed": failed,
              "message": f"Pixiv 批量下载中断: {exc}"})
        logging.exception("Pixiv 批量下载出错")


async def pixiv_following_download_all(content: str = "illust", options: dict = None) -> None:
    """下载全部关注用户的作品（功能栏"批量下载"入口）：

    遍历 /v1/user/following 全部分页（跟随 next_url 游标）收集所有关注用户，
    然后复用 pixiv_batch_download 的逐用户批量逻辑（每人一个下载任务，
    目录 = 作者名/...，与关注列表勾选批量一致）。
    """
    options = options or {}
    content = "novel" if content == "novel" else "illust"
    emit({"event": "pixiv_batch_progress", "done": 0, "total": 0,
          "message": "正在获取关注列表（遍历全部分页）..."})
    uid = _pixiv_load_cred().get("user_id") or ""
    if not uid:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "未登录：请先完成 Refresh Token 登录"})
        return
    user_ids: list[str] = []
    names: dict[str, str] = {}
    req_path = "/v1/user/following"
    req_params: dict = {"user_id": uid, "restrict": "public"}
    try:
        while True:
            result = await asyncio.to_thread(_pixiv_app_api, "GET", req_path, req_params)
            for d in result.get("user_previews") or []:
                u = d.get("user") or {}
                wid = str(u.get("id") or "")
                if wid and wid not in names:
                    names[wid] = u.get("name") or ""
                    user_ids.append(wid)
            emit({"event": "pixiv_batch_progress", "done": 0, "total": 0,
                  "message": f"已获取 {len(user_ids)} 个关注用户..."})
            next_url = result.get("next_url") or ""
            if not next_url or not (result.get("user_previews") or []) or len(user_ids) >= 5000:
                break
            req_path, req_params = _pixiv_parse_next_url(next_url)
    except Exception as exc:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": f"获取关注列表失败: {exc}"})
        logging.exception("Pixiv 关注列表遍历失败")
        return
    if not user_ids:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "关注列表为空"})
        return
    logging.info("Pixiv 下载全部关注：共 %d 人（%s）", len(user_ids), content)
    await pixiv_batch_download_users(user_ids, content, [], [], options)


PIXIV_BOOKMARKS_MAX_WORKS = 10000  # 全量收藏下载上限（防御性，正常用户达不到）


def _pixiv_all_downloaded_keys() -> set[str]:
    """全站已下载记录的 item_page 集合（跨相册精确查重）。

    收藏列表按收藏时间排序而非发帖时间，不能用 latest_post 截断日期，
    只按 item_page 精确匹配（pixiv.net/artworks/{id} / novel/show.php?id=），
    这样无论之前是按画师批量下还是单作品下载过，都能正确跳过。
    """
    keys: set[str] = set()
    for album in (_load_download_state() or {}).values():
        for k in (album or {}).get("downloaded", []):
            if isinstance(k, str) and "pixiv.net" in k:
                keys.add(k)
    return keys


async def pixiv_bookmarks_download_all(content: str = "illust", restrict: str = "public",
                                       allow_r18: bool = True, options: dict | None = None) -> None:
    """下载全部收藏：遍历收藏列表全部分页，跳过历史已下载内容后提交下载。

    与按画师批量下载不同：不按画师分层，统一放进
    插画 →「我的插画收藏」/ 漫画 →「我的漫画收藏」/ 小说 →「我的小说收藏」，
    每个作品一个子文件夹（YYYY-MM-标题）。
    """
    content = content if content in ("illust", "manga", "novel") else "illust"
    restrict = "private" if restrict == "private" else "public"
    options = options or {}

    def _progress(msg: str) -> None:
        emit({"event": "pixiv_batch_progress", "done": 0, "total": 0, "message": msg})

    try:
        uid = _pixiv_load_cred().get("user_id") or ""
        if not uid:
            emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
                  "message": "未登录：请先完成 Refresh Token 登录"})
            return

        # ---------- 1. 遍历收藏列表全部分页（跟随 next_url 游标） ----------
        # App API 忽略 offset（offset 翻页只会重复拿第一页），必须跟随 next_url
        works: list[dict] = []
        seen_ids: set[str] = set()
        req_path = f"/v1/user/bookmarks/{content}"
        req_params: dict = {"user_id": uid, "restrict": restrict}
        while True:
            _progress(f"正在获取收藏列表（已收集 {len(works)} 个作品）...")
            result = await asyncio.to_thread(_pixiv_app_api, "GET", req_path, req_params)
            batch = result.get("novels" if content == "novel" else "illusts") or []
            if not allow_r18:
                batch = [d for d in batch if not (d.get("x_restrict") or 0)]
            for d in batch:
                wid = str(d.get("id") or "")
                if wid and wid not in seen_ids:
                    seen_ids.add(wid)
                    works.append(d)
            next_url = result.get("next_url") or ""
            if (not next_url or not batch
                    or len(works) >= PIXIV_BOOKMARKS_MAX_WORKS):
                break
            req_path, req_params = _pixiv_parse_next_url(next_url)
        if not works:
            emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
                  "message": "收藏列表为空，没有可下载的内容"})
            return

        # ---------- 2. 构造下载条目（一作品一条目，原图直链下载时懒解析） ----------
        downloaded = _pixiv_all_downloaded_keys()
        items: list[dict] = []
        skipped = 0
        for d in works:
            wid = str(d.get("id") or "")
            title = d.get("title") or f"pixiv_{wid}"
            author = (d.get("user") or {}).get("name") or ""
            create_date = (d.get("create_date") or "")[:10]
            date_prefix = create_date[:7] if create_date else ""
            sub = f"{date_prefix}-{title}" if date_prefix else title
            subfolder = sanitize_directory_name(sub)
            if content == "novel":
                item_page = f"{PIXIV_BASE}/novel/show.php?id={wid}"
                if item_page in downloaded:
                    skipped += 1
                    continue
                items.append({
                    "filename": "", "size": None,
                    "item_page": item_page, "status": "ok",
                    "thumbnail": (d.get("image_urls") or {}).get("medium") or "",
                    "media_url": "",
                    "site": "pixiv", "kind": "novel", "novel_id": wid,
                    "post_title": title, "post_date": create_date,
                    "artist": author, "subfolder": subfolder,
                })
            else:
                item_page = f"{PIXIV_BASE}/artworks/{wid}"
                if item_page in downloaded:
                    skipped += 1
                    continue
                items.append({
                    "filename": "", "size": None,
                    "item_page": item_page, "status": "ok",
                    "thumbnail": (d.get("image_urls") or {}).get("medium") or "",
                    "media_url": "",
                    "site": "pixiv", "illust_id": wid,
                    "ugoira": d.get("type") == "ugoira",
                    "post_title": title, "post_date": create_date,
                    "artist": author, "subfolder": subfolder,
                })

        album_name = {"illust": "我的插画收藏", "manga": "我的漫画收藏",
                      "novel": "我的小说收藏"}[content]
        if not items:
            emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
                  "message": f"{album_name}：共 {len(works)} 个作品，全部已下载过（跳过 {skipped} 个）"})
            return

        # ---------- 3. 提交下载任务（album_id 固定，下载完成后写入查重记录） ----------
        _apply_cached_thumbnails(items)
        album_id = f"pixiv_bookmarks_{content}"
        task_id = download_manager.submit("https://www.pixiv.net/", items, options,
                                          album_name, album_id)
        download_manager.start(task_id)
        summary = f"{album_name}：收藏 {len(works)} 个，跳过已下载 {skipped} 个，本次下载 {len(items)} 个作品"
        emit({"event": "pixiv_batch_done", "done": len(items), "total": len(items),
              "failed": [], "message": summary})
        logging.info("Pixiv 下载全部收藏 %s/%s: 收藏 %d 跳过 %d 提交 %d",
                     content, restrict, len(works), skipped, len(items))
    except PermissionError as exc:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": str(exc)})
    except Exception as exc:
        emit({"event": "pixiv_batch_done", "done": 0, "total": 0, "failed": [],
              "message": f"Pixiv 下载全部收藏失败: {exc}"})
        logging.exception("Pixiv 下载全部收藏出错 content=%s", content)


def is_pixiv_novel_url(url: str) -> bool:
    return bool(re.search(r"pixiv\.net/(?:en/)?novel/show\.php\?.*id=(\d+)", url, re.I))


def _pixiv_filename(title: str, index: int, total: int, url: str) -> str:
    """作品文件名：多页作品带 _p{N} 序号，扩展名取自直链。"""
    ext = Path(urlparse(url).path).suffix.lstrip(".") or "jpg"
    safe_title = sanitize_directory_name((title or "").strip()) or "pixiv"
    if total > 1:
        return f"{safe_title}_p{index}.{ext}"
    return f"{safe_title}.{ext}"


async def _pixiv_build_illust_items(illust_id: str) -> tuple[list[dict], dict]:
    """解析单个作品的全部页面 → 文件条目列表（返回 items + 详情元数据）。

    多页作品走 /ajax/illust/{id}/pages；动图(ugoira)额外取 ugoira_meta 的 zip 包。
    """
    detail = await asyncio.to_thread(_pixiv_api_get, f"/ajax/illust/{illust_id}")
    title = detail.get("title") or f"pixiv_{illust_id}"
    author = detail.get("userName") or ""
    create_date = (detail.get("createDate") or "")[:10]
    illust_type = detail.get("illustType")
    page_count = int(detail.get("pageCount") or 1)
    urls = detail.get("urls") or {}

    # 子文件夹：YYYY-MM-作者（单作品任务：album=作品名 → 下载根/作品名/YYYY-MM-作者/文件）
    date_prefix = create_date[:7] if create_date else ""
    sub_parts = []
    if date_prefix and author:
        sub_parts.append(f"{date_prefix}-{author}")
    elif author:
        sub_parts.append(author)
    subfolder = str(Path(*sub_parts)) if sub_parts else ""

    items: list[dict] = []
    if illust_type == 2:
        # 动图：下载原始帧 zip（i.pximg.net，同样需要 Referer）
        try:
            ugoira = await asyncio.to_thread(_pixiv_api_get, f"/ajax/illust/{illust_id}/ugoira_meta")
            zip_url = ugoira.get("originalSrc") or ""
            if zip_url:
                items.append({
                    "filename": _pixiv_filename(title + "_动图", 0, 1, zip_url),
                    "size": None,
                    "item_page": f"{PIXIV_BASE}/artworks/{illust_id}",
                    "status": "ok",
                    "thumbnail": urls.get("regular") or "",
                    "media_url": zip_url,
                    "site": "pixiv", "illust_id": illust_id, "page_index": 0,
                    "post_title": title, "post_date": create_date, "artist": author,
                    "ugoira": True, "subfolder": subfolder,
                })
        except Exception:
            logging.warning("Pixiv 动图 %s ugoira 元数据获取失败，回退为静态图", illust_id)
    if not items:
        if page_count > 1:
            pages = await asyncio.to_thread(_pixiv_api_get, f"/ajax/illust/{illust_id}/pages")
            for i, p in enumerate(pages or []):
                original = (p.get("urls") or {}).get("original") or ""
                if not original:
                    continue
                items.append({
                    "filename": _pixiv_filename(title, i, page_count, original),
                    "size": None,
                    "item_page": f"{PIXIV_BASE}/artworks/{illust_id}",
                    "status": "ok",
                    "thumbnail": (p.get("urls") or {}).get("regular") or "",
                    "media_url": original,
                    "site": "pixiv", "illust_id": illust_id, "page_index": i,
                    "post_title": title, "post_date": create_date, "artist": author,
                    "subfolder": subfolder,
                })
        else:
            original = urls.get("original") or ""
            if original:
                items.append({
                    "filename": _pixiv_filename(title, 0, 1, original),
                    "size": None,
                    "item_page": f"{PIXIV_BASE}/artworks/{illust_id}",
                    "status": "ok",
                    "thumbnail": urls.get("regular") or "",
                    "media_url": original,
                    "site": "pixiv", "illust_id": illust_id, "page_index": 0,
                    "post_title": title, "post_date": create_date, "artist": author,
                    "subfolder": subfolder,
                })
    meta = {"title": title, "author": author, "user_id": detail.get("userId") or "",
            "page_count": page_count, "create_date": create_date}
    return items, meta


async def _pixiv_user_items(uid: str) -> tuple[list[dict], str]:
    """解析用户主页全部作品 → 文件条目列表（下载时按需解析原图直链）。

    用户作品数可能上千：profile/all 只拿 id 列表（1 个请求），
    profile/illusts 批量拿卡片数据（每批 30 个）；文件条目不带 media_url，
    下载时由 _pixiv_download_one 按需解析（原图直链规则稳定）。
    """
    body = await asyncio.to_thread(_pixiv_api_get, f"/ajax/user/{uid}/profile/all")
    ids: list[str] = []
    for section in ("illusts", "manga"):
        ids.extend(str(k) for k in (body.get(section) or {}).keys())
    # id 即时间序：降序 = 最新在前；去重 + 截断上限
    ids = sorted(set(ids), key=int, reverse=True)[:PIXIV_USER_MAX_WORKS]
    if not ids:
        return [], ""

    # 批量取卡片数据（title/pageCount/userName/createDate）
    cards: dict[str, dict] = {}
    for i in range(0, len(ids), PIXIV_DETAIL_CHUNK):
        chunk = ids[i:i + PIXIV_DETAIL_CHUNK]
        params = [("ids[]", iid) for iid in chunk]
        params += [("work_category", "illustManga"), ("is_first_page", "1"), ("lang", "zh")]
        try:
            works = await asyncio.to_thread(_pixiv_api_get, f"/ajax/user/{uid}/profile/illusts", params)
            for wid, w in (works or {}).items():
                cards[str(wid)] = w
        except Exception as exc:
            logging.warning("Pixiv 用户作品批次获取失败 %s: %s", uid, exc)
        emit({"event": "inspect_progress", "current": min(i + PIXIV_DETAIL_CHUNK, len(ids)),
              "total": len(ids), "filename": f"获取作品列表 {min(i + PIXIV_DETAIL_CHUNK, len(ids))}/{len(ids)}..."})

    user_name = ""
    items: list[dict] = []
    for iid in ids:
        w = cards.get(iid)
        if not w:
            continue
        if not user_name:
            user_name = w.get("userName") or ""
        title = w.get("title") or f"pixiv_{iid}"
        create_date = (w.get("createDate") or "")[:10]
        date_prefix = create_date[:7] if create_date else ""
        # 子文件夹：YYYY-MM-作品名（用户任务：album=作者名 → 下载根/作者名/YYYY-MM-作品名/文件）
        sub = f"{date_prefix}-{title}" if date_prefix else title
        thumb = w.get("url") or ""
        if thumb.startswith("//"):
            thumb = "https:" + thumb
        page_count = int(w.get("pageCount") or 1)
        items.append({
            "filename": "",  # 下载时解析直链后确定（含扩展名与多页序号）
            "size": None,
            "item_page": f"{PIXIV_BASE}/artworks/{iid}",
            "status": "ok",
            "thumbnail": thumb,
            "media_url": "",  # 下载时按需解析（profile/illusts 不含原图直链）
            "site": "pixiv", "illust_id": iid, "page_index": 0,
            "post_title": title, "post_date": create_date,
            "artist": w.get("userName") or "",
            "ugoira": w.get("illustType") == 2,
            "subfolder": sanitize_directory_name(sub),
            "_page_count": page_count,
        })
    return items, user_name


async def pixiv_inspect(url: str, options: dict) -> None:
    """解析 Pixiv 作品页 / 小说页 / 用户主页 → 文件列表。"""
    # 小说页：/novel/show.php?id={id} → txt/docx 全文 + 封面（fmt 由前端下载按钮选择）
    m_novel = re.search(r"pixiv\.net/(?:en/)?novel/show\.php\?.*id=(\d+)", url, re.I)
    if m_novel:
        await pixiv_novel_items(
            m_novel.group(1),
            fmt=str((options or {}).get("pixiv_novel_fmt") or "txt"))
        return

    # 用户主页：/users/{uid}
    m_user = re.search(r"pixiv\.net/(?:en/)?users/(\d+)", url, re.I)
    if m_user:
        uid = m_user.group(1)
        try:
            emit({"event": "inspect_progress", "current": 0, "total": 0,
                  "filename": f"获取用户 {uid} 的作品列表..."})
            items, user_name = await _pixiv_user_items(uid)
            if not items:
                emit({"event": "inspect_error", "message": "该用户没有可下载的作品"})
                return
            album_name = user_name or f"pixiv用户_{uid}"
            album_id = f"pixiv_user_{uid}"
            _apply_cached_thumbnails(items)
            _mark_items_new(album_id, items)
            emit({
                "event": "inspect_complete",
                "album_name": album_name,
                "album_id": album_id,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Pixiv 用户 %s 解析完成: %d 个作品", uid, len(items))
            return
        except Exception as exc:
            emit({"event": "inspect_error",
                  "message": f"Pixiv 用户解析失败: {exc}（请检查网络或 Pixiv 代理设置）"})
            logging.exception("Pixiv 用户解析出错")
            return

    # 作品页：/artworks/{id}（兼容旧 member_illust.php?illust_id=）
    m = re.search(r"pixiv\.net/(?:en/)?artworks/(\d+)", url, re.I)
    if not m:
        m = re.search(r"member_illust\.php\?.*illust_id=(\d+)", url, re.I)
    if not m:
        emit({"event": "inspect_error",
              "message": "无法识别的 Pixiv 链接（支持 /artworks/{id} 与 /users/{id}）"})
        return
    illust_id = m.group(1)
    try:
        items, meta = await _pixiv_build_illust_items(illust_id)
        if not items:
            emit({"event": "inspect_error", "message": "作品没有可下载的文件（可能已删除或需登录查看）"})
            return
        album_id = f"pixiv_{illust_id}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": meta["title"],
            "album_id": album_id,
            "is_album": len(items) > 1,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("Pixiv 作品 %s 解析完成: %d 个文件", illust_id, len(items))
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"Pixiv 解析失败: {exc}（请检查网络或 Pixiv 代理设置）"})
        logging.exception("Pixiv 解析过程出错")
