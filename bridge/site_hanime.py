# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：Hanime1。

由 gui_bridge.py 按物理顺序拆出（原行区间 6834-7581），
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
# Hanime1 站点支持 (hanime1.me，里番视频站，X站类型)
# ============================
# - 服务端渲染 HTML（Laravel），无公开 JSON API
# - 登录: GET /login 取 _token → POST /login {email,password,submit:login}
#   会话 cookie（remember_token）长期有效；密码一并加密保存用于自动重登
# - 搜索: GET /search?query=&genre=&sort=&page=N（Laravel 分页，rel="next" 翻页）
# - 视频页: GET /watch?v={id} → <video><source> MP4 直链（480/720/1080，secure 签名会过期）
# - 评论: GET /loadComment?id={vid}&type=video（JSON 内嵌 HTML）；发表 POST /createComment
#   注意：网站本身不提供删除评论功能（/deleteComment 服务端已损坏，任何参数都 500）
# - 收藏: POST /save {input_id:"save", video_id, is_checked}（"稍後觀看"播放清单）
# - 国内需代理（默认 http://127.0.0.1:10809）

HANIME_BASE = "https://hanime1.me"
HANIME_DEFAULT_PROXY = "http://127.0.0.1:10809"
# 分类（与官网导航一致；"新番預告"是独立页面 /previews/{YYYYMM}，不在此列）
HANIME_GENRES = ["裏番", "泡麵番", "Motion Anime", "3DCG", "2.5D", "2D動畫", "AI生成", "MMD", "Cosplay"]
# 排序方式（官网排序下拉的 data-value）
HANIME_SORTS = ["最新上市", "最新上傳", "本日排行", "本週排行", "本月排行", "觀看次數", "讚好比例", "時長最長"]

_hanime_proxy = HANIME_DEFAULT_PROXY
_hanime_username = ""


def _hanime_username_now() -> str:
    """当前用户名（跨模块读取入口）。"""
    return _hanime_username or ""


def _hanime_set_username(v: str) -> None:
    """跨模块写入口（账号档案恢复等）。"""
    global _hanime_username
    _hanime_username = v or ""

_hanime_session = requests.Session()
_hanime_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
})


def hanime_set_proxy(proxy: str) -> None:
    """设置 Hanime1 代理（空 = 直连）。"""
    global _hanime_proxy
    _hanime_proxy = (proxy or "").strip()
    if _hanime_proxy and not _hanime_proxy.startswith(("http://", "https://", "socks5://")):
        _hanime_proxy = "http://" + _hanime_proxy
    proxies = {"http": _hanime_proxy, "https": _hanime_proxy} if _hanime_proxy else {}
    _hanime_session.proxies = proxies
    emit({"event": "hanime_proxy_set", "proxy": _hanime_proxy})


_hanime_throttle = _make_throttle(0.6)


def _hanime_load_cred() -> dict:
    """读取已保存的 Hanime1 登录信息（加密存储：cookies + 邮箱 + 密码）。"""
    return _secure_store_read_cred("hanime")


def _hanime_save_cred(data: dict) -> None:
    _secure_store_write_cred("hanime", dict(data))


def _hanime_restore_session() -> None:
    """启动时从加密存储恢复会话 cookie。"""
    global _hanime_username
    cred = _hanime_load_cred()
    cookies = cred.get("cookies") or {}
    for name, value in cookies.items():
        try:
            _hanime_session.cookies.set(name, value, domain=".hanime1.me")
        except Exception:
            pass
    _hanime_username = cred.get("username") or ""


def _hanime_sync_cookies(cred: dict) -> dict:
    """把当前会话 cookie 写回凭据（XSRF-TOKEN / remember_token 会刷新）。"""
    cred["cookies"] = {c.name: c.value for c in _hanime_session.cookies}
    return cred


def _hanime_get(path: str, params: dict | None = None) -> requests.Response:
    """带节流的 GET（返回原始 Response）。"""
    _hanime_throttle()
    return _hanime_session.get(f"{HANIME_BASE}{path}", params=params, timeout=25)


