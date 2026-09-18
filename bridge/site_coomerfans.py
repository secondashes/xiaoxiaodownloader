# -*- coding: utf-8 -*-
"""CoomerFans 站点模块（综合资源站点家族；交互逻辑对齐 PA 站）。

考古结论（2026-09-13 真站探针）：
- **反爬**：全站 PoW 挑战（503 + "Checking your browser"）——提取 token/difficulty，
  本地算 SHA-256(token:nonce) 前导零 ≥ difficulty，POST /__bg/verify 种
  bg_clearance cookie 后放行（difficulty=15 时 ~0.01s 解出，纯后端可过）
- 结构：
  - 帖子搜索/最新：GET /post-search?q={kw}&page={N} → 卡片 /p/{cid}/{pid}/{service}
    + 封面 img{N}.coomerfans.com/storage/...
  - 创作者主页：GET /u/{service}/{cid}/{name} → 同款帖子卡片
  - 帖子详情：GET /p/{cid}/{pid}/{service} → 媒体直链 img{N}.coomerfans.com/storage/...
- 媒体（img*.coomerfans.com）：直连 403 → 必须带挑战 cookie + 代理；前端预览与
  下载条目统一经本地媒体代理转发（media_proxy 带 coomerfans 分支）
模块级名字会被 _state.register 注入 bridge 扁平命名空间（跨段引用直接写名字）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（requests/emit/…；注册后本行必需）

import asyncio
import hashlib
import logging
import re
import time

# ============================
# 0. 站点标识
# ============================
CFANS_SITE_KEY = "coomerfans"
CFANS_SITE_NAME = "CoomerFans"

CFANS_BASE = "https://coomerfans.com"
CFANS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CFANS_DEFAULT_PROXY = "http://127.0.0.1:10809"   # 国内直连不通（媒体 403）

# ============================
# 1. 会话 / 代理 / PoW 过盾 / 节流
# ============================
_coomerfans_session = requests.Session()  # noqa: F821
_coomerfans_session.headers.update({"User-Agent": CFANS_UA})
_coomerfans_session.proxies = {"http": CFANS_DEFAULT_PROXY, "https": CFANS_DEFAULT_PROXY}
_coomerfans_last_ts = 0.0


def coomerfans_set_proxy(proxy: str) -> None:
    """设置代理（空 = 直连；默认 10809）。"""
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    _coomerfans_session.proxies = proxies


def _coomerfans_throttle(min_interval: float = 1.0) -> None:
    """全站低频节流：503 限流是频率触发，慢速是硬要求。"""
    global _coomerfans_last_ts
    now = time.time()
    wait = _coomerfans_last_ts + min_interval - now
    if wait > 0:
        time.sleep(wait)
    _coomerfans_last_ts = time.time()


def _coomerfans_pow_solve(html: str) -> dict | None:
    """503 挑战页 → 解 PoW → {token, nonce, url}（解不出返回 None）。"""
    tok = re.search(r'const token = "([^"]+)"', html)
    dif = re.search(r'difficulty =\s*(\d+)', html)
    vurl = re.search(r'url = "([^"]+)"', html)
    if not (tok and dif and vurl):
        return None
    token, difficulty = tok.group(1), int(dif.group(1))
    prefix = f"{token}:".encode()
    nonce = 0
    while True:
        d = hashlib.sha256(prefix + str(nonce).encode()).digest()
        zeros = 0
        for b in d:
            if b == 0:
                zeros += 8
                continue
            zeros += 8 - b.bit_length()
            break
        if zeros >= difficulty:
            return {"token": token, "nonce": str(nonce), "url": vurl.group(1)}
        nonce += 1


def _coomerfans_get(path: str, params: dict | None = None) -> str | None:
    """GET 页面：503 挑战自动解 PoW 过盾后重试（最多 3 轮）。"""
    for _ in range(3):
        _coomerfans_throttle()
        try:
            r = _coomerfans_session.get(f"{CFANS_BASE}{path}", params=params or {}, timeout=30)
        except Exception as exc:
            logging.warning("CoomerFans GET %s 失败: %s", path, exc)
            return None
        if r.status_code == 200:
            return r.text
        if r.status_code != 503:
            logging.warning("CoomerFans GET %s: HTTP %s", path, r.status_code)
            return None
        sol = _coomerfans_pow_solve(r.text)
        if not sol:
            logging.warning("CoomerFans 503 挑战页解析失败")
            return None
        try:
            _coomerfans_session.post(f"{CFANS_BASE}{sol['url']}", timeout=20, json={
                "token": sol["token"], "nonce": sol["nonce"],
                "env": {"wd": False, "tz": "Asia/Shanghai", "hc": 8, "w": 1920, "h": 1080},
            })
        except Exception as exc:
            logging.warning("CoomerFans verify 失败: %s", exc)
            return None
        time.sleep(1)
    return None


def _coomerfans_gs_emit(state: dict) -> None:
    emit({"event": "gs_state", "site": CFANS_SITE_KEY, **state})  # noqa: F821


def _coomerfans_media_proxy_url(url: str) -> str:
    """媒体直链 → 本地媒体代理 URL（img*.coomerfans.com 需 cookie+代理转发）。"""
    port = globals().get("_media_proxy_port") or 0  # noqa: F821
    if not port or not url:
        return url
    from urllib.parse import quote
    return f"http://127.0.0.1:{port}/media?url={quote(url, safe='')}"


def _coomerfans_parse_cards(html: str) -> list[dict]:
    """帖子卡片：/p/{cid}/{pid}/{service} + 封面图 + 创作者名（/u/ 链接）。"""
    cards: dict[str, dict] = {}
    for m in re.finditer(
            r'href="(/p/([a-z0-9]+)/(\d+)/([a-z]+))"[\s\S]{0,800}?'
            r'(?:src|data-src)=["\'](https://img\d*\.coomerfans\.com/storage/[^"\']+?\.(?:jpg|png|webp))',
            html or "", re.I):
        path, cid, pid, service, thumb = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        key = f"{cid}:{pid}"
        if key in cards:
            continue
        cards[key] = {
            "kind": "post",
            "video_id": key,
            "creator_id": cid,
            "post_id": pid,
            "service": service,
            "album_name": f"{service}_{cid}_{pid}",
            "album_url": f"{CFANS_BASE}{path}",
            "detail_path": path,
            "thumbnail": thumb,
            "site": CFANS_SITE_KEY,
            "posted": "",
            "badges": [{"text": service, "type": "info"}],
        }
    return list(cards.values())


# ============================
# 2. GS 命令（home / search / open-detail / download-files）
# ============================
async def _coomerfans_cmd_home(command: dict) -> None:
    page = max(1, int(command.get("page") or 1))
    _coomerfans_gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    html = await asyncio.to_thread(_coomerfans_get, f"/post-search?page={page}")
    items = _coomerfans_parse_cards(html or "")
    _coomerfans_gs_emit({
        "view": "list", "items": items, "page": page,
        "hasMore": len(items) >= 10,
        "label": f"最新帖子 第{page}页",
    })
    logging.info("CoomerFans 首页 第 %d 页: %d 帖", page, len(items))


async def _coomerfans_cmd_search(command: dict) -> None:
    query = str(command.get("query") or command.get("keyword") or "").strip()
    page = max(1, int(command.get("page") or 1))
    _coomerfans_gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    if not query:
        _coomerfans_gs_emit({"view": "list", "items": [], "page": page,
                             "error": "请输入关键词或创作者名搜索"})
        return
    html = await asyncio.to_thread(_coomerfans_get, f"/post-search?q={query}&page={page}")
    items = _coomerfans_parse_cards(html or "")
    _coomerfans_gs_emit({
        "view": "list", "items": items, "page": page,
        "hasMore": len(items) >= 10,
        "label": f"「{query}」搜索 第{page}页",
    })
    logging.info("CoomerFans 搜索 '%s' 第 %d 页: %d 帖", query, page, len(items))


async def _coomerfans_cmd_open_detail(command: dict) -> None:
    """点帖子卡片 → 帖子详情页全部媒体 → inspect_complete（文件列表 + 下载）。"""
    item = command.get("item") or {}
    detail_path = str(item.get("detail_path") or item.get("album_url") or "")
    if detail_path.startswith(CFANS_BASE):
        detail_path = detail_path.split("coomerfans.com", 1)[-1]
    if not detail_path.startswith("/p/"):
        _coomerfans_gs_emit({"view": "list", "error": "缺少帖子信息"})
        return
    _coomerfans_gs_emit({"view": "list", "loading": True, "items": [], "message": "正在解析帖子媒体..."})
    html = await asyncio.to_thread(_coomerfans_get, detail_path)
    if not html:
        _coomerfans_gs_emit({"view": "list", "items": [], "error": "帖子解析失败（限流/网络）"})
        return
    medias = re.findall(
        r'(https://img\d*\.coomerfans\.com/storage/[^"\s]+?\.(?:jpg|jpeg|png|webp|mp4|gif))',
        html)
    # 创作者名（帖子页 /u/ 链接里带 screen_name）
    un = re.search(r'href="/u/([a-z]+)/(\d+)/([A-Za-z0-9_.-]+)"', html)
    artist = un.group(3) if un else "coomerfans"
    files: list[dict] = []
    seen: set = set()
    for i, u in enumerate(medias, 1):
        u = u.split("?")[0]
        if u in seen:
            continue
        seen.add(u)
        base = u.rsplit("/", 1)[-1]
        ext = base.rsplit(".", 1)[-1].lower()
        files.append({
            "filename": sanitize_filename(base) or f"media_{i}.{ext}",  # noqa: F821
            "size": None,
            "item_page": f"{CFANS_BASE}{detail_path}",
            "status": "ok",
            "thumbnail": "",
            "media_url": _coomerfans_media_proxy_url(u),
            "site": CFANS_SITE_KEY,
            "post_title": f"{artist}_{pid}" if False else (f"{artist} 帖子"),
            "post_date": "",
            "artist": artist,
            "media_type": "video" if ext == "mp4" else "image",
            "subfolder": "",
        })
    if not files:
        _coomerfans_gs_emit({"view": "list", "items": [], "error": "该帖子没有可下载的媒体"})
        return
    album_id = f"coomerfans_{detail_path.replace('/p/', '').replace('/', '_')}"
    _mark_items_new(album_id, files)  # noqa: F821
    emit({  # noqa: F821
        "event": "inspect_complete",
        "album_name": f"帖子 {detail_path.rsplit('/', 2)[-2]}",
        "album_id": album_id,
        "is_album": True,
        "items": files,
    })
    logging.info("CoomerFans 帖子 %s: %d 个媒体", detail_path, len(files))


async def _coomerfans_cmd_download_files(command: dict) -> None:
    files = [f for f in (command.get("files") or []) if isinstance(f, dict) and f.get("media_url")]
    if not files:
        _coomerfans_gs_emit({"view": "list", "error": "没有可下载的文件"})
        return
    album = "CoomerFans 下载"
    task_id = download_manager.submit(  # noqa: F821
        f"{CFANS_BASE}/", files, command.get("options") or {},
        album, "coomerfans",
    )
    download_manager.start(task_id)  # noqa: F821
    _coomerfans_gs_emit({"view": "list", "message": f"下载已提交：{len(files)} 个文件"})


COOMERFANS_SITE_COMMANDS = {
    "coomerfans_home": _coomerfans_cmd_home,
    "coomerfans_load-more": _coomerfans_cmd_home,   # GSV「加载更多」：同 home 按 page 抓（前端负责追加去重）
    "coomerfans_search": _coomerfans_cmd_search,
    "coomerfans_open_detail": _coomerfans_cmd_open_detail,
    "coomerfans_download_files": _coomerfans_cmd_download_files,
}


# ============================
# 3. URL 路由（gui_inspect）
# ============================
def is_coomerfans_url(url: str) -> bool:
    import re
    return bool(re.search(r"coomerfans\.com/", str(url or ""), re.I))


async def coomerfans_inspect(url: str, options: dict) -> None:
    """帖子页 / 创作者主页 URL → 文件列表。"""
    import re
    u = str(url or "")
    m_p = re.search(r"coomerfans\.com(/p/[a-z0-9]+/\d+/[a-z]+)", u, re.I)
    if m_p:
        html = await asyncio.to_thread(_coomerfans_get, m_p.group(1))
        medias = re.findall(
            r'(https://img\d*\.coomerfans\.com/storage/[^"\s]+?\.(?:jpg|jpeg|png|webp|mp4|gif))',
            html or "")
        files: list[dict] = []
        seen: set = set()
        for i, mi in enumerate(medias, 1):
            mi = mi.split("?")[0]
            if mi in seen:
                continue
            seen.add(mi)
            base = mi.rsplit("/", 1)[-1]
            files.append({
                "filename": sanitize_filename(base) or f"media_{i}.jpg",  # noqa: F821
                "size": None,
                "item_page": f"{CFANS_BASE}{m_p.group(1)}",
                "status": "ok", "thumbnail": "",
                "media_url": _coomerfans_media_proxy_url(mi),
                "site": CFANS_SITE_KEY,
                "post_title": "帖子", "post_date": "", "artist": "coomerfans",
                "media_type": "image", "subfolder": "",
            })
        if files:
            album_id = f"coomerfans_{re.sub(r'[^a-z0-9]', '_', m_p.group(1).lower())}"
            _mark_items_new(album_id, files)  # noqa: F821
            emit({"event": "inspect_complete", "album_name": "CoomerFans 帖子",
                  "album_id": album_id, "is_album": True, "items": files})  # noqa: F821
            return
        emit({"event": "inspect_error", "message": "该帖子没有可下载的媒体"})  # noqa: F821
        return
    m_u = re.search(r"coomerfans\.com(/u/[a-z]+/\d+/[A-Za-z0-9_.-]+)", u, re.I)
    if m_u:
        html = await asyncio.to_thread(_coomerfans_get, m_u.group(1))
        cards = _coomerfans_parse_cards(html or "")
        if cards:
            # 创作者主页：逐帖文件量可能巨大 → 先发帖子卡片列表供勾选，
            # 下载时逐帖解析（open-detail 逻辑复用）
            emit({  # noqa: F821
                "event": "inspect_error",
                "message": f"该创作者有 {len(cards)} 个帖子：请在搜索结果里逐帖打开下载（创作者主页批量下载开发中）",
            })
            return
    emit({"event": "inspect_error", "message": "无法识别的 CoomerFans 链接"})  # noqa: F821
