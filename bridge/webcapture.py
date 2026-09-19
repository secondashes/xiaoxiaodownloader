# -*- coding: utf-8 -*-
# 表世界网页捕获工具集：文字转 Word / 流媒体拼接完整版 / 视频时长探测。
# 命名：全模块 WEB_ 前缀唯一（bridge finalize 同名互踩坑）；WEB_COMMANDS 在
# bridge/__init__.py 显式并入总表。
# 1. web_to_word: 前端在 webview 页面内提取正文元素序列（文档序），后端
#    python-docx 按序生成 .docx：图片按原位插入、表格还原为 Word 表格。
# 2. hls_concat: m3u8（含二级）解析分片 -> 分片字节流直送 ffmpeg stdin 拼接 ->
#    remux 成 MP4（含完整声音）；可另产「无声音版」（-an 去音轨）。
# 3. probe_duration: 视频时长探测（ffprobe 远程直读）。
# 4. web_registry_fetch: 表世界站点校验表（发布仓库 surface_sites.json）拉取，
#    raw → jsDelivr → 缓存兜底；前端据 status=ok/dead 下发新地址/标记失效。
# 安全：输出路径经 web_output_path 校验（abspath 后必须位于输出根目录内）；
# 子进程一律 argv 参数列表内联 + shell=False；URL 一律公网 https 校验。
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin, urlunparse

import requests

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_WEB_PROBE_CACHE = {}
_WEB_PROBE_LOCK = threading.Lock()

# web_to_word 加固阈值：内容块/图片上限 + 网络预算，保证单条命令不会拖死命令循环
WEB_WORD_MAX_BLOCKS = 1500       # 单篇最多处理的内容块数（超出截断）
WEB_WORD_MAX_TEXT = 20000        # 单块文本最大字符数
WEB_WORD_MAX_IMAGES = 40         # 整页最多下载的图片数（超出跳过并记占位）
WEB_WORD_IMG_TIMEOUT = 12        # 单张图片超时（秒）
WEB_WORD_IMG_MAX_BYTES = 12 * 1024 * 1024   # 单张图片大小上限
WEB_WORD_NET_BUDGET = 90         # 整页图片总网络预算（秒），到点后剩余图片直接占位

# python-docx add_picture 靠文件头识别，只认这些格式（docx.image.SIGNATURES）：
# WebP / AVIF / HEIC 一律 UnrecognizedImageError，必须转码后才能插入。
WEB_WORD_DOCX_FORMATS = frozenset({"PNG", "JPEG", "GIF", "BMP", "TIFF"})
# 已知「URL 自带图片处理后缀」的 CDN：base.png@976w_550h_!cover.avif → base.png 即原图。
# 只对这些域名生效，避免对任意 URL 乱剥后缀剥出 404。
WEB_WORD_CDN_STRIP_HOSTS = ("hdslb.com", "biliimg.com")
WEB_WORD_CDN_IMG_EXTS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".tiff", ".heic"})
# 失败归因类别 → 用户可读文案（word_result 里分类统计，让用户一眼看出问题）
WEB_WORD_FAIL_LABELS = {
    "download": "下载失败",      # 网络/HTTP 错误
    "format": "格式不支持",      # 解码/转码失败（如 Pillow 缺 libavif）
    "limit": "超限跳过",         # 张数上限 / 网络预算
    "invalid": "地址无效",       # 空地址或非 http(s)
    "decode": "解码失败",        # data: URI 本身坏掉
}
_web_word_avif_ok = None         # Pillow libavif 探测结果缓存（None = 尚未探测）


def web_safe_name(text, limit=60):
    name = re.sub(r'[\\/:*?"<>|\r\n`$;&]+', "_", str(text or "").strip())
    return name[:limit] or "web"


def web_check_url(url):
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host in ("localhost", "0.0.0.0", "::1") or host.endswith(".local"):
        return False
    try:
        import ipaddress as _ip
        ip = _ip.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            return False
    except ValueError:
        pass
    return True


def web_output_path(base_dir, name):
    # 输出位置限定在 base_dir 内：先消毒文件名，再 abspath+前缀校验防越界
    safe = web_safe_name(name, 120)
    root = os.path.normpath(os.path.abspath(base_dir))
    full = os.path.normpath(os.path.join(root, safe))
    if not full.startswith(root + os.sep):
        return None
    return full


def web_surface_root():
    """表世界（美好世界）保存根目录。

    取设置里的 `surface_save_path`（设置区「表世界保存位置」可改）；留空 = 用户下载夹。
    只影响表世界：媒体下载、流媒体拼接、Word 导出的落盘根目录都走这里，
    里世界/各站点下载继续沿用它们自己的路径规则（互不干扰）。
    """
    base = ""
    try:
        base = str((_load_settings() or {}).get("surface_save_path") or "").strip()
    except Exception:                     # noqa: BLE001（设置读取失败不能拖垮下载）
        base = ""
    if not base:
        base = os.path.join(os.path.expanduser("~"), "Downloads")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return base


def web_surface_downloads_dir():
    return web_surface_root()


def web_word_dir():
    # Word 导出归表世界产物：跟随「表世界保存位置」，默认 下载夹/Word导出
    base = os.path.join(web_surface_root(), "Word导出")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return base


# ============ HLS 智能识别：哪一条 m3u8 才是「要下的正片」 ============
# 判断依据全部来自播放清单本身（零额外网络请求），四类信号加权：
#   1. 总时长：#EXTINF 求和即节目时长。广告 15/30 秒，正片通常 ≥5 分钟
#      —— 最强也最便宜的信号（用户实测「广告基本都是 0.5 分钟内」）。
#   2. 广告插播硬标记：SCTE-35 系（#EXT-X-CUE-OUT / #EXT-OATCLS-SCTE35 /
#      #EXT-X-DATERANGE 带 SCTE35-* 属性）由广告系统自己写进清单，命中即广告、
#      不看时长——广告主标的，比任何启发式都准。
#   3. 地址特征：/ad/ /preroll/ /midroll/ /vast/ /vmap/ /bumper/ /trailer/
#      /promo/ /preview/ /sample/ 等独立词（清单地址 + 变体地址 + 全部分片地址）。
#   4. 分片数与清晰度：≤3 片且无高清变体 → 短片；≥30 片 → 完整长视频。
# 打分落 3 档：ad（疑似广告，「全部下载」自动跳过）/ unknown（存疑，照常列出）
# / content（正片，排序优先 + 「已识别到正片」提示）。
WEB_HLS_AD_HARD_SEC = 30.0      # ≤30s 直接判广告（广告标准长度 15/30 秒）
WEB_HLS_AD_SOFT_SEC = 60.0      # ≤60s 再叠加弱信号 → 也判广告
WEB_HLS_CONTENT_SEC = 300.0     # ≥5 分钟：正片
WEB_HLS_AD_TAGS = (
    "#EXT-X-CUE-OUT", "#EXT-X-CUE-IN", "#EXT-X-CUE-OUT-CONT",
    "#EXT-OATCLS-SCTE35", "#EXT-X-SCTE35",
)
WEB_HLS_AD_DATERANGE = ("SCTE35-", "X-AD-ID", "AD-ID=", "ADS-")
# 广告词必须**独立成词**（前后为 / _ . - 或串首尾）：download / loading / hadron
# 里的 ad 都不算。故意不含 "adv"——实测 Apple 官方测试流
# img_bipbop_adv_example 会被 "adv" 误命中，而 adv/advanced 在正常资源名里很常见。
WEB_HLS_AD_URL_RE = re.compile(
    r"(?:^|[/_.\-])(ad|ads|advert|advertising|preroll|pre-?roll|midroll|mid-?roll"
    r"|postroll|post-?roll|vast|vmap|bumper|sponsor|promo|trailer|preview|sample|teaser)"
    r"(?:[/_.\-]|$)", re.I)


def _web_hls_ad_url_hits(*sources):
    """地址里的广告特征词（清单地址 + 变体地址 + 分片地址），去重后返回。"""
    hits, seen = [], set()
    for src in sources:
        if not src:
            continue
        if isinstance(src, str):
            cand = [src]
        elif isinstance(src, dict):
            cand = [src.get("url") or ""]
        else:
            cand = []
            for x in src:
                if isinstance(x, str):
                    cand.append(x)
                elif isinstance(x, dict):
                    cand.append(x.get("url") or "")
        for s in cand:
            for m in WEB_HLS_AD_URL_RE.finditer(str(s)):
                w = m.group(1).lower()
                if w not in seen:
                    seen.add(w)
                    hits.append(w)
    return hits[:6]


def web_hls_fmt_dur(sec):
    """秒 → 中文时长文案（判决理由与列表展示共用）。"""
    try:
        s = int(round(float(sec)))
    except (TypeError, ValueError):
        return "未知"
    if s <= 0:
        return "未知"
    if s >= 3600:
        return f"{s // 3600} 小时 {s % 3600 // 60} 分"
    if s >= 60:
        return f"{s // 60} 分 {s % 60} 秒"
    return f"{s} 秒"


