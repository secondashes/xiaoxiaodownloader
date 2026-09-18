# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：GitHub 更新检查。

由 gui_bridge.py 按物理顺序拆出（原行区间 17036-17350），
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
# GitHub 仓库更新检查（公开发布仓库，匿名可访问：更新检查 + 更新日志 + Release 安装包）
# ============================
GITHUB_REPO = "secondashes/xiaoxiaodownloader"
GITHUB_LAST_SHA_FILE = "cache/github_last_sha.json"
# 发布仓库（更新日志 + 版本安装包）：secondashes/xiaoxiao-release
GITHUB_RELEASE_REPO = "secondashes/xiaoxiaodownloader"
GITHUB_CHANGELOG_URL = (
    "https://raw.githubusercontent.com/"
    + GITHUB_RELEASE_REPO
    + "/main/"
    + urllib.parse.quote("更新日志.md")
)
# 更新日志备用地址（jsDelivr CDN：国内可直连，raw.githubusercontent.com 被墙时的回退）
GITHUB_CHANGELOG_FALLBACK_URL = (
    "https://cdn.jsdelivr.net/gh/"
    + GITHUB_RELEASE_REPO
    + "@main/"
    + urllib.parse.quote("更新日志.md")
)


def _github_last_sha() -> str:
    try:
        with Path(GITHUB_LAST_SHA_FILE).open("r", encoding="utf-8") as f:
            return json.load(f).get("sha") or ""
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""


def _github_save_last_sha(sha: str) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with Path(GITHUB_LAST_SHA_FILE).open("w", encoding="utf-8") as f:
            json.dump({"sha": sha, "checked_at": int(time.time())}, f, ensure_ascii=False)
    except OSError as exc:
        logging.warning("保存 GitHub last_sha 失败: %s", exc)


def _version_tuple(v: str) -> tuple:
    """把版本字符串（如 v1.2.21 / 1.2.21 / 1.2）解析为可比较的数字元组。"""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0, 0, 0)


def check_github_update(current_version: str = "") -> None:
    """检查 GitHub 仓库 secondashes/xiaoxiaodownloader 的 main 分支最新 commit 与最新 release。

    国内访问 api.github.com 需走代理（github_proxy 设置）。成功 emit 'github_update_info'。
    current_version：当前程序版本号（前端从 Electron app.getVersion() 取来），
    与最新 release tag 比较生成 has_new_release（有新版安装包可下载）。
    """
    s = _load_settings()
    proxy = _github_proxy_cfg()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0",
        "Accept": "application/vnd.github+json",
    }
    # 1. 拉取 main 分支最新 commit（带 cache-busting 头避免 CDN 缓存）
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=20)
        if resp.status_code != 200:
            emit({
                "event": "github_update_info",
                "ok": False,
                "error": f"GitHub 返回 HTTP {resp.status_code}",
            })
            return
        data = resp.json()
    except Exception as exc:
        emit({
            "event": "github_update_info",
            "ok": False,
            "error": f"网络请求失败：{exc}",
        })
        return
    sha = data.get("sha") or ""
    commit = data.get("commit") or {}
    message = (commit.get("message") or "").strip()
    date = commit.get("author", {}).get("date") or data.get("commit", {}).get("committer", {}).get("date", "")
    author = (commit.get("author") or {}).get("name") or (data.get("author") or {}).get("login", "")
    html_url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/commit/{sha}"

    # 2. 拉取最新 release（无 release 时 fallback 到 commit）
    latest_release: dict = {}
    try:
        r2 = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers=headers, proxies=proxies, timeout=15,
        )
        if r2.status_code == 200:
            latest_release = r2.json() or {}
    except Exception:
        pass  # 无 release 不算错误

    # 3. 对比本地记录的 sha
    local_sha = _github_last_sha()
    has_update = bool(sha) and (sha != local_sha)

    # 4. release 安装包更新判定：最新 release tag 版本 > 当前程序版本
    release_tag = latest_release.get("tag_name") or ""
    # 找到 release 里的安装包附件（.exe），供前端直接下载
    release_assets = []
    for asset in (latest_release.get("assets") or []):
        a_name = asset.get("name") or ""
        if a_name.lower().endswith(".exe"):
            release_assets.append({
                "name": a_name,
                "url": asset.get("browser_download_url") or "",
                "size": asset.get("size") or 0,
            })
    has_new_release = bool(release_tag and release_assets) and (
        _version_tuple(release_tag) > _version_tuple(current_version)
    )

    emit({
        "event": "github_update_info",
        "ok": True,
        "current_version": current_version or "",
        "latest_sha": sha,
        "latest_message": message,
        "latest_date": date,
        "latest_author": author,
        "latest_url": html_url,
        "local_sha": local_sha,
        "has_update": has_update,
        "has_new_release": has_new_release,
        "is_first_check": not local_sha,
        "release": {
            "tag": release_tag,
            "name": latest_release.get("name") or "",
            "url": latest_release.get("html_url") or "",
            "published_at": latest_release.get("published_at") or "",
            "body": (latest_release.get("body") or "")[:800],
            "assets": release_assets,
        } if latest_release else None,
        "repo_url": f"https://github.com/{GITHUB_REPO}",
        "commits_url": f"https://github.com/{GITHUB_REPO}/commits/main",
    })


