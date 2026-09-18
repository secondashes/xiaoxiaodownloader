# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：谷歌邮箱 OAuth。

由 gui_bridge.py 按物理顺序拆出（原行区间 18428-18850），
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
# 谷歌邮箱（OAuth 授权共用凭据源）
# ============================
# 登录判定 cookie：Google 会话核心（SID/HSID/SSID 任一 + SAPISID 即视为已登录）
_GOOGLE_AUTH_COOKIES = ("SID", "HSID", "SSID")


def google_save_cred(email: str, password: str) -> None:
    """保存谷歌邮箱账号密码（cookie 保留不动；供内置浏览器登录时自动预填凭据）。
    同时把账号密码 upsert 进多账号列表（accounts），支持前端切换/复制/删除。"""
    email = (email or "").strip()
    if not email:
        emit({"event": "site_login_result", "site": "google", "logged_in": False,
              "message": "请输入谷歌邮箱地址"})
        return
    cred = _secure_store_read_cred("google")
    cred["email"] = email
    if password:
        cred["password"] = password
    cred["cred_saved_at"] = time.time()
    # 多账号列表：同邮箱覆盖更新，不同邮箱追加
    accounts = list(cred.get("accounts") or [])
    if password:
        accounts = [a for a in accounts if (a.get("email") or "").lower() != email.lower()]
        accounts.append({"email": email, "password": password, "saved_at": time.time()})
        accounts.sort(key=lambda a: a.get("saved_at") or 0)
        cred["accounts"] = accounts
    elif not any((a.get("email") or "").lower() == email.lower() for a in accounts):
        accounts.append({"email": email, "password": "", "saved_at": time.time()})
        cred["accounts"] = accounts
    _secure_store_write_cred("google", cred)
    cookies = cred.get("cookies") or {}
    logged_in = _google_has_auth(cookies)
    emit({
        "event": "site_login_result",
        "site": "google",
        "logged_in": logged_in,
        "username": email,
        "cookie_count": len(cookies),
        "message": "谷歌邮箱账号密码已保存" + ("（cookie 已就绪，可给其他网站授权）" if logged_in else ""),
    })
    logging.info("谷歌邮箱凭据已保存: %s", email)
    _emit_login_info()


def google_switch_account(email: str) -> None:
    """切换谷歌邮箱账号：把选中账号的邮箱密码设为当前使用（登录表单/浏览器预填用）。"""
    email = (email or "").strip()
    cred = _secure_store_read_cred("google")
    accounts = list(cred.get("accounts") or [])
    target = next((a for a in accounts if (a.get("email") or "").lower() == email.lower()), None)
    if not target:
        emit({"event": "site_login_result", "site": "google", "logged_in": False,
              "message": "未找到该谷歌账号，请重新保存"})
        return
    cred["email"] = target.get("email") or email
    cred["password"] = target.get("password") or ""
    _secure_store_write_cred("google", cred)
    emit({
        "event": "site_login_result",
        "site": "google",
        "logged_in": _google_has_auth(cred.get("cookies") or {}),
        "username": cred["email"],
        "message": f"已切换谷歌账号：{cred['email']}（下次打开内置浏览器登录时自动预填）",
    })
    _emit_login_info()


def google_delete_account(email: str) -> None:
    """删除谷歌邮箱账号记录（不影响当前 cookie 会话）。"""
    email = (email or "").strip()
    cred = _secure_store_read_cred("google")
    accounts = [a for a in (cred.get("accounts") or [])
                if (a.get("email") or "").lower() != email.lower()]
    cred["accounts"] = accounts
    # 删除的是当前账号时清空当前邮箱密码（cookie 保留）
    if (cred.get("email") or "").lower() == email.lower():
        cred["email"] = (accounts[0].get("email") if accounts else "")
        cred["password"] = (accounts[0].get("password") if accounts else "")
    _secure_store_write_cred("google", cred)
    emit({
        "event": "site_login_result",
        "site": "google",
        "logged_in": _google_has_auth(cred.get("cookies") or {}),
        "username": cred.get("email") or "",
        "message": f"已删除谷歌账号记录：{email}",
    })
    _emit_login_info()


