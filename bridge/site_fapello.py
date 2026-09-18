# -*- coding: utf-8 -*-
"""Fapello 站点模块（综合资源站点家族；交互逻辑对齐 PA 站）。

考古结论（2026-09-13 真站探针）：
- 浏览分页：GET /ajax/index/page-{N}（HTML 片段，卡片 = /{model}/ 链接 +
  https://fapello.com/content/{x}/{y}/{model}/1000/{model}_NNNN.jpg 封面）
- 搜索：POST /search_v2/（form: query=）→ 结果页含 /{model}/ 卡片
- 模型页：GET /{model}/（SSR，第一页图片）+ /ajax/model/{model}/page-{N}（N≥2 追加）
- 图片直链：https://fapello.com/content/...（国内直连不通 → 全站走代理；
  前端预览与下载条目统一经本地媒体代理转发）
模块级名字会被 _state.register 注入 bridge 扁平命名空间（跨段引用直接写名字）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（requests/emit/…；注册后本行必需）

import asyncio
import logging
import re
import time

# ============================
# 0. 站点标识
# ============================
FAPELLO_SITE_KEY = "fapello"
FAPELLO_SITE_NAME = "Fapello"

FAPELLO_BASE = "https://fapello.com"
FAPELLO_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FAPELLO_DEFAULT_PROXY = "http://127.0.0.1:10809"   # 国内直连不通

# ============================
# 1. 会话 / 代理 / 节流
# ============================
_fapello_session = requests.Session()  # noqa: F821
_fapello_session.headers.update({"User-Agent": FAPELLO_UA})
_fapello_session.proxies = {"http": FAPELLO_DEFAULT_PROXY, "https": FAPELLO_DEFAULT_PROXY}
_fapello_last_ts = 0.0


def fapello_set_proxy(proxy: str) -> None:
    """设置代理（空 = 直连；默认 10809）。"""
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    _fapello_session.proxies = proxies


def _fapello_throttle(min_interval: float = 0.5) -> None:
    global _fapello_last_ts
    now = time.time()
    wait = _fapello_last_ts + min_interval - now
    if wait > 0:
        time.sleep(wait)
    _fapello_last_ts = time.time()


def _fapello_get(url: str):
    _fapello_throttle()
    try:
        r = _fapello_session.get(url, timeout=25)
        if r.status_code == 200:
            return r.text
        logging.warning("Fapello GET %s: HTTP %s", url, r.status_code)
    except Exception as exc:
        logging.warning("Fapello GET %s 失败: %s", url, exc)
    return None


def _fapello_gs_emit(state: dict) -> None:
    emit({"event": "gs_state", "site": FAPELLO_SITE_KEY, **state})  # noqa: F821


def _fapello_media_proxy_url(url: str) -> str:
    """图片直链 → 本地媒体代理 URL（代理转发，前端/下载机直连本地即可）。"""
    port = globals().get("_media_proxy_port") or 0  # noqa: F821
    if not port or not url:
        return url
    from urllib.parse import quote
    return f"http://127.0.0.1:{port}/media?url={quote(url, safe='')}"


def _fapello_model_card(model: str, thumb: str = "") -> dict:
    model = (model or "").strip("/").strip()
    name = model.replace("-", " ").title()
    return {
        "kind": "model",
        "video_id": model,
        "model": model,
        "album_name": name,
        "author": name,
        "album_url": f"{FAPELLO_BASE}/{model}/",
        "thumbnail": thumb,
        "site": FAPELLO_SITE_KEY,
        "posted": "",
        "badges": [{"text": "model", "type": "info"}],
    }


def _fapello_parse_cards(html: str) -> list[dict]:
    """AJAX/搜索 HTML 片段 → 模型卡片（model 链接 + content 封面去重）。"""
    cards: dict[str, str] = {}
    for m in re.finditer(
            r'href="(https://fapello\.com/([a-z0-9-]+)/)"[\s\S]{0,600}?'
            r'(?:src|data-src)=["\'](https://fapello\.com/content/[^"\']+?\.(?:jpg|png|webp))',
            html or "", re.I):
        url, model, thumb = m.group(1), m.group(2).lower(), m.group(3)
        if model and model not in cards:
            cards[model] = thumb
    return [_fapello_model_card(model, thumb) for model, thumb in cards.items()]


# ============================
# 2. GS 命令（home / search / open-detail / download-files）
# ============================
async def _fapello_cmd_home(command: dict) -> None:
    page = max(1, int(command.get("page") or 1))
    _fapello_gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    html = await asyncio.to_thread(_fapello_get, f"{FAPELLO_BASE}/ajax/index/page-{page}")
    items = _fapello_parse_cards(html or "")
    _fapello_gs_emit({
        "view": "list", "items": items, "page": page,
        "hasMore": len(items) >= 10,
        "label": f"最新模型 第{page}页",
    })
    logging.info("Fapello 首页 第 %d 页: %d 个模型", page, len(items))


async def _fapello_cmd_search(command: dict) -> None:
    query = str(command.get("query") or command.get("keyword") or "").strip()
    _fapello_gs_emit({"view": "list", "items": [], "loading": True, "page": 1})
    if not query:
        _fapello_gs_emit({"view": "list", "items": [], "page": 1, "error": "请输入模型名称搜索"})
        return

    def _do() -> list[dict]:
        _fapello_throttle()
        r = _fapello_session.post(f"{FAPELLO_BASE}/search_v2/",
                                  data={"query": query}, timeout=25)
        if r.status_code != 200:
            return []
        return _fapello_parse_cards(r.text)

    items = await asyncio.to_thread(_do)
    _fapello_gs_emit({
        "view": "list", "items": items, "page": 1, "hasMore": False,
        "label": f"「{query}」模型",
    })
    logging.info("Fapello 搜索 '%s': %d 个模型", query, len(items))


async def _fapello_cmd_open_detail(command: dict) -> None:
    """点模型卡片 → 模型全部图片 → inspect_complete（文件列表 + 下载，PA 同款）。"""
    item = command.get("item") or {}
    model = str(item.get("model") or item.get("video_id") or "").strip("/")
    if not model:
        _fapello_gs_emit({"view": "list", "error": "缺少模型信息"})
        return
    _fapello_gs_emit({"view": "list", "loading": True, "items": [],
              "message": f"正在解析 {model} 的全部图片..."})
    files = await asyncio.to_thread(_fapello_model_files, model)
    if not files:
        _fapello_gs_emit({"view": "list", "items": [], "error": "该模型没有可下载的图片"})
        return
    album_id = f"fapello_{model}"
    _mark_items_new(album_id, files)  # noqa: F821
    emit({
        "event": "inspect_complete",
        "album_name": model.replace("-", " ").title(),
        "album_id": album_id,
        "is_album": True,
        "items": files,
    })
    logging.info("Fapello 模型 %s: %d 张图", model, len(files))


def _fapello_model_files(model: str) -> list[dict]:
    """模型全部图片：/{model}/ 首页 + /ajax/model/{model}/page-N（N≥2 直到失效）。"""
    files: list[dict] = []
    seen: set = set()

    def _add(img_url: str):
        img_url = img_url.split("?")[0]
        if img_url in seen or not img_url:
            return
        seen.add(img_url)
        base = img_url.rsplit("/", 1)[-1]
        files.append({
            "filename": sanitize_filename(base) or f"{model}_{len(files) + 1}.jpg",  # noqa: F821
            "size": None,
            "item_page": f"{FAPELLO_BASE}/{model}/",
            "status": "ok",
            "thumbnail": _fapello_media_proxy_url(img_url),
            # 下载/预览统一走本地媒体代理（fapello 需代理转发）
            "media_url": _fapello_media_proxy_url(img_url),
            "site": FAPELLO_SITE_KEY,
            "post_title": model,
            "post_date": "",
            "artist": model,
            "media_type": "image",
            "subfolder": "",
        })

    html = _fapello_get(f"{FAPELLO_BASE}/{model}/")
    if not html:
        return files
    for img in re.findall(r'(https://fapello\.com/content/[^"]+\.(?:jpg|png|webp))', html):
        _add(img)
    page = 2
    while page <= 50:
        frag = _fapello_get(f"{FAPELLO_BASE}/ajax/model/{model}/page-{page}")
        if not frag:
            break
        before = len(seen)
        for img in re.findall(r'(https://fapello\.com/content/[^"]+\.(?:jpg|png|webp))', frag):
            _add(img)
        if len(seen) == before:
            break
        page += 1
    return files


async def _fapello_cmd_download_files(command: dict) -> None:
    files = [f for f in (command.get("files") or []) if isinstance(f, dict) and f.get("media_url")]
    if not files:
        _fapello_gs_emit({"view": "list", "error": "没有可下载的文件"})
        return
    artists = {f.get("artist") for f in files if f.get("artist")}
    album = next(iter(artists)) if len(artists) == 1 else "Fapello 下载"
    task_id = download_manager.submit(  # noqa: F821
        f"{FAPELLO_BASE}/", files, command.get("options") or {},
        album or "Fapello 下载", f"fapello:{album}",
    )
    download_manager.start(task_id)  # noqa: F821
    _fapello_gs_emit({"view": "list", "message": f"下载已提交：{len(files)} 个文件"})


FAPELLO_SITE_COMMANDS = {
    "fapello_home": _fapello_cmd_home,
    "fapello_load-more": _fapello_cmd_home,   # GSV「加载更多」：同 home 按 page 抓（前端负责追加去重）
    "fapello_search": _fapello_cmd_search,
    "fapello_open_detail": _fapello_cmd_open_detail,
    "fapello_download_files": _fapello_cmd_download_files,
}


# ============================
# 3. URL 路由（gui_inspect）
# ============================
def is_fapello_url(url: str) -> bool:
    import re
    return bool(re.search(r"fapello\.com/[a-z0-9-]+", str(url or ""), re.I))


async def fapello_inspect(url: str, options: dict) -> None:
    """模型页 URL → 文件列表（PA 交互：粘贴链接直达文件列表）。"""
    import re
    m = re.search(r"fapello\.com/([a-z0-9-]+)/?", str(url or ""), re.I)
    if not m or m.group(1).lower() in ("search_v2", "ajax", "assets", "login", "signup",
                                       "contacts", "top-likes", "daily-search-ranking"):
        emit({"event": "inspect_error", "message": "无法识别的 Fapello 模型链接（格式: fapello.com/{模型}/）"})  # noqa: F821
        return
    model = m.group(1).lower()
    files = await asyncio.to_thread(_fapello_model_files, model)
    if not files:
        emit({"event": "inspect_error", "message": "该模型没有可下载的图片"})  # noqa: F821
        return
    album_id = f"fapello_{model}"
    _mark_items_new(album_id, files)  # noqa: F821
    emit({
        "event": "inspect_complete", "album_name": model.replace("-", " ").title(),
        "album_id": album_id, "is_album": True, "items": files,
    })