def web_hls_analyze(text, base_url):
    """播放清单结构化解析（判决 + 任务化下载共用，零额外网络请求）。

    返回字段：
      master/sub/variants  主清单与最高码率变体（#EXT-X-STREAM-INF）
      segs/seg_count       媒体清单分片绝对地址（相对地址 urljoin 补全）
      seg_ranges           与 segs 同序的 BYTERANGE (offset, length)，无则为 None
      duration             总时长（#EXTINF 求和，秒）；0 = 未知
      live                 True = 无 #EXT-X-ENDLIST 且有分片（直播/边录边写）
      vod                  #EXT-X-PLAYLIST-TYPE:VOD
      encrypted/key_*      #EXT-X-KEY（METHOD/URI/IV）；key_multi=多密钥轮换（不支持）
      media_sequence       #EXT-X-MEDIA-SEQUENCE（AES 未给 IV 时 IV 的推导起点）
      fmp4/init_uri        #EXT-X-MAP（fMP4 初始化段）
      byte_range           分片走 #EXT-X-BYTERANGE 区间请求
      ad_tags/ad_url_hits  广告硬标记 / 地址广告特征词（判决输入）
      max_res/max_bandwidth 变体里的最高清晰度（短边像素）与最高码率

    永不抛异常——清单畸形时返回尽可能多的已知信息。
    """
    info = {
        "base": base_url, "master": False, "sub": None, "segs": [], "variants": [],
        "duration": 0.0, "seg_count": 0, "target_duration": 0.0,
        "live": False, "endlist": False, "vod": False,
        "encrypted": False, "key_uri": "", "key_iv": "", "key_method": "",
        "key_multi": False, "media_sequence": 0,
        "init_uri": "", "fmp4": False, "byte_range": False, "seg_ranges": [],
        "ad_tags": [], "ad_url_hits": [], "max_res": 0, "max_bandwidth": 0,
    }
    lines = str(text or "").splitlines()
    _key_uri_1st = None      # 首个非 NONE 的 KEY URI（判「多密钥轮换」）
    _pending_range = None    # #EXT-X-BYTERANGE 待绑定给下一个分片
    _prev_end = 0            # 上一分片结束位置（BYTERANGE 省略 offset 时接着算）
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        up = line.upper()
        if line.startswith("#EXTINF"):
            m = re.search(r"#EXTINF:\s*([0-9]*\.?[0-9]+)", line, re.I)
            if m:
                with contextlib.suppress(ValueError):
                    info["duration"] += float(m.group(1))
        elif up.startswith("#EXT-X-TARGETDURATION"):
            m = re.search(r":\s*([0-9]*\.?[0-9]+)", line)
            if m:
                with contextlib.suppress(ValueError):
                    info["target_duration"] = float(m.group(1))
        elif up.startswith("#EXT-X-MEDIA-SEQUENCE"):
            # 媒体序列号：AES-128 未显式给 IV 时，它就是分片 IV 的推导起点（RFC 8216）
            m = re.search(r":\s*(\d+)", line)
            if m:
                with contextlib.suppress(ValueError):
                    info["media_sequence"] = int(m.group(1))
        elif up.startswith("#EXT-X-STREAM-INF"):
            info["master"] = True
            bw = res = 0
            mb = re.search(r"BANDWIDTH=(\d+)", up)
            if mb:
                bw = int(mb.group(1))
            mr = re.search(r"RESOLUTION=(\d+)X(\d+)", up)
            if mr:
                res = min(int(mr.group(1)), int(mr.group(2)))
            j = i + 1
            while j < len(lines) and (not lines[j].strip()
                                      or lines[j].strip().startswith("#")):
                j += 1
            uri = lines[j].strip() if j < len(lines) else ""
            if uri and not uri.startswith("#"):
                info["variants"].append(
                    {"url": urljoin(base_url, uri), "bandwidth": bw, "resolution": res})
                info["max_bandwidth"] = max(info["max_bandwidth"], bw)
                info["max_res"] = max(info["max_res"], res)
            i = j
        elif up.startswith("#EXT-X-KEY"):
            m = re.search(r"METHOD=([A-Z0-9\-]+)", up)
            method = m.group(1) if m else ""
            if method and method != "NONE":
                info["encrypted"] = True
                info["key_method"] = method
                mu = re.search(r'URI="([^"]+)"', line) or re.search(r"URI=([^,]+)", line)
                if mu:
                    uri = urljoin(base_url, mu.group(1).strip())
                    if _key_uri_1st is None:
                        _key_uri_1st = uri
                    elif uri != _key_uri_1st:
                        # 多密钥轮换（广告段换 key 是常见手法）：单 key 模型处理不了，
                        # 标记出来让下载端明确拒绝，而不是拼出一个坏文件
                        info["key_multi"] = True
                    if not info["key_uri"]:
                        info["key_uri"] = uri
                mv = re.search(r"IV=(0[Xx][0-9A-Fa-f]+)", line)
                if mv and not info["key_iv"]:
                    info["key_iv"] = mv.group(1)
        elif up.startswith("#EXT-X-MAP"):
            info["fmp4"] = True
            m = re.search(r'URI="([^"]+)"', line) or re.search(r"URI=([^,]+)", line)
            if m:
                info["init_uri"] = urljoin(base_url, m.group(1).strip())
        elif up.startswith("#EXT-X-BYTERANGE"):
            # #EXT-X-BYTERANGE:<长度>[@<偏移>]：偏移省略时接着上一分片末尾算
            info["byte_range"] = True
            m = re.search(r":\s*(\d+)(?:@(\d+))?", line)
            if m:
                length = int(m.group(1))
                offset = int(m.group(2)) if m.group(2) else _prev_end
                _pending_range = (offset, length)
                _prev_end = offset + length
        elif up.startswith("#EXT-X-PLAYLIST-TYPE:VOD"):
            info["vod"] = True
        elif up.startswith("#EXT-X-ENDLIST"):
            info["endlist"] = True
        elif line.startswith("#"):
            for tag in WEB_HLS_AD_TAGS:
                if up.startswith(tag) and tag not in info["ad_tags"]:
                    info["ad_tags"].append(tag)
            if up.startswith("#EXT-X-DATERANGE") and "#EXT-X-DATERANGE(SCTE35)" not in info["ad_tags"]:
                if any(kw.upper() in up for kw in WEB_HLS_AD_DATERANGE):
                    info["ad_tags"].append("#EXT-X-DATERANGE(SCTE35)")
        else:
            info["segs"].append(urljoin(base_url, line))
            info["seg_ranges"].append(_pending_range)
            _pending_range = None
        i += 1
    info["seg_count"] = len(info["segs"])
    info["live"] = (not info["endlist"]) and bool(info["segs"])
    # 选下钻目标：优先在「带 RESOLUTION 的变体」里取最高码率——部分站点的 master
    # 把纯音频轨与视频轨并列（音频轨 BANDWIDTH 可能反而更高），不看 RESOLUTION
    # 会下钻到纯音频清单，结果「下载整片」只得到一段音频。全都没标 RESOLUTION
    # 时才退回全变体最高码率。
    with_res = [v for v in info["variants"] if v.get("resolution")]
    pool = with_res or info["variants"]
    if pool:
        info["sub"] = max(pool, key=lambda v: v.get("bandwidth") or 0)["url"]
    info["ad_url_hits"] = _web_hls_ad_url_hits(
        base_url, info["sub"], info["variants"], info["segs"])
    return info


def web_hls_verdict(info):
    """对 web_hls_analyze 的结果打分 → (verdict, score, reasons)。

    verdict: "ad"（疑似广告，批量下载时自动跳过）/ "content"（正片，优先展示）
             / "unknown"（存疑，照常列出但不高亮）。reasons 为中文理由（前端 tooltip）。
    """
    score = 0
    reasons = []
    ad_tags = info.get("ad_tags") or []
    ad_urls = info.get("ad_url_hits") or []
    try:
        dur = float(info.get("duration") or 0)
    except (TypeError, ValueError):
        dur = 0.0
    segs = int(info.get("seg_count") or 0)
    res = int(info.get("max_res") or 0)

    if ad_tags:
        score += 5
        reasons.append("清单含广告插播标记（" + "、".join(ad_tags[:2]) + "）")
    if ad_urls:
        score += 3
        reasons.append("地址含广告特征词：" + "、".join(ad_urls[:3]))
    live = bool(info.get("live"))
    # 直播清单的 #EXTINF 只是滑动窗口，不是节目总长；分片少也只是「刚开播」。
    # 两者都不参与打分，否则直播会被短时长规则误判成广告。
    if dur > 0 and not live:
        if dur <= WEB_HLS_AD_HARD_SEC:
            score += 4
            reasons.append(f"总时长仅 {web_hls_fmt_dur(dur)}，是广告的典型长度")
        elif dur <= WEB_HLS_AD_SOFT_SEC:
            score += 1
            reasons.append(f"总时长 {web_hls_fmt_dur(dur)}，明显偏短")
        elif dur >= WEB_HLS_CONTENT_SEC:
            score -= 4
            reasons.append(f"总时长 {web_hls_fmt_dur(dur)}，符合正片长度")
        elif dur >= 180:
            score -= 2
            reasons.append(f"总时长 {web_hls_fmt_dur(dur)}，像完整内容")
        else:
            score -= 1
    if segs and not live:
        if segs >= 30:
            score -= 2
            reasons.append(f"共 {segs} 个分片，是完整长视频")
        elif segs >= 12:
            score -= 1
        elif segs <= 3 and dur <= 0:
            # 分片数与时长高度相关，短时长已经计过分，这里只在「时长未知」时补一刀
            score += 1
            reasons.append(f"只有 {segs} 个分片")
    if live:
        score -= 1
        reasons.append("无 ENDLIST（直播/边录边写）")
    if res and res <= 360:
        score += 1
        reasons.append(f"最高清晰度仅 {res}p")

    if live and score < 3:
        # 直播：没命中广告硬信号（SCTE-35/广告路径）就一律算存疑，
        # 不把「正在直播」误标成正片，也不在批量下载时跳过它
        return "unknown", score, reasons
    if score >= 3:
        verdict = "ad"
    elif score <= -2:
        verdict = "content"
    else:
        verdict = "unknown"
    return verdict, score, reasons


def web_parse_m3u8(text, base_url):
    """解析 m3u8 文本 → (子播放列表地址或 None, 分片地址列表)。

    向后兼容薄封装（老调用点仍在用）；新代码请直接用 web_hls_analyze 拿完整
    信息（时长/加密/fMP4/广告判决）。加密流（AES/SAMPLE-AES）分片列表返回空。
    """
    info = web_hls_analyze(text, base_url)
    if info.get("encrypted"):
        return None, []
    return info.get("sub"), list(info.get("segs") or [])


def _web_ts_sync_offset(buf, max_off=4096):
    """定位 MPEG-TS 同步偏移（图片马甲流剥壳）。

    部分站点把 TS 分片整个塞进合法 PNG/JPEG 外壳（文件头 + 假 IHDR/IDAT 块），
    放在公共图片 CDN 上，content-type 也报 image/png —— CDN 当图片收、嗅探器当
    图片放行。真身是 TS：以 188 字节为单位、每包首字节 0x47 同步字节。
    在 buf 前 max_off 字节内找「连续 4 个 188 间隔的 0x47」即同步点。
    返回偏移（0=本来就是对齐 TS；-1=没找到，可能根本不是 TS，原样使用）。
    """
    limit = min(max_off, max(0, len(buf) - 188 * 3))
    for off in range(0, limit):
        if (buf[off] == 0x47 and buf[off + 188] == 0x47
                and buf[off + 376] == 0x47 and buf[off + 564] == 0x47):
            return off
    return -1


# ============ HLS 任务化：分片落盘 + 断点续传 + 合并 ============
# 与 hls_concat（一体式、分片字节流直送 ffmpeg stdin）的分工：hls_concat 是一次性
# 动作，进不了下载管理、不可暂停续传。本组函数把分片先落盘到
# cache/hls_parts/<task_id>/，同目录 state.json 记「已完成分片 → 字节数」，
# 清单指纹变化时自动作废重下；全部分片就绪后按序二进制拼接 + ffmpeg remux 成 MP4。
# 「下载整片」经 hls_submit 提交为下载任务，因而可暂停 / 继续 / 重试，进度实时
# 出现在下载管理（进度单位=分片数，HLS 一个视频就是几百个分片）。
WEB_HLS_PARTS_ROOT = os.path.join("cache", "hls_parts")
WEB_HLS_SEG_WORKERS = 4          # 分片并发数（过高易被 CDN 限速或封 IP）
WEB_HLS_SEG_BATCH = 16           # 每批提交数：批间查暂停，保证暂停响应及时
WEB_HLS_SEG_RETRIES = 3          # 单个分片下载重试次数
WEB_HLS_SEG_TIMEOUT = 60         # 单个分片读取超时（秒）
WEB_HLS_PAUSED = "__paused__"    # 暂停/取消哨兵：调用方据此保留断点而非记失败


def _web_hls_task_dir(task_id: str) -> str:
    """任务的分片暂存目录（task_id 由 download_manager 生成，仍做一次净化）。"""
    safe = re.sub(r"[^0-9A-Za-z_\-]", "", str(task_id))[:80] or "task"
    return os.path.join(WEB_HLS_PARTS_ROOT, safe)


def _web_hls_state_path(task_dir: str) -> str:
    return os.path.join(task_dir, "state.json")