def google_check_login(silent: bool = False) -> dict:
    """检查谷歌邮箱登录态（基于 cookie 判定，不做网络请求避免 Google 反爬误判）。"""
    cred = _secure_store_read_cred("google")
    cookies = cred.get("cookies") or {}
    logged_in = _google_has_auth(cookies)
    username = cred.get("email") or ""
    # 静默模式也要推送：前端按 silent 标志抑制提示，只更新界面登录态
    emit({
        "event": "site_login_result",
        "site": "google",
        "silent": silent,
        "logged_in": logged_in,
        "username": username,
        "cookie_count": len(cookies),
        "message": "谷歌邮箱已登录: " + username if logged_in else "谷歌邮箱未登录（请使用内置浏览器登录）",
    })
    return {"logged_in": logged_in, "username": username, "cookie_count": len(cookies)}


def _google_has_auth(cookies: dict) -> bool:
    """Google 登录判定：会话 cookie（SID/HSID/SSID）+ SAPISID 同时存在。"""
    has_session = any(name in cookies for name in _GOOGLE_AUTH_COOKIES)
    return has_session and "SAPISID" in cookies


def google_get_cred() -> dict:
    """读取谷歌邮箱凭据（email/password/cookies），给前端预填和 webview 注入用。"""
    return _secure_store_read_cred("google")


def _emit_login_info() -> None:
    accounts = _load_accounts()
    pa_cookies = {c.name: c.value for c in _pawchive_session.cookies}
    tw = _twitter_load_cookies()
    ex = _exhentai_load_cookies()
    sites: dict = {}
    for site, logged_in, cookie_str in (
        ("twitter", bool(tw.get("auth_token")), _twitter_cookie_str()),
        ("exhentai", bool(ex.get("ipb_member_id")), _exhentai_cookie_str()),
        ("pawchive", bool(pa_cookies.get("session")), "; ".join(f"{k}={v}" for k, v in pa_cookies.items())),
        ("iwara", bool(_iwara_load_token().get("user_token")), _iwara_load_token().get("user_token") or ""),
        ("hanime", bool(_hanime_load_cred().get("cookies")), _site_cookie_str("hanime")),
        ("pixiv", bool(_pixiv_load_cred().get("refresh_token")), _site_cookie_str("pixiv")),
        ("asmr", bool(_asmr_load_cred().get("token")), _site_cookie_str("asmr")),
        ("xhamster", bool(_generic_load_cookies("xhamster").get("cookies")), _generic_cookie_str("xhamster")),
        ("pornhub", bool(_generic_load_cookies("pornhub").get("cookies")), _generic_cookie_str("pornhub")),
        ("xvideos", bool(_generic_load_cookies("xvideos").get("cookies")), _generic_cookie_str("xvideos")),
        ("javdb", bool(_javdb_load_cred().get("cookies")), _javdb_load_cred().get("cookie_str") or ""),
        ("google", _google_has_auth(_generic_load_cookies("google").get("cookies") or {}), _generic_cookie_str("google")),
        ("oreno3d", bool(_generic_load_cookies("oreno3d").get("cookies")), _generic_cookie_str("oreno3d")),
        ("erommdtube", bool(_generic_load_cookies("erommdtube").get("cookies")), _generic_cookie_str("erommdtube")),
        ("fc2", bool(_generic_load_cookies("fc2").get("cookies")), _generic_cookie_str("fc2")),
    ):
        entry = accounts.get(site) or {}
        try:
            _site_uname = _site_username(site)
        except Exception:  # 单站故障不允许杀死整次登录信息推送（后端曾因此整进程退出）
            logging.exception("获取 %s 用户名失败（置空继续）", site)
            _site_uname = ""
        sites[site] = {
            "logged_in": logged_in,
            "username": _site_uname,
            "cookie_str": cookie_str,
            "accounts": entry.get("profiles") or {},
            "active": entry.get("active") or "",
        }
    # O3D / E站：用户名 = 保存的账号（凭据库），并回填账号密码供登录表单预填
    for _o_site in ("oreno3d", "erommdtube"):
        o_cred = _secure_store_read_cred(_o_site)
        if o_cred.get("email"):
            if sites.get(_o_site):
                sites[_o_site]["username"] = o_cred["email"]
                sites[_o_site]["email"] = o_cred["email"]
            if o_cred.get("password") and sites.get(_o_site):
                sites[_o_site]["password"] = o_cred["password"]
    # 全站登录套件：回填保存的账号密码（登录表单预填 + 内置浏览器登录页自动预填）
    for _s_site in ("pawchive", "twitter", "exhentai", "iwara", "hanime", "pixiv", "asmr",
                    "xhamster", "pornhub", "xvideos"):
        _s_cred = _secure_store_read_cred(_s_site)
        _s_user = _s_cred.get(_SITE_CRED_USER_FIELD.get(_s_site, "email")) or ""
        if _s_user and sites.get(_s_site):
            sites[_s_site]["email"] = _s_user
            if _s_cred.get("password"):
                sites[_s_site]["password"] = _s_cred["password"]
    # 谷歌邮箱：用户名 = 保存的邮箱（凭据库）+ 多账号列表（切换/复制/删除）
    g_cred = _secure_store_read_cred("google")
    if g_cred.get("email"):
        sites["google"]["username"] = g_cred["email"]
    sites["google"]["accounts"] = list(g_cred.get("accounts") or [])
    # JavDB：回填保存的账号密码（前端登录表单预填）
    j_cred = _javdb_load_cred()
    if j_cred.get("email"):
        sites["javdb"]["email"] = j_cred["email"]
        if j_cred.get("password"):
            sites["javdb"]["password"] = j_cred["password"]
    emit({"event": "login_info", "sites": sites})