def _hanime_soup(path: str, params: dict | None = None) -> BeautifulSoup | None:
    resp = _hanime_get(path, params)
    if resp.status_code != 200:
        raise PermissionError(f"Hanime1 返回 HTTP {resp.status_code}")
    return BeautifulSoup(resp.text, "html.parser")


def _hanime_csrf(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]
    inp = soup.find("input", attrs={"name": "_token"})
    return (inp.get("value") if inp else "") or ""


def _hanime_logged_in(soup: BeautifulSoup) -> bool:
    """页面里是否处于登录状态（右上角用户弹窗存在）。"""
    return bool(soup.find(id="user-modal-name") or soup.select_one("form[action*='/logout']"))


def _hanime_parse_card(card: BeautifulSoup) -> dict | None:
    """列表卡片（video-item-container）→ 前端视频卡片。"""
    link = card.select_one("a.video-link") or card.find("a", href=re.compile(r"watch\?v="))
    if not link:
        return None
    m = re.search(r"watch\?v=(\w+)", link.get("href") or "")
    if not m:
        return None
    vid = m.group(1)
    img = card.select_one("img.main-thumb") or card.find("img")
    duration = card.select_one(".duration")
    stats = [s.get_text(strip=True) for s in card.select(".stat-item")]
    rating = ""
    views = ""
    for s in stats:
        if "%" in s:
            rating = s
        else:
            views = s
    # 列表/搜索页卡片标题类名 .title；watch 页相關影片卡片是 h4.video-title（探针实测）
    title_el = card.select_one(".title") or card.select_one(".video-title")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        title = card.get("title") or ""
    author_el = card.select_one(".subtitle a")
    author = author_el.get_text(strip=True) if author_el else ""
    time_el = card.select_one(".subtitle-time")
    return {
        "album_name": title or f"hanime_{vid}",
        "album_url": f"{HANIME_BASE}/watch?v={vid}",
        "thumbnail": (img.get("src") or "") if img else "",
        "files": 1,
        "site": "hanime",
        "video_id": vid,
        "author": author,
        "duration": duration.get_text(strip=True) if duration else "",
        "rating": rating,
        "views": views,
        "posted": time_el.get_text(strip=True).lstrip("• ").strip() if time_el else "",
    }


