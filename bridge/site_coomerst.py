# -*- coding: utf-8 -*-
"""Coomer.st 站点模块（综合资源站点家族；逻辑对齐 PA 站/kemono 家族）。

考古结论（2026-09-13 真站探针）：
- kemono 家族 API：GET /api/v1/creators?q=X&o=offset（创作者搜索，返回
  [{id, name, service, ...}]）；GET /api/v1/{service}/user/{id}/posts（帖子列表，
  list[{id, title, published, file:{name,path}, attachments:[{name,path}]}]）
- **反扒**：API 必须带 `Accept: text/css` 头（站方提示"If you want to scrape,
  use Accept: text/css"），否则 403
- 媒体：https://coomer.st/data{path} → 302 → n{N}.coomer.st/data...（站方 CDN 节点，
  2026-09-13 时节点全部超时属站方问题；下载走 download_manager 共享下载机，
  下载分支按 site=coomerst 调 coomerst_download_info 取 (直链, 文件名)）
- 网络：国内必须代理（会话默认代理 10809，settings.coomerst_proxy 可覆盖）

模块级名字会被 _state.register 注入 bridge 扁平命名空间（跨段引用直接写名字）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（requests/emit/…；注册后本行必需）

import asyncio
import logging
import time

# ============================
# 0. 站点标识
# ============================
COOMERST_SITE_KEY = "coomerst"
COOMERST_SITE_NAME = "Coomer.st"

COOMERST_BASE = "https://coomer.st"
COOMERST_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
COOMERST_DEFAULT_PROXY = "http://127.0.0.1:10809"   # 国内必须代理
COOMERST_PAGE_SIZE = 50                              # creators 每页
COOMERST_MAX_POST_PAGES = 20                         # 单创作者最多抓 20×30 帖

# ============================
# 1. 会话 / 代理 / 节流
# ============================
_coomerst_session = requests.Session()  # noqa: F821
_coomerst_session.headers.update({
    "User-Agent": COOMERST_UA,
    # 站方反扒：API 必须带此 Accept 头，否则 403
    "Accept": "text/css",
})
_coomerst_session.proxies = {"http": COOMERST_DEFAULT_PROXY, "https": COOMERST_DEFAULT_PROXY}
_coomerst_last_ts = 0.0


def coomerst_set_proxy(proxy: str) -> None:
    """设置代理（空 = 直连；默认 10809）。"""
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    _coomerst_session.proxies = proxies


def _coomerst_throttle(min_interval: float = 0.6) -> None:
    global _coomerst_last_ts
    now = time.time()
    wait = _coomerst_last_ts + min_interval - now
    if wait > 0:
        time.sleep(wait)
    _coomerst_last_ts = time.time()


def _coomerst_get_json(path: str, params: dict | None = None):
    """API GET → JSON；失败返回 None。"""
    _coomerst_throttle()
    try:
        r = _coomerst_session.get(f"{COOMERST_BASE}{path}", params=params or {}, timeout=25)
        if r.status_code != 200:
            logging.warning("Coomer.st API %s: HTTP %s", path, r.status_code)
            return None
        return r.json()
    except Exception as exc:
        logging.warning("Coomer.st API %s 失败: %s", path, exc)
        return None


def _coomerst_gs_emit(state: dict) -> None:
    emit({"event": "gs_state", "site": COOMERST_SITE_KEY, **state})  # noqa: F821


_PALETTE = ["#d3416f", "#3a7fd5", "#2f9e6e", "#d08a2e", "#8a5cd6", "#2ea3a3", "#c2554d"]


def _coomerst_letter_avatar(name: str) -> str:
    """kemono API 无公开头像端点（icon/thumbnail 均 404，og:image 为通用 logo）→
    生成首字母 SVG 字母头像（data URI，按名字哈希取色，卡片视觉稳定）。"""
    letter = (name or "?").strip().upper()[:1] or "?"
    color = _PALETTE[(len(name or "") * 31 + ord(letter)) % len(_PALETTE)]
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'>"
           f"<rect width='200' height='200' fill='{color}'/>"
           f"<text x='100' y='128' font-size='96' font-family='Arial' "
           f"font-weight='bold' fill='#fff' text-anchor='middle'>{letter}</text></svg>")
    return "data:image/svg+xml;utf8," + svg.replace("#", "%23")


def _coomerst_creator_card(c: dict) -> dict:
    """creators API 条目 → GSV 创作者卡片。"""
    service = str(c.get("service") or "onlyfans")
    cid = str(c.get("id") or "")
    name = str(c.get("name") or cid)
    return {
        "kind": "creator",
        "video_id": f"{service}:{cid}",          # GSV 批量/勾选 id 键
        "service": service,
        "creator_id": cid,
        "album_name": name,
        "author": name,
        "album_url": f"{COOMERST_BASE}/{service}/user/{cid}",
        "thumbnail": _coomerst_letter_avatar(name),
        "site": COOMERST_SITE_KEY,
        "posted": "",
        "badges": [{"text": service, "type": "info"}],
    }


def _coomerst_media_url(path: str) -> str:
    path = path or ""
    if path.startswith("http"):
        return path
    return f"{COOMERST_BASE}/data{'' if path.startswith('/') else '/'}{path}"


def _coomerst_post_files(post: dict, creator_name: str, service: str,
                         cid: str, out: list, seen_urls: set) -> None:
    """单帖 → 文件条目（file 主文件 + attachments 附件，全部去重）。

    文件名只取 basename 并经 sanitize_filename 消毒（站方 name 不受信任）。"""
    pid = str(post.get("id") or "")
    title = (post.get("title") or post.get("substring") or "").strip()
    published = str(post.get("published") or "")[:10]
    medias = []
    f = post.get("file") or {}
    if f.get("path"):
        medias.append(f)
    for a in (post.get("attachments") or []):
        if a.get("path"):
            medias.append(a)
    for i, m in enumerate(medias, 1):
        url = _coomerst_media_url(m.get("path"))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        raw_name = str(m.get("name") or f"{pid}_{i}.jpg").replace("\\", "/").split("/")[-1]
        name = sanitize_filename(raw_name) or f"{pid}_{i}.jpg"  # noqa: F821
        out.append({
            "filename": name,
            "size": None,
            "item_page": f"{COOMERST_BASE}/{service}/user/{cid}/post/{pid}",
            "status": "ok",
            "thumbnail": "",
            "media_url": url,
            "site": COOMERST_SITE_KEY,
            "post_title": title or creator_name,
            "post_date": published,
            "artist": creator_name,
            "media_type": "image",
            "subfolder": "",
        })


async def _coomerst_creator_files(service: str, cid: str, creator_name: str) -> list[dict]:
    """创作者全部帖子 → 文件条目（分页抓取，最多 COOMERST_MAX_POST_PAGES 页）。"""
    files: list[dict] = []
    seen_urls: set = set()
    offset = 0
    for _ in range(COOMERST_MAX_POST_PAGES):
        data = await asyncio.to_thread(
            _coomerst_get_json, f"/api/v1/{service}/user/{cid}/posts", {"o": offset})
        if not isinstance(data, list) or not data:
            break
        for post in data:
            _coomerst_post_files(post, creator_name, service, cid, files, seen_urls)
        if len(data) < 30:
            break
        offset += len(data)
    return files


# ============================
# 2. GS 命令（home / search / open-detail / download-files）
# ============================
async def _coomerst_cmd_home(command: dict) -> None:
    page = max(1, int(command.get("page") or 1))
    _coomerst_gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    offset = (page - 1) * COOMERST_PAGE_SIZE
    data = await asyncio.to_thread(
        _coomerst_get_json, "/api/v1/creators", {"o": offset, "q": ""})
    items = [_coomerst_creator_card(c) for c in (data or [])][:COOMERST_PAGE_SIZE]
    _coomerst_gs_emit({
        "view": "list", "items": items, "page": page,
        "hasMore": len(items) >= COOMERST_PAGE_SIZE,
        "label": f"热门创作者 第{page}页",
    })
    logging.info("Coomer.st 创作者 第 %d 页: %d 个", page, len(items))


async def _coomerst_cmd_search(command: dict) -> None:
    query = str(command.get("query") or command.get("keyword") or "").strip()
    page = max(1, int(command.get("page") or 1))
    _coomerst_gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    if not query:
        _coomerst_gs_emit({"view": "list", "items": [], "page": page, "error": "请输入创作者名称搜索"})
        return
    offset = (page - 1) * COOMERST_PAGE_SIZE
    data = await asyncio.to_thread(
        _coomerst_get_json, "/api/v1/creators", {"q": query, "o": offset})
    items = [_coomerst_creator_card(c) for c in (data or [])][:COOMERST_PAGE_SIZE]
    _coomerst_gs_emit({
        "view": "list", "items": items, "page": page,
        "hasMore": len(items) >= COOMERST_PAGE_SIZE,
        "label": f"「{query}」创作者 第{page}页",
    })
    logging.info("Coomer.st 搜索 '%s' 第 %d 页: %d 个创作者", query, page, len(items))


async def _coomerst_cmd_open_detail(command: dict) -> None:
    """点创作者卡片 → 解析全部帖子文件 → inspect_complete（文件列表 + 下载）。
    与 PA 站交互一致：点开创作者即出文件列表。"""
    item = command.get("item") or {}
    service = str(item.get("service") or "onlyfans")
    cid = str(item.get("creator_id") or "")
    name = str(item.get("album_name") or cid)
    if not cid:
        _coomerst_gs_emit({"view": "list", "error": "缺少创作者信息"})
        return
    _coomerst_gs_emit({"view": "list", "loading": True, "items": [],
              "message": f"正在解析 {name} 的全部帖子..."})
    files = await _coomerst_creator_files(service, cid, name)
    if not files:
        _coomerst_gs_emit({"view": "list", "items": [], "error": "该创作者没有可下载的文件"})
        return
    album_id = f"coomerst_{service}_{cid}"
    _mark_items_new(album_id, files)  # noqa: F821
    _apply_cached_thumbnails(files)   # noqa: F821
    emit({  # noqa: F821
        "event": "inspect_complete",
        "album_name": name,
        "album_id": album_id,
        "is_album": True,
        "items": files,
    })
    asyncio.create_task(_cache_thumbnails(files))  # noqa: F821
    logging.info("Coomer.st 创作者 %s(%s/%s): %d 个文件", name, service, cid, len(files))


async def _coomerst_cmd_download_files(command: dict) -> None:
    files = [f for f in (command.get("files") or []) if isinstance(f, dict) and f.get("media_url")]
    if not files:
        _coomerst_gs_emit({"view": "list", "error": "没有可下载的文件"})
        return
    artists = {f.get("artist") for f in files if f.get("artist")}
    album = next(iter(artists)) if len(artists) == 1 else "Coomer.st 下载"
    task_id = download_manager.submit(  # noqa: F821
        f"{COOMERST_BASE}/", files, command.get("options") or {},
        album or "Coomer.st 下载", f"coomerst:{album}",
    )
    download_manager.start(task_id)  # noqa: F821
    _coomerst_gs_emit({"view": "list", "message": f"下载已提交：{len(files)} 个文件"})


# 注意：finalize 会把各模块同名 SITE_COMMANDS 互相覆盖（fc2 为最后写入者），
# 故本模块用唯一名，由 bridge/__init__.py 显式并入总表
COOMERST_SITE_COMMANDS = {
    "coomerst_home": _coomerst_cmd_home,
    "coomerst_load-more": _coomerst_cmd_home,   # GSV「加载更多」：同 home 按 page 抓（前端负责追加去重）
    "coomerst_search": _coomerst_cmd_search,
    "coomerst_open_detail": _coomerst_cmd_open_detail,
    "coomerst_download_files": _coomerst_cmd_download_files,
}


# ============================
# 3. URL 路由（gui_inspect）
# ============================
def is_coomerst_url(url: str) -> bool:
    import re
    return bool(re.search(r"coomer\.st/", str(url or ""), re.I))


async def coomerst_inspect(url: str, options: dict) -> None:
    """创作者页 / 帖子页 URL → 文件列表（PA 交互：粘贴链接直达文件列表）。"""
    import re
    u = str(url or "")
    m_post = re.search(r"coomer\.st/([a-z0-9]+)/user/([A-Za-z0-9_.-]+)/post/(\d+)", u, re.I)
    if m_post:
        service, cid, pid = m_post.group(1).lower(), m_post.group(2), m_post.group(3)
        data = await asyncio.to_thread(
            _coomerst_get_json, f"/api/v1/{service}/user/{cid}/post/{pid}")
        files: list[dict] = []
        seen: set = set()
        for post in ([data] if isinstance(data, dict) else []):
            _coomerst_post_files(post, cid, service, cid, files, seen)
        if files:
            album_id = f"coomerst_{service}_{cid}_{pid}"
            _mark_items_new(album_id, files)  # noqa: F821
            emit({  # noqa: F821
                "event": "inspect_complete", "album_name": f"post_{pid}",
                "album_id": album_id, "is_album": True, "items": files,
            })
            return
        emit({"event": "inspect_error", "message": "该帖子没有可下载的文件"})
        return
    m = re.search(r"coomer\.st/([a-z0-9]+)/user/([A-Za-z0-9_.-]+)", u, re.I)
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 Coomer.st 链接（格式: coomer.st/{服务}/user/{id}）"})
        return
    service, cid = m.group(1).lower(), m.group(2)
    name = cid
    files = await _coomerst_creator_files(service, cid, name)
    if not files:
        emit({"event": "inspect_error", "message": "该创作者没有可下载的文件"})
        return
    album_id = f"coomerst_{service}_{cid}"
    _mark_items_new(album_id, files)  # noqa: F821
    _apply_cached_thumbnails(files)   # noqa: F821
    emit({
        "event": "inspect_complete", "album_name": name,
        "album_id": album_id, "is_album": True, "items": files,
    })
    asyncio.create_task(_cache_thumbnails(files))  # noqa: F821


# ============================
# 4. 下载信息钩子（download_manager 按 site=coomerst 调用，返回 (直链, 文件名)）
# ============================
def coomerst_download_info(item: dict) -> tuple[str, str]:
    """下载直链与文件名（直链 302 → CDN 由共享下载机跟随）。"""
    url = str(item.get("media_url") or "")
    raw = str(item.get("filename") or "coomerst_file").replace("\\", "/").split("/")[-1]
    return url, sanitize_filename(raw) or "coomerst_file"  # noqa: F821