# 更新包下载进行中标志（防止重复点击重复下载）
_update_downloading = False


def fetch_changelog(current_version: str = "") -> None:
    """从发布仓库拉取更新日志（更新日志.md），返回比当前版本新的所有版本说明。

    emit 事件 changelog_info：
    - ok: 是否成功
    - versions: [{version, date, lines: [每条更新说明]}] 从新到旧
    - has_new: 是否存在比当前版本新的版本
    """
    s = _load_settings()
    proxy = _github_proxy_cfg()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}
    text = ""
    last_err = ""
    # 尝试顺序：raw.githubusercontent（走设置代理）→ jsDelivr CDN（直连，国内可访问）
    # 注意：jsDelivr 不认代理，仅在 raw 失败且未配置代理时直连尝试（有代理时 raw 一般可成）
    for url, use_proxies in ((GITHUB_CHANGELOG_URL, proxies), (GITHUB_CHANGELOG_FALLBACK_URL, None)):
        try:
            resp = requests.get(url, headers=headers, proxies=use_proxies, timeout=15)
            if resp.status_code == 200:
                text = resp.content.decode("utf-8", errors="replace")
                if text.strip():
                    break
            else:
                last_err = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_err = str(exc)
    if not text.strip():
        emit({
            "event": "changelog_info",
            "ok": False,
            "error": f"更新日志拉取失败（{last_err or '内容为空'}），请检查网络或设置 GitHub 代理",
        })
        return

    # 解析 "## v1.2.25（2026-08-30）" 分节
    versions: list[dict] = []
    cur_ver, cur_date, cur_lines = "", "", []

    def _clean_line(l: str) -> str:
        # 去掉 markdown 列表符号与首尾空白，弹窗里直接显示纯文本
        t = l.strip()
        if t.startswith("- ") or t.startswith("* "):
            t = t[2:].strip()
        elif t in ("-", "*"):
            t = ""
        return t

    for line in text.splitlines():
        m = re.match(r"^##\s+(v[\d.]+)\s*[（(]([^）)]*)[）)]\s*$", line.strip())
        if m:
            if cur_ver:
                versions.append({
                    "version": cur_ver,
                    "date": cur_date,
                    "lines": [c for c in (_clean_line(l) for l in cur_lines) if c],
                })
            cur_ver, cur_date, cur_lines = m.group(1), m.group(2), []
        elif cur_ver:
            # 跳过分隔线与空行
            if line.strip() == "---":
                continue
            cur_lines.append(line)
    if cur_ver:
        versions.append({
            "version": cur_ver,
            "date": cur_date,
            "lines": [c for c in (_clean_line(l) for l in cur_lines) if c],
        })

    if not versions:
        emit({"event": "changelog_info", "ok": False, "error": "更新日志格式异常（未找到版本条目）"})
        return

    cur_tuple = _version_tuple(current_version)
    newer = [v for v in versions if _version_tuple(v["version"]) > cur_tuple]
    # 没有新版时也返回最新一节，供前端展示"当前版本说明"
    result = newer if newer else versions[:1]
    emit({
        "event": "changelog_info",
        "ok": True,
        "current_version": current_version or "",
        "versions": result,
        "has_new": bool(newer),
        "latest_version": versions[0]["version"] if versions else "",
    })