def _hanime_parse_cards(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for card in soup.select("div.video-item-container"):
        item = _hanime_parse_card(card)
        if item:
            items.append(item)
    return items


def _hanime_has_next(soup: BeautifulSoup) -> bool:
    return bool(soup.find("a", rel="next") or soup.select_one("a.page-link[rel='next']"))


def _hanime_parse_total_pages(soup: BeautifulSoup) -> int:
    """搜索页分页控件 → 真实总页数（page-link 数字 + 当前页取最大）。

    此前只给 has_more 不给总页数 → 前端分页栏页码显示不出来（"页码是假的"）。"""
    nums = []
    for a in soup.select("a.page-link"):
        t = a.get_text(strip=True)
        if t.isdigit():
            nums.append(int(t))
    for el in soup.select(".page-item.active, li.active"):
        t = el.get_text(strip=True)
        if t.isdigit():
            nums.append(int(t))
    return max(nums) if nums else 0


def _hanime_parse_related(soup: BeautifulSoup, video_id: str) -> list[dict]:
    """watch 页「相關影片」标签页 → 相关视频卡片（详情一次带全，无需二次请求）。

    探针实测（2026-09-09）：卡片容器是 #related-tabcontent 内的
    div.video-item-container；同一卡片按响应式断点重复渲染（59 个视频渲染
    118 张），必须按 video_id 去重保序；右侧播放列表（#playlist-scroll）
    卡片不在此容器内，天然排除。
    """
    rel_sec = soup.select_one("#related-tabcontent")
    if not rel_sec:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for card in rel_sec.select("div.video-item-container"):
        item = _hanime_parse_card(card)
        if not item:
            continue
        vid = item["video_id"]
        if vid == video_id or vid in seen:
            continue
        seen.add(vid)
        items.append(item)
        if len(items) >= 12:
            break
    return items


def hanime_login(email: str, password: str) -> None:
    """Hanime1 登录（邮箱 + 密码；会话 cookie 与密码一起加密保存）。"""
    global _hanime_username
    try:
        soup = _hanime_soup("/login")
        token = _hanime_csrf(soup)
        resp = _hanime_session.post(
            f"{HANIME_BASE}/login", timeout=25,
            data={"_token": token, "email": email, "password": password, "submit": "login"},
        )
        home = _hanime_soup("/")
        if not _hanime_logged_in(home):
            emit({"event": "hanime_login_result", "success": False,
                  "message": "登录失败（邮箱或密码错误）"})
            return
        name_el = home.find(id="user-modal-name")
        username = name_el.get_text(strip=True) if name_el else email
        # 从用户中心链接提取 user_id
        uid = ""
        um = home.select_one("a.user-modal-link[href*='/user/']")
        if um:
            mm = re.search(r"/user/(\d+)", um.get("href") or "")
            if mm:
                uid = mm.group(1)
        _hanime_username = username
        cred = {"email": email, "password": password, "username": username, "user_id": uid}
        _hanime_save_cred(_hanime_sync_cookies(cred))
        _emit_login_info()
        emit({"event": "hanime_login_result", "success": True, "username": username,
              "message": "Hanime1 登录成功"})
    except requests.RequestException as exc:
        emit({"event": "hanime_login_result", "success": False,
              "message": f"连接失败: {exc}（国内建议在设置里配置 Hanime1 代理）",
              "network_issue": True})
    except Exception as exc:
        emit({"event": "hanime_login_result", "success": False, "message": f"登录失败: {exc}"})


def hanime_set_cookies(cookie_str: str, email: str = "", password: str = "") -> None:
    """内置浏览器登录 Hanime1 后保存会话 cookie（真人验证/Cloudflare 在弹窗内完成后抓取）。

    webview 里完成登录（含真人验证）→ 点"确认"抓取 cookie → 应用到后端会话并加密保存；
    表单里输入的邮箱密码一并保存（会话失效时自动重登）。
    """
    global _hanime_username
    try:
        _hanime_session.cookies.clear()
        for pair in (cookie_str or "").split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            try:
                _hanime_session.cookies.set(name.strip(), value.strip(), domain=".hanime1.me")
            except Exception:
                continue
        cred = _hanime_load_cred()
        if (email or "").strip():
            cred["email"] = email.strip()
        if password:
            cred["password"] = password
        _hanime_save_cred(_hanime_sync_cookies(cred))
        _emit_login_info()
        emit({"event": "hanime_login_result", "success": True,
              "message": "Hanime1 会话已保存（真人验证完成）"})
        # 立即校验会话是否有效（无效时会用保存的密码自动重登）
        hanime_check_login(False)
    except Exception as exc:
        logging.exception("Hanime1 cookie 保存失败")
        emit({"event": "hanime_login_result", "success": False,
              "message": f"保存会话失败: {exc}"})


def hanime_logout() -> None:
    global _hanime_username
    _secure_store_clear_cred("hanime")
    _hanime_session.cookies.clear()
    _hanime_username = ""
    _emit_login_info()
    emit({"event": "hanime_login_result", "success": False, "logout": True,
          "message": "已退出 Hanime1 登录"})


def hanime_check_login(silent: bool = False) -> None:
    """检查 Hanime1 登录状态（会话失效时用保存的密码自动重登）。"""
    global _hanime_username
    cred = _hanime_load_cred()
    if not cred.get("cookies"):
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": "" if silent else "未登录"})
        return
    try:
        home = _hanime_soup("/")
        if _hanime_logged_in(home):
            name_el = home.find(id="user-modal-name")
            username = name_el.get_text(strip=True) if name_el else (cred.get("username") or "")
            _hanime_username = username
            cred["username"] = username
            if not cred.get("user_id"):
                um = home.select_one("a.user-modal-link[href*='/user/']")
                if um:
                    mm = re.search(r"/user/(\d+)", um.get("href") or "")
                    if mm:
                        cred["user_id"] = mm.group(1)
            _hanime_save_cred(_hanime_sync_cookies(cred))
            _emit_login_info()
            emit({"event": "hanime_login_result", "success": True, "silent": silent,
                  "username": username, "message": "Hanime1 登录有效"})
            return
        # 会话失效 → 用保存的密码自动重登
        if cred.get("email") and cred.get("password"):
            _hanime_session.cookies.clear()
            hanime_login(cred["email"], cred["password"])
            return
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": "登录已失效，请重新登录"})
    except requests.RequestException as exc:
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": f"连接失败: {exc}（请检查网络或 Hanime1 代理设置）",
              "network_issue": True})
    except Exception as exc:
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": f"检查登录失败: {exc}"})