def save_account(site: str, label: str = "") -> None:
    """把当前登录信息保存为账号档案（多账号记录，长期持久化）。"""
    cookie_str = _site_cookie_str(site)
    if not cookie_str:
        emit({"event": "account_error", "message": "当前站点没有可保存的登录信息"})
        return
    accounts = _load_accounts()
    entry = accounts.setdefault(site, {"active": "", "profiles": {}})
    profiles = entry.setdefault("profiles", {})
    name = (label or _site_username(site) or "").strip() or f"账号{len(profiles) + 1}"
    profile = {
        "label": name,
        "username": _site_username(site),
        "cookie_str": cookie_str,
        "saved_at": time.time(),
    }
    # Iwara：连密码一起存进档案（加密存储），切换账号后 token 过期也能自动续期
    if site == "iwara":
        iw_cred = _iwara_load_token()
        profile["password"] = iw_cred.get("password") or ""
        profile["email"] = iw_cred.get("email") or profile["username"]
    # Hanime1：连邮箱密码一起存进档案（加密存储），切换账号后会话失效也能自动重登
    if site == "hanime":
        ha_cred = _hanime_load_cred()
        profile["password"] = ha_cred.get("password") or ""
        profile["email"] = ha_cred.get("email") or profile["username"]
        profile["hanime_cred"] = {
            "email": ha_cred.get("email") or "",
            "password": ha_cred.get("password") or "",
            "username": ha_cred.get("username") or "",
            "user_id": ha_cred.get("user_id") or "",
            "cookies": ha_cred.get("cookies") or {},
        }
    # Pixiv：连邮箱密码一起存进档案（加密存储），切换账号后 PHPSESSID 失效也能自动重登
    if site == "pixiv":
        px_cred = _pixiv_load_cred()
        profile["password"] = px_cred.get("password") or ""
        profile["email"] = px_cred.get("email") or profile["username"]
        profile["pixiv_cred"] = {
            "email": px_cred.get("email") or "",
            "password": px_cred.get("password") or "",
            "username": px_cred.get("username") or "",
            "user_id": px_cred.get("user_id") or "",
            "cookies": px_cred.get("cookies") or {},
        }
    # ASMR：token + 用户名密码一起存进档案（加密存储），切换后失效也能自动重登
    if site == "asmr":
        as_cred = _asmr_load_cred()
        profile["password"] = as_cred.get("password") or ""
        profile["username"] = as_cred.get("username") or profile["username"]
        profile["asmr_cred"] = dict(as_cred)
    profiles[name] = profile
    entry["active"] = name
    _save_accounts(accounts)
    emit({"event": "account_saved", "message": f"已保存账号档案: {name}"})
    logging.info("已保存 %s 账号档案: %s", site, name)
    _emit_login_info()


