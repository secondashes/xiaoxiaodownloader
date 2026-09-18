# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：核心工具（日志/NDJSON 输出/文件类型/LiveManager/目录构建/Inspect 文件列表/加密账号存储）。

由 gui_bridge.py 按物理顺序拆出（原行区间 108-1089），
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
# 日志配置
# ============================
LOG_FOLDER = "logs"


def setup_logging() -> None:
    """配置 debug 日志，写入 logs/ 文件夹，按时间命名。"""
    log_dir = Path(LOG_FOLDER)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_filename = datetime.now().strftime("debug_%Y%m%d_%H%M%S.log")
    log_path = log_dir / log_filename

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    logging.info("GUI 桥接模块启动，日志文件: %s", log_path)


# ============================
# NDJSON 输出 (线程安全)
# ============================
_stdout_lock = threading.Lock()


def _atomic_write_json(file_path: str, data) -> None:
    """原子写入 JSON 文件（先写临时文件再 os.replace）。

    任务表/设置/历史等关键状态文件在高频写盘时若被强杀（用户关进程、断电），
    直接 open("w") 会留下半截 JSON → 下次启动解析失败 → 下载记录全部丢失。
    os.replace 在同一卷上是原子的，保证文件要么是旧内容要么是完整新内容。
    """
    tmp_path = f"{file_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp_path, file_path)


# 事件旁路：_emit_sinks 收集事件副本（供内部复用解析流程时取回结果），
# _emit_mute 命中时只入 sink、不写 stdout（避免解析进度污染主界面）
_emit_sinks: list[list[dict]] = []
_emit_mute: "Callable[[dict], bool] | None" = None


@contextlib.contextmanager
def _emit_capture(mute: "Callable[[dict], bool] | None" = None):
    """临时接管 emit：期间事件写入 sink，mute 命中的事件不再推给前端。"""
    global _emit_mute
    buf: list[dict] = []
    _emit_sinks.append(buf)
    prev_mute = _emit_mute
    _emit_mute = mute
    try:
        yield buf
    finally:
        _emit_mute = prev_mute
        try:
            _emit_sinks.remove(buf)
        except ValueError:
            pass


def emit(event: dict) -> None:
    """向 stdout 输出一行 JSON 事件（线程安全）。

    使用 ensure_ascii=True 输出纯 ASCII，避免 Windows 下 stdout 默认 GBK 编码
    遇到非 GBK 字符（如 ¹）时抛 UnicodeEncodeError；前端 JSON.parse 会还原 \\uXXXX。
    """
    line = json.dumps(event, ensure_ascii=True)
    if _emit_sinks:
        for sink in list(_emit_sinks):
            try:
                sink.append(event)
            except Exception:  # noqa: BLE001 —— 旁路收集失败绝不能影响主链路
                pass
    mute = _emit_mute
    if mute is not None and mute(event):
        return
    with _stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