async def hanime_home() -> None:
    """Hanime1 主页：各分区（最新上市/最新上傳 + 每个分类）的视频，每区最多 20 条。"""
    emit({"event": "hanime_home_loading", "loading": True})
    try:
        soup = await asyncio.to_thread(_hanime_soup, "/")
        sections: list[dict] = []
        # 每个 home-rows-videos-wrapper 前面最近的 h3 是分区标题
        for wrapper in soup.select("div.home-rows-videos-wrapper"):
            # 向上找分区标题（h3 在 wrapper 的同级/祖先前面）
            title = ""
            prev = wrapper.find_previous("h3")
            if prev:
                # 去掉"查看更多"链接文字与 material 图标文字残留
                title = re.sub(r"(查看更多|arrow_forward_ios)+\s*$", "", prev.get_text(strip=True)).strip()
            items = _hanime_parse_cards(wrapper)[:20]
            if items:
                sections.append({"title": title or "推荐", "items": items})
        all_items = [it for sec in sections for it in sec["items"]]
        _apply_cached_thumbnails(all_items)
        asyncio.create_task(_cache_thumbnails(all_items))
        emit({"event": "hanime_home", "sections": sections,
              "genres": HANIME_GENRES, "sorts": HANIME_SORTS})
        logging.info("Hanime1 主页: %d 个分区", len(sections))
    except Exception as exc:
        emit({"event": "hanime_home", "sections": [],
              "error": f"获取主页失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 主页获取失败")
    finally:
        emit({"event": "hanime_home_loading", "loading": False})


async def hanime_search(query: str, page: int = 1, genre: str = "",
                        sort: str = "", tags: list | None = None,
                        broad: str = "") -> None:
    """Hanime1 搜索（关键词 + 可选分类/排序/标签过滤，Laravel 分页）。

    参数格式与站内一致（参考 RSSHub hanime1 路由）：
    /search?query=&genre=&sort=&broad=&tags[]=純愛&tags[]=中文字幕&page=1
    """
    query = (query or "").strip()
    genre = genre or ""
    tags = [t for t in (tags or []) if t]
    if not query and not genre and not tags:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if query:
            params["query"] = query
        if genre and genre != "全部":
            params["genre"] = genre
        if sort:
            params["sort"] = sort
        # 标签过滤：requests 对 list 值会生成重复键 tags[]=a&tags[]=b
        if tags:
            params["tags[]"] = tags
            # broad=on 模糊匹配（包含任一标签），off/空 精确匹配（包含全部）
            if broad:
                params["broad"] = broad
        soup = await asyncio.to_thread(_hanime_soup, "/search", params)
        results = _hanime_parse_cards(soup)
        label_parts = [query] if query else []
        if genre and genre != "全部":
            label_parts.append(genre)
        if tags:
            label_parts.append("·".join(tags))
        emit({
            "event": "search_result", "query": query or genre or tags[0], "site": "hanime",
            "items": results, "page": page,
            "has_more": _hanime_has_next(soup),
            "total_pages": _hanime_parse_total_pages(soup),
            "genre": genre, "sort": sort, "tags": tags,
            "label": " · ".join(label_parts) or "Hanime1",
        })
        if results:
            asyncio.create_task(_cache_thumbnails(results))
        logging.info("Hanime1 搜索 '%s' (genre=%s tags=%s page=%d): %d 个结果",
                     query, genre, tags, page, len(results))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"Hanime1 搜索失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


def _hanime_best_source(sources: list[dict]) -> dict:
    """选最高画质（1080 > 720 > 480 > 其他）。"""
    def rank(s: dict) -> int:
        try:
            return -int(s.get("quality") or 0)
        except (ValueError, TypeError):
            return 0
    return sorted(sources, key=rank)[0] if sources else {}


def _hanime_parse_detail(soup: BeautifulSoup, video_id: str) -> dict:
    """watch 页 → 视频详情字典。"""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    title = (og_title.get("content") if og_title else "") or ""
    title = re.sub(r"\s*-\s*Hanime1\.me\s*$", "", title).strip()
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    description = (og_desc.get("content") if og_desc else "") or ""
    # 上传者（video-details-wrapper 内第一个 /user/ 链接）
    uploader = ""
    uploader_id = ""
    up_el = soup.select_one(".video-details-wrapper a[href*='/user/'] span")
    if up_el:
        uploader = up_el.get_text(strip=True)
    up_link = soup.select_one(".video-details-wrapper a[href*='/user/']")
    if up_link:
        mm = re.search(r"/user/(\d+)", up_link.get("href") or "")
        if mm:
            uploader_id = mm.group(1)
    # 观看数 + 日期（"觀看次數：209.7萬次  2026-08-08"）
    views = ""
    date = ""
    for div in soup.select(".video-details-wrapper div"):
        text = div.get_text(" ", strip=True)
        if "觀看次數" in text or "观看次数" in text:
            mm = re.search(r"[觀观]看次數[：:]\s*([^\s]+)", text)
            if mm:
                views = mm.group(1)
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", text)
            if dm:
                date = dm.group(1)
            break
    # 标签
    tags = []
    for tag_el in soup.select(".single-video-tag a"):
        name = tag_el.get_text(strip=True)
        name = re.sub(r"\s*\(\d+\)$", "", name)
        if name:
            tags.append(name)
    # 播放源（<source src="...mp4?secure=..." size="720">）
    sources = []
    for src in soup.select("#player source"):
        url = src.get("src") or ""
        if url.startswith("//"):
            url = "https:" + url
        if url:
            sources.append({"quality": src.get("size") or "", "url": url})
    # 缩略图（player 的 poster）
    player = soup.find(id="player")
    poster = (player.get("poster") or "") if player else ""
    # 收藏状态（"稍後觀看" checkbox 是否勾选）
    saved = False
    save_cb = soup.find("input", id="save")
    if save_cb and save_cb.has_attr("checked"):
        saved = True
    return {
        "album_name": title or f"hanime_{video_id}",
        "album_url": f"{HANIME_BASE}/watch?v={video_id}",
        "video_id": video_id,
        "site": "hanime",
        "title": title,
        "description": description,
        "thumbnail": poster,
        "uploader": uploader,
        "uploader_id": uploader_id,
        "views": views,
        "post_date": date,
        "tags": tags,
        "sources": sources,
        "saved": saved,
        # 相关推荐（相關影片标签页，详情一次带全；无此区块时为空列表）
        "related": _hanime_parse_related(soup, video_id),
    }


def _hanime_parse_comments_html(html: str) -> list[dict]:
    """loadComment 返回的评论 HTML → 评论列表（含回复，缩进标记）。"""
    soup = BeautifulSoup(html or "", "html.parser")
    comments: list[dict] = []
    for wrapper in soup.select("div.report-btn-wrapper"):
        # 判断是否为回复（祖先有 reply-section-wrapper）
        is_reply = False
        parent = wrapper.parent
        while parent is not None:
            pid = parent.get("id") or "" if hasattr(parent, "get") else ""
            if str(pid).startswith("reply-section-wrapper"):
                is_reply = True
                break
            parent = parent.parent
        texts = wrapper.select("div.comment-index-text")
        if len(texts) < 2:
            continue
        head = texts[0].get_text(" ", strip=True)
        body = texts[1].get_text(strip=True)
        # 用户名 + 相对时间（"yuejiaxiaosi  1分鐘前"）
        username = head
        posted = ""
        tm = re.search(r"(\d+\s*(?:秒|分鐘|小時|天|週|月|年)前)", head)
        if tm:
            posted = tm.group(1)
            username = head[:tm.start()].strip()
        report = wrapper.select_one("span.report-btn")
        avatar_el = wrapper.find_previous("img", class_="img-circle")
        comments.append({
            "id": (report.get("data-reportable-id") or "") if report else "",
            "username": username,
            "text": body,
            "posted": posted,
            "avatar": (avatar_el.get("src") or "") if avatar_el else "",
            "is_reply": is_reply,
        })
    return comments


async def hanime_video_detail(video_id: str) -> None:
    """Hanime1 视频详情：名称/视频源/tags/评论/收藏状态。"""
    emit({"event": "hanime_detail_loading", "loading": True})
    try:
        soup = await asyncio.to_thread(_hanime_soup, "/watch", {"v": video_id})
        video = _hanime_parse_detail(soup, video_id)
        # 在线播放：最高画质直链经本地媒体代理（带代理转发）
        best = _hanime_best_source(video["sources"])
        video["video_url"] = best.get("url") or ""
        # 评论（loadComment 需登录后才返回内容）
        comments: list[dict] = []
        comment_count = 0
        try:
            _hanime_throttle()
            resp = await asyncio.to_thread(
                lambda: _hanime_session.get(
                    f"{HANIME_BASE}/loadComment",
                    params={"id": video_id, "type": "video",
                            "content": "comment-tabcontent"},
                    timeout=30,
                ))
            data = {}
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    data = {}
            comments = _hanime_parse_comments_html(data.get("comments") or "")
            comment_count = data.get("comment_count") or len(comments)
        except Exception:
            pass
        _apply_cached_thumbnails([video])
        related = video.get("related") or []
        _apply_cached_thumbnails(related)
        avatars = [{"thumbnail": c["avatar"]} for c in comments if c.get("avatar")]
        _apply_cached_thumbnails(avatars)
        asyncio.create_task(_cache_thumbnails([video] + avatars + related))
        video.pop("sources", None)
        emit({"event": "hanime_video_detail", "video": video, "comments": comments,
              "comment_count": comment_count})
        logging.info("Hanime1 视频详情: %s", video_id)
    except Exception as exc:
        emit({"event": "hanime_video_detail", "video": None,
              "error": f"获取视频详情失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 视频详情获取失败")
    finally:
        emit({"event": "hanime_detail_loading", "loading": False})


async def hanime_comments(video_id: str) -> None:
    """刷新视频评论列表。"""
    try:
        data = {}
        try:
            _hanime_throttle()
            resp = await asyncio.to_thread(
                lambda: _hanime_session.get(
                    f"{HANIME_BASE}/loadComment",
                    params={"id": video_id, "type": "video",
                            "content": "comment-tabcontent"},
                    timeout=30,
                ))
            if resp.status_code == 200:
                data = resp.json()
        except Exception:
            data = {}
        comments = _hanime_parse_comments_html(data.get("comments") or "")
        avatars = [{"thumbnail": c["avatar"]} for c in comments if c.get("avatar")]
        _apply_cached_thumbnails(avatars)
        asyncio.create_task(_cache_thumbnails(avatars))
        emit({"event": "hanime_comments", "video_id": video_id, "items": comments,
              "comment_count": data.get("comment_count") or len(comments)})
    except Exception as exc:
        emit({"event": "hanime_comments", "video_id": video_id, "items": [],
              "error": f"获取评论失败: {exc}"})


def hanime_add_comment(video_id: str, text: str) -> None:
    """发表评论（POST /createComment，表单字段与官网一致）。"""
    text = (text or "").strip()
    if not text:
        emit({"event": "hanime_comment_result", "success": False, "message": "评论内容为空"})
        return
    cred = _hanime_load_cred()
    if not cred.get("cookies"):
        emit({"event": "hanime_comment_result", "success": False,
              "message": "未登录：请先登录 Hanime1 账号"})
        return
    try:
        soup = _hanime_soup("/watch", {"v": video_id})
        if not _hanime_logged_in(soup):
            # 会话失效 → 自动重登一次
            if cred.get("email") and cred.get("password"):
                _hanime_session.cookies.clear()
                hanime_login(cred["email"], cred["password"])
                cred = _hanime_load_cred()
                soup = _hanime_soup("/watch", {"v": video_id})
            if not _hanime_logged_in(soup):
                emit({"event": "hanime_comment_result", "success": False,
                      "message": "登录已失效，评论失败"})
                return
        token = _hanime_csrf(soup)
        user_id = cred.get("user_id") or ""
        count_el = soup.find("input", id="comment-count")
        count = count_el.get("value") if count_el else "0"
        _hanime_throttle()
        resp = _hanime_session.post(
            f"{HANIME_BASE}/createComment", timeout=25,
            data={
                "_token": token,
                "comment-user-id": user_id,
                "comment-type": "video",
                "comment-foreign-id": video_id,
                "comment-count": count,
                "comment-text": text,
            },
            headers={"Referer": f"{HANIME_BASE}/watch?v={video_id}",
                     "X-Requested-With": "XMLHttpRequest"},
        )
        if resp.status_code == 200:
            _hanime_save_cred(_hanime_sync_cookies(_hanime_load_cred()))
            emit({"event": "hanime_comment_result", "success": True,
                  "message": "评论已发表", "video_id": video_id})
        else:
            emit({"event": "hanime_comment_result", "success": False,
                  "message": f"评论失败: HTTP {resp.status_code}"})
    except requests.RequestException as exc:
        emit({"event": "hanime_comment_result", "success": False,
              "message": f"连接失败: {exc}"})
    except Exception as exc:
        emit({"event": "hanime_comment_result", "success": False,
              "message": f"评论失败: {exc}"})


def hanime_save_video(video_id: str, saved: bool) -> None:
    """收藏 / 取消收藏视频（"稍後觀看"播放清单，POST /save）。"""
    cred = _hanime_load_cred()
    if not cred.get("cookies"):
        emit({"event": "hanime_save_result", "success": False, "saved": saved,
              "message": "未登录：请先登录 Hanime1 账号"})
        return
    try:
        soup = _hanime_soup("/watch", {"v": video_id})
        token = _hanime_csrf(soup)
        _hanime_throttle()
        resp = _hanime_session.post(
            f"{HANIME_BASE}/save", timeout=25,
            data={"input_id": "save", "user_id": cred.get("user_id") or "",
                  "video_id": video_id, "is_checked": "true" if saved else "false"},
            headers={"Referer": f"{HANIME_BASE}/watch?v={video_id}",
                     "X-Requested-With": "XMLHttpRequest", "X-CSRF-TOKEN": token},
        )
        if resp.status_code == 200:
            _hanime_save_cred(_hanime_sync_cookies(_hanime_load_cred()))
            emit({"event": "hanime_save_result", "success": True, "saved": saved,
                  "video_id": video_id,
                  "message": "已加入稍後觀看" if saved else "已取消收藏"})
        else:
            emit({"event": "hanime_save_result", "success": False, "saved": not saved,
                  "message": f"操作失败: HTTP {resp.status_code}"})
    except Exception as exc:
        emit({"event": "hanime_save_result", "success": False, "saved": not saved,
              "message": f"操作失败: {exc}"})


# 用户中心各 tab 对应的路径后缀（官网账号功能）
HANIME_USER_TABS = {
    "history": ("histories", "觀看紀錄"),
    "saves": ("saves", "稍後觀看"),
    "likes": ("likes", "讚好的影片"),
    "uploaded": ("uploaded", "上傳的影片"),
    "uploading": ("uploading", "審核中的影片"),
}


async def hanime_user_videos(tab: str, page: int = 1) -> None:
    """用户中心的视频列表（觀看紀錄/稍後觀看/讚好的影片/上傳的影片/審核中的影片）。"""
    cred = _hanime_load_cred()
    uid = cred.get("user_id") or ""
    tab = tab or "saves"
    path, label = HANIME_USER_TABS.get(tab, HANIME_USER_TABS["saves"])
    if not uid:
        emit({"event": "hanime_user_videos", "tab": tab, "items": [], "page": 1,
              "has_more": False, "error": "未登录或缺少用户信息：请先登录 Hanime1 账号"})
        return
    emit({"event": "hanime_user_loading", "loading": True})
    try:
        page = max(1, page or 1)
        soup = await asyncio.to_thread(
            _hanime_soup, f"/user/{uid}/{path}", {"page": page})
        items = _hanime_parse_cards(soup)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "hanime_user_videos", "tab": tab, "items": items,
              "page": page, "has_more": _hanime_has_next(soup),
              "label": f"我的{label}"})
        logging.info("Hanime1 用户列表 %s 第 %d 页: %d 个", tab, page, len(items))
    except Exception as exc:
        emit({"event": "hanime_user_videos", "tab": tab, "items": [], "page": page,
              "has_more": False, "error": f"获取列表失败: {exc}"})
    finally:
        emit({"event": "hanime_user_loading", "loading": False})