def _writeback_iwara_profile(site: str, label: str) -> None:
    """把当前 Iwara 凭据（密码/用户名/邮箱）回写进账号档案（旧档案自动补全密码）。"""
    if site != "iwara" or not label:
        return
    try:
        accounts = _load_accounts()
        profile = (accounts.get("iwara") or {}).get("profiles", {}).get(label)
        cred = _iwara_load_token()
        if profile and cred.get("password"):
            profile.setdefault("password", "")
            if not profile.get("password"):
                profile["password"] = cred.get("password")
            if not profile.get("email") and cred.get("email"):
                profile["email"] = cred.get("email")
            if not profile.get("username") and cred.get("username"):
                profile["username"] = cred.get("username")
            _save_accounts(accounts)
    except Exception:
        pass


def switch_account(site: str, label: str) -> None:
    """切换到已保存的账号档案（写入站点登录文件并重新验证登录）。"""
    accounts = _load_accounts()
    profiles = (accounts.get(site) or {}).get("profiles") or {}
    profile = profiles.get(label)
    if not profile:
        emit({"event": "account_error", "message": f"账号档案不存在: {label}"})
        return
    cookie_str = profile.get("cookie_str") or ""
    accounts.setdefault(site, {})["active"] = label
    _save_accounts(accounts)
    if site == "twitter":
        twitter_set_cookies(cookie_str)
    elif site == "leakedzone":
        # 过盾会话重灌（cookie+已存档 UA，cf_clearance 与 UA/IP 绑定）后重新验证
        leakedzone_set_cookies(cookie_str)
        leakedzone_check_login(True)
    elif site == "exhentai":
        exhentai_set_cookies(cookie_str)
    elif site == "pawchive":
        pawchive_set_cookies(cookie_str, profile.get("username") or label)
    elif site == "iwara":
        # 旧档案可能没存密码/邮箱：保留现存的密码，避免覆盖成空导致自动续期失效
        old_cred = _iwara_load_token()
        _iwara_save_token({
            "user_token": cookie_str,
            "email": profile.get("email") or old_cred.get("email") or profile.get("username") or label,
            "username": profile.get("username") or label,
            "password": profile.get("password") or old_cred.get("password") or "",
        })
        _emit_login_info()
        emit({"event": "iwara_login_result", "success": True, "silent": True,
              "username": profile.get("username") or label, "message": "账号档案已恢复"})
        # 档案恢复后验证登录（token 过期时用档案里的密码自动续期），
        # 验证成功后把密码/用户名回写进档案，旧档案从此也自带密码
        iwara_check_login(silent=True)
        _writeback_iwara_profile(site, label)
    elif site == "hanime":
        # 恢复完整凭据（cookies + 邮箱密码），会话失效时自动重登
        cred = dict(profile.get("hanime_cred") or {})
        cred.setdefault("cookies", {})
        if not cred.get("cookies") and cookie_str:
            # 旧档案只有 cookie 字符串：解析回字典
            cred["cookies"] = {
                p.split("=", 1)[0]: p.split("=", 1)[1]
                for p in cookie_str.split("; ") if "=" in p
            }
        if not cred.get("password") and profile.get("password"):
            cred["password"] = profile.get("password")
        if not cred.get("email") and profile.get("email"):
            cred["email"] = profile.get("email")
        cred["username"] = profile.get("username") or cred.get("username") or label
        _hanime_save_cred(cred)
        _hanime_session.cookies.clear()
        _hanime_restore_session()
        _hanime_set_username(cred.get("username") or "")
        _emit_login_info()
        emit({"event": "hanime_login_result", "success": True, "silent": True,
              "username": cred.get("username") or label, "message": "账号档案已恢复"})
        hanime_check_login(silent=True)
    elif site == "pixiv":
        # 恢复完整凭据（cookies + 邮箱密码），PHPSESSID 失效时自动重登
        cred = dict(profile.get("pixiv_cred") or {})
        cred.setdefault("cookies", {})
        if not cred.get("cookies") and cookie_str:
            # 旧档案只有 cookie 字符串：解析回字典
            cred["cookies"] = {
                p.split("=", 1)[0]: p.split("=", 1)[1]
                for p in cookie_str.split("; ") if "=" in p
            }
        if not cred.get("password") and profile.get("password"):
            cred["password"] = profile.get("password")
        if not cred.get("email") and profile.get("email"):
            cred["email"] = profile.get("email")
        cred["username"] = profile.get("username") or cred.get("username") or label
        _pixiv_save_cred(cred)
        _pixiv_session.cookies.clear()
        _pixiv_restore_session()
        _pixiv_set_username(cred.get("username") or "")
        _emit_login_info()
        emit({"event": "pixiv_login_result", "success": True, "silent": True,
              "username": cred.get("username") or label, "user_id": cred.get("user_id") or "",
              "message": "账号档案已恢复"})
        pixiv_check_login(silent=True)
    elif site == "asmr":
        # 恢复完整凭据（token + 用户名密码），token 过期时自动重登
        cred = dict(profile.get("asmr_cred") or {})
        if not cred.get("token") and cookie_str:
            cred["token"] = cookie_str
        if not cred.get("password") and profile.get("password"):
            cred["password"] = profile.get("password")
        if not cred.get("username"):
            cred["username"] = profile.get("username") or label
        _asmr_save_cred(cred)
        _asmr_set_state(cred.get("token") or "", cred.get("username") or "")
        _emit_login_info()
        emit({"event": "asmr_login_result", "success": True, "silent": True,
              "username": cred.get("username") or "", "message": "账号档案已恢复"})
        asmr_check_login(silent=True)
    elif site in _GENERIC_OAUTH_SITES and site != "google":
        # 通用 webview 站点（xhamster/pornhub/xvideos/oreno3d/erommdtube/fc2）：
        # 恢复档案 cookie 到凭据库并重放请求会话
        _generic_save_cookies(site, cookie_str)
        if site == "fc2":
            _fc2_restore_session()
            fc2_check_login(silent=True)
        _emit_login_info()
    else:
        _emit_login_info()
        return
    logging.info("已切换 %s 账号: %s", site, label)