# ============================
# 文件类型分类
# ============================
FILE_TYPE_CATEGORIES: dict[str, list[str]] = {
    "图片": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg"],
    "视频": [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts"],
    "音频": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
    "文档": [".pdf", ".doc", ".docx", ".txt", ".zip", ".rar", ".7z", ".tar", ".gz"],
}


def get_file_type_folder(filename: str) -> str:
    """根据文件扩展名返回分类文件夹名。"""
    ext = Path(filename).suffix.lower()
    for category, extensions in FILE_TYPE_CATEGORIES.items():
        if ext in extensions:
            return category
    return "其他"


# ============================
# GUI LiveManager (替代 rich LiveManager)
# ============================
class GuiLiveManager:
    """替代 LiveManager，将进度和日志以 JSON 事件形式输出到 stdout。"""

    def __init__(self) -> None:
        self._task_counter = 0
        self._task_filenames: dict[int, str] = {}
        self._task_indices: dict[int, int] = {}
        self._task_sizes: dict[int, int] = {}
        self._task_last_bytes: dict[int, float] = {}
        self._task_last_time: dict[int, float] = {}
        # 进度事件节流：每个内部任务上次 emit 时间（0.3s 一条，防 IPC 洪泛卡顿）
        self._task_last_emit: dict[int, float] = {}
        self._summary: dict[str, int] = {}
        self.start_time = time.time()
        # 关联的下载任务 ID（用于下载管理器分组展示）
        self.task_id: str | None = None
        # LiveManager.live 被 with 语句使用，这里用空上下文管理器
        self.live = nullcontext()

    def add_overall_task(self, description: str, num_tasks: int) -> None:
        """通知前端开始下载。"""
        emit({
            "event": "download_start",
            "album": description,
            "total_files": num_tasks,
        })

    def add_task(self, current_task: int = 0, total: int = 100) -> int:
        """创建一个新任务，返回 task_id。"""
        task_id = self._task_counter
        self._task_counter += 1
        self._task_indices[task_id] = current_task
        return task_id

    def set_task_info(self, task_id: int, filename: str, size: int | None = None) -> None:
        """关联 task_id 与文件名、文件大小（用于进度与速度计算）。"""
        self._task_filenames[task_id] = filename
        if size:
            self._task_sizes[task_id] = size
        self._task_last_bytes[task_id] = 0.0
        self._task_last_time[task_id] = time.time()

    def _compute_speed(self, task_id: int, completed: float) -> int:
        """根据进度变化计算下载速度（字节/秒）。"""
        size = self._task_sizes.get(task_id)
        downloaded = (completed / 100.0 * size) if size else completed
        now = time.time()
        last_bytes = self._task_last_bytes.get(task_id, downloaded)
        last_time = self._task_last_time.get(task_id, now)
        elapsed = now - last_time
        speed = (downloaded - last_bytes) / elapsed if elapsed > 0 else 0
        self._task_last_bytes[task_id] = downloaded
        self._task_last_time[task_id] = now
        return max(0, int(speed))

    def update_task(
        self,
        task_id: int,
        completed: float | None = None,
        advance: float = 0,
        *,
        visible: bool = True,
    ) -> None:
        """输出文件下载进度（含速度）。

        性能：每个 chunk 回调一次，多文件并发时事件量会撑爆 IPC 管道导致界面卡顿，
        因此按文件节流（≥0.3s 才发一次），完成(100%)必发。
        """
        filename = self._task_filenames.get(task_id, "")
        if not filename:
            return
        if completed is not None:
            now = time.time()
            last = self._task_last_emit.get(task_id, 0.0)
            if completed < 99.9 and (now - last) < 0.3:
                return
            self._task_last_emit[task_id] = now
            emit({
                "event": "file_progress",
                "filename": filename,
                "completed": round(completed, 1),
                "speed": self._compute_speed(task_id, completed),
                "visible": visible,
                "task_id": self.task_id,
            })

    def update_log(self, *, event: str, details: str) -> None:
        """输出日志事件。"""
        emit({"event": "log", "type": event, "message": details})
        logging.debug("日志事件 [%s]: %s", event, details)

    def update_summary(self, task_reason: IntEnum) -> None:
        """更新下载统计。"""
        reason_name = task_reason.name
        self._summary[reason_name] = self._summary.get(reason_name, 0) + 1

    def stop(self) -> None:
        """输出下载完成事件和统计摘要。"""
        execution_time = time.time() - self.start_time
        emit({
            "event": "download_complete",
            "summary": self._summary,
            "execution_time": round(execution_time, 1),
        })


# ============================
# 参数构建
# ============================
def create_args(options: dict) -> Namespace:
    """从前端传入的 options 字典构建 argparse.Namespace。"""
    return Namespace(
        custom_path=options.get("custom_path"),
        no_download_folder=options.get("no_download_folder", False),
        disable_ui=True,  # GUI 模式始终禁用 rich UI
        disable_disk_check=options.get("disable_disk_check", False),
        disable_server_check=options.get("disable_server_check", False),
        clean_name=options.get("clean_name", False),
        max_retries=options.get("max_retries", MAX_RETRIES),
        connections=options.get("connections", DEFAULT_CONNECTIONS),
        concurrent_files=int(options.get("concurrent_files", 2) or 2),
        rate_limit=options.get("rate_limit"),
        dry_run=False,
        max_concurrent_urls=1,
        ignore=options.get("ignore"),
        include=options.get("include"),
    )


# ============================
# 文件夹路径构建
# ============================
def build_album_directory(
    album_name: str | None,
    album_id: str | None,
    options: dict,
) -> str:
    """构建相册下载目录路径。

    支持选项:
      - date_stamp: 在相册文件夹名后加日期戳 _YYYYMMDD
      - custom_path: 自定义根下载路径
      - no_download_folder: 不创建 Downloads 子文件夹
    """
    custom_path = options.get("custom_path")
    no_download_folder = options.get("no_download_folder", False)
    date_stamp = options.get("date_stamp", False)

    # 构建相册文件夹名
    if date_stamp and album_name:
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = sanitize_directory_name(album_name)
        directory_name = f"{safe_name}_{date_str}"
    elif album_name and album_id:
        directory_name = format_directory_name(album_name, album_id)
    elif album_name:
        directory_name = album_name
    elif album_id:
        directory_name = album_id
    else:
        directory_name = None

    try:
        return create_download_directory(
            directory_name or "",
            custom_path=custom_path,
            no_download_folder=no_download_folder,
        )
    except (OSError, SystemExit) as exc:
        error_msg = f"创建下载目录失败: {exc}"
        logging.exception(error_msg)
        raise RuntimeError(error_msg) from exc


def build_file_download_path(
    album_path: str,
    filename: str,
    options: dict,
) -> str:
    """构建单个文件的下载路径，支持按文件类型分类。"""
    organize_by_type = options.get("organize_by_type", False)
    if not organize_by_type:
        return album_path

    type_folder = get_file_type_folder(filename)
    file_path = str(Path(album_path) / type_folder)
    Path(file_path).mkdir(parents=True, exist_ok=True)
    return file_path


def _unique_download_filename(download_path: str, filename: str) -> str:
    """若目标文件已存在，则生成带序号的新文件名，避免覆盖。"""
    target = Path(download_path) / truncate_filename(filename)
    if not target.exists():
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate = f"{stem} ({counter}){suffix}"
        if not (Path(download_path) / truncate_filename(candidate)).exists():
            return candidate
        counter += 1


def _atomic_stream_save(resp, final_path: Path, *, on_chunk, is_cancelled) -> None:
    """流式下载到 .part 临时文件，完成后原子改名；中断/失败自动清理临时文件。

    修复"残缺文件 + (2) 后缀"问题：此前流式下载直接写目标文件，
    暂停/取消/网络中断会留下半截文件，重试时被迫使用"(2)"后缀另存，
    导致文件夹里同时存在残缺原文件和完整 (2) 文件。
    """
    tmp_path = final_path.with_name(final_path.name + ".part")
    try:
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if is_cancelled():
                    raise InterruptedError("任务已暂停/取消")
                if chunk:
                    f.write(chunk)
                    on_chunk(chunk)
        os.replace(tmp_path, final_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _stream_to_file(
    session,
    url: str,
    final_path: Path,
    *,
    final_name: str,
    task: dict,
    task_id: str,
    internal_task,
    live_manager,
    max_retries: int,
    headers: dict | None = None,
    timeout=60,
    throttle=None,
    open_response=None,
    validate=None,
    fallback_size: int | None = None,
    log_label: str = "文件",
) -> tuple[int, str]:
    """通用流式下载核心（全部站点 `_xxx_download_one` 共用）。

    重试退避 + 节流钩子 + file_start/进度事件 + .part 原子写入 + Content-Length
    完整性校验（半截文件防假完成，缺失时跳过）+ MD5 增量计算。

    钩子：
      - open_response(attempt) -> resp：站点自定义打开响应（EX 的 ?nl= 换节点重解析、
        iwara 的系统代理回退、hanime/xhamster 的下载时重解析都在这里做），
        返回已 raise_for_status 的 stream 响应；为 None 时用 session.get 默认路径。
      - validate(final_path)：下载后校验（如 EX 文件头校验），抛异常视为本次失败进入重试。
      - throttle：每次尝试前调用（站点节流函数）。

    返回 (size, md5_hex)；全部重试失败抛最后一次异常；暂停/取消抛 InterruptedError。
    """
    last_exc: Exception = RuntimeError("下载未执行")
    for attempt in range(max(1, max_retries)):
        try:
            if throttle:
                throttle()
            if open_response is not None:
                resp = open_response(attempt)
            else:
                resp = session.get(url, stream=True, timeout=timeout, headers=headers or {})
                resp.raise_for_status()
            try:
                size = int(resp.headers.get("Content-Length") or 0) or (fallback_size or 0)
                live_manager.set_task_info(internal_task, final_name, size or None)
                emit({
                    "event": "file_start",
                    "filename": final_name,
                    "index": 0,
                    "size": size or None,
                    "task_id": task_id,
                })

                hasher = hashlib.md5()
                downloaded = 0
                last_pct = -1

                def _on_chunk(chunk: bytes) -> None:
                    nonlocal downloaded, last_pct
                    downloaded += len(chunk)
                    hasher.update(chunk)
                    if size:
                        pct = round(downloaded / size * 100, 1)
                        if pct != last_pct:
                            live_manager.update_task(internal_task, pct)
                            last_pct = pct

                # 原子写入：.part 临时文件 + 完成后改名（中断不留半截文件）
                _atomic_stream_save(
                    resp, final_path,
                    on_chunk=_on_chunk,
                    is_cancelled=lambda: task.get("status") in ("paused", "cancelled"),
                )

                # 完整性校验：流被提前掐断时字节不足（假完成），
                # 按 Content-Length 比对，不一致删残缺文件并抛异常进入重试
                if size > 0:
                    actual = final_path.stat().st_size if final_path.exists() else 0
                    if actual != size:
                        final_path.unlink(missing_ok=True)
                        raise PermissionError(
                            f"下载不完整（{actual}/{size} 字节），将重试")
                elif not final_path.exists():
                    raise PermissionError("下载后文件不存在，将重试")
                if validate:
                    validate(final_path)
                return size, hasher.hexdigest()
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
        except InterruptedError:
            raise
        except (requests.RequestException, PermissionError, OSError) as exc:
            last_exc = exc
            logging.warning(
                "%s 下载失败(第 %d 次) %s: %s", log_label, attempt + 1, final_name, exc,
            )
            if attempt < max(1, max_retries) - 1:
                time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
    raise last_exc


_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    """文件名消毒：把 Windows 非法字符（\\ / : 等）替换为下划线。

    站点解析的文件名可能直接携带标题（如 "标题 / 副标题_0001.jpg"）——
    不消毒时 / 与 \\ 会被当成目录分隔符，写盘目录不存在 → 该文件
    Errno 2 全部下载失败（2026-09-13 EX 画廊实锤）。"""
    name = _INVALID_FS_CHARS.sub("_", str(name or ""))
    return name.strip().strip(".").strip() or "file"


def _resolve_duplicate(download_path: str, filename: str, expected_size,
                        options: dict) -> tuple[str, str]:
    """下载去重处理（skip_duplicates 设置）。

    返回 (最终文件名, 动作)：
      - download：正常下载（目标不存在）
      - skip：同名且大小一致，直接跳过不下载
      - prompt：同名但大小不同且 manual_rename 开启，等待用户手动改名
      - renamed：同名但大小不同且自动改名，返回序号顺延的新文件名
    skip_duplicates 关闭时始终返回 (原文件名, "download")，由调用方沿用原有逻辑。
    """
    # 文件名消毒必须先于所有分支（skip_duplicates 关闭时同样生效）
    filename = sanitize_filename(filename)
    if not options.get("skip_duplicates"):
        return filename, "download"
    target = Path(download_path) / truncate_filename(filename)
    if not target.exists():
        return filename, "download"
    try:
        existing_size = target.stat().st_size
    except OSError:
        return filename, "download"
    if expected_size and existing_size == expected_size:
        return filename, "skip"
    if options.get("manual_rename"):
        return filename, "prompt"
    return _unique_download_filename(download_path, filename), "renamed"


def _make_throttle(default_interval: float, *, lock=None):
    """生成节流闭包：两次调用间隔 ≥ default_interval（可用 min_interval 参数临时覆盖）。

    lock 传入共享 threading.Lock 时睡眠期持锁（原 exhentai/twitter/iwara/search 语义）；
    lock=None 时不加锁（原 hanime/xhamster/pixiv/oreno/asmr/javdb 的并发语义）。
    """
    state = {"last": 0.0}

    def _throttle(min_interval: float | None = None) -> None:
        iv = default_interval if min_interval is None else min_interval
        if lock is not None:
            with lock:
                wait = state["last"] + iv - time.time()
                if wait > 0:
                    time.sleep(wait)
                state["last"] = time.time()
        else:
            wait = state["last"] + iv - time.time()
            if wait > 0:
                time.sleep(wait)
            state["last"] = time.time()

    return _throttle


# 下载任务条目字段（submit 新建与增量合并共用；新增字段只改这里，两处自动生效）
# size 缺省 None，其余缺省 ""（与历史行为一致）
TASK_FILE_FIELDS = (
    "item_page", "filename", "size", "site", "media_url", "media_path",
    "artist", "post_title", "post_date", "media_type", "xh_kind", "hls_url",
    "video_id",
    # Pixiv：下载器现场解析必需（缺这些 ⇒ 批量/用户下载条目到下载器后
    # kind/novel_id/illust_id 全空 → 全部失败——"批量完成即失败"悬案真凶）
    "illust_id", "novel_id", "kind", "subfolder", "ugoira", "page_index",
    "pixiv_novel_fmt",
    # B站 DASH（热门平台）：下载器现场按 mode 合并/分离音视频分轨
    "video_url", "audio_url", "mode", "quality_label",
)


def _task_file_entry(item: dict) -> dict:
    """由下载条目构造任务文件记录（pending 初始态），字段以 TASK_FILE_FIELDS 为准。"""
    entry = {"status": "pending", "completed": 0}
    for key in TASK_FILE_FIELDS:
        entry[key] = item.get(key, None if key == "size" else "")
    return entry


def _apply_rename_map(options: dict, item: dict, filename: str) -> str:
    """应用前端改名弹窗回传的重命名映射（键：原文件名 或 item_page）。"""
    rename_map = options.get("rename_map") or {}
    if not isinstance(rename_map, dict):
        return filename
    for key in (filename, item.get("item_page") or ""):
        new_name = str(rename_map.get(key) or "").strip()
        if new_name:
            return new_name
    return filename


# ============================
# Inspect 命令：获取文件列表
# ============================
ALBUM_CACHE_DIR = "cache/albums"
# 相册信息缓存有效期（秒）：24 小时内再次打开直接命中缓存，超时重新解析
ALBUM_CACHE_TTL = 24 * 60 * 60
# 解析相册文件列表时的并发数（只抓取 item 页面，不请求签名/大小，可适度调高）
INSPECT_CONCURRENCY = 8


def _album_cache_path(identifier: str) -> Path:
    """返回相册解析结果的缓存文件路径。"""
    return Path(ALBUM_CACHE_DIR) / f"{identifier}.json"


def _load_album_cache(identifier: str) -> dict | None:
    """读取相册解析缓存，未过期则返回数据，过期或无效则返回 None。"""
    cache_path = _album_cache_path(identifier)
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
            if not (isinstance(data, dict) and data.get("items")):
                return None
            cached_at = data.get("cached_at")
            if not cached_at or (time.time() - float(cached_at)) > ALBUM_CACHE_TTL:
                # 缓存已过期，删除并视为未命中，触发重新解析
                cache_path.unlink(missing_ok=True)
                return None
            return data
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return None


def _save_album_cache(identifier: str, data: dict) -> None:
    """保存相册解析结果到本地缓存，并记录缓存时间。"""
    try:
        Path(ALBUM_CACHE_DIR).mkdir(parents=True, exist_ok=True)
        data["cached_at"] = time.time()
        with _album_cache_path(identifier).open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
    except OSError as exc:
        logging.warning("保存相册缓存失败: %s", exc)


# ============================
# 加密账号存储（全站点登录凭据 + 账号档案，伪装文件保存于根目录）
# ============================
# 伪装文件名：看起来像 UI 主题缓存，实际是加密的账号数据库
# 便携版由 main.cjs 注入 XXD_THEME_CACHE_PATH（藏在 Chromium 磁盘缓存目录
# data/Cache/Cache_Data/ 内，与真实缓存文件混在一起）；默认在根目录
SECURE_STORE_FILE = os.environ.get("XXD_THEME_CACHE_PATH") or "theme_cache.dat"
# 解密密码（任一密码均可解密；加密时用第一个）
SECURE_STORE_PASSWORDS = ("yueyangxi", "yueyangxi1995")
# 文件头：4 字节伪装标记 + 1 字节版本
SECURE_STORE_MAGIC = b"TCHE"
SECURE_STORE_HEAD_LEN = 4 + 1 + 16 + 16  # magic + version + salt + nonce

_secure_store_cache: dict | None = None  # 内存缓存（首次解密后常驻）
_secure_store_lock = threading.Lock()


def _secure_store_keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    """PBKDF2 派生密钥：前 32 字节加密密钥，后 32 字节校验密钥。"""
    okm = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 60000, dklen=64)
    return okm[:32], okm[32:]


def _secure_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """SHA-256 计数器模式生成密钥流。"""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return bytes(out[:length])


def _secure_store_encrypt(data: dict) -> bytes:
    """把账号数据加密为二进制（结构：magic+ver+salt+nonce+密文+hmac）。"""
    plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(16)
    enc_key, mac_key = _secure_store_keys(SECURE_STORE_PASSWORDS[0], salt)
    body = bytes(a ^ b for a, b in zip(plain, _secure_keystream(enc_key, nonce, len(plain))))
    head = SECURE_STORE_MAGIC + b"\x01" + salt + nonce
    mac = hmac.new(mac_key, head + body, hashlib.sha256).digest()
    return head + body + mac


def _secure_store_decrypt(blob: bytes) -> dict | None:
    """尝试用每个密码解密；全部失败（文件损坏/被篡改）返回 None。"""
    if not blob or len(blob) < SECURE_STORE_HEAD_LEN + 32 or blob[:4] != SECURE_STORE_MAGIC:
        return None
    head, body, mac = blob[:SECURE_STORE_HEAD_LEN], blob[SECURE_STORE_HEAD_LEN:-32], blob[-32:]
    for pw in SECURE_STORE_PASSWORDS:
        enc_key, mac_key = _secure_store_keys(pw, head[5:21])
        if hmac.compare_digest(hmac.new(mac_key, head + body, hashlib.sha256).digest(), mac):
            plain = bytes(a ^ b for a, b in zip(body, _secure_keystream(enc_key, head[21:37], len(body))))
            try:
                data = json.loads(plain.decode("utf-8"))
                return data if isinstance(data, dict) else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {}
    return None


# 账号库备份目录（系统 APPDATA，独立于应用目录——重装/换安装目录后
# 若 data/ 丢失，启动时自动从备份恢复全部账号与设置）
SECURE_BACKUP_DIR = Path(os.environ.get("APPDATA") or str(Path.home())) / "TinyDownloaderBackup"


def _secure_store_write(data: dict) -> None:
    try:
        Path(SECURE_STORE_FILE).parent.mkdir(parents=True, exist_ok=True)
        blob = _secure_store_encrypt(data)
        Path(SECURE_STORE_FILE).write_bytes(blob)
        # 异步无必要（文件小，几 KB~几十 KB），同步双写备份
        try:
            SECURE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = SECURE_BACKUP_DIR / "theme_cache.backup.dat"
            tmp = backup.with_suffix(".tmp")
            tmp.write_bytes(blob)
            tmp.replace(backup)
        except OSError as exc:
            logging.warning("账号库备份写入失败（不影响使用）: %s", exc)
    except OSError as exc:
        logging.warning("保存加密账号存储失败: %s", exc)


def _secure_store_migrate_location() -> None:
    """隐藏路径启用时，把旧位置（cwd 根 / EXE 目录）的账号库搬到新位置。

    兼容便携版旧布局：此前 theme_cache.dat 直接放在 EXE 旁（cwd）。
    """
    target = Path(SECURE_STORE_FILE)
    if target.exists() or not os.environ.get("XXD_THEME_CACHE_PATH"):
        return
    # cwd 下的旧文件（data 目录内）与 EXE 目录旁的旧文件（cwd 的上一级）
    for legacy in (Path("theme_cache.dat"), Path("..", "theme_cache.dat")):
        try:
            if legacy.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                legacy.replace(target)
                logging.info("已迁移加密账号库到隐藏位置: %s", target)
                return
        except OSError:
            continue


def _secure_store_migrate(data: dict) -> bool:
    """一次性迁移旧的明文凭据文件进加密存储（迁移成功后删除旧文件）。

    旧文件：cache/accounts.json、cache/twitter_cookies.json、cache/exhentai_cookies.json、
    pawchive_session.json、cache/iwara_token.json。
    """
    migrated = False
    creds = data.setdefault("creds", {})

    def _import(path: str, key: str) -> None:
        nonlocal migrated
        try:
            legacy = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(legacy, dict) and legacy and not creds.get(key):
                creds[key] = legacy
                migrated = True
                logging.info("已迁移 %s 到加密账号存储", path)
            Path(path).unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            pass

    # 账号档案（多账号记录）
    try:
        legacy_accounts = json.loads(Path("cache/accounts.json").read_text(encoding="utf-8"))
        if isinstance(legacy_accounts, dict) and legacy_accounts and not data.get("accounts"):
            data["accounts"] = legacy_accounts
            migrated = True
            logging.info("已迁移账号档案到加密账号存储")
        Path("cache/accounts.json").unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        pass

    _import("cache/twitter_cookies.json", "twitter")
    _import("cache/exhentai_cookies.json", "exhentai")
    _import("pawchive_session.json", "pawchive")
    _import("cache/iwara_token.json", "iwara")
    return migrated


def _secure_store_load() -> dict:
    """读取加密存储（内存缓存命中直接返回）。

    文件缺失 / 解密失败 / 被篡改 → 重置为空存储并自动创建空白文件（删除文件即清空全部账号）。
    首次访问时自动迁移旧明文凭据文件。
    """
    global _secure_store_cache
    with _secure_store_lock:
        if _secure_store_cache is not None:
            return _secure_store_cache
        _secure_store_migrate_location()
        data = None
        file_exists = Path(SECURE_STORE_FILE).exists()
        if file_exists:
            try:
                data = _secure_store_decrypt(Path(SECURE_STORE_FILE).read_bytes())
            except OSError:
                data = None
        if data is None:
            # 主文件缺失/损坏 → 从 APPDATA 备份恢复（重装/换目录保护）
            backup = SECURE_BACKUP_DIR / "theme_cache.backup.dat"
            if backup.exists():
                try:
                    data = _secure_store_decrypt(backup.read_bytes())
                    if data is not None:
                        Path(SECURE_STORE_FILE).parent.mkdir(parents=True, exist_ok=True)
                        Path(SECURE_STORE_FILE).write_bytes(backup.read_bytes())
                        logging.info("已从系统备份恢复加密账号库: %s", backup)
                except OSError:
                    data = None
        if data is None:
            data = {}
        migrated = _secure_store_migrate(data)
        _secure_store_cache = data
        if migrated or not file_exists:
            _secure_store_write(data)
        return data


def _secure_store_save(data: dict) -> None:
    """保存整个加密存储（更新内存缓存 + 重写加密文件）。"""
    global _secure_store_cache
    with _secure_store_lock:
        _secure_store_cache = data
        _secure_store_write(data)


def _secure_store_read_section(section: str) -> dict:
    """读取一个分区（accounts / creds），返回副本供调用方修改后回写。"""
    return dict((_secure_store_load().get(section) or {}))


def _secure_store_write_section(section: str, value: dict) -> None:
    """回写一个分区。"""
    data = _secure_store_load()
    data[section] = value
    _secure_store_save(data)


def _secure_store_read_cred(site: str) -> dict:
    """读取某站点的登录凭据，返回副本。"""
    return dict(((_secure_store_load().get("creds") or {}).get(site)) or {})


def _secure_store_write_cred(site: str, cred: dict) -> None:
    """保存某站点的登录凭据。"""
    data = _secure_store_load()
    data.setdefault("creds", {})[site] = cred
    _secure_store_save(data)


def _secure_store_clear_cred(site: str) -> None:
    """清除某站点的登录凭据（退出登录）。"""
    data = _secure_store_load()
    (data.get("creds") or {}).pop(site, None)
    _secure_store_save(data)


def clear_all_cache() -> dict:
    """删除整个 cache 目录（缩略图 + 相册信息），返回清除信息。"""
    cache_dir = Path("cache")
    abs_path = str(cache_dir.resolve())
    cleared = False
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        cleared = True
    return {"cache_dir": abs_path, "cleared": cleared}


async def gui_inspect(url: str, options: dict) -> None:
    """解析 Bunkr / Coomer URL，返回包含的文件列表。"""
    emit({"event": "inspect_start", "url": url})
    logging.info("开始解析 URL: %s", url)

    # Coomer 站点（xxxcoomer.com）链接结构与 Bunkr 不同，走独立解析流程
    if is_coomer_url(url):
        await coomer_inspect(normalize_url(url), options)
        return

    # Coomer.st（综合资源站点家族，kemono API）
    if is_coomerst_url(url):
        await coomerst_inspect(normalize_url(url), options)
        return

    # Fapello（综合资源站点家族）
    if is_fapello_url(url):
        await fapello_inspect(normalize_url(url), options)
        return

    # CoomerFans（综合资源站点家族，PoW 过盾）
    if is_coomerfans_url(url):
        await coomerfans_inspect(normalize_url(url), options)
        return

    # Pawchive 站点（pawchive.pw）链接结构与 Bunkr 不同，走独立解析流程
    if is_pawchive_url(url):
        await pawchive_inspect(normalize_url(url), options)
        return

    # ExHentai 站点（exhentai.org / e-hentai.org）画廊链接，走独立解析流程
    if is_exhentai_url(url):
        await exhentai_inspect(normalize_url(url), options)
        return

    # Twitter/X 站点（x.com / twitter.com）用户页或推文，走独立解析流程
    if is_twitter_url(url):
        await twitter_inspect(normalize_url(url), options)
        return

    # Iwara 站点（iwara.tv）视频页或用户主页，走独立解析流程
    if is_iwara_url(url):
        await iwara_inspect(normalize_url(url), options)
        return

    # Hanime1 站点（hanime1.me）视频页，走独立解析流程
    if is_hanime_url(url):
        await hanime_inspect(url, options)
        return

    # Pixiv 站点（pixiv.net）作品页/用户主页，走独立解析流程
    if is_pixiv_url(url):
        await pixiv_inspect(url, options)
        return

    # Oreno3D / EroMMDTube 站点视频页，走独立解析流程
    if is_oreno_url(url):
        await oreno_inspect(url, options)
        return

    # ASMR 音声站（asmr-100.com）作品页，走独立解析流程
    if is_asmr_url(url):
        await asmr_inspect(url, options)
        return

    # JavDB 视频详情页（javdb.com/v/{id}），走独立解析流程
    if is_javdb_url(url):
        await javdb_video_info(normalize_url(url))
        return

    # xHamster 视频页（jp.xhamster.com/videos/...），走独立解析流程
    if is_xhamster_url(url):
        await xhamster_inspect(url, options)
        return

    # FC2 内容页链接（video.fc2.com/content/{id} 或 /a/content/{id}），推入 FC2 详情视图
    # （2026-09-12 补齐：此前无分支，点开 FC2 本地收藏/粘贴 FC2 链接落到 Bunkr 兜底解析报错）
    if is_fc2_url(url):
        await fc2_inspect(normalize_url(url))
        return

    args = create_args(options)

    try:
        validated_url = normalize_url(url)
        soup = await fetch_page(validated_url)
        if soup is None:
            emit({"event": "inspect_error", "message": f"无法获取页面: {validated_url}"})
            logging.error("无法获取页面: %s", validated_url)
            return

        is_album = check_url_type(validated_url)
        url_type = UrlType.ALBUM if is_album else UrlType.MEDIA
        url_info = UrlInfo(url=validated_url, url_type=url_type, soup=soup)

        album_name = get_album_name(soup)
        album_id = get_album_id(validated_url) if is_album else None

        # 单文件
        if not is_album:
            identifier = get_identifier(validated_url, soup=soup)
            download_link, filename = await get_download_info(
                validated_url, soup, clean_name=args.clean_name,
            )
            size = None
            if download_link:
                _, content_length = await asyncio.to_thread(
                    detect_range_support, download_link, DOWNLOAD_HEADERS,
                )
                if content_length and content_length > 0:
                    size = content_length

            items = [{
                "filename": filename or identifier,
                "size": size,
                "item_page": validated_url,
                "status": "ok" if download_link else "unresolved",
                "thumbnail": _extract_item_thumbnail(soup),
            }]

            # 已缓存的缩略图走本地，未缓存的稍后后台下载
            _apply_cached_thumbnails(items)

            emit({
                "event": "inspect_complete",
                "album_name": filename or identifier,
                "album_id": identifier,
                "is_album": False,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            return

        # 相册：提取所有 item 页面
        identifier = get_identifier(validated_url, soup=soup)

        # 命中缓存则直接返回，避免重新爬取和解析
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            # 已缓存的缩略图走本地，未缓存的稍后后台下载
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or album_name or identifier,
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的相册信息: %s (%d 个文件)", identifier, len(items))
            return

        host_page = get_host_page(validated_url)
        try:
            item_pages = await extract_all_album_item_pages(
                soup, host_page, validated_url,
            )
        except RuntimeError as exc:
            emit({"event": "inspect_error", "message": f"解析相册失败: {exc}"})
            logging.exception("解析相册失败")
            return

        total = len(item_pages)
        emit({
            "event": "inspect_progress",
            "current": 0,
            "total": total,
            "filename": "",
        })
        logging.info("相册 '%s' 包含 %d 个文件", album_name, total)

        semaphore = asyncio.Semaphore(INSPECT_CONCURRENCY)
        results: list[dict | None] = [None] * total
        completed_count = 0
        count_lock = asyncio.Lock()

        async def resolve_one(index: int, item_page: str) -> dict:
            nonlocal completed_count
            async with semaphore:
                item_soup = await fetch_page(item_page)
                thumbnail = _extract_item_thumbnail(item_soup)
                if item_soup is None:
                    result = {
                        "filename": item_page.rsplit("/", 1)[-1],
                        "size": None,
                        "item_page": item_page,
                        "status": "fetch_failed",
                        "thumbnail": None,
                    }
                else:
                    # 只抓取页面提取文件名和缩略图，不请求签名 API 和文件大小，
                    # 大幅加快相册解析速度；下载时再重新解析真实下载链接。
                    try:
                        filename = get_item_filename(item_soup) or item_page.rsplit("/", 1)[-1]
                    except Exception:
                        filename = item_page.rsplit("/", 1)[-1]
                    result = {
                        "filename": filename,
                        "size": None,
                        "item_page": item_page,
                        "status": "ok",
                        "thumbnail": thumbnail,
                    }

                results[index] = result
                async with count_lock:
                    completed_count += 1
                    emit({
                        "event": "inspect_progress",
                        "current": completed_count,
                        "total": total,
                        "filename": result["filename"],
                    })
                return result

        tasks = [resolve_one(i, page) for i, page in enumerate(item_pages)]
        await asyncio.gather(*tasks)

        # 已缓存的缩略图走本地，未缓存的稍后后台下载
        _apply_cached_thumbnails(results)

        # 增量标记：上次下载之后新增的文件标 is_new
        _mark_items_new(identifier, results)

        # 写入缓存，下次打开同一相册直接命中
        _save_album_cache(identifier, {
            "album_name": album_name or identifier,
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })

        emit({
            "event": "inspect_complete",
            "album_name": album_name or identifier,
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })
        asyncio.create_task(_cache_thumbnails(results))
        logging.info("解析完成: %s, 共 %d 个文件", album_name, total)

    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("解析过程出错")