def download_update(url: str, file_name: str = "") -> None:
    """下载 GitHub Release 更新安装包到系统「下载」文件夹（流式 + 进度事件）。

    emit 事件：
    - update_download_progress { received, total, percent, speed, file_name }
    - update_download_done { path, file_name, size }
    - update_download_error { error }
    """
    global _update_downloading
    url = (url or "").strip()
    if not url:
        emit({"event": "update_download_error", "error": "下载地址为空"})
        return
    if _update_downloading:
        emit({"event": "update_download_error", "error": "已有更新包正在下载，请稍候"})
        return
    _update_downloading = True
    try:
        s = _load_settings()
        proxy = _github_proxy_cfg()
        proxies = {"http": proxy, "https": proxy} if proxy else None
        # 保存目录：系统「下载」文件夹，不可用时退回当前目录
        downloads_dir = Path.home() / "Downloads"
        if not downloads_dir.is_dir():
            downloads_dir = Path.cwd()
        name = (file_name or "").strip() or os.path.basename(urlparse(url).path) or "小小下载器安装包.exe"
        dest = downloads_dir / name
        emit({"event": "update_download_progress", "received": 0, "total": 0,
              "percent": 0, "speed": 0, "file_name": name, "path": str(dest), "started": True})
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}
        with requests.get(url, stream=True, proxies=proxies, timeout=(15, 60), headers=headers) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            received = 0
            start = time.time()
            last_emit = 0.0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=512 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    received += len(chunk)
                    now = time.time()
                    if now - last_emit >= 0.5:  # 限频推送进度，避免刷爆事件通道
                        speed = received / max(now - start, 0.001)
                        percent = round(received * 100 / total, 1) if total else 0
                        emit({"event": "update_download_progress", "received": received,
                              "total": total, "percent": percent, "speed": round(speed, 1),
                              "file_name": name, "path": str(dest)})
                        last_emit = now
        emit({"event": "update_download_done", "path": str(dest), "file_name": name,
              "size": received, "total": total})
        logging.info("更新安装包已下载: %s（%.1f MB）", dest, received / 1048576)
    except Exception as exc:
        logging.exception("更新安装包下载失败")
        emit({"event": "update_download_error", "error": f"下载失败：{exc}"})
    finally:
        _update_downloading = False


def open_update_installer(path: str) -> None:
    """运行已下载的更新安装包（NSIS 覆盖安装即更新）。"""
    path = (path or "").strip()
    if not path or not Path(path).is_file():
        emit({"event": "update_download_error", "error": "安装包文件不存在，请重新下载"})
        return
    try:
        os.startfile(path)  # noqa: S606 Windows 默认关联运行 exe
        emit({"event": "update_installer_launched", "path": path})
    except Exception as exc:
        logging.exception("运行更新安装包失败")
        emit({"event": "update_download_error", "error": f"运行安装包失败：{exc}"})


def _github_proxy_cfg() -> str | None:
    """GitHub 更新的代理：github_proxy → common_proxy（通用代理）→ 默认 10809。
    值 off/direct/直连 = 强制直连（用户挂 VPN 场景）。返回 proxies dict 或 None。"""
    s = _load_settings()
    proxy = (s.get("github_proxy") or s.get("common_proxy") or "").strip()
    if proxy.lower() in ("off", "direct", "直连", "none"):
        return None
    if not proxy:
        proxy = "http://127.0.0.1:10809"   # 默认生效（不写死进设置）
    if not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    return {"http": proxy, "https": proxy}


def github_mark_update_done(sha: str) -> None:
    """用户确认已更新（或拉取代码后），把当前 sha 记为本地 last_sha。"""
    _github_save_last_sha((sha or "").strip())
    emit({"event": "github_update_marked", "ok": True, "sha": sha})
