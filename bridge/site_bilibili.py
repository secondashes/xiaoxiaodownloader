# -*- coding: utf-8 -*-
"""B站专属下载模块（热门平台·正规爬虫路线）。

插件式分工（对标 B站浏览器插件的能力）：
  - 解析：前端在 bilibili 页面内 fetch view/playurl API（真实浏览器指纹 + 登录
    cookie，天然过 B站对 requests 的 TLS 风控 412），拿到 DASH 分轨直链与清晰度清单。
  - 下载：本模块收 bili_download 命令，走 download_manager site="bilibili" 分支：
    视频流 + 音频流分别下载（MediaDownloader 带 bilibili Referer + 浏览器 UA），
    ffmpeg -c copy 合并成 MP4（不重编码，见 download_manager._dash_remux_mp4）；
    也可仅视频 / 仅音频。

命名：全模块 BILI_ 前缀唯一（bridge finalize 同名互踩坑）；BILI_COMMANDS 在
bridge/__init__.py 显式并入总表。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（emit/download_manager/ipaddress/…）

import asyncio
import logging
import os
import re
import time
from urllib.parse import urlparse

# ============================
# 0. 站点标识 / 命令表名
# ============================
BILI_SITE_KEY = "bilibili"
BILI_ALBUM_NAME = "哔哩哔哩"
BILI_REFERER = "https://www.bilibili.com/"
BILI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BILI_VIDEO_QUALITY = {
    127: "8K 超高清", 126: "杜比视界", 125: "HDR 真彩", 120: "4K 超清",
    116: "1080P 60帧", 112: "1080P 高码率", 100: "智能修复",
    80: "1080P 高清", 74: "720P 60帧", 64: "720P 高清",
    32: "480P 清晰", 16: "360P 流畅",
}
BILI_AUDIO_QUALITY = {30280: "320kbps", 30232: "128kbps", 30216: "64kbps"}


# ============================
# 1. URL 安全校验（与嗅探同规则：仅公网 http/https）
# ============================
def _bili_check_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        return False
    try:
        import ipaddress as _ip
        ip = _ip.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            return False
    except ValueError:
        pass  # 域名放行
    return True


def _bili_safe_name(text: str, limit: int = 80) -> str:
    """文件名消毒（去路径非法字符与元字符；与下载器 truncate_filename 双保险）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n`$;&]+', "_", str(text or "").strip())
    return name[:limit] or "bilibili"


# ============================
# 2. GS 命令：提交下载（条目由前端页内解析产出）
# ============================
async def _bili_cmd_download(command: dict) -> None:
    raw = command.get("item") or {}
    if not isinstance(raw, dict):
        emit({"event": "bili_download_result", "ok": False, "message": "无效的下载参数"})  # noqa: F821
        return
    video_url = str(raw.get("video_url") or "").strip()
    audio_url = str(raw.get("audio_url") or "").strip()
    mode = str(raw.get("mode") or "merge")
    if mode in ("merge", "video") and not video_url.startswith("http"):
        emit({"event": "bili_download_result", "ok": False, "message": "视频流地址无效"})  # noqa: F821
        return
    if mode in ("merge", "audio") and not audio_url.startswith("http"):
        emit({"event": "bili_download_result", "ok": False, "message": "音频流地址无效"})  # noqa: F821
        return
    for u in (video_url, audio_url):
        if u and not _bili_check_url(u):
            emit({"event": "bili_download_result", "ok": False, "message": "资源地址不在公网白名单"})  # noqa: F821
            return

    quality = _bili_safe_name(str(raw.get("quality_label") or ""), 24)
    page_no = raw.get("page") or 1
    page_part = _bili_safe_name(str(raw.get("page_part") or ""), 60)
    base = _bili_safe_name(str(raw.get("title") or "bilibili"), 80)
    if page_part and page_part == base:
        page_part = ""  # 分P名与标题相同（单P视频常见）时不重复拼接
    suffix = f"_P{page_no}" + (f"_{page_part}" if page_part else "")
    if mode == "audio":
        filename = f"{base}{suffix}_{quality}.m4a"
    else:
        filename = f"{base}{suffix}_{quality}.mp4"

    item = {
        "site": BILI_SITE_KEY,
        "filename": filename,
        "mode": mode,
        "video_url": video_url,
        "audio_url": audio_url,
        "quality_label": quality,
        "title": base,
        "page": page_no,
        "page_url": BILI_REFERER,
    }
    page_url = str(raw.get("page_url") or BILI_REFERER)
    # 表世界下载：真实落盘 C 盘用户下载文件夹（防露馅——路径即事实，不是伪装）
    surface_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    try:
        os.makedirs(surface_dir, exist_ok=True)
    except OSError:
        pass
    task_id = download_manager.submit(  # noqa: F821
        page_url, [item], {"custom_path": surface_dir, "world": "surface"},
        command.get("album") or BILI_ALBUM_NAME,
        f"{BILI_SITE_KEY}:{_bili_safe_name(str(raw.get('bvid') or ''), 24) or int(time.time() * 1000)}",
    )
    download_manager.start(task_id)  # noqa: F821
    logging.info("B站下载已提交: %s (%s)", filename, mode)
    emit({  # noqa: F821
        "event": "bili_download_result", "ok": True, "task_id": task_id,
        "urls": [u for u in (video_url, audio_url) if u],
        "message": f"已提交下载：{filename}",
    })


BILI_COMMANDS = {
    "bili_download": _bili_cmd_download,
}


# ============================
# 3. 下载 worker（download_manager site="bilibili" 分支调用）
# ============================
async def bili_download_one(task, item, album_path, task_id, max_retries):
    """B站 DASH 下载：视频/音频分轨 MediaDownloader 直下 → ffmpeg 转封装/合并。

    item: {filename, mode: merge|video|audio, video_url, audio_url, quality_label}
    完成/失败状态与进度事件沿用 download_manager 通用约定。"""
    logging.info(
        "B站 worker 启动: mode=%s video_url_len=%d audio_url_len=%d",
        item.get("mode"), len(str(item.get("video_url") or "")),
        len(str(item.get("audio_url") or "")),
    )
    try:
        Path("_bili_worker_ran.txt").write_text(
            f"{time.time()} site={item.get('site')!r} "
            f"vlen={len(str(item.get('video_url') or ''))} "
            f"alen={len(str(item.get('audio_url') or ''))}", encoding="utf-8")
    except Exception:
        pass
    mode = str(item.get("mode") or "merge")
    filename = str(item.get("filename") or "bilibili.mp4")
    headers = {"User-Agent": BILI_UA, "Referer": BILI_REFERER,
               "Connection": "keep-alive"}

    def _fail(msg: str) -> None:
        item["status"] = "failed"
        item["error"] = msg[:200]
        task["failed"] = task.get("failed", 0) + 1
        emit({"event": "file_complete", "filename": filename, "success": False,  # noqa: F821
              "task_id": task_id, "error": msg[:160]})
        download_manager._save()  # noqa: F821
        download_manager.emit_snapshot()  # noqa: F821

    async def _fetch(url: str, dest_name: str) -> bool:
        """单分轨下载（复用 MediaDownloader；dest_name 唯一避免去重误判）。"""
        dl_info = DownloadInfo(  # noqa: F821
            item_url=BILI_REFERER, download_link=url,
            filename=dest_name, task=live_task,
        )
        md = MediaDownloader(  # noqa: F821
            session_info=file_session_info,
            download_info=dl_info,
            live_manager=live_task,
            retry_config=RetryConfig(retries=3, has_external_retry=False),  # noqa: F821
            should_abort=lambda: task.get("status") in ("paused", "cancelled"),
            headers=headers,
        )
        return not await asyncio.to_thread(md.download)

    # 会话骨架：file_session_info.download_path 指向唯一临时目录（分轨落盘处）。
    # 注意：扁平命名空间里 download_manager 是「管理器实例」；模块级函数
    # （_dash_remux_mp4/_unique_download_filename）须经 sys.modules 取模块对象。
    import sys as _sys
    _dm = _sys.modules["bridge.download_manager"]
    args = task.get("_args")
    if args is None:
        from argparse import Namespace as _Namespace
        args = _Namespace(connections=4, rate_limit=None, clean_name=False)
    # 非 Bunkr 站禁用"Bunkr 子域名离线"检测（空子域名会被误判离线直接跳过）
    args.disable_server_check = True

    item["status"] = "downloading"
    emit({"event": "log", "type": "下载", "message": f"B站开始下载: {filename}"})  # noqa: F821

    import uuid as _uuid
    run_id = _uuid.uuid4().hex[:8]
    tmp = Path(str(album_path)) / f"_bili_{run_id}"  # noqa: F821
    tmp.mkdir(parents=True, exist_ok=True)
    file_session_info = SessionInfo(  # noqa: F821
        args=args, bunkr_status={}, download_path=str(tmp), rate_limiter=None,
    )
    live_task = GuiLiveManager()  # noqa: F821
    internal_task = live_task.add_task()
    live_task.set_task_info(internal_task, filename, 0)

    video_path = tmp / f"video_{run_id}.m4s"
    audio_path = tmp / f"audio_{run_id}.m4s"

    if mode in ("merge", "video"):
        if not await _fetch(item.get("video_url") or "", video_path.name):
            return
    if mode in ("merge", "audio"):
        if not await _fetch(item.get("audio_url") or "", audio_path.name):
            return

    final_path = Path(str(album_path)) / filename  # noqa: F821
    if final_path.exists():
        filename = _dm._unique_download_filename(str(album_path), filename)
        final_path = Path(str(album_path)) / filename  # noqa: F821

    ok, err_tail = await asyncio.to_thread(
        _dm._dash_remux_mp4,
        video_path if mode in ("merge", "video") else None,
        audio_path if mode in ("merge", "audio") else None,
        final_path,
    )
    if not ok:
        # 无 ffmpeg 兜底：分轨原样保存（m4s 可被 mpv/VLC 播放），不吞掉已下载内容
        try:
            if mode == "audio":
                audio_path.replace(final_path)
            elif video_path.exists():
                video_path.replace(final_path)
            logging.warning("B站 ffmpeg 合并失败(%s)，分轨原样保存: %s",
                            err_tail[:120], final_path.name)
        except Exception as exc:  # noqa: BLE001
            _fail(f"合并失败且兜底保存失败: {exc}")
            return
    import shutil as _shutil
    _shutil.rmtree(tmp, ignore_errors=True)  # 清理分轨临时目录（省磁盘）

    item["status"] = "completed"
    item["completed"] = 100
    item["_final_path"] = str(final_path)
    task["done"] = task.get("done", 0) + 1
    task["completed"] = task.get("completed", 0) + 1
    download_manager._save()  # noqa: F821
    download_manager.emit_snapshot()  # noqa: F821
    emit({"event": "file_complete", "filename": filename, "success": True,  # noqa: F821
          "task_id": task_id, "path": str(final_path)})
    logging.info("B站下载完成: %s", final_path)