def _web_hls_load_state(task_dir: str) -> dict:
    """读续传状态；损坏/缺失一律当空（重下即可，不阻断下载）。"""
    try:
        with open(_web_hls_state_path(task_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:                                      # noqa: BLE001
        return {}


def _web_hls_save_state(task_dir: str, state: dict) -> None:
    """原子写续传状态（先写 .tmp 再 replace，中断不会留下半截 JSON）。"""
    try:
        os.makedirs(task_dir, exist_ok=True)
        dst = _web_hls_state_path(task_dir)
        tmp = dst + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, dst)
    except Exception:                                      # noqa: BLE001
        logging.exception("HLS 续传状态写入失败: %s", task_dir)


def _web_hls_seg_ext(u: str) -> str:
    """分片落盘扩展名（按地址推断；仅便于排查，拼接收内容不看扩展名）。"""
    try:
        ext = os.path.splitext(urlparse(str(u)).path)[1].lower()
        if ext in (".ts", ".m4s", ".mp4", ".aac", ".m4a", ".mp3"):
            return ext
    except Exception:                                      # noqa: BLE001
        pass
    return ".ts"


def _web_hls_playlist_sig(final_url: str, segs: list) -> str:
    """清单指纹：清单换了（换签名 / 换清晰度 / 直播增长）就不能复用旧分片。"""
    raw = "\n".join([str(final_url), str(len(segs)),
                     str(segs[0]) if segs else "", str(segs[-1]) if segs else ""])
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _web_hls_clear_parts(task_dir: str) -> None:
    """清空分片文件（保留目录本身）；供清单指纹失效时重下。"""
    try:
        for fn in os.listdir(task_dir):
            fp = os.path.join(task_dir, fn)
            if os.path.isfile(fp):
                with contextlib.suppress(OSError):
                    os.remove(fp)
    except OSError:
        pass


def _web_hls_fetch_key(sess, info: dict) -> bytes:
    """拉取 AES-128 密钥（#EXT-X-KEY 的 URI）。失败返回空 bytes。"""
    uri = str(info.get("key_uri") or "")
    if not uri:
        return b""
    try:
        r = sess.get(uri, timeout=30)
        r.raise_for_status()
        return r.content or b""
    except Exception:                                      # noqa: BLE001
        logging.warning("HLS 密钥拉取失败: %s", uri[:120])
        return b""


def _web_hls_seg_iv(info: dict, seq: int) -> bytes:
    """分片 IV：清单显式给了就用它，否则用媒体序列号做 128 位大端整数（RFC 8216）。"""
    iv_hex = str(info.get("key_iv") or "").strip()
    if iv_hex:
        raw = iv_hex[2:] if iv_hex.lower().startswith("0x") else iv_hex
        with contextlib.suppress(ValueError):
            return bytes.fromhex(raw.rjust(32, "0"))
    base_seq = int(info.get("media_sequence") or 0)
    return (base_seq + seq).to_bytes(16, "big")


def _web_hls_aes_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC 解密 + 去 PKCS7 填充。失败原样返回（宁可拼出错也别中断整片）。"""
    if not data or len(key) != 16:
        return data
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        out = dec.update(data) + dec.finalize()
    except Exception:                                      # noqa: BLE001
        logging.exception("HLS 分片解密失败（按原样使用）")
        return data
    if out:
        pad = out[-1]
        if 1 <= pad <= 16 and out[-pad:] == bytes([pad]) * pad:
            out = out[:-pad]
    return out


def _web_hls_fetch_one_seg(sess, seg_url: str, dest: str, *,
                           rng=None, key: bytes = b"",
                           iv: bytes = b"") -> tuple[int, bool]:
    """下载单个分片到 dest（原子落盘：先 .part 再 rename）。

    rng=(offset, length) → 走 Range 请求（#EXT-X-BYTERANGE 分片）；
    返回 (字节数, 是否命中「图片马甲」剥壳)。
    key 非空 → 先 AES-128-CBC 解密再落盘（HLS 是逐片独立加密，落盘即明文，
    续传时读到的直接可用，不必把密钥写进断点状态）。
    剥壳（TS 套 PNG 外壳）必须在落盘前完成，否则最后拼出来的东西 ffmpeg 会认成
    png_pipe 直接失败。
    """
    tmp = dest + ".part"
    headers = None
    if rng:
        off, length = rng
        headers = {"Range": f"bytes={off}-{off + length - 1}"}
    last_err = None
    for attempt in range(WEB_HLS_SEG_RETRIES):
        masked = False
        written = 0
        resp = None
        try:
            resp = sess.get(seg_url, timeout=WEB_HLS_SEG_TIMEOUT,
                            stream=True, headers=headers)
            resp.raise_for_status()
            if key:
                # 加密分片必须整块拿到（CBC 要完整密文块）→ 解密 → 剥壳 → 写盘
                data = _web_hls_aes_decrypt(resp.content or b"", key, iv)
                off = _web_ts_sync_offset(data)
                if off > 0:
                    masked = True
                    data = data[off:]
                written = len(data)
                if written <= 0:
                    raise ValueError("分片解密后为空")
                with open(tmp, "wb") as f:
                    f.write(data)
            else:
                # pending 非空 = 还在攒首块（攒满 768B = 4 个 TS 包才判同步偏移，
                # 首块过小会误判；剥壳后立刻写盘，保证 ffmpeg 见到的首字节就是真 TS）
                pending = b""
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(256 * 1024):
                        if not chunk:
                            continue
                        if pending is not None:
                            pending += chunk
                            if len(pending) < 768:
                                continue
                            off = _web_ts_sync_offset(pending)
                            if off > 0:
                                masked = True
                                pending = pending[off:]
                            f.write(pending)
                            written += len(pending)
                            pending = None
                            continue
                        f.write(chunk)
                        written += len(chunk)
                    if pending:                 # 整片不足 768B 的极端情况
                        off = _web_ts_sync_offset(pending)
                        if off > 0:
                            masked = True
                            pending = pending[off:]
                        f.write(pending)
                        written += len(pending)
            if written <= 0:
                raise ValueError("分片内容为空")
            os.replace(tmp, dest)
            return written, masked
        except Exception as exc:                           # noqa: BLE001
            last_err = exc
            with contextlib.suppress(OSError):
                os.remove(tmp)
            if attempt < WEB_HLS_SEG_RETRIES - 1:
                time.sleep(1 + attempt)
        finally:
            if resp is not None:
                with contextlib.suppress(Exception):
                    resp.close()
    raise RuntimeError(f"{type(last_err).__name__}: {last_err}")


def web_hls_fetch_segments(
    url: str,
    referer: str,
    task_dir: str,
    out_path: str,
    *,
    mute: bool = False,
    stop_check=None,
    progress_cb=None,
    log_cb=None,
):
    """分片下载（落盘 + 断点续传 + AES 解密）→ 二进制拼接 → remux 成 MP4。

    返回 (ok, message)；ok=False 且 message == WEB_HLS_PAUSED 表示被暂停/取消
    （调用方保留断点，不要计失败）。stop_check() 为 True 时立刻停下并保留已下
    分片，下次启动即从断点续传。progress_cb(done, total, phase, extra) 回报进度。

    覆盖的清单特性：#EXT-X-MAP（fMP4 初始化段，作为首个"分片"参与拼接）、
    #EXT-X-BYTERANGE（Range 区间分片）、#EXT-X-KEY AES-128（逐片解密后落盘）、
    分片地址签名过期（大批 403 时重拉清单换新地址再续，不必整片重下）。
    """
    import subprocess

    def _log(msg: str) -> None:
        if log_cb:
            with contextlib.suppress(Exception):
                log_cb(msg)

    def _progress(done: int, total: int, phase: str, **extra) -> None:
        if progress_cb:
            with contextlib.suppress(Exception):
                progress_cb(done, total, phase, extra)

    def _stopped() -> bool:
        with contextlib.suppress(Exception):
            return bool(stop_check and stop_check())
        return False

    os.makedirs(task_dir, exist_ok=True)
    sess = requests.Session()
    sess.headers.update({"User-Agent": WEB_UA})
    if referer:
        sess.headers["Referer"] = referer

    info, final_url, err = _web_hls_resolve(sess, url)
    if info is None:
        return False, err or "播放清单解析失败"
    segs = list(info.get("segs") or [])
    if not segs:
        return False, _web_hls_no_seg_reason(info)

    # ---- 加密：只做 AES-128 单密钥。其它方式/多密钥轮换明确拒绝——半吊子解密
    #      只会拼出一个能播但花屏的结果，比直接说"不支持"更糟。
    key = b""
    if info.get("encrypted"):
        method = str(info.get("key_method") or "").upper()
        if method != "AES-128":
            return False, f"该流用 {method or '未知方式'} 加密，暂不支持（仅支持 AES-128）"
        if info.get("key_multi"):
            return False, "该流中途切换了多个加密密钥（多 KEY 轮换），暂不支持"
        key = _web_hls_fetch_key(sess, info)
        if len(key) != 16:
            return False, "AES-128 密钥拉取失败（地址失效或需要来源页 Referer）"
        _log("检测到 AES-128 加密流：分片将逐片解密后再合并")

    ext = _web_hls_seg_ext(segs[0])
    init_url = str(info.get("init_uri") or "")
    seg_ranges = list(info.get("seg_ranges") or [])
    if init_url:
        _log("fMP4 清单：带初始化段（#EXT-X-MAP），将作为首个分片参与拼接")

    def _parts() -> list:
        """(落盘文件名, URL, 分片序号（用于推导 IV；init 段为 None）, BYTERANGE)"""
        out = []
        if init_url:
            out.append(("00000.init", init_url, None, None))
        for idx, u in enumerate(segs, 1):
            rng = seg_ranges[idx - 1] if idx - 1 < len(seg_ranges) else None
            out.append((f"{idx:05d}{ext}", u, idx - 1, rng))
        return out

    parts = _parts()
    sig = _web_hls_playlist_sig(final_url, segs)

    state = _web_hls_load_state(task_dir)
    if str(state.get("sig") or "") != sig:
        if state:
            _log("播放清单已变化（换清晰度 / 换签名 / 直播增长），丢弃旧分片重新下载")
        _web_hls_clear_parts(task_dir)
        state = {"sig": sig, "done": {}}
    raw_done = state.get("done") if isinstance(state.get("done"), dict) else {}
    state.update({"sig": sig, "url": url, "total": len(parts), "ext": ext,
                  "encrypted": bool(key), "fmp4": bool(init_url)})

    # 已有分片核对：文件必须存在且字节数与记录一致，否则视为未完成（重下）
    done_map: dict = {}
    for name, _u, _s, _r in parts:
        recorded = raw_done.get(name)
        if not isinstance(recorded, int) or recorded <= 0:
            continue
        with contextlib.suppress(OSError):
            if os.path.getsize(os.path.join(task_dir, name)) == recorded:
                done_map[name] = recorded
    state["done"] = done_map
    _web_hls_save_state(task_dir, state)
    if done_map:
        _log(f"断点续传：已完成 {len(done_map)}/{len(parts)} 个分片，接着下剩下的")
    _progress(len(done_map), len(parts), "downloading", bytes=sum(done_map.values()))

    def _refresh() -> bool:
        """分片地址带时效签名会过期（403/410）——重拉清单换新地址，已下的照旧复用。"""
        new_info, _fu, _e = _web_hls_resolve(sess, url)
        if new_info is None:
            return False
        new_segs = list(new_info.get("segs") or [])
        if not new_segs or len(new_segs) != len(segs) or new_segs == segs:
            # 结构变了或清单根本没变 → 不是签名问题，别瞎折腾（保持失败，让用户重试）
            return False
        segs[:] = new_segs
        seg_ranges[:] = list(new_info.get("seg_ranges") or [])
        if new_info.get("key_uri") and key:
            nk = _web_hls_fetch_key(sess, new_info)
            if len(nk) == 16:
                nonlocal_key[0] = nk
        if new_info.get("media_sequence") or new_info.get("key_iv"):
            info["media_sequence"] = new_info.get("media_sequence") or 0
            if new_info.get("key_iv"):
                info["key_iv"] = new_info["key_iv"]
        return True

    nonlocal_key = [key]                       # 让 _refresh 能换密钥（闭包里改列表）
    import concurrent.futures as _cf
    batch = max(WEB_HLS_SEG_BATCH, WEB_HLS_SEG_WORKERS)
    refresh_left = 1                           # 签名过期只救一次，避免死循环
    masked_segs = 0
    while True:
        todo = [i for i, prt in enumerate(parts) if prt[0] not in done_map]
        if not todo:
            break
        first_fail = None
        for start in range(0, len(todo), batch):
            if _stopped():
                _web_hls_save_state(task_dir, state)
                return False, WEB_HLS_PAUSED
            # 分批并发：一次性提交全部分片的话，暂停要等整批跑完才能生效
            with _cf.ThreadPoolExecutor(max_workers=WEB_HLS_SEG_WORKERS) as pool:
                futures = {}
                for idx in todo[start:start + batch]:
                    name, seg_url, seq, rng = parts[idx]
                    futures[pool.submit(
                        _web_hls_fetch_one_seg, sess, seg_url,
                        os.path.join(task_dir, name),
                        rng=rng, key=nonlocal_key[0],
                        iv=(_web_hls_seg_iv(info, seq) if seq is not None else b""),
                    )] = name
                for fut in _cf.as_completed(futures):
                    name = futures[fut]
                    try:
                        written, masked = fut.result()
                    except Exception as exc:               # noqa: BLE001
                        if first_fail is None:
                            first_fail = (name, exc)
                        continue
                    if masked:
                        masked_segs += 1
                    done_map[name] = written
                    state["done"] = done_map
            # 一批结束落一次状态（中途断电只丢最后一批）+ 报一次进度
            _web_hls_save_state(task_dir, state)
            _progress(len(done_map), len(parts), "downloading",
                      bytes=sum(done_map.values()))
            if first_fail is not None:
                break
        if first_fail is None:
            break
        name, exc = first_fail
        if refresh_left > 0 and _refresh():
            refresh_left -= 1
            parts = _parts()
            _log("分片地址已过期（签名时效）——已重拉播放清单换用新地址，从断点继续")
            continue
        return False, (f"分片 {name} 下载失败：{type(exc).__name__}"
                       f"（已下 {len(done_map)}/{len(parts)} 片，点「重试」可从断点继续）")
    if masked_segs:
        _log(f"其中 {masked_segs} 个分片为「图片马甲」流，已自动剥壳")

    if _stopped():
        _web_hls_save_state(task_dir, state)
        return False, WEB_HLS_PAUSED

    # 拼接：按序号二进制拼接（TS 顺序拼接即为合法流；fMP4 则是 init + 各 fragment），
    # 再交给 ffmpeg 转封装成 MP4（不重编码）。
    _progress(len(parts), len(parts), "merging")
    concat_path = os.path.join(task_dir, "concat" + ext)
    try:
        with open(concat_path, "wb") as out:
            for name, _u, _s, _r in parts:
                with open(os.path.join(task_dir, name), "rb") as part:
                    while True:
                        buf = part.read(4 * 1024 * 1024)
                        if not buf:
                            break
                        out.write(buf)
    except OSError as exc:
        return False, f"分片拼接失败：{type(exc).__name__}（分片已保留，可重试）"

    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", concat_path]
    if mute:
        args += ["-an"]
    args += ["-c", "copy", "-movflags", "+faststart", out_path]
    ok = False
    rc = -1
    err_tail = ""
    try:
        r = subprocess.run(args, capture_output=True, timeout=1800)
        rc = r.returncode
        err_tail = (r.stderr or b"")[-300:].decode("utf-8", errors="replace").strip()
        ok = rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception as exc:                               # noqa: BLE001
        err_tail = f"{type(exc).__name__}: {exc}"
    if not ok:
        # 兜底：ffmpeg 不可用/转封装失败时，直接把拼接产物交付（TS 容器多数能播，
        # 与 _hls_remux_mp4「失败保留原样」策略一致），避免用户白下几百个分片
        try:
            import shutil
            shutil.copyfile(concat_path, out_path)
            ok = os.path.exists(out_path) and os.path.getsize(out_path) > 0
            if ok:
                _log("ffmpeg 转封装未成功，已交付原始拼接产物（TS 容器，多数播放器可播）")
        except OSError:
            ok = False
    if not ok:
        return False, f"合并失败（ffmpeg 返回 {rc}）{('：' + err_tail) if err_tail else ''}"

    _progress(len(parts), len(parts), "done")
    # 成功后清理分片与状态（失败/暂停时保留，供续传与排查）
    with contextlib.suppress(Exception):
        import shutil
        shutil.rmtree(task_dir, ignore_errors=True)
    return True, ""


def _web_hls_no_seg_reason(info: dict) -> str:
    """没有可用分片时的精确原因（以前只会笼统说「加密流或直播流」）。"""
    if info.get("master"):
        return "主清单里没有可用的变体子清单（地址可能已失效）"
    if info.get("live"):
        return "该流是直播/录制中且当前清单为空，稍后重试"
    if info.get("encrypted"):
        method = str(info.get("key_method") or "未知方式").upper()
        if method != "AES-128":
            return f"该流用 {method} 加密，暂不支持（仅支持 AES-128）"
    return "m3u8 中未解析到分片（清单格式异常或地址已失效）"


def _web_hls_enc_unsupported(info: dict) -> str:
    """加密方式不受支持时的原因；支持（AES-128 单密钥）时返回空串。"""
    if not info.get("encrypted"):
        return ""
    method = str(info.get("key_method") or "").upper()
    if method != "AES-128":
        return f"该流用 {method or '未知方式'} 加密，暂不支持（仅支持 AES-128）"
    if info.get("key_multi"):
        return "该流中途切换了多个加密密钥（多 KEY 轮换），暂不支持"
    return ""


def _web_hls_submit_impl(command):
    """「下载整片」任务化入口：提交为下载任务（可暂停/续传/重试）而非一次性拼接。"""
    url = str((command or {}).get("url") or "").strip()
    if not web_check_url(url):
        emit({"event": "hls_submit_result", "ok": False, "url": url,
              "message": "流媒体地址无效（仅支持公网 http/https）"})
        return
    referer = str((command or {}).get("referer") or "")
    world = str((command or {}).get("world") or "inner")
    mute = bool((command or {}).get("mute"))
    album = str((command or {}).get("album") or "流媒体")
    base = web_safe_name(str((command or {}).get("filename") or "stream"), 60)

    # 提交前先探一次清单：拿时长/分片数/判决，并把「加密流」这类必然失败的
    # 情况挡在任务创建之前（否则用户会看到一个注定失败的任务）
    sess = requests.Session()
    sess.headers.update({"User-Agent": WEB_UA})
    if referer:
        sess.headers["Referer"] = referer
    info, _final, err = _web_hls_resolve(sess, url)
    if info is None:
        emit({"event": "hls_submit_result", "ok": False, "url": url, "message": err})
        return
    if not info.get("segs"):
        emit({"event": "hls_submit_result", "ok": False, "url": url,
              "message": _web_hls_no_seg_reason(info)})
        return
    enc_bad = _web_hls_enc_unsupported(info)
    if enc_bad:
        emit({"event": "hls_submit_result", "ok": False, "url": url, "message": enc_bad})
        return

    verdict, _score, reasons = web_hls_verdict(info)
    dur = float(info.get("duration") or 0)
    suffix = "_无声版" if mute else ""
    item = {
        "site": "sniffer_hls",
        "filename": f"{base}{suffix}.mp4",
        "media_type": "video",
        "hls_url": url,
        "item_page": referer,
        "size": 0,
    }
    options = {"hls_mute": mute, "hls_referer": referer}
    if world == "surface":
        # 美好世界发起：落盘跟随「保存位置」设置（同 sniff_download 的口径），
        # no_download_folder 关掉再拼一层 "Downloads"（否则双重目录）
        options["custom_path"] = web_surface_root()
        options["no_download_folder"] = True
        options["world"] = "surface"
    try:
        task_id = download_manager.submit(                 # noqa: F821（包加载器注入）
            url, [item], options, album,
            f"hls:{hashlib.sha1(url.encode('utf-8', 'replace')).hexdigest()[:12]}")
        download_manager.start(task_id)                    # noqa: F821
    except Exception as exc:                               # noqa: BLE001
        logging.exception("HLS 任务提交失败: %s", url[:120])
        emit({"event": "hls_submit_result", "ok": False, "url": url,
              "message": f"加入下载管理失败：{type(exc).__name__}"})
        return
    dur_txt = f"时长 {web_hls_fmt_dur(dur)}、" if dur > 0 else ""
    vtxt = {"content": "判定为正片，", "ad": "判定为疑似广告，"}.get(verdict, "")
    seg_n = int(info.get("seg_count") or 0)
    emit({"event": "hls_submit_result", "ok": True, "url": url, "task_id": task_id,
          "duration": round(dur, 1), "verdict": verdict, "segCount": seg_n,
          "message": (f"已加入下载管理（{dur_txt}{vtxt}{seg_n} 个分片）："
                      "分片下载完成后自动合并为 MP4，可暂停/继续/重试")})


async def web_cmd_hls_submit(command):
    """hls_submit：提交流媒体下载任务（拉清单是同步网络调用，放线程池）。"""
    await asyncio.to_thread(_web_hls_submit_impl, command)


def _web_hls_concat_impl(command):
    """流媒体完整版：m3u8 分片字节流直送 ffmpeg stdin 拼接（零中间文件）。"""
    import subprocess
    url = str(command.get("url") or "").strip()
    mute = bool(command.get("mute"))
    if not web_check_url(url):
        emit({"event": "hls_result", "ok": False, "url": url,
              "message": "流媒体地址无效（仅支持公网 http/https）"})
        return
    referer = str(command.get("referer") or "")
    world = str(command.get("world") or "inner")
    album = web_safe_name(str(command.get("album") or "流媒体"), 40)
    base = web_safe_name(str(command.get("filename") or "stream"), 60)
    suffix = "无声版" if mute else "完整版"
    # 表世界发起：跟随「表世界保存位置」设置；其余（嗅探窗等）沿用下载夹
    root = web_surface_root() if world == "surface" else os.path.join(os.path.expanduser("~"), "Downloads")
    out_dir = os.path.join(root, album)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        pass
    out_path = web_output_path(out_dir, f"{base}_{suffix}.mp4")
    if out_path is None:
        emit({"event": "hls_result", "ok": False, "url": url, "message": "输出文件名不合法"})
        return
    n = 1
    while os.path.exists(out_path):
        out_path = web_output_path(out_dir, f"{base}_{suffix}_{n}.mp4")
        n += 1

    emit({"event": "log", "type": "下载",
          "message": f"开始下载流媒体{suffix}: {os.path.basename(out_path)}"})
    emit({"event": "hls_progress", "url": url, "done": 0, "total": 0,
          "phase": "parsing", "filename": os.path.basename(out_path)})

    sess = requests.Session()
    sess.headers.update({"User-Agent": WEB_UA})
    if referer:
        sess.headers["Referer"] = referer

    # 统一走 web_hls_analyze 系列（与 hls_probe 判决同一套代码）：
    # 主清单自动下钻到最高码率变体，一次拿到时长/分片/加密/fMP4/广告判决。
    info, _final, _err = _web_hls_resolve(sess, url)
    if info is None:
        emit({"event": "hls_result", "ok": False, "url": url, "message": _err})
        return
    segs = list(info.get("segs") or [])
    verdict, _score, reasons = web_hls_verdict(info)
    if not segs:
        # 精确报错：以前只会笼统说「加密流或直播流」，用户不知道该改什么
        emit({"event": "hls_result", "ok": False, "url": url,
              "message": _web_hls_no_seg_reason(info)})
        return
    if info.get("encrypted"):
        # 这条路径是「分片直送 ffmpeg stdin」的一体式拼接，做不了解密；
        # 加密流一律引导到 hls_submit（走下载任务，支持 AES-128 逐片解密）
        emit({"event": "hls_result", "ok": False, "url": url,
              "message": "加密流请用「下载整片」（加入下载管理，AES-128 会自动解密）"})
        return

    # 直播流（无 ENDLIST）只能录到当前进度，提示但不阻止
    if info.get("live"):
        emit({"event": "log", "type": "下载",
              "message": "该流无 ENDLIST（疑似直播/录制中），将下载已列出的分片"})
    dur = float(info.get("duration") or 0)
    if verdict == "ad":
        emit({"event": "log", "type": "下载",
              "message": "该流被判为疑似广告（" + "；".join(reasons[:2]) + "），仍按你的点击继续下载"})
    # 解析完成：把「分片数 / 时长 / 判决」先推给前端（列表项立即显示 分片 0/N）
    emit({"event": "hls_progress", "url": url, "done": 0, "total": len(segs),
          "phase": "analyzed", "filename": os.path.basename(out_path),
          "duration": round(dur, 1), "verdict": verdict,
          "encrypted": bool(info.get("encrypted")), "fmp4": bool(info.get("fmp4"))})

    if mute:
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0",
             "-an", "-c", "copy", "-movflags", "+faststart", out_path],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    else:
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0",
             "-c", "copy", "-movflags", "+faststart", out_path],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    total = len(segs)
    last_report = 0
    masked_segs = 0        # 命中「图片马甲」并成功剥壳的分片数
    for i, seg in enumerate(segs, 1):
        if proc.stdin is None:
            break
        sr = None
        for st in range(3):
            try:
                sr = sess.get(seg, timeout=60, stream=True)
                sr.raise_for_status()
                break
            except Exception:
                sr = None
                time.sleep(1 + st)
        if sr is None:
            proc.kill()
            emit({"event": "hls_result", "ok": False, "url": url,
                  "message": f"分片 {i}/{total} 下载失败（网络不佳）"})
            return
        # pending != None 表示还在攒首块、尚未判定同步偏移；攒到 768B（4 个 TS 包）
        # 再判，避免首块过小时误判。剥壳后的字节立刻写入，保证 ffmpeg 探测到的
        # 第一个字节就是真 TS —— 否则 ffmpeg 会锁定成 png_pipe 直接失败。
        pending = b""
        try:
            for chunk in sr.iter_content(256 * 1024):
                if pending is not None:
                    pending += chunk
                    if len(pending) < 768:
                        continue
                    off = _web_ts_sync_offset(pending)
                    if off > 0:
                        masked_segs += 1
                        pending = pending[off:]
                    proc.stdin.write(pending)
                    pending = None
                    continue
                proc.stdin.write(chunk)
            if pending:                      # 分片整体不足 768B 的极端情况
                off = _web_ts_sync_offset(pending)
                if off > 0:
                    masked_segs += 1
                    pending = pending[off:]
                proc.stdin.write(pending)
        except (BrokenPipeError, OSError):
            proc.kill()
            emit({"event": "hls_result", "ok": False, "url": url,
                  "message": f"拼接中断于分片 {i}/{total}（ffmpeg 已退出）"})
            return
        finally:
            try:
                sr.close()
            except Exception:
                pass
        # 进度回传：每 10 片或收尾时发一次（前端列表项显示 下载中 i/total）
        if i - last_report >= 10 or i == total:
            last_report = i
            emit({"event": "hls_progress", "url": url, "done": i, "total": total,
                  "phase": "downloading", "filename": os.path.basename(out_path)})
    proc.stdin.close()
    rc = proc.wait()
    if rc == 0 and os.path.exists(out_path):
        extra = f"，其中 {masked_segs} 片为图片马甲已自动剥壳" if masked_segs else ""
        dur_txt = f"，时长 {web_hls_fmt_dur(dur)}" if dur > 0 else ""
        vtxt = {"content": "，判定为正片", "ad": "，判定为疑似广告"}.get(verdict, "")
        emit({"event": "hls_result", "ok": True, "path": out_path, "url": url,
              "duration": round(dur, 1), "verdict": verdict,
              "message": (f"流媒体{suffix}已下载：{os.path.basename(out_path)}"
                          f"（{total} 个分片{dur_txt}{vtxt}{extra}）")})
        logging.info("HLS 拼接完成: %s (masked=%d)", out_path, masked_segs)
    else:
        emit({"event": "hls_result", "ok": False, "url": url,
              "message": f"流媒体{suffix}下载失败（ffmpeg 返回 {rc}）"})


async def web_cmd_hls_concat(command):
    # ffmpeg 分片拼接可达数分钟，放线程池避免阻塞命令循环（同 probe_duration）
    await asyncio.to_thread(_web_hls_concat_impl, command)


WEB_HLS_COMMANDS = {
    "hls_concat": web_cmd_hls_concat,
    # 任务化入口：把「下载整片」提交为下载管理里的任务（可暂停/续传/重试）
    "hls_submit": web_cmd_hls_submit,
}


def _web_word_img_kind(src, page_url=""):
    """归一化图片地址 → (kind, value)。

    kind = "url"（http/https，含 //host 协议相对地址补 https）/ "data"（data: URI）
         / "skip"（空或非 http(s)，调用方计 fail）。
    """
    s = str(src or "").strip()
    if not s:
        return "skip", ""
    if s.startswith("//"):
        s = "https:" + s
    if s.lower().startswith("data:"):
        return "data", s
    if s[:5].lower() == "http:" or s[:6].lower() == "https:":
        return "url", s
    try:
        joined = urljoin(str(page_url or ""), s)
    except Exception:
        joined = ""
    if joined[:5].lower() == "http:" or joined[:6].lower() == "https:":
        return "url", joined
    return "skip", ""


def _web_word_data_uri_bytes(src):
    """data: URI → 图片字节；失败返回 None（不抛异常）。"""
    import base64
    try:
        head, payload = str(src or "").split(",", 1)
    except ValueError:
        return None
    try:
        if "base64" in head.lower():
            return base64.b64decode(payload + "===", validate=False)
        from urllib.parse import unquote_to_bytes
        return unquote_to_bytes(payload)
    except Exception:
        return None


def _web_word_pillow_avif_ok():
    """探测 Pillow 是否编入 libavif（AVIF 解码靠本机库，不能假设可用）。结果缓存。"""
    global _web_word_avif_ok
    if _web_word_avif_ok is None:
        try:
            from PIL import features
            _web_word_avif_ok = bool(features.check("avif"))
        except Exception as exc:
            logging.warning("web_to_word：Pillow AVIF 能力探测失败（%s）", exc)
            _web_word_avif_ok = False
        logging.info("web_to_word：Pillow AVIF 解码支持 = %s", _web_word_avif_ok)
    return _web_word_avif_ok


def _web_word_sniff_format(raw):
    """按文件头判定图片格式（大写）；无法识别返回 ""。不依赖 Pillow。"""
    if not raw or len(raw) < 12:
        return ""
    head = raw[:32]
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if head[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if head[:2] == b"BM":
        return "BMP"
    if head[:4] in (b"MM\x00*", b"II*\x00"):
        return "TIFF"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head[4:8] == b"ftyp":
        brand = head[8:12].lower()
        if brand in (b"avif", b"avis"):
            return "AVIF"
        if brand in (b"mif1", b"heic", b"heix", b"hevc", b"hevx"):
            return "HEIC"
    return ""


def _web_word_strip_cdn_suffix(url):
    """已知 CDN 的「图片处理后缀」URL → 原图 URL；不识别时返回 None。

    例：https://i0.hdslb.com/bfs/banner/xx.png@976w_550h_!cover.avif
        → https://i0.hdslb.com/bfs/banner/xx.png（原生 PNG，省一次转码）

    仅当「域名在名单内 + @ 后缀像处理指令（含数字或 !）+ 基础路径是图片扩展名」
    三者同时满足才剥离，避免对普通 URL 乱剥出 404。
    """
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in WEB_WORD_CDN_STRIP_HOSTS):
        return None
    path = parsed.path or ""
    at = path.rfind("@")
    if at <= 0:
        return None
    base_path, suffix = path[:at], path[at + 1:]
    if not suffix or not re.search(r"[0-9!]", suffix):
        return None
    if os.path.splitext(base_path)[1].lower() not in WEB_WORD_CDN_IMG_EXTS:
        return None
    stripped = urlunparse(parsed._replace(path=base_path))
    return stripped if stripped != str(url).strip() else None


def _web_word_convert_image(raw, fmt):
    """python-docx 不认的格式 → PNG（带透明）/ JPEG（不透明）。返回 (BytesIO|None, 原因)。

    降级路径明确：Pillow 缺失 / 解码失败 / 转码失败都返回可读原因，调用方写进
    占位文本，绝不静默失败。
    """
    import io
    fmt = str(fmt or "").upper()
    if fmt == "AVIF" and not _web_word_pillow_avif_ok():
        # 探测为 False 仍然尝试一次（打包环境探测可能误报），失败再按格式不支持归因
        logging.warning("web_to_word：Pillow 未探测到 libavif，仍尝试解码 AVIF")
    try:
        from PIL import Image
    except Exception as exc:
        logging.warning("web_to_word：Pillow 不可用，无法转码 %s（%s）", fmt or "?", exc)
        return None, f"格式不支持：{fmt or '未知格式'} 且 Pillow 不可用"
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()                       # 动图只取首帧（WebP 动图/多帧）
    except Exception as exc:
        logging.warning("web_to_word：%s 解码失败 %s", fmt or "?", exc)
        if fmt == "AVIF" and not _web_word_pillow_avif_ok():
            return None, "格式不支持：AVIF 需 libavif（当前 Pillow 编入缺失，无法解码）"
        if fmt in ("AVIF", "HEIC", "WEBP"):
            return None, f"格式不支持：{fmt} 解码失败（{exc.__class__.__name__}）"
        return None, f"格式不支持：{fmt or '未知格式'} 解码失败（{exc.__class__.__name__}）"
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (
        im.mode == "P" and "transparency" in im.info)
    try:
        buf = io.BytesIO()
        if has_alpha:
            im.convert("RGBA").save(buf, "PNG")
            target = "PNG"
        else:
            im.convert("RGB").save(buf, "JPEG", quality=88)
            target = "JPEG"
        buf.seek(0)
        logging.info("web_to_word：图片 %s → %s 转码成功（源 %d 字节）",
                     fmt, target, len(raw))
        return buf, ""
    except Exception as exc:
        logging.warning("web_to_word：%s → %s 转码失败 %s", fmt, "PNG/JPEG", exc)
        return None, f"格式不支持：{fmt or '未知格式'} 转码失败（{exc.__class__.__name__}）"


def _web_word_prepare_image(data):
    """原始图片字节/BytesIO → python-docx 可插入的 BytesIO。返回 (BytesIO|None, 原因)。

    原生支持（PNG/JPEG/GIF/BMP/TIFF）原样返回，省一次转码；
    其余（WebP/AVIF/HEIC…）交给 Pillow 转 PNG/JPEG。
    """
    import io
    if data is None:
        return None, "下载失败"
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
        buf = None
    else:
        try:
            data.seek(0)
            raw = data.read()
        except Exception:
            return None, "图片数据不可读"
        buf = data if isinstance(data, io.BytesIO) else None
    fmt = _web_word_sniff_format(raw)
    if fmt in WEB_WORD_DOCX_FORMATS:
        if buf is not None:
            buf.seek(0)
            return buf, ""
        return io.BytesIO(raw), ""
    return _web_word_convert_image(raw, fmt)


def _web_word_fetch_image(sess, url, page_url, timeout):
    """单 URL 下载 → (BytesIO|None, 失败原因)。不做格式处理。

    尝试矩阵：直连/应用代理 × 带 Referer/去 Referer（最多 4 次）。
    - 带 Referer：破解常规防盗链；被 401/403 拒绝时去掉 Referer 反而放行（常见）
    - 应用代理：github_proxy → common_proxy → 默认 10809（境外图床如维基/推特必须走代理）
    全部异常内部消化，不向上抛。
    """
    import io
    base_headers = {"User-Agent": WEB_UA}
    if page_url:
        base_headers["Referer"] = str(page_url)

    attempts = [None]                      # 先直连
    try:
        cfg = _github_proxy_cfg()          # 复用应用代理配置（common_proxy/默认 10809）
        if cfg:
            attempts.append(cfg)
    except Exception:
        pass

    last = ""
    for proxies in attempts:
        for with_referer in (True, False):
            r = None
            try:
                h = dict(base_headers)
                if not with_referer:
                    h.pop("Referer", None)
                r = sess.get(url, timeout=timeout, stream=True, headers=h, proxies=proxies)
                if r.status_code in (401, 403):
                    last = f"HTTP {r.status_code}"
                    continue                      # 换下一种组合（去 Referer / 走代理）
                if r.status_code >= 400:
                    return None, f"HTTP {r.status_code}"
                buf = io.BytesIO()
                size = 0
                for chunk in r.iter_content(64 * 1024):
                    buf.write(chunk)
                    size += len(chunk)
                    if size > WEB_WORD_IMG_MAX_BYTES:
                        return None, "超过 12MB 上限"
                buf.seek(0)
                return buf, ""
            except Exception as exc:
                last = f"{exc.__class__.__name__}"
            finally:
                if r is not None:
                    try:
                        r.close()
                    except Exception:
                        pass
    return None, last or "下载失败"


def _web_word_download_image(sess, url, page_url, timeout=WEB_WORD_IMG_TIMEOUT):
    """下载单张图片 → (BytesIO|None, 失败原因, 失败类别)。返回的流保证可插入 docx。

    URL 级优化：B站等 CDN 的 `base.png@976w_550h_!cover.avif` 剥掉 @ 后缀就是原生格式原图。
    但**顺序有讲究**——优先拿「页面原始 URL」走转码：
      压缩版 AVIF 约 26KB → 转 JPEG 约 90KB；
      剥离后缀的原图 PNG 可达 1.1MB（实测 B站 banner），40 张会撑出几十 MB 文档。
    只有在本机解码不了 AVIF 时，才把「剥离后缀取原生原图」提到首选，保证图能进文档。
    单 URL 内部仍走「直连/代理 × 带/去 Referer」四组合矩阵（见 _web_word_fetch_image）。
    拿到字节后统一过 _web_word_prepare_image：WebP/AVIF 转 PNG 或 JPEG。
    """
    stripped = _web_word_strip_cdn_suffix(url)
    # 解码不了 AVIF 且原 URL 就是 AVIF → 只能靠原生原图兜底
    prefer_stripped = bool(stripped) and (
        ".avif" in str(url).lower() and not _web_word_pillow_avif_ok())
    ordered = [stripped, url] if prefer_stripped else [url, stripped]
    candidates = []
    for cand in ordered:
        if cand and cand not in candidates:
            candidates.append(cand)
    last_reason = "下载失败"
    for cand in candidates:
        buf, reason = _web_word_fetch_image(sess, cand, page_url, timeout)
        if buf is None:
            last_reason = reason
            if len(candidates) > 1:
                logging.info("web_to_word：图片下载失败 %s（%s）", cand[:120], reason)
            continue
        data, conv_reason = _web_word_prepare_image(buf)
        if data is None:
            logging.info("web_to_word：图片转码失败 %s（%s）", cand[:120], conv_reason)
            return None, conv_reason, "format"
        return data, "", ""
    kind = "limit" if "上限" in last_reason else "download"
    return None, last_reason, kind


def _web_word_is_ad_text(text: str) -> bool:
    """短文本块的广告特征词防御过滤（前端已滤一道，这里是后端兜底）。

    判据：文本较短（<120 字）且命中广告行为词——正文段落极少出现这些组合。
    """
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    hits = ("广告", "赞助", "赞助商", "推广", "扫码关注", "下载app", "下载 app",
            "打开app", "打开 app", "立即抢购", "限时优惠", "免费注册",
            "关注公众号", "微信公众号", "点击了解", "推广链接", "合作热线",
            "bit.ly/", "t.cn/", "扫码下载")
    low = t.lower()
    return any(k in low for k in hits)


_AD_SRC_RE = re.compile(
    r"/ad(?:s|vert|server)?[/-]|/ads/|advert|sponsor|promo|banner"
    r"|doubleclick|googlesyndication|adserver|tracking|/pixel", re.I)


def _web_word_is_ad_img(src: str) -> bool:
    """图片地址的广告特征防御过滤（CDN 广告位/tracking 像素）。"""
    return bool(_AD_SRC_RE.search(src or ""))


def _web_to_word_impl(command):
    """前端页内提取的元素序列 → python-docx 按原位生成 Word。

    command: {title, page_url, doc_title,
              elements: [{t:'h1|h2|h3|p|li|quote|pre', text},
                         {t:'table', html, text}, {t:'img', src}]}

    健壮性约定：
    - 未知 t 值按普通段落处理；空 text 块跳过；连续完全相同的段落只写一次；
    - elements 上限 WEB_WORD_MAX_BLOCKS（超出截断并记 log）；
    - 图片/表格各自异常隔离，单块失败不影响整篇；
    - 图片先试剥离 CDN 处理后缀拿原图；WebP/AVIF 等非 docx 原生格式自动转 PNG/JPEG；
    - 无论成功失败都 emit word_result（前端据此提示，不再静默）。
    """
    command = command or {}
    title = web_safe_name(str(command.get("title") or "网页导出"), 60)
    page_url = str(command.get("page_url") or "")
    raw_elements = command.get("elements")

    if not isinstance(raw_elements, list) or not raw_elements:
        emit({"event": "word_result", "ok": False,
              "message": "Word 导出失败：提取到 0 个内容块（页面正文未识别到内容）"})
        return

    try:
        from docx import Document
        from docx.shared import Inches
    except Exception as exc:
        logging.exception("python-docx 不可用")
        emit({"event": "word_result", "ok": False,
              "message": f"python-docx 不可用（{exc}）：请安装 python-docx 后重试"})
        return

    word_dir = web_word_dir()
    if not os.path.isdir(word_dir) or not os.access(word_dir, os.W_OK):
        emit({"event": "word_result", "ok": False,
              "message": f"导出目录不可写：{word_dir}"})
        return

    elements = [e for e in raw_elements if isinstance(e, dict)]
    if not elements:
        emit({"event": "word_result", "ok": False,
              "message": "Word 导出失败：提取到 0 个内容块（元素格式非法）"})
        return
    if len(elements) > WEB_WORD_MAX_BLOCKS:
        emit({"event": "log", "type": "系统",
              "message": f"内容块超过上限（{len(elements)}），仅导出前 "
                         f"{WEB_WORD_MAX_BLOCKS} 块"})
        elements = elements[:WEB_WORD_MAX_BLOCKS]

    emit({"event": "log", "type": "系统",
          "message": f"开始导出 Word：{title}（{len(elements)} 个内容块）"})

    total = len(elements)
    written = img_ok = img_fail = img_seen = 0
    img_kinds = {}          # 失败类别 → 张数（word_result 分类统计用）
    last_text = None
    img_deadline = time.monotonic() + WEB_WORD_NET_BUDGET
    budget_hit = False

    try:
        doc = Document()
        doc.add_heading(str(command.get("doc_title") or title)[:120] or "网页导出", level=0)
        if page_url:
            p_src = doc.add_paragraph()
            run = p_src.add_run("来源：")
            run.bold = True
            p_src.add_run(page_url[:300])
            doc.add_paragraph()

        sess = requests.Session()
        sess.headers.update({"User-Agent": WEB_UA})

        for idx, el in enumerate(elements, 1):
            t = str(el.get("t") or "").strip().lower()
            text = str(el.get("text") or "").strip()
            html = str(el.get("html") or "")

            if t == "img":
                img_seen += 1
                src = str(el.get("src") or "").strip()
                # 广告图防御过滤（前端已滤一道；tracking/广告 CDN 兜底）
                if _web_word_is_ad_img(src):
                    img_fail += 1
                    img_kinds["ad"] = img_kinds.get("ad", 0) + 1
                    continue
                kind, val = _web_word_img_kind(src, page_url)
                data = None
                reason = ""
                fkind = "download"
                if kind == "skip":
                    reason, fkind = "地址为空或非 http(s)", "invalid"
                elif img_seen > WEB_WORD_MAX_IMAGES:
                    reason = f"图片超过 {WEB_WORD_MAX_IMAGES} 张上限"
                    fkind = "limit"
                elif time.monotonic() > img_deadline:
                    budget_hit = True
                    reason, fkind = "整体网络预算已用尽", "limit"
                else:
                    try:
                        if kind == "data":
                            raw = _web_word_data_uri_bytes(val)
                            if not raw:
                                reason, fkind = "data: URI 解码失败", "decode"
                            else:
                                data, reason = _web_word_prepare_image(raw)
                                fkind = "format"
                        else:
                            data, reason, fkind = _web_word_download_image(
                                sess, val, page_url, WEB_WORD_IMG_TIMEOUT)
                    except Exception as exc:   # 下载链路异常绝不影响整篇
                        data, reason = None, f"{exc.__class__.__name__}"
                        fkind = "download"
                try:
                    if data is None:
                        raise ValueError(reason or "下载失败")
                    doc.add_picture(data, width=Inches(5.8))
                    img_ok += 1
                except Exception as exc:
                    img_fail += 1
                    img_kinds[fkind] = img_kinds.get(fkind, 0) + 1
                    try:
                        doc.add_paragraph(
                            f"[图片未能插入: {src[:100]}（{exc}）]")
                    except Exception:
                        pass
                continue

            if t == "table":
                written += 1
                try:
                    web_add_table(doc, html, text)
                except Exception as exc:
                    logging.warning("web 表格块失败，回退文本: %s", exc)
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            doc.add_paragraph(line[:WEB_WORD_MAX_TEXT])
                last_text = None
            elif t.startswith("h"):
                try:
                    level = min(4, max(1, int(t[1])))
                except (ValueError, IndexError):
                    level = 2
                head_text = text[:200] or "标题"
                doc.add_heading(head_text, level=level)
                written += 1
                last_text = None
            elif not text:
                continue          # 空文本块无内容可写
            elif text == last_text:
                continue          # 连续完全相同的段落只写一次
            elif _web_word_is_ad_text(text):
                # 短文本广告词防御过滤（"下载APP/扫码关注/限时优惠"等行为词）
                img_kinds["ad_text"] = img_kinds.get("ad_text", 0) + 1
                last_text = None
                continue
            else:
                # 未知 t 值同样按普通段落处理，绝不丢内容
                if t == "pre":
                    p_code = doc.add_paragraph()
                    run = p_code.add_run(text[:WEB_WORD_MAX_TEXT])
                    run.font.name = "Consolas"
                else:
                    doc.add_paragraph(text[:WEB_WORD_MAX_TEXT])
                written += 1
                last_text = text

            if idx % 50 == 0:
                emit({"event": "log", "type": "系统",
                      "message": f"Word 导出进度 {idx}/{total}"})

        if budget_hit:
            emit({"event": "log", "type": "系统",
                  "message": f"图片下载超 {WEB_WORD_NET_BUDGET} 秒预算，剩余图片已跳过占位"})

        out_path = web_output_path(word_dir, f"{title}.docx")
        if out_path is None:
            emit({"event": "word_result", "ok": False,
                  "message": f"导出文件名不合法：{title}"})
            return
        n = 1
        while os.path.exists(out_path):
            out_path = web_output_path(word_dir, f"{title}_{n}.docx")
            n += 1
        try:
            doc.save(out_path)
        except Exception as exc:
            logging.exception("Word 保存失败")
            emit({"event": "word_result", "ok": False,
                  "message": f"Word 保存失败：{exc.__class__.__name__}（{exc}）"
                             f"，目标：{word_dir}"})
            return
        logging.info("web_to_word 完成: %s", out_path)
        # 失败按归因分类：让用户一眼看出是格式问题还是网络问题（不再是笼统「N 张失败」）
        fail_detail = "、".join(
            f"{WEB_WORD_FAIL_LABELS.get(k, k)} {v} 张"
            for k, v in sorted(img_kinds.items(), key=lambda kv: (-kv[1], kv[0])))
        msg = (f"Word 已导出：{os.path.basename(out_path)}"
               f"（{written} 个内容块，图片 {img_ok} 张成功、{img_fail} 张失败")
        if fail_detail:
            msg += f"：{fail_detail}"
        msg += f"）· 保存于 {word_dir}"
        # 登记进下载记录（world=surface 才会出现在表世界的下载管理里）：
        # 用户既能直接看到保存位置，也能在下载管理里一键「打开文件夹」。
        # 登记失败绝不影响文件本身——这里整体兜住异常。
        try:
            download_manager.record_local_file(          # noqa: F821
                str(command.get("album") or "网页导出"), out_path, page_url,
                str(command.get("world") or "surface"), "doc")
        except Exception:                                # noqa: BLE001
            logging.exception("Word 导出登记到下载记录失败（文件已正常保存）")
        emit({"event": "word_result", "ok": True, "path": out_path, "dir": word_dir,
              "filename": os.path.basename(out_path), "message": msg})
    except Exception as exc:
        logging.exception("web_to_word 失败")
        emit({"event": "word_result", "ok": False,
              "message": f"Word 导出失败：{exc.__class__.__name__}（{exc}）"})


def web_add_table(doc, table_html, fallback_text=""):
    """把 <table> HTML 还原为 Word 表格（保序保位）。

    bs4 不可用 / 解析失败 / 空表时**回退**：把 fallback_text（元素携带的纯文本）
    按行拆成段落写进文档 —— 内容绝不丢，也绝不向调用方抛异常。
    """
    grid = None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(str(table_html or ""), "html.parser")
        table = soup.find("table")
        if table is not None:
            rows = []
            ncol = 0
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if not cells:
                    continue
                rows.append([c.get_text(" ", strip=True)[:500] for c in cells])
                ncol = max(ncol, len(cells))
            if rows:
                grid = (rows, max(ncol, 1))
    except Exception as exc:
        logging.warning("web 表格解析失败（回退文本）: %s", exc)
        grid = None

    if grid:
        rows, ncol = grid
        try:
            docx_table = doc.add_table(rows=len(rows), cols=ncol)
            docx_table.style = "Table Grid"
            for ri, row in enumerate(rows):
                for ci, val in enumerate(row):
                    if ci < ncol:
                        docx_table.cell(ri, ci).text = val
            doc.add_paragraph()
            return True
        except Exception as exc:
            logging.warning("web 表格写入失败（回退文本）: %s", exc)

    lines = [ln.strip() for ln in str(fallback_text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    for ln in lines:
        try:
            doc.add_paragraph(ln[:WEB_WORD_MAX_TEXT])
        except Exception:
            pass
    if not lines:
        try:
            doc.add_paragraph("[表格内容为空]")
        except Exception:
            pass
    return False


_web_probe_sema = threading.Semaphore(2)
_web_probe_cache = {}
_web_probe_lock = threading.Lock()


def web_probe_duration(url, referer):
    """ffprobe 远程读媒体时长（秒）；失败返回 -1。8 秒超时防拖死。"""
    try:
        if referer:
            headers = f"Referer: {referer}\r\n"
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-headers", headers,
                 "-show_entries", "format=duration", "-of", "csv=p=0", url],
                capture_output=True, timeout=8)
        else:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", url],
                capture_output=True, timeout=8)
        val = float((r.stdout or b"-1").decode("utf-8", errors="replace").strip() or -1)
        return val if val > 0 else -1.0
    except Exception:
        return -1.0


def _web_probe_duration_impl(command):
    """视频时长探测（ffprobe 远程直读，并发限制+缓存）。"""
    url = str(command.get("url") or "").strip()
    if not web_check_url(url):
        return
    referer = str(command.get("referer") or "")
    with _web_probe_sema:
        with _web_probe_lock:
            if _web_probe_cache.get(url):
                return
            _web_probe_cache[url] = 1
    dur = web_probe_duration(url, referer)
    if dur > 0:
        emit({"event": "duration_result", "url": url, "duration": dur})


async def web_cmd_probe_duration(command):
    # 同步 ffprobe（最长 8s）放线程池：命令循环 await 同步函数会抛
    # "NoneType can't be used in 'await' expression" 并卡住后续命令
    await asyncio.to_thread(_web_probe_duration_impl, command)


# ============ HLS 智能探测（判断「这一条是不是要下的正片」） ============
# 与 probe_duration 的分工：probe_duration 走 ffprobe 远程读 mp4/m3u8（慢、易失败）；
# hls_probe 只拉播放清单、读 #EXTINF 求和（毫秒级、精确），并顺带给出正片/广告判决。
# 前端对 hls 条目一律调 hls_probe，不再对 m3u8 调 ffprobe。
_HLS_PROBE_TTL = 600            # 同一地址 10 分钟内不重复探测（清单内容会变，不缓存太久）
_HLS_PROBE_MAX = 400            # 缓存条目上限（防长会话无限膨胀）
_web_hls_probe_cache = {}       # url -> (ts, payload)
_web_hls_probe_lock = threading.Lock()
_web_hls_inflight = set()       # 同一地址并发去重（嗅探器常同一清单连发多条）
_web_hls_sema = threading.Semaphore(3)   # 同时在飞的清单拉取数（防一次抓 10 条打满连接）


def _web_hls_resolve(sess, url, depth=0):
    """拉清单；是主清单（#EXT-X-STREAM-INF）则下钻到最高码率变体。

    返回 (info, 最终地址, 错误文案)；info=None 表示失败。
    主清单本身没有 #EXTINF，不下钻就拿不到时长——而时长正是判决的主信号。
    """
    if depth > 2:
        return None, url, "m3u8 层级过深（主清单套了 3 层还没到分片）"
    try:
        r = sess.get(url, timeout=30)
        r.raise_for_status()
        text = r.text
    except Exception as exc:                       # noqa: BLE001
        return None, url, f"m3u8 拉取失败：{type(exc).__name__}（需代理的站请先开系统代理）"
    info = web_hls_analyze(text, url)
    if info.get("master") and info.get("sub") and not info.get("segs"):
        sub_info, final_url, err = _web_hls_resolve(sess, info["sub"], depth + 1)
        if sub_info is not None:
            # 主清单的清晰度信息保留（子清单没有 RESOLUTION），地址特征合并
            sub_info["master"] = True
            sub_info["max_res"] = max(sub_info.get("max_res") or 0, info.get("max_res") or 0)
            sub_info["max_bandwidth"] = max(sub_info.get("max_bandwidth") or 0,
                                            info.get("max_bandwidth") or 0)
            sub_info["ad_url_hits"] = _web_hls_ad_url_hits(
                info.get("ad_url_hits") or [], sub_info.get("ad_url_hits") or [])
            sub_info["_variant_count"] = len(info.get("variants") or [])
            return sub_info, final_url, ""
        return info, url, ""      # 子清单拉不动：退回主清单信息（至少能报变体数/清晰度）
    return info, url, ""


def _web_hls_probe_run(url, referer):
    """实际探测：建会话 → 拉清单（含下钻）→ 判决 → 组装 hls_probe_result。"""
    sess = requests.Session()
    sess.headers.update({"User-Agent": WEB_UA})
    if referer:
        sess.headers["Referer"] = referer
    base = {"event": "hls_probe_result", "url": url}
    info, final_url, err = _web_hls_resolve(sess, url)
    if info is None:
        return dict(base, ok=False, message=err)

    verdict, score, reasons = web_hls_verdict(info)
    dur = float(info.get("duration") or 0)
    notes = []
    if info.get("encrypted"):
        _m = str(info.get("key_method") or "AES").upper()
        if _m == "AES-128" and not info.get("key_multi"):
            notes.append("AES-128 加密流（下载时自动解密）")
        else:
            notes.append(f"{_m} 加密流（暂不支持）")
    if info.get("key_multi"):
        notes.append("中途切换多个密钥（多 KEY 轮换，暂不支持）")
    if info.get("byte_range"):
        notes.append("分片走 BYTERANGE 区间请求")
    if info.get("init_uri"):
        notes.append("fMP4 分片（带初始化段）")
    if info.get("live"):
        notes.append("无 ENDLIST（直播/录制中，只能下到已列出的分片）")
    if not info.get("segs") and not info.get("master"):
        notes.append("清单里没有分片（地址可能已失效）")
    return {
        "event": "hls_probe_result",
        "url": url,
        "ok": True,
        "resolved": final_url,
        "master": bool(info.get("master")),
        "variantCount": int(info.get("_variant_count") or len(info.get("variants") or [])),
        "verdict": verdict,
        "score": score,
        "reasons": reasons,
        "duration": round(dur, 1),
        "durationText": web_hls_fmt_dur(dur) if dur > 0 else "",
        "segCount": int(info.get("seg_count") or 0),
        "live": bool(info.get("live")),
        "vod": bool(info.get("vod")),
        "encrypted": bool(info.get("encrypted")),
        "keyMethod": info.get("key_method") or "",
        "fmp4": bool(info.get("fmp4")),
        "byteRange": bool(info.get("byte_range")),
        "resolution": int(info.get("max_res") or 0),
        "bandwidth": int(info.get("max_bandwidth") or 0),
        "adTags": info.get("ad_tags") or [],
        "adUrlHits": info.get("ad_url_hits") or [],
        "note": "；".join(notes),
    }


def _web_hls_probe_impl(command):
    """m3u8 智能探测入口（缓存 + 并发去重 + 限流）。"""
    url = str((command or {}).get("url") or "").strip()
    if not web_check_url(url):
        return
    referer = str((command or {}).get("referer") or "")
    force = bool((command or {}).get("force"))
    now = time.time()
    with _web_hls_probe_lock:
        hit = _web_hls_probe_cache.get(url)
        if hit and not force and now - hit[0] < _HLS_PROBE_TTL:
            emit(dict(hit[1], cached=True))
            return
        if url in _web_hls_inflight:
            return          # 同一地址正在探测：结果由先到的那次 emit
        _web_hls_inflight.add(url)
    try:
        with _web_hls_sema:
            payload = _web_hls_probe_run(url, referer)
    except Exception:                                  # noqa: BLE001
        logging.exception("hls_probe 探测异常: %s", url[:120])
        payload = {"event": "hls_probe_result", "url": url, "ok": False,
                   "message": "探测异常（详见日志）"}
    finally:
        with _web_hls_probe_lock:
            _web_hls_inflight.discard(url)
    with _web_hls_probe_lock:
        _web_hls_probe_cache[url] = (time.time(), payload)
        if len(_web_hls_probe_cache) > _HLS_PROBE_MAX:
            cutoff = time.time() - _HLS_PROBE_TTL
            for k in [k for k, v in _web_hls_probe_cache.items() if v[0] < cutoff]:
                _web_hls_probe_cache.pop(k, None)
            if len(_web_hls_probe_cache) > _HLS_PROBE_MAX:
                for k in sorted(_web_hls_probe_cache,
                                key=lambda k: _web_hls_probe_cache[k][0])[:100]:
                    _web_hls_probe_cache.pop(k, None)
    emit(payload)


async def web_cmd_hls_probe(command):
    # 清单拉取是同步 requests（主清单下钻最多 3 跳），放线程池避免阻塞命令循环
    await asyncio.to_thread(_web_hls_probe_impl, command)


async def web_cmd_to_word(command):
    # python-docx 生成 Word（含图片抓取）秒级耗时，放线程池避免阻塞命令循环
    await asyncio.to_thread(_web_to_word_impl, command)


# ============ 表世界站点校验（三层全自动：上游 GitHub 直取 → 发布仓 → 缓存/随包兜底） ============
# 第 1 层（上游直取，全自动）：
#   动漫  agefanscom/website README「最新域名」→ AGE动漫 官方随时换域，这里自动跟
#   影视  laoma2053/awesome-zhuiju-free resources/resources.json（GitHub Actions 每日
#         自动检测，status=recommended/caution/removed）→ 匹配磁贴更新地址，
#         recommended 且未收录的自动补为新磁贴
#   书源  书源.txt 中的活端点自动验证（XIU2 shuyuan JSON / aoaostar 聚合页 / PixivSource JSON）
# 第 2 层：发布仓库 surface_sites.json（人工运营层，标注上游不覆盖的站点）
# 第 3 层：本地缓存（30 分钟 TTL）+ 前端随包 BUNDLED_REGISTRY（离线兜底）
# 事件契约不变：surface_registry_result {ok, registry:{sites,extra,updated}, source}
SURFACE_REGISTRY_PATH = "surface_sites.json"
SURFACE_REGISTRY_RAW_URL = (
    "https://raw.githubusercontent.com/secondashes/xiaoxiao-release/main/"
    + SURFACE_REGISTRY_PATH
)
SURFACE_REGISTRY_FALLBACK_URL = (
    "https://cdn.jsdelivr.net/gh/secondashes/xiaoxiao-release@main/"
    + SURFACE_REGISTRY_PATH
)
AGEFANS_README_URLS = (
    "https://raw.githubusercontent.com/agefanscom/website/main/README.md",
    "https://raw.githubusercontent.com/agefanscom/website/master/README.md",
    "https://cdn.jsdelivr.net/gh/agefanscom/website@main/README.md",
)
ZHUIJU_RESOURCES_URLS = (
    "https://raw.githubusercontent.com/laoma2053/awesome-zhuiju-free/main/resources/resources.json",
    "https://cdn.jsdelivr.net/gh/laoma2053/awesome-zhuiju-free@main/resources/resources.json",
)
# 书源端点（书源.txt，2026-09 活跃）：JSON 数组非空 / 聚合页可达即视为该磁贴有效
BOOKSRC_CHECKS = (
    ("xiu2", "XIU2 精品书源", (
        "https://raw.githubusercontent.com/XIU2/Yuedu/master/shuyuan",
        "https://cdn.jsdelivr.net/gh/XIU2/Yuedu@master/shuyuan",
    ), "json"),
    ("legado", "aoaostar 书源聚合", ("https://legado.aoaostar.com/",), "page"),
    ("pxsource", "Pixiv 书源", (
        "https://raw.githubusercontent.com/DowneyRem/PixivSource/main/pixiv.json",
        "https://cdn.jsdelivr.net/gh/DowneyRem/PixivSource@main/pixiv.json",
    ), "json"),
)
# awesome-zhuiju-free 条目 → 本地磁贴 key（id/名称关键词匹配）
ZHUIJU_KEY_MATCH = {
    "jianyun": ("jianyun", "简云"),
    "juzong": ("juzong", "剧踪"),
    "pianku": ("pianku", "片库"),
    "kxyy": ("kxyy", "开心影院"),
    "xiaoya": ("xiaoya", "小鸭", "777tv"),
    "mmov": ("mmov",),
    # 2026-09-18 细分板块：新基线影视站纳入上游匹配（防与 zj_* 动态补站重复磁贴）
    "xinghe": ("xhkan", "星河"),
    "zhuiying": ("zhuiying", "追影"),
    "douhua": ("dhvideo", "豆花"),
    "fandazi": ("fdzys", "饭搭子"),
    "sasp": ("sa-video", "lsjys"),
    "dp66": ("66-dapianwang", "77dpw", "66大片"),
    "changz": ("czzymovie", "厂长"),
    "duboku": ("dbku", "独播库"),
    "naifei": ("netflixgc", "奈飞工厂"),
    "iyf": ("iyf", "爱壹帆"),
}
_WEB_REGISTRY_CACHE_FILE = "cache/surface_registry_cache.json"
_WEB_REGISTRY_TTL = 30 * 60
_WEB_FETCH_BUDGET = 50   # 单次同步整体网络预算（秒），防多源多镜像拖太久
# 站点同步只允许访问这些固定上游主机（防 SSRF：协议+主机白名单+解析 IP 公网校验）
_WEB_FETCH_ALLOWED_HOSTS = frozenset({
    "raw.githubusercontent.com",
    "cdn.jsdelivr.net",
    "legado.aoaostar.com",
    "objects.githubusercontent.com",
})
_web_registry_fetching = threading.Lock()


def _web_fetch_host_allowed(url):
    """http/https + 主机白名单 + DNS 解析结果全为公网才放行（防内网/环回/重绑定）。"""
    import ipaddress as _ip
    import socket as _socket
    try:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").strip().lower()
        if not host or host not in _WEB_FETCH_ALLOWED_HOSTS:
            return False
        for info in _socket.getaddrinfo(host, 443, proto=_socket.IPPROTO_TCP):
            ip = _ip.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_reserved
                    or ip.is_multicast or ip.is_link_local):
                return False
        return True
    except Exception:
        return False


def _web_registry_load_cache():
    try:
        with Path(_WEB_REGISTRY_CACHE_FILE).open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _web_registry_save_cache(registry):
    try:
        Path(_WEB_REGISTRY_CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)
        with Path(_WEB_REGISTRY_CACHE_FILE).open("w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "registry": registry}, f,
                      ensure_ascii=False)
    except Exception as exc:
        logging.warning("surface registry 缓存写入失败: %s", exc)


def _web_registry_http_get(url):
    """主机白名单校验后，依次直连 → GitHub 代理链拉取 JSON；都失败返回 None。"""
    if not _web_fetch_host_allowed(url):
        logging.warning("站点同步拒绝非白名单地址: %s", str(url)[:120])
        return None
    attempts = [None]
    try:
        attempts.append(_github_proxy_cfg())
    except Exception:
        pass
    for proxies in attempts:
        try:
            r = requests.get(url, timeout=15, proxies=proxies, headers={
                "User-Agent": WEB_UA, "Accept": "application/json"})
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


def _web_fetch_text(urls, deadline):
    """多镜像多代理拉文本：raw → jsDelivr，直连 → GitHub 代理链；超预算即止。

    每个 URL 先过 _web_fetch_host_allowed（协议+主机白名单+解析 IP 公网校验）。
    """
    attempts = [None]
    try:
        gp = _github_proxy_cfg()
        if gp:
            attempts.append(gp)
    except Exception:
        pass
    for url in urls:
        if time.monotonic() > deadline:
            return None
        if not _web_fetch_host_allowed(url):
            logging.warning("站点同步拒绝非白名单地址: %s", str(url)[:120])
            continue
        for proxies in attempts:
            if time.monotonic() > deadline:
                return None
            try:
                r = requests.get(url, timeout=15, proxies=proxies, headers={
                    "User-Agent": WEB_UA, "Accept": "*/*"})
                if r.status_code == 200 and r.text:
                    return r.text
            except Exception:
                continue
    return None


def _web_upstream_agefans(deadline):
    """AGE动漫官方发布页 README → 最新域名（跳过 ~~弃用~~ 删除线行）。"""
    md = _web_fetch_text(AGEFANS_README_URLS, deadline)
    if not md:
        return {}
    edited = ""
    m = re.search(r"(\d{4}\.\d{1,2}\.\d{1,2})[^:\n]*最后编辑", md)
    if m:
        edited = m.group(1)
    for line in md.splitlines():
        if "最新域名" not in line or "~~" in line:
            continue
        m = (re.search(r"\]\((https?://[^)\s]+)\)", line)
             or re.search(r"(https?://[^\s\)\]）】]+)", line))
        if m:
            url = m.group(1).split("?ref=")[0].rstrip("。，；")
            note = "GitHub agefanscom/website 官方发布页自动同步"
            if edited:
                note += f"（{edited} 编辑）"
            return {"sites": {"agefans": {"status": "ok", "url": url, "note": note}}}
    return {}


def _web_upstream_zhuiju(deadline):
    """awesome-zhuiju-free resources.json：匹配磁贴更新地址；未收录的影视站补新磁贴。

    收录口径：recommended/caution 都收（caution=上游标记"需观察"，非失效），removed 不收；
    同名/同域去重，上限 60（上游 online_video 总量约 52）。
    """
    txt = _web_fetch_text(ZHUIJU_RESOURCES_URLS, deadline)
    if not txt:
        return {}
    try:
        data = json.loads(txt)
    except ValueError:
        return {}
    items = data.get("resources") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}
    sites, extras, seen_hosts, seen_names = {}, [], set(), set()
    for it in items:
        if not isinstance(it, dict):
            continue
        status = str((it.get("verification") or {}).get("status") or "").lower()
        url = str(it.get("url") or "").strip().rstrip("/")
        name = str(it.get("name") or "").strip()
        if not url.startswith("http") or not name:
            continue
        ident = (str(it.get("id") or "") + " " + name).lower()
        key = next((k for k, kws in ZHUIJU_KEY_MATCH.items()
                    if any(w.lower() in ident for w in kws)), None)
        if key:
            if status == "removed":
                sites[key] = {"status": "dead", "url": "",
                              "note": "Awesome-zhuiju-free 每日检测：已移除（域名失效）"}
            elif status in ("recommended", "caution", "ok", ""):
                note = "Awesome-zhuiju-free 每日自动检测"
                if status == "caution":
                    note += "：上游标记需观察"
                elif status == "recommended":
                    note += "：上游推荐"
                sites[key] = {"status": "ok", "url": url, "note": note}
        elif (status in ("recommended", "caution")
              and str(it.get("category") or "") == "online_video"
              and len(extras) < 60):
            host = urlparse(url).hostname or ""
            if host and host not in seen_hosts and name not in seen_names:
                seen_hosts.add(host)
                seen_names.add(name)
                summary = str(it.get("summary") or "").strip()
                short = (str(it.get("summary_short") or "").strip() or summary)[:16]
                tip = (summary or short) + "（来源：Awesome-zhuiju-free 每日自动检测"
                tip += "，上游标记需观察）" if status == "caution" else "，上游推荐）"
                extras.append({
                    "key": f"zj_{it.get('id') or len(extras)}",
                    "name": name[:12], "desc": short,
                    "tip": tip,
                    "cats": ["video"], "home": url, "proxy": False,
                })
    out = {}
    if sites:
        out["sites"] = sites
    if extras:
        out["extra"] = extras
    return out


def _web_upstream_booksrc(deadline):
    """书源.txt 活端点自动验证：JSON 数组非空 / 聚合页可达 → 该磁贴有效。"""
    sites = {}
    for key, label, urls, kind in BOOKSRC_CHECKS:
        txt = _web_fetch_text(urls, deadline)
        ok, detail = False, ""
        if txt:
            if kind == "json":
                try:
                    arr = json.loads(txt)
                    if isinstance(arr, list) and arr:
                        ok = True
                        detail = f"书源 JSON 可用（{len(arr)} 条，自动验证）"
                except ValueError:
                    pass
            else:
                low = txt.lower()
                if len(txt) > 1000 and ("书源" in txt or "legado" in low):
                    ok = True
                    detail = "聚合页可达（自动验证）"
        sites[key] = (
            {"status": "ok", "url": "", "note": f"GitHub {label}：{detail}"}
            if ok else
            {"status": "dead", "url": "",
             "note": f"{label} 端点自动验证失败，按磁贴说明找最新导入地址"})
    return {"sites": sites, "extra": []}


def _web_registry_fetch_impl(force=False):
    with _web_registry_fetching:
        cache = _web_registry_load_cache()
        if not force and cache and time.time() - (cache.get("fetched_at") or 0) < _WEB_REGISTRY_TTL:
            emit({"event": "surface_registry_result", "ok": True,
                  "registry": cache.get("registry") or {}, "source": "cache"})
            return
        deadline = time.monotonic() + _WEB_FETCH_BUDGET
        # 第 1 层：上游 GitHub 直取（全自动）
        upstream_sites, upstream_extra, src_flags = {}, [], []
        for label, fn in (("agefans", _web_upstream_agefans),
                          ("zhuiju", _web_upstream_zhuiju),
                          ("booksrc", _web_upstream_booksrc)):
            try:
                layer = fn(deadline) or {}
                got_s = layer.get("sites") or {}
                got_e = layer.get("extra") or []
                if got_s or got_e:
                    src_flags.append(label)
                    upstream_sites.update(got_s)
                    upstream_extra.extend(got_e)
            except Exception as exc:
                logging.warning("上游站点源 %s 解析失败: %s", label, exc)
        # 第 2 层：发布仓库人工运营表（上游已覆盖的键让上游优先）
        release_sites, release_extra = {}, []
        for _, url in (("raw", SURFACE_REGISTRY_RAW_URL),
                       ("jsdelivr", SURFACE_REGISTRY_FALLBACK_URL)):
            data = _web_registry_http_get(url)
            if isinstance(data, dict) and isinstance(data.get("sites"), dict):
                release_sites = data.get("sites") or {}
                release_extra = data.get("extra") or []
                src_flags.append("release")
                break
        if upstream_sites or upstream_extra or release_sites or release_extra:
            registry = {
                "version": 3,
                "updated": time.strftime("%Y-%m-%d"),
                "note": ("三层合成：上游 GitHub 直取（agefans 发布页/zhuiju 每日检测/书源端点）"
                         "优先，发布仓运营表兜底，本地缓存与随包表离线兜底"),
                "sites": {**release_sites, **upstream_sites},
                "extra": release_extra + upstream_extra,
            }
            _web_registry_save_cache(registry)
            emit({"event": "surface_registry_result", "ok": True,
                  "registry": registry, "source": "sync:" + ",".join(src_flags)})
            logging.info("surface registry 已同步（%s，站点 %d / 动态 %d）",
                         ",".join(src_flags), len(registry["sites"]), len(registry["extra"]))
            return
        # 网络失败：旧缓存 → 随包兜底由前端负责；无缓存也如实上报
        if cache and isinstance(cache.get("registry"), dict):
            emit({"event": "surface_registry_result", "ok": True,
                  "registry": cache.get("registry"), "source": "cache-stale"})
        else:
            emit({"event": "surface_registry_result", "ok": False,
                  "message": "站点同步失败（使用随包本地站点表）"})


async def web_cmd_registry_fetch(command):
    # 多源网络请求放线程池，不阻塞命令循环；force=true 跳过缓存强制重拉（「同步站点」按钮）
    force = bool((command or {}).get("force"))
    await asyncio.to_thread(_web_registry_fetch_impl, force)


WEB_COMMANDS = {
    "hls_concat": web_cmd_hls_concat,
    "hls_probe": web_cmd_hls_probe,
    "web_to_word": web_cmd_to_word,
    "probe_duration": web_cmd_probe_duration,
    "web_registry_fetch": web_cmd_registry_fetch,
}
