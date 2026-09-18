# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：识图（反向图片搜索）。

由 gui_bridge.py 按物理顺序拆出（原行区间 15784-16689），
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
# 识图（反向图片搜索）
# ============================
# 站点表字段说明：
#   key         - 解析器键名（见 _REVERSE_PARSERS）
#   name        - 展示名
#   needs_proxy - True = 国内必须走代理（Lenso.ai），只有这些站点使用用户填写的识图代理
#   max_bytes   - 该站上传体积上限（超出时用 Pillow 压缩；无法压缩则跳过并给出原因）
#   max_edge    - 压缩时的最长边上限（体积未超限时原样上传，不降分辨率）
#
# 2026-09-16 探针实测收缩（每站"真实丢图→结果页"逐一验证，置信度 ✅实测）：
#   保留 tracemoe / saucenao / iqdb / lenso（token 门控）。
#   移除 google（searchbyimage/upload 跳 Lens 纯 JS 壳，requests 解析不到任何结果）、
#   ascii2d（Cloudflare 盾直连/代理均 403）、yandex（multipart 被静默拒，真实流程依赖
#   前端 JS）、soutubot.moe（服务端 500）、whos.tv（域名超时已死）、baidu graph（Reject）、
#   tineye/bing（上传端点 404/400）。宁可少站不留假结果。
REVERSE_SITES: list[dict] = [
    {"key": "tracemoe", "name": "trace.moe", "needs_proxy": False,
     "max_bytes": 1 * 1024 * 1024, "max_edge": 640},
    {"key": "saucenao", "name": "SauceNAO", "needs_proxy": False,
     "max_bytes": 15 * 1024 * 1024, "max_edge": 1600},
    {"key": "iqdb", "name": "IQDB", "needs_proxy": False,
     "max_bytes": 8 * 1024 * 1024, "max_edge": 1000},
    {"key": "lenso", "name": "Lenso.ai", "needs_proxy": True,
     "max_bytes": 20 * 1024 * 1024, "max_edge": 1600},
]

_REVERSE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 模块级 settings 引用（main() 加载后 update 进来，供 lenso token 等读取）
_reverse_settings: dict = {}
# 识图代理（只给 needs_proxy 的站点用；reverse_proxy_all=True 时全站生效）
_reverse_proxy = ""
_reverse_proxy_all = False


def _reverse_apply_proxy(p: str, proxy_all: bool) -> None:
    """跨模块写入口（启动恢复/设置命令）：更新识图代理设置。"""
    global _reverse_proxy, _reverse_proxy_all
    _reverse_proxy = p or ""
    _reverse_proxy_all = bool(proxy_all)

# 会话状态：session 用于丢弃过期搜索的回传事件，cancel 用于中断
_reverse_seq = 0
_reverse_session: str | None = None
_reverse_cancel = threading.Event()
_reverse_running = False

try:  # Pillow 可选：安装后可自动缩放/压缩大图，未安装则退化为体积校验
    from PIL import Image as _PILImage  # type: ignore
    _PIL_AVAILABLE = True
except Exception:  # noqa: BLE001 —— 打包环境可能没有 Pillow
    _PILImage = None  # type: ignore
    _PIL_AVAILABLE = False

_REVERSE_CACHE_DIR = Path("cache") / "reverse_cache"
_REVERSE_CACHE_TTL = 7 * 24 * 3600
_REVERSE_CACHE_MAX = 120
_REVERSE_CACHE_VERSION = "v3"  # v3: 站点收缩 + saucenao 真实来源链 + iqdb 新解析器


class _ReverseImage:
    """准备好的待上传图片（内存字节 + 正确的文件名与 MIME）。"""

    __slots__ = ("data", "filename", "mime")

    def __init__(self, data: bytes, filename: str, mime: str) -> None:
        self.data = data
        self.filename = filename
        self.mime = mime


# ---------- 代理 ----------
def reverse_set_proxy(proxy: str, all_sites: bool | None = None) -> None:
    """设置识图代理；all_sites=None 表示不改变"全站生效"开关。"""
    global _reverse_proxy, _reverse_proxy_all
    p = (proxy or "").strip()
    if p and not p.startswith("http"):
        p = "http://" + p
    _reverse_proxy = p
    if all_sites is not None:
        _reverse_proxy_all = bool(all_sites)
    emit({"event": "reverse_proxy_set", "proxy": p, "all_sites": _reverse_proxy_all})