def delete_account(site: str, label: str) -> None:
    """删除账号档案（不影响当前登录状态）。"""
    accounts = _load_accounts()
    entry = accounts.get(site)
    if entry and (entry.get("profiles") or {}).pop(label, None) is not None:
        if entry.get("active") == label:
            entry["active"] = ""
        _save_accounts(accounts)
        emit({"event": "account_saved", "message": f"已删除账号档案: {label}"})
        logging.info("已删除 %s 账号档案: %s", site, label)
    _emit_login_info()


def _load_login_state() -> dict:
    try:
        data = json.loads(Path(LOGIN_STATE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_login_state(state: dict) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(LOGIN_STATE_FILE).write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError:
        pass


def _cookie_fingerprint(site: str) -> str:
    cookie_str = _site_cookie_str(site)
    return hashlib.md5(cookie_str.encode("utf-8")).hexdigest() if cookie_str else ""


def _record_login_ok(site: str) -> None:
    """登录验证成功时记录当前 cookie 指纹（用于失效原因判断）。"""
    state = _load_login_state()
    state[site] = {"ok_hash": _cookie_fingerprint(site), "ok_at": time.time()}
    _save_login_state(state)


def _login_network_issue(site: str) -> bool:
    """登录检查失败时判断是否为网络问题：

    当前 cookie 与上次成功登录时一致 → 网络问题（登录信息没变，只是连不上）；
    不一致 → 登录信息已被更换/失效，提示用户重新检查 Cookie。
    """
    state = _load_login_state()
    ok_hash = (state.get(site) or {}).get("ok_hash") or ""
    if not ok_hash:
        return False
    return _cookie_fingerprint(site) == ok_hash
