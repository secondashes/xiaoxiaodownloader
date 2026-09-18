# -*- coding: utf-8 -*-
"""Leakedzone 站点模块（综合资源站点家族）。

状态（2026-09-13）：**Cloudflare "Just a moment" JS 挑战**——纯后端 requests
无法过盾（完整浏览器头族同样 403）。本模块为 cookie 会话骨架：
- 过盾后的 cookie 存 cache/leakedzone_cookies.json（由内置浏览器登录套件写入，
  套件 UI 接线下一轮完成）；
- 未过盾/cookie 失效：inspect/search 明确报错引导先登录；
- 过盾后：按 WordPress 文章网格通用解析（article 链接+图片 → 模型/帖子条目），
  结构细节需以真实过盾页面调优（标记 ⬜）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（requests/emit/…；注册后本行必需）

import asyncio
import json
import logging
import re
import time
from pathlib import Path

# ============================
# 0. 站点标识
# ============================
LZ_SITE_KEY = "leakedzone"
LZ_SITE_NAME = "Leakedzone"

LZ_BASE = "https://leakedzone.com"
# UA 必须与内置浏览器 webview 完全一致：cf_clearance 绑定 UA，不一致过盾 cookie 直接失效。
# Electron 44 ≈ Chrome/146（自洽新引擎——2026-09 已从 Electron 30/Chrome 124 升级，
# 旧引擎指纹过不了 CF 深层检测）。过盾后 set_cookies 回传的精确 UA 会覆盖此初始值。
LZ_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
LZ_DEFAULT_PROXY = "http://127.0.0.1:10809"
LZ_COOKIES_FILE = "cache/leakedzone_cookies.json"

# ============================
# 1. 会话 / cookie / 代理
# ============================
_lz_session = requests.Session()  # noqa: F821
_lz_session.headers.update({"User-Agent": LZ_UA})
_lz_session.proxies = {"http": LZ_DEFAULT_PROXY, "https": LZ_DEFAULT_PROXY}


def leakedzone_set_proxy(proxy: str) -> None:
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    _lz_session.proxies = proxies


def leakedzone_set_cookies(cookie_str: str, user_agent: str = "", silent: bool = False) -> None:
    """内置浏览器登录套件写入的 cookie 串（cf_clearance 等）→ 会话 + 落盘。

    user_agent：webview 过盾时的实际 UA——cf_clearance 与 UA 强绑定，
    后续 requests 必须用同一 UA，否则盾 cookie 无效（403）。
    """
    cookie_str = (cookie_str or "").strip()
    if not cookie_str:
        return
    ua = (user_agent or "").strip()
    if ua:
        _lz_session.headers.update({"User-Agent": ua})
        try:
            Path("cache").mkdir(exist_ok=True)
            Path("cache/leakedzone_ua.txt").write_text(ua, encoding="utf-8")
        except OSError:
            pass
    _lz_session.cookies.update(dict(
        (k.strip(), v.strip())
        for k, v in (pair.split("=", 1) for pair in cookie_str.split(";") if "=" in pair)
    ))
    try:
        Path("cache").mkdir(exist_ok=True)
        Path(LZ_COOKIES_FILE).write_text(cookie_str, encoding="utf-8")
    except OSError:
        pass
    emit({"event": "account_saved", "message": "Leakedzone Cookie 已保存（过盾会话生效）",
          "silent": silent})  # noqa: F821


def _lz_restore_cookies() -> None:
    try:
        cookie_str = Path(LZ_COOKIES_FILE).read_text(encoding="utf-8").strip()
        if cookie_str:
            # 启动自动恢复：silent=True，不弹"Cookie 已保存"提醒（避免旁人看到内部信息）
            leakedzone_set_cookies(cookie_str, silent=True)
    except OSError:
        pass
    try:
        ua = Path("cache/leakedzone_ua.txt").read_text(encoding="utf-8").strip()
        if ua:
            _lz_session.headers.update({"User-Agent": ua})
    except OSError:
        pass


_lz_restore_cookies()


def _lz_get(path: str) -> str | None:
    _lz_throttle()
    try:
        r = _lz_session.get(f"{LZ_BASE}{path}", timeout=30)
    except Exception as exc:
        logging.warning("Leakedzone GET %s 失败: %s", path, exc)
        return None
    if r.status_code == 403 or "Just a moment" in r.text[:2000]:
        emit({"event": "inspect_error", "message":  # noqa: F821
              "Leakedzone 需要先过 Cloudflare 盾：请点左侧「打开内置浏览器登录」，"
              "在弹窗内等页面加载完成后关闭，再重试"})
        return None
    if r.status_code != 200:
        logging.warning("Leakedzone GET %s: HTTP %s", path, r.status_code)
        return None
    return r.text


_lz_last_ts = 0.0


def _lz_throttle(min_interval: float = 1.0) -> None:
    global _lz_last_ts
    now = time.time()
    wait = _lz_last_ts + min_interval - now
    if wait > 0:
        time.sleep(wait)
    _lz_last_ts = time.time()


def _lz_gs_emit(state: dict) -> None:
    emit({"event": "gs_state", "site": LZ_SITE_KEY, **state})  # noqa: F821


def _lz_parse_creators(html: str) -> list[dict]:
    """解析 /creators 卡片网格（真实 SSR 结构，2026-09-14 实测）：

    <a href="https://leakedzone.com/{slug}" ...>
      <img src="https://image-cdn.leakedzone.com/storage/models/{id}/avatar.jpg" alt="{名字}">
      <div class="font-bold ...">{名字}</div>
      <div ...>&commat;{handle}</div>
      <div ...>{views} views</div></a>
    """
    items: list[dict] = []
    seen: set = set()
    for m in re.finditer(
            r'<a\s+href="https://leakedzone\.com/([^"/?#]+)"[^>]*>([\s\S]{0,1500}?)</a>', html or ""):
        slug, block = m.group(1), m.group(2)
        if slug in seen or slug in ("premium", "user", "request-model"):
            continue
        av = re.search(r'(https://image-cdn\.leakedzone\.com/storage/models/\d+/avatar\.\w+)', block)
        if not av:
            continue
        seen.add(slug)
        name_m = re.search(r'class="font-bold[^"]*"[^>]*>([^<]+)<', block)
        handle_m = re.search(r'&commat;([^<\s]+)', block)
        views_m = re.search(r'>([\d\.]+[KM]?\s*views)<', block)
        name = (name_m.group(1) if name_m else slug).strip()
        items.append({
            "kind": "creator", "video_id": slug,
            "album_name": name,
            "author": f"@{handle_m.group(1)}" if handle_m else "",
            "album_url": f"{LZ_BASE}/{slug}",
            "detail_path": f"/{slug}",
            "thumbnail": av.group(1),
            "posted": views_m.group(1).replace(" ", "") if views_m else "",
            "site": LZ_SITE_KEY,
        })
    return items


def _lz_parse_photo_files(html: str, slug: str) -> list[dict]:
    """解析创作者照片网格：image-cdn .../storage/images/.../*_300.webp|thumbnail_300.jpg
    全尺寸 = 文件名去掉 _300（_300 是 CDN 缩略后缀，实测去后缀即原图）。"""
    files: list[dict] = []
    seen: set = set()
    thumbs = re.findall(r'(https://image-cdn\.leakedzone\.com/storage/images/[^"\s]+)', html or "")
    for idx, thumb in enumerate(thumbs, 1):
        full = re.sub(r'_300(\.\w+)$', r'\1', thumb)
        if full in seen:
            continue
        seen.add(full)
        fname = full.rsplit("/", 1)[-1]
        files.append({
            "media_url": full,
            "filename": f"{slug}_{idx:03d}_{fname}",
            "media_type": "image",
            "site": LZ_SITE_KEY,
        })
    return files


# ============================
# 2. GS 命令（home / search / open-detail / download-files）
# ============================
async def _lz_cmd_home(command: dict) -> None:
    page = max(1, int(command.get("page") or 1))
    _lz_gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    suffix = f"/creators?page={page}" if page > 1 else "/creators"
    html = await asyncio.to_thread(_lz_get, suffix)
    items = _lz_parse_creators(html or "") if html else []
    _lz_gs_emit({
        "view": "list", "items": items, "page": page,
        "hasMore": len(items) >= 10,
        "error": "" if items else "需要过 Cloudflare 盾：点左侧「用系统 Edge 过盾登录」后重试",
        "label": f"创作者列表 第{page}页",
    })


async def _lz_cmd_search(command: dict) -> None:
    query = str(command.get("query") or command.get("keyword") or "").strip()
    _lz_gs_emit({"view": "list", "items": [], "loading": True, "page": 1})
    if not query:
        _lz_gs_emit({"view": "list", "items": [], "page": 1, "error": "请输入关键词搜索"})
        return
    from urllib.parse import quote
    html = await asyncio.to_thread(_lz_get, f"/creators?search={quote(query)}")
    items = _lz_parse_creators(html or "") if html else []
    _lz_gs_emit({"view": "list", "items": items, "page": 1, "hasMore": False,
                 "error": "" if items else "没有匹配的创作者",
                 "label": f"「{query}」搜索"})


async def _lz_cmd_open_detail(command: dict) -> None:
    """点创作者卡片 → 详情：/photo 页前 2 页图片（全尺寸直链，可下载）。"""
    item = command.get("item") or {}
    slug = str(item.get("video_id") or item.get("detail_path") or "").strip().strip("/")
    if not slug:
        _lz_gs_emit({"view": "detail", "error": "缺少创作者标识"})
        return
    name = str(item.get("album_name") or slug)
    _lz_gs_emit({
        "view": "detail",
        "detail": {"album_name": f"{name}（照片）", "album_url": f"{LZ_BASE}/{slug}",
                   "author": item.get("author") or "", "tags": [], "is_sample": False},
        "files": [], "loading": True,
    })
    files: list[dict] = []
    for page in (1, 2):
        html = await asyncio.to_thread(_lz_get, f"/{slug}/photo?page={page}")
        if html:
            files.extend(_lz_parse_photo_files(html, slug))
        if len(files) >= 96:
            break
    note = "（视频走外站播放器，暂不支持）" if files else ""
    _lz_gs_emit({
        "view": "detail",
        "detail": {"album_name": f"{name}（照片 {len(files)}）{note}",
                   "album_url": f"{LZ_BASE}/{slug}",
                   "author": item.get("author") or "", "tags": [], "is_sample": False},
        "files": files, "loading": False,
        "error": "" if files else "没有解析到照片（需要过盾会话，请先用左侧 Edge 过盾登录）",
    })


async def _lz_cmd_download_files(command: dict) -> None:
    files = [f for f in (command.get("files") or []) if isinstance(f, dict) and f.get("media_url")]
    if not files:
        _lz_gs_emit({"view": "list", "error": "没有可下载的文件"})
        return
    task_id = download_manager.submit(  # noqa: F821
        f"{LZ_BASE}/", files, command.get("options") or {},
        "Leakedzone 下载", "leakedzone",
    )
    download_manager.start(task_id)  # noqa: F821
    _lz_gs_emit({"view": "list", "message": f"下载已提交：{len(files)} 个文件"})


async def leakedzone_check_login(silent: bool = False) -> None:
    """检查过盾会话：GET 主页 200=过盾有效 / 403=需重新过盾 / 网络异常。"""
    _lz_throttle()
    try:
        r = _lz_session.get(LZ_BASE + "/", timeout=20)
    except Exception as exc:
        emit({"event": "site_login_result", "site": LZ_SITE_KEY, "silent": silent,  # noqa: F821
              "logged_in": False, "username": "", "network_issue": True,
              "message": f"Leakedzone 检查异常（网络/代理）：{exc}"})
        return
    if r.status_code == 200 and "Just a moment" not in r.text[:2000]:
        emit({"event": "site_login_result", "site": LZ_SITE_KEY, "silent": silent,  # noqa: F821
              "logged_in": True, "username": "已过盾",
              "message": "Leakedzone 过盾会话有效"})
    else:
        emit({"event": "site_login_result", "site": LZ_SITE_KEY, "silent": silent,  # noqa: F821
              "logged_in": False, "username": "",
              "message": "Leakedzone 需要过 Cloudflare 盾：点「打开内置浏览器登录」等页面加载完成后确认"})


async def _lz_cmd_set_cookies(command: dict) -> None:
    await asyncio.to_thread(
        leakedzone_set_cookies,
        str(command.get("cookie_str") or command.get("cookies") or ""),
        str(command.get("user_agent") or ""))


LZ_SITE_COMMANDS = {
    "leakedzone_home": _lz_cmd_home,
    "leakedzone_load-more": _lz_cmd_home,   # GSV「加载更多」：同 home 按 page 抓（前端负责追加去重）
    "leakedzone_search": _lz_cmd_search,
    "leakedzone_open_detail": _lz_cmd_open_detail,
    "leakedzone_download_files": _lz_cmd_download_files,
    "leakedzone_check_login": lambda command: asyncio.to_thread(
        leakedzone_check_login, bool(command.get("silent", False))),
    "leakedzone_set_cookies": lambda command: _lz_cmd_set_cookies(command),
}