def _reverse_proxies(site_key: str) -> dict | None:
    """按站点决定是否走代理：只有 needs_proxy 的站点（或开启全站代理时）使用。

    未配置专属代理时，needs_proxy 站点（Google/Yandex/Lenso 国内直连必挂）
    回退系统代理——否则表现为"识图只有部分站有结果"（2026-09-13）。"""
    proxy = _reverse_proxy
    if not proxy:
        sys_p = _system_proxies() or [None]
        proxy = sys_p[0]
    if not proxy:
        return None
    if not _reverse_proxy_all:
        site = next((s for s in REVERSE_SITES if s["key"] == site_key), None)
        if not site or not site.get("needs_proxy"):
            return None
    return {"http": proxy, "https": proxy}


# ---------- 图片预处理 ----------
def _reverse_sniff(raw: bytes, src_path: str) -> tuple[str, str]:
    """按文件头判断真实类型，返回 (mime, 扩展名)。"""
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if raw[:2] == b"BM":
        return "image/bmp", ".bmp"
    ext = os.path.splitext(src_path)[1].lower()
    return {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
            ".bmp": "image/bmp"}.get(ext, "image/jpeg"), (ext or ".jpg")


def _reverse_dimensions(raw: bytes, mime: str) -> tuple[int, int]:
    """不依赖 Pillow 读取图片宽高（失败返回 0,0）。"""
    try:
        if mime == "image/png" and len(raw) >= 24:
            return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
        if mime == "image/gif" and len(raw) >= 10:
            return int.from_bytes(raw[6:8], "little"), int.from_bytes(raw[8:10], "little")
        if mime == "image/bmp" and len(raw) >= 26:
            return int.from_bytes(raw[18:22], "little"), int.from_bytes(raw[22:26], "little")
        if mime == "image/webp":
            if raw[12:16] == b"VP8X" and len(raw) >= 30:
                return (int.from_bytes(raw[24:27], "little") + 1,
                        int.from_bytes(raw[27:30], "little") + 1)
            if raw[12:16] == b"VP8 " and len(raw) >= 30:
                return (int.from_bytes(raw[26:28], "little") & 0x3FFF,
                        int.from_bytes(raw[28:30], "little") & 0x3FFF)
            if raw[12:16] == b"VP8L" and len(raw) >= 25:
                bits = int.from_bytes(raw[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            return 0, 0
        if mime == "image/jpeg":
            idx = 2
            while idx < len(raw) - 9:
                if raw[idx] != 0xFF:
                    idx += 1
                    continue
                marker = raw[idx + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    idx += 2
                    continue
                seg_len = int.from_bytes(raw[idx + 2:idx + 4], "big")
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    return (int.from_bytes(raw[idx + 7:idx + 9], "big"),
                            int.from_bytes(raw[idx + 5:idx + 7], "big"))
                if marker == 0xDA:
                    break
                idx += 2 + seg_len
    except Exception:  # noqa: BLE001 —— 尺寸解析失败不影响上传，按未知处理
        pass
    return 0, 0


def _reverse_prepare(src_path: str, max_bytes: int, max_edge: int) -> _ReverseImage:
    """读取并按站点限制预处理图片：修正 MIME、必要时缩放压缩。"""
    with open(src_path, "rb") as f:
        raw = f.read()
    if not raw:
        raise RuntimeError("图片文件为空")
    mime, ext = _reverse_sniff(raw, src_path)
    # 只在体积超限时才压缩：分辨率对以图搜图的匹配精度有价值，
    # 只要站点收得下就原样上传（max_edge 仅在压缩时作为上限）
    if len(raw) <= max_bytes:
        return _ReverseImage(raw, "image" + ext, mime)
    if not _PIL_AVAILABLE:
        width, height = _reverse_dimensions(raw, mime)
        raise RuntimeError(
            f"图片超出该站体积限制（{len(raw) / 1048576:.1f}MB"
            + (f"，{width}x{height}" if width and height else "")
            + f"，上限 {max_bytes / 1048576:.0f}MB）；安装 Pillow 后可自动压缩")
    import io

    im = _PILImage.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    width, height = im.size
    edge = max(width, height)
    while True:
        if edge > max_edge:
            scale = max_edge / edge
            im_resized = im.resize((max(1, int(width * scale)), max(1, int(height * scale))),
                                   getattr(_PILImage, "Resampling", _PILImage).LANCZOS
                                   if hasattr(_PILImage, "Resampling") else _PILImage.LANCZOS)
        else:
            im_resized = im
        for quality in (85, 72, 60, 48, 38, 30):
            buf = io.BytesIO()
            im_resized.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() <= max_bytes:
                return _ReverseImage(buf.getvalue(), "image.jpg", "image/jpeg")
        # 质量压到最低仍超限：继续缩小最长边再试
        if max_edge <= 240:
            break
        max_edge = max(240, max_edge // 2)
        edge = max_edge + 1
    raise RuntimeError(f"图片压缩后仍超过该站 {max_bytes / 1048576:.0f}MB 限制，已跳过该站")


def _reverse_post_file(url: str, field: str, image: _ReverseImage,
                       extra_data: dict | None = None, timeout: int = 40,
                       site_key: str = "") -> "requests.Response":
    """以 multipart 上传图片到识图网站（使用正确的 MIME，按站点决定是否走代理）。"""
    files = {field: (image.filename, image.data, image.mime)}
    return requests.post(url, files=files, data=extra_data or {},
                         headers={"User-Agent": _REVERSE_UA},
                         proxies=_reverse_proxies(site_key), timeout=timeout)


def _reverse_clean(text: str, limit: int = 80) -> str:
    return " ".join((text or "").split())[:limit]


# ---------- 各站点解析器 ----------
def _reverse_tracemoe(image: _ReverseImage) -> dict:
    """trace.moe：番剧截图识别（免费 JSON API，返回动画/集数/时间点）。"""
    r = requests.post("https://api.trace.moe/search?cutBorders",
                      files={"image": (image.filename, image.data, image.mime)},
                      headers={"User-Agent": _REVERSE_UA},
                      proxies=_reverse_proxies("tracemoe"), timeout=40)
    r.raise_for_status()
    data = r.json() or {}
    items = []
    for it in (data.get("result") or [])[:8]:
        ani = it.get("anilist")
        if not isinstance(ani, dict):
            ani = {}
        title = ani.get("title")
        if not isinstance(title, dict):
            title = {}
        name = title.get("native") or title.get("romaji") or title.get("english") \
            or it.get("filename") or "未知作品"
        try:
            sub = f"第 {it.get('episode') or '?'} 集 · {int(it.get('from') or 0)}s ~ {int(it.get('to') or 0)}s"
        except Exception:  # noqa: BLE001
            sub = f"第 {it.get('episode') or '?'} 集"
        items.append({
            "title": _reverse_clean(name, 120),
            "subtitle": sub,
            "similarity": f"{(it.get('similarity') or 0) * 100:.1f}%",
            "url": f"https://anilist.co/anime/{ani['id']}" if ani.get("id") else "https://trace.moe/",
            "thumbnail": it.get("image") or "",
        })
    return {"results": items, "url": "https://trace.moe/"}


def _reverse_saucenao(image: _ReverseImage) -> dict:
    """SauceNAO：二次元插画/漫画来源（P站/推特等）。

    与真人网页上传同一 multipart 端点（2026-09-16 探针实测 9 结果块）。
    设置里填 API Key（saucenao.com 账号页获取）可提升免费配额。"""
    key = (_reverse_settings.get("reverse_saucenao_api_key") or "").strip()
    extra = {"api_key": key} if key else None
    r = _reverse_post_file("https://saucenao.com/search.php", "file", image,
                           extra_data=extra, timeout=45, site_key="saucenao")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for block in soup.select(".result")[:8]:
        # 真实来源页优先：块内第一个非 saucenao 域外链（pixiv/danbooru/twitter…），
        # 否则退回站内跳转包装链接
        link = ext_link = title = ""
        for a in block.select("a[href]"):
            href = a.get("href") or ""
            if not href.startswith("http"):
                continue
            if "saucenao.com" not in href:
                ext_link, title = href, _reverse_clean(a.get_text(), 120)
                break
            if not link:
                link = href
                title = _reverse_clean(a.get_text(), 120)
        link = ext_link or link
        sim_el = block.select_one(".resultsimilarityinfo")
        sim = _reverse_clean(sim_el.get_text()).strip("()") if sim_el else ""
        img_el = block.select_one(".resultimage img")
        thumb = (img_el.get("src") or "") if img_el else ""
        if thumb.startswith("/"):
            thumb = "https://saucenao.com" + thumb
        content_el = block.select_one(".resultcontent")
        subtitle = _reverse_clean(content_el.get_text(), 100) if content_el else ""
        if link:
            items.append({"title": title or "匹配结果", "subtitle": subtitle,
                          "similarity": sim, "url": link, "thumbnail": thumb})
    if not items:
        if "exceeded" in r.text.lower():
            raise RuntimeError("免费配额已用尽（可注册 saucenao.com 获取 API Key 填入设置提升配额）")
        raise RuntimeError("无匹配结果（该图未被 SauceNAO 收录）")
    return {"results": items, "url": "https://saucenao.com/"}


def _reverse_iqdb(image: _ReverseImage) -> dict:
    """IQDB：booru 图库聚合（gelbooru/danbooru/sankaku 等）。

    multipart 直传 https://iqdb.org/（同真人网页上传），结果页为 .pages 下的一组
    表格：第一张是原图本身，其后每张是带来源链接与相似度的匹配（2026-09-16 实测）。"""
    r = _reverse_post_file("https://iqdb.org/", "file", image, timeout=90, site_key="iqdb")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    kind_zh = {"Best match": "最佳匹配", "Additional match": "附加匹配",
               "Possible match": "可能匹配"}
    items = []
    for tbl in soup.select(".pages table")[1:9]:   # 第一张表=原图本身，跳过
        a = tbl.select_one("a[href]")
        if not a:
            continue
        href = a.get("href") or ""
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = "https://iqdb.org" + href
        if not href.startswith("http"):
            continue
        text = " ".join(tbl.get_text(" ", strip=True).split())
        sim_m = re.search(r"(\d+(?:\.\d+)?)% similarity", text)
        kind_m = re.match(r"(Best match|Additional match|Possible match)\s*(.*)", text)
        kind_en = kind_m.group(1) if kind_m else "Match"
        rest = kind_m.group(2) if kind_m else text
        # 站名在匹配类型之后、尺寸/分级标记之前（可能是 "Danbooru Gelbooru" 双站名）
        site_m = re.match(r"(.*?)\s*(?:\d+\s*[×x]\s*\d+|\[|$)", rest)
        site = (site_m.group(1) if site_m else rest).strip() or "匹配"
        sim = f"{sim_m.group(1)}%" if sim_m else ""
        img = tbl.select_one("img")
        thumb = (img.get("src") or "") if img else ""
        if thumb.startswith("/"):
            thumb = "https://iqdb.org" + thumb
        items.append({"title": f"{site} · {kind_zh.get(kind_en, kind_en)}",
                      "subtitle": _reverse_clean(text, 120),
                      "similarity": sim, "url": href, "thumbnail": thumb})
    if not items:
        raise RuntimeError("无匹配结果（该图未被 gelbooru/danbooru 等 booru 图库收录）")
    return {"results": items, "url": "https://iqdb.org/"}


def _reverse_lenso(image: _ReverseImage) -> dict:
    """Lenso.ai：AI 反向图片搜索（官方 API 需付费订阅 token；留空则跳过该站）。"""
    token = (_reverse_settings.get("reverse_lenso_token") or "").strip()
    if not token:
        raise RuntimeError("Lenso.ai 官方 API 需付费订阅；在设置中填写 Token 后启用")
    b64 = base64.b64encode(image.data).decode()
    r = requests.post("https://api.lenso.ai/search",
                      json={"image": b64, "category": "similar", "page": 1},
                      headers={"Authorization": f"Bearer {token}",
                               "User-Agent": _REVERSE_UA},
                      proxies=_reverse_proxies("lenso"), timeout=40)
    r.raise_for_status()
    data = r.json() or {}
    items = []
    for res in (data.get("results") or [])[:8]:
        for u in (res.get("urlList") or [])[:1]:
            items.append({"title": _reverse_clean(u.get("title"), 120) or "匹配结果",
                          "subtitle": "", "similarity": "",
                          "url": u.get("sourceUrl") or "",
                          "thumbnail": u.get("imageUrl") or ""})
    if not items:
        raise RuntimeError("未返回结果")
    return {"results": items, "url": "https://lenso.ai/"}


_REVERSE_PARSERS = {
    "tracemoe": _reverse_tracemoe,
    "saucenao": _reverse_saucenao,
    "iqdb": _reverse_iqdb,
    "lenso": _reverse_lenso,
}


# ---------- 结果缓存 ----------
def _reverse_cache_path(digest: str) -> Path:
    return _REVERSE_CACHE_DIR / f"{digest}.json"


def _reverse_cache_key(src_path: str) -> str:
    """按文件内容（而非文件名）算缓存键，改名/移动后依然命中。"""
    h = hashlib.sha256()
    with open(src_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    h.update(_REVERSE_CACHE_VERSION.encode())
    return h.hexdigest()


def _reverse_cache_get(digest: str) -> dict | None:
    path = _reverse_cache_path(digest)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if time.time() - float(data.get("ts") or 0) > _REVERSE_CACHE_TTL:
        try:
            path.unlink()
        except OSError:
            pass
        return None
    # 命中即刷新 mtime，配合下面的 LRU 清理
    try:
        os.utime(path, None)
    except OSError:
        pass
    return data


def _reverse_cache_put(digest: str, payload: dict) -> None:
    try:
        _REVERSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = dict(payload, ts=time.time())
        _atomic_write_json(str(_reverse_cache_path(digest)), payload)
        files = sorted(_REVERSE_CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for stale in files[:-_REVERSE_CACHE_MAX] if len(files) > _REVERSE_CACHE_MAX else []:
            try:
                stale.unlink()
            except OSError:
                pass
    except OSError as exc:
        logging.debug("识图缓存写入失败: %s", exc)


# ---------- 结果聚合（去重 + 相似度排序） ----------
def _reverse_sim_value(text: str) -> float:
    """把各种相似度写法归一化成 0-100 的浮点数；无相似度返回 -1。"""
    t = (text or "").strip()
    if not t:
        return -1.0
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", t)
    if m:
        return max(0.0, min(100.0, float(m.group(1))))
    m = re.fullmatch(r"0?\.(\d+)", t)
    if m:
        return float("0." + m.group(1)) * 100
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", t)
    if m:
        val = float(m.group(1))
        return val * 100 if val <= 1 else val
    return -1.0


def _reverse_norm_url(url: str) -> str:
    """归一化 URL 用于跨站去重（去锚点、去常见追踪参数、统一大小写）。"""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    try:
        p = urlparse(u)
    except Exception:  # noqa: BLE001
        return u
    query = "&".join(
        kv for kv in (p.query.split("&") if p.query else [])
        if kv.split("=")[0].lower() not in ("utm_source", "utm_medium", "utm_campaign",
                                            "utm_term", "utm_content", "ref", "ref_src",
                                            "spm", "from", "share_token")
    )
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/") or "/"
    return f"{netloc}{path}" + (f"?{query}" if query else "")


def _reverse_merge(groups: list[dict]) -> list[dict]:
    """把各站点结果按 URL 去重合并，按相似度降序聚合排序。"""
    buckets: dict[str, dict] = {}
    order: list[str] = []
    for grp in groups:
        site_name = grp.get("name") or ""
        for it in grp.get("results") or []:
            url = it.get("url") or ""
            if not url.startswith("http"):
                continue
            key = _reverse_norm_url(url) or url
            sim = _reverse_sim_value(it.get("similarity") or "")
            if key not in buckets:
                buckets[key] = {
                    "title": it.get("title") or "",
                    "subtitle": it.get("subtitle") or "",
                    "similarity": it.get("similarity") or "",
                    "score": sim,
                    "url": url,
                    "thumbnail": it.get("thumbnail") or "",
                    "sources": [site_name] if site_name else [],
                }
                order.append(key)
                continue
            bucket = buckets[key]
            if site_name and site_name not in bucket["sources"]:
                bucket["sources"].append(site_name)
            if sim > bucket["score"]:
                bucket["score"] = sim
                bucket["similarity"] = it.get("similarity") or ""
                if it.get("title"):
                    bucket["title"] = it["title"]
            if not bucket["thumbnail"] and it.get("thumbnail"):
                bucket["thumbnail"] = it["thumbnail"]
            if not bucket["subtitle"] and it.get("subtitle"):
                bucket["subtitle"] = it["subtitle"]
    merged = [buckets[k] for k in order]
    merged.sort(key=lambda x: (x.get("score") or -1.0, len(x.get("sources") or [])), reverse=True)
    return merged[:30]


def _reverse_with_proxied_thumbs(results: list[dict]) -> list[dict]:
    """缩略图改走本地媒体代理（自动带 Referer 绕防盗链），并标注可否直接下载。"""
    for it in results:
        thumb = it.get("thumbnail") or ""
        if thumb.startswith(("http://", "https://")):
            it["thumbnail"] = media_proxy_url(thumb)
        it["downloadable"] = reverse_can_download(it.get("url") or "")
    return results


# ---------- 结果回灌下载器 ----------
def reverse_can_download(url: str) -> bool:
    """判断识图结果链接是否已被下载器支持（决定前端是否显示"下载"按钮）。"""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return False
    for matcher in (is_coomer_url, is_pixiv_url, is_twitter_url, is_iwara_url,
                    is_hanime_url, is_oreno_url, is_asmr_url, is_exhentai_url,
                    is_pawchive_url, is_javdb_url):
        try:
            if matcher(u):
                return True
        except Exception:  # noqa: BLE001 —— 各站匹配函数容错，不匹配即视为不支持
            continue
    return "bunkr" in urlparse(u).netloc.lower()


async def reverse_download(url: str) -> None:
    """把识图结果链接交给下载器：内部复用 gui_inspect 解析成文件列表后直接建任务。"""
    url = (url or "").strip()
    if not reverse_can_download(url):
        emit({"event": "reverse_download_error", "url": url,
              "message": "该链接所在站点未接入下载器，无法直接下载"})
        return
    emit({"event": "reverse_download_start", "url": url})
    options = _load_settings()
    # 捕获 inspect 事件：避免解析进度污染主界面，同时拿到文件列表
    with _emit_capture(mute=lambda e: str(e.get("event", "")).startswith("inspect_")) as events:
        try:
            await gui_inspect(url, options)
        except Exception as exc:  # noqa: BLE001
            logging.exception("识图结果解析失败: %s", url)
            emit({"event": "reverse_download_error", "url": url, "message": f"解析失败: {exc}"})
            return
    done = next((e for e in events if e.get("event") == "inspect_complete"), None)
    if done is None:
        err = next((e for e in events if e.get("event") == "inspect_error"), None)
        emit({"event": "reverse_download_error", "url": url,
              "message": (err or {}).get("message") or "未解析到可下载的文件"})
        return
    items = done.get("items") or []
    if not items:
        emit({"event": "reverse_download_error", "url": url, "message": "未解析到可下载的文件"})
        return
    album_name = done.get("album_name") or ""
    task_id = download_manager.submit(url, items, options, album_name, done.get("album_id"))
    download_manager.start(task_id)
    logging.info("识图结果已创建下载任务: %s (%d 个文件)", task_id, len(items))
    emit({"event": "reverse_download_done", "url": url, "task_id": task_id,
          "count": len(items), "album": album_name})


# ---------- 搜索主流程 ----------
def _reverse_public_sites() -> list[dict]:
    return [{"key": s["key"], "name": s["name"], "needs_proxy": bool(s["needs_proxy"])}
            for s in REVERSE_SITES]


def reverse_cancel() -> None:
    """取消进行中的识图（已发出的请求会在后台结束，但结果一律丢弃）。"""
    global _reverse_session
    if not _reverse_running:
        return
    session = _reverse_session
    _reverse_session = None
    _reverse_cancel.set()
    logging.info("识图已取消: %s", session)
    emit({"event": "reverse_cancelled", "session": session or ""})


async def reverse_search(path: str) -> None:
    """识图入口：并发请求各识图网站，逐站推送进度，全部返回后推送聚合结果。"""
    global _reverse_seq, _reverse_session, _reverse_running
    path = (path or "").strip()
    if not path or not os.path.isfile(path):
        emit({"event": "reverse_error", "message": f"图片文件不存在: {path}"})
        return

    # 新一轮搜索前先作废旧会话，避免上一轮结果串到本轮
    if _reverse_running:
        reverse_cancel()

    _reverse_seq += 1
    session = f"{int(time.time() * 1000)}-{_reverse_seq}"
    _reverse_session = session
    _reverse_cancel.clear()
    _reverse_running = True

    def _alive() -> bool:
        return _reverse_session == session and not _reverse_cancel.is_set()

    emit({"event": "reverse_start", "session": session, "sites": _reverse_public_sites()})

    try:
        cache_key = _reverse_cache_key(path)
    except OSError as exc:
        _reverse_running = False
        emit({"event": "reverse_error", "session": session, "message": f"读取图片失败: {exc}"})
        return

    cached = _reverse_cache_get(cache_key)
    if cached:
        groups = cached.get("groups") or []
        for grp in groups:
            _reverse_with_proxied_thumbs(grp.get("results") or [])
        ok_sites = [g.get("name") for g in groups if g.get("results")]
        _reverse_running = False
        emit({"event": "reverse_all_done", "session": session, "ok_sites": ok_sites,
              "failed_sites": [], "groups": groups,
              "merged": _reverse_merge(groups), "cached": True})
        return

    async def _run(site: dict) -> None:
        key, name = site["key"], site["name"]
        if not _alive():
            emit({"event": "reverse_site_update", "session": session, "site": key,
                  "name": name, "status": "cancelled", "results": []})
            return
        try:
            image = await asyncio.to_thread(
                _reverse_prepare, path, int(site["max_bytes"]), int(site["max_edge"]))
            if not _alive():
                emit({"event": "reverse_site_update", "session": session, "site": key,
                      "name": name, "status": "cancelled", "results": []})
                return
            data = await asyncio.to_thread(_REVERSE_PARSERS[key], image)
            if not _alive():
                emit({"event": "reverse_site_update", "session": session, "site": key,
                      "name": name, "status": "cancelled", "results": []})
                return
            results = _reverse_with_proxied_thumbs(data.get("results") or [])
            emit({"event": "reverse_site_update", "session": session, "site": key,
                  "name": name, "status": "done", "results": results,
                  "url": data.get("url") or ""})
            collected.append({"site": key, "name": name, "results": results})
        except Exception as exc:  # noqa: BLE001 —— 单站失败不影响其他站点
            logging.info("识图站点 %s 失败: %s", name, exc)
            if not _alive():
                emit({"event": "reverse_site_update", "session": session, "site": key,
                      "name": name, "status": "cancelled", "results": []})
                return
            emit({"event": "reverse_site_update", "session": session, "site": key,
                  "name": name, "status": "failed", "error": str(exc)[:200], "results": []})

    collected: list[dict] = []
    await asyncio.gather(*[_run(s) for s in REVERSE_SITES])

    if _reverse_session != session:
        # 已被取消或已被新一轮取代：不回传结果
        return
    _reverse_running = False
    ok_sites = [g["name"] for g in collected]
    failed_sites = [s["name"] for s in REVERSE_SITES
                    if s["name"] not in ok_sites]
    if collected:
        _reverse_cache_put(cache_key, {"groups": collected})
    emit({"event": "reverse_all_done", "session": session, "ok_sites": ok_sites,
          "failed_sites": failed_sites, "groups": collected,
          "merged": _reverse_merge(collected), "cached": False})


def _reverse_paste_path() -> str:
    return os.path.join("cache", "reverse_paste.txt")


def reverse_paste_get() -> None:
    """读取左侧识图粘贴板内容（cache/reverse_paste.txt）。"""
    text = ""
    try:
        with open(_reverse_paste_path(), "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        text = ""
    emit({"event": "reverse_paste", "text": text})


def reverse_paste_save(text: str) -> None:
    """保存识图粘贴板内容。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(_reverse_paste_path(), "w", encoding="utf-8") as f:
            f.write(text or "")
        emit({"event": "reverse_paste_saved", "ok": True})
    except Exception as exc:  # noqa: BLE001
        logging.warning("保存识图粘贴板失败: %s", exc)
        emit({"event": "reverse_paste_saved", "ok": False, "error": str(exc)})


DEFAULT_SETTINGS = {
    "custom_path": "",
    "site": "bunkr",
    # 表世界（美好世界）专属保存位置：留空 = 用户下载夹。
    # 只影响表世界的媒体下载 / 流媒体拼接 / Word 导出；里世界沿用 custom_path 与各站规则
    "surface_save_path": "",
    # 识图（反向图片搜索）设置：代理默认只给 Lenso.ai 用，
    # reverse_proxy_all=True 时所有识图站点都走该代理
    "reverse_proxy": "",
    "reverse_proxy_all": False,
    "reverse_lenso_token": "",       # Lenso.ai 付费 API token（留空跳过该站）
    "reverse_saucenao_api_key": "",  # SauceNAO API Key（免费注册获取；留空走免费配额）
    "pawchive_search_mode": "artist",
    "pawchive_subfolder": "date_post",
    "exhentai_proxy": "http://127.0.0.1:10809",
    # ExHentai 搜索过滤选项（对应原版搜索页按钮）
    "exhentai_cats": [key for key, _, _ in EXHENTAI_CATEGORIES],  # 默认全部分类
    "exhentai_min_rating": 0,      # 最低评分（0=不限，2-5）
    "exhentai_torrents_only": False,  # 仅显示有种子的画廊
    "exhentai_page_min": 0,        # 最小页数（0=不限）
    "exhentai_page_max": 0,        # 最大页数（0=不限）
    "exhentai_subfolder": "date_post",
    # Twitter/X 专属设置
    "twitter_proxy": "http://127.0.0.1:10809",
    # twitter_subfolder: media（图片/视频分类，默认，旧值 date_post 等已兼容为新结构）
    "twitter_subfolder": "media",
    # X 站 MD5 查重：同内容（同 MD5）媒体在多条推文重复出现时只保留最早发布的一份
    "twitter_md5_dedup": True,
    # Iwara 专属设置（代理留空 = 直连）
    "iwara_proxy": "",
    # Hanime1 / Oreno3D / EroMMDTube / ASMR 专属设置（Hanime1 国内需代理；其余默认直连）
    "hanime_proxy": "http://127.0.0.1:10809",
    "oreno_proxy": "",
    "erommd_proxy": "",
    "asmr_proxy": "",
    # 三次元新站（xhamster/pornhub 走 OAuth + 代理；xvideos 默认直连；javdb 国内必须代理）
    "xhamster_proxy": "http://127.0.0.1:10809",
    "pornhub_proxy": "http://127.0.0.1:10809",
    "xvideos_proxy": "",
    "javdb_proxy": "http://127.0.0.1:10809",
    # 谷歌邮箱（OAuth 授权共用凭据源，国内必须代理）与 Oreno3D 登录会话
    "google_proxy": "http://127.0.0.1:10809",
    "oreno3d_proxy": "",
    # 每站点自定义子文件夹模板（留空=使用上方的组织规则；变量 {date}/{date_full}/{title}/{id}）
    "pawchive_folder_template": "",
    "exhentai_folder_template": "",
    "twitter_folder_template": "",
    "iwara_folder_template": "",
    "search_history_switch_site": False,
    # 下载去重：同名且大小一致直接跳过；重名按 manual_rename 决定手动改/自动序号
    "skip_duplicates": False,
    "manual_rename": False,
    # 界面主题：dark=夜间 / light=日间
    "theme": "dark",
    "connections": 8,
    "concurrent_files": 2,
    "rate_limit": None,
    "max_retries": 5,
    "clean_name": False,
    "organize_by_type": False,
    "date_stamp": False,
    "no_download_folder": False,
    "disable_disk_check": False,
    "ignore": [],
    "include": [],
    "float_visible": False,  # 默认不开下载悬浮窗（2026-09-17 用户要求：避免旁人看到下载历史）
    # 主界面模式：False=经典下载器界面 / True=热门平台界面（B站/抖音/小红书等）
    "ui_mode_hot": False,
    # 有道智云翻译 API（用户在设置区填写，留空=未配置）
    "youdao_app_id": "",
    "youdao_app_secret": "",
    # 免费翻译引擎配置（默认 Google 无 key；可选填 LibreTranslate 自建实例 URL + key）
    "translate_engine": "google_free",   # "google_free" | "libretranslate" | "youdao"
    "libretranslate_url": "",             # 如 https://libretranslate.com 或自建实例
    "libretranslate_api_key": "",
    # 翻译代理（Google 端点国内必须代理；留空=直连。先代理后直连自动回退）
    "translate_proxy": "http://127.0.0.1:10809",
    # 全局自动翻译目标语言（右侧 🌐 按钮开关；左侧翻译面板可修改）
    "auto_translate_to": "zh-CN",
    # P3 设置功能：快捷键 / 拟态模式
    "shortcut_quick_minimize": "",        # 快速缩小到托盘（如 "Ctrl+Shift+M"）
    "shortcut_toggle_mimic": "",          # 切换拟态模式（如 "Ctrl+Shift+P"）
    "shortcut_toggle_float": "",         # 切换悬浮窗显示（如 "Ctrl+Shift+F"）
    "mimic_file_path": "",               # 拟态面板上传的文件路径（txt/word/pdf/图片等）
    "mimic_enabled": False,              # 拟态模式开关
    # GitHub 仓库更新检查代理（国内默认 http://127.0.0.1:10809）
    "github_proxy": "http://127.0.0.1:10809",
}


def _load_settings() -> dict:
    """读取用户设置，并与默认值合并。

    读取优先级：theme_cache.dat 的 settings 分区（用户习惯快照，随账号库走）
    > settings.json（主进程/后端共用的明文文件）> 默认值。
    theme_cache 分区由每次 _save_settings 自动镜像——重装/换目录后只要
    账号库还在，用户的全部设置习惯就会自动恢复。"""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with Path(SETTINGS_FILE).open("r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                settings.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    try:
        saved = (_secure_store_load() or {}).get("settings")
        if isinstance(saved, dict) and saved:
            settings.update(saved)
    except Exception:
        pass
    return settings


def _save_settings(settings: dict) -> None:
    """保存用户设置：settings.json（主进程共用）+ 镜像进 theme_cache.dat。"""
    try:
        _atomic_write_json(SETTINGS_FILE, settings)
    except OSError as exc:
        logging.warning("保存设置失败: %s", exc)
    try:
        data = _secure_store_load()
        data["settings"] = dict(settings)
        _secure_store_save(data)
    except Exception as exc:
        logging.warning("设置镜像到账号库失败（不影响使用）: %s", exc)