async def hanime_batch_download(video_ids: list, options: dict) -> None:
    """批量下载 Hanime1 视频（逐个解析详情取标题，下载时重新解析最高画质直链）。"""
    video_ids = [str(v).strip() for v in (video_ids or []) if str(v).strip()]
    if not video_ids:
        emit({"event": "hanime_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "请先勾选要下载的视频"})
        return
    total = len(video_ids)
    failed: list[str] = []
    items: list[dict] = []
    emit({"event": "hanime_batch_progress", "done": 0, "total": total,
          "message": f"正在解析 {total} 个视频..."})
    try:
        for i, vid in enumerate(video_ids):
            try:
                soup = await asyncio.to_thread(_hanime_soup, "/watch", {"v": vid})
                detail = _hanime_parse_detail(soup, vid)
                title = sanitize_directory_name((detail["title"] or f"hanime_{vid}").strip())
                items.append({
                    "filename": f"{title}.mp4",
                    "size": None,
                    "item_page": f"{HANIME_BASE}/watch?v={vid}",
                    "status": "ok",
                    "thumbnail": "",
                    "media_url": _hanime_best_source(detail["sources"]).get("url") or "",
                    "site": "hanime",
                    "video_id": vid,
                    "post_title": detail["title"] or title,
                    "post_date": detail.get("post_date") or "",
                    "artist": detail.get("uploader") or "",
                })
            except Exception as exc:
                failed.append(f"{vid}（{exc}）")
                logging.warning("Hanime1 视频 %s 解析失败: %s", vid, exc)
            emit({"event": "hanime_batch_progress", "done": i + 1, "total": total,
                  "message": f"解析进度 {i + 1}/{total}"})
        if items:
            album = "Hanime1 批量下载" if len(items) > 1 else (items[0].get("post_title") or "Hanime1")
            task_id = download_manager.submit(
                f"{HANIME_BASE}/", items, options, album, "hanime_batch",
            )
            download_manager.start(task_id)
        summary = f"批量下载已提交：{len(items)}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "hanime_batch_done", "done": len(items), "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "hanime_batch_done", "done": len(items), "total": total,
              "failed": failed, "message": f"批量下载中断: {exc}"})
