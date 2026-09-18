# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：下载任务管理器（含各站 _xxx_download_one）。

由 gui_bridge.py 按物理顺序拆出（原行区间 13764-15745），
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
# 下载任务管理器
# ============================
DOWNLOAD_TASKS_FILE = "downloads_tasks.json"


def _hls_remux_mp4(ts_path, timeout: int = 600) -> bool:
    """HLS 拼接 TS 产物 remux 成真 MP4 容器（ffmpeg -c copy 不重编码）。

    TS 伪装 .mp4 的产物部分播放器解析显示比例（SAR/DAR）异常（用户实测画面拉伸）；
    remux 把宽高比/时间戳正确写进 MP4 头。失败（无 ffmpeg 等）保留拼接产物原样。"""
    try:
        import subprocess
        src = Path(ts_path)
        tmp = src.with_name(src.name + ".remux.mp4")
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
             "-c", "copy", "-movflags", "+faststart", str(tmp)],
            capture_output=True, timeout=timeout)
        if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            os.replace(tmp, src)
            return True
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    except Exception:
        try:
            src = Path(ts_path)
            tmp = src.with_name(src.name + ".remux.mp4")
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except Exception:
            pass
    return False


def _dash_remux_mp4(video_path, audio_path, out_path, timeout: int = 900):
    """B站 DASH 分轨合并：video.m4s + audio.m4s → MP4（ffmpeg -c copy 不重编码）。

    audio_path 传 None 则仅视频转封装；video_path 传 None 则仅音频转封装（.m4a）。
    返回 (ok, err_tail)：失败（无 ffmpeg 等）ok=False，调用方兜底保存分轨原样。
    安全：argv 参数列表 + 不经 shell；路径均为程序内部构造的临时文件与任务文件名。
    显式 -map：B站 fMP4 分轨在 ffmpeg 默认流选择下偶发只保留视频（音频被静默丢弃）。"""
    try:
        import subprocess
        if video_path and audio_path:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", str(video_path), "-i", str(audio_path),
                 "-map", "0:v", "-map", "1:a",
                 "-c", "copy", "-movflags", "+faststart", str(out_path)],
                capture_output=True, timeout=timeout)
        elif video_path:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", str(video_path),
                 "-map", "0:v",
                 "-c", "copy", "-movflags", "+faststart", str(out_path)],
                capture_output=True, timeout=timeout)
        else:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", str(audio_path),
                 "-map", "0:a",
                 "-c", "copy", "-movflags", "+faststart", str(out_path)],
                capture_output=True, timeout=timeout)
        out = Path(out_path)
        ok = r.returncode == 0 and out.exists() and out.stat().st_size > 0
        err_tail = (r.stderr or b"")[-300:].decode("utf-8", errors="replace")
        if not ok and not err_tail:
            err_tail = "ffmpeg 返回非零但无错误输出"
        return ok, err_tail
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


class DownloadManager:
    """管理下载任务队列：持久化、后台下载、暂停/继续/取消、关机、重启恢复。"""

    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}
        self._runners: dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()
        self._shutdown_after_done = False
        # 快照/落盘防抖（任务和文件数量多时，全量推送 + 全量写盘会造成卡顿）
        self._snapshot_handle: asyncio.TimerHandle | None = None
        self._save_handle: asyncio.TimerHandle | None = None
        self._dirty = False
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        try:
            with Path(DOWNLOAD_TASKS_FILE).open("r", encoding="utf-8") as file:
                data = json.load(file)
            for task in data.get("tasks", []):
                if not task.get("id"):
                    continue
                # 上次退出时仍在运行的任务，恢复为暂停，等待用户手动继续
                if task.get("status") in ("running", "pending"):
                    task["status"] = "paused"
                # 历史任务路径转绝对（前端"打开文件夹/定位文件"需要绝对路径）
                if task.get("save_dir") and not Path(task["save_dir"]).is_absolute():
                    task["save_dir"] = str(Path(task["save_dir"]).resolve())
                phantom = 0
                for item in task.get("files", []):
                    if item.get("status") == "downloading":
                        item["status"] = "pending"
                    fp = item.get("_final_path")
                    if fp and not Path(fp).is_absolute():
                        item["_final_path"] = str(Path(fp).resolve())
                    # 幽灵完成修复：标记 completed 但本地文件不存在
                    # （非 Bunkr 子域名被误标离线后"离线跳过"却记成功的假完成）
                    if item.get("status") == "completed" and fp and not Path(fp).exists():
                        item["status"] = "pending"
                        item["completed"] = 0
                        task["done"] = max(0, task.get("done", 0) - 1)
                        phantom += 1
                if phantom and task.get("status") == "completed":
                    # 完成任务里发现幽灵文件 → 回到暂停态，用户点"继续"即可补齐缺失文件
                    task["status"] = "paused"
                    logging.warning(
                        "任务 %s 检测到 %d 个假完成文件（本地缺失），已重置待补下",
                        task["id"], phantom,
                    )
                self.tasks[task["id"]] = task
        except (OSError, json.JSONDecodeError):
            pass

    def _write_tasks_file(self) -> None:
        """把任务表写入磁盘（调用方持有 _dirty 语义，本函数只做 IO）。"""
        try:
            payload = {"tasks": [self._json_safe_task(t) for t in self.tasks.values()]}
            _atomic_write_json(DOWNLOAD_TASKS_FILE, payload)
        except OSError as exc:
            logging.warning("保存下载任务失败: %s", exc)

    def _save(self, immediate: bool = False) -> None:
        """保存任务表（默认防抖 1s 合并写盘；immediate=True 立即写）。

        多任务/多文件时每个文件状态变化都全量写盘会拖慢整个后端，
        防抖合并后磁盘压力从 O(文件数) 降到 O(1次/秒)。
        """
        self._dirty = True
        if immediate:
            if self._save_handle is not None:
                self._save_handle.cancel()
                self._save_handle = None
            self._dirty = False
            with self._lock:
                self._write_tasks_file()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            if self._save_handle is None:
                self._save_handle = loop.call_later(1.0, self._flush_save)
        else:
            # 不在事件循环内（理论不会发生）：直接写
            self._dirty = False
            with self._lock:
                self._write_tasks_file()

    def _flush_save(self) -> None:
        self._save_handle = None
        if not self._dirty:
            return
        self._dirty = False
        with self._lock:
            self._write_tasks_file()

    @staticmethod
    def _json_safe_task(task: dict) -> dict:
        """深拷贝出可安全序列化的任务副本（并发下载线程可能同时在改原对象）。"""
        try:
            return json.loads(json.dumps(task, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            return dict(task)

    def snapshot(self) -> list[dict]:
        """任务快照（深拷贝，避免序列化时并发修改导致崩溃/脏数据）。

        最新创建的任务排在最前（用户优先关心刚发起的下载）。"""
        with self._lock:
            tasks = [self._json_safe_task(t) for t in self.tasks.values()]
        tasks.sort(key=lambda t: t.get("created_at") or 0, reverse=True)
        return tasks

    def emit_snapshot(self, immediate: bool = False) -> None:
        """推送任务快照给前端（默认防抖 0.5s 合并；immediate=True 立即推）。

        快照包含全部任务与全部文件条目，任务多时单条就很大；
        每个文件状态变化都全量推送会淹没 IPC 通道 → 前端卡顿。
        """
        if immediate:
            if self._snapshot_handle is not None:
                self._snapshot_handle.cancel()
                self._snapshot_handle = None
            emit({"event": "tasks_snapshot", "tasks": self.snapshot()})
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            emit({"event": "tasks_snapshot", "tasks": self.snapshot()})
            return
        if self._snapshot_handle is None:
            self._snapshot_handle = loop.call_later(0.5, self._flush_snapshot)

    def _flush_snapshot(self) -> None:
        self._snapshot_handle = None
        emit({"event": "tasks_snapshot", "tasks": self.snapshot()})

    # ---------- 任务操作 ----------
    @staticmethod
    def _norm_source_url(u: str) -> str:
        """任务源 URL 规范化（去 query/尾斜杠/大小写），用于同源任务匹配。"""
        return (u or "").split("?", 1)[0].strip().rstrip("/").lower()

    def _find_same_source_task(self, url: str, album_id: str | None) -> dict | None:
        """找同源任务（同一 URL 或同一 album_id、未取消），取最近创建的一个。"""
        norm = self._norm_source_url(url)
        best = None
        for t in self.tasks.values():
            if t.get("status") == "cancelled":
                continue
            same = False
            if album_id and t.get("album_id") and t.get("album_id") == album_id:
                same = True
            elif norm and self._norm_source_url(t.get("url", "")) == norm:
                same = True
            if same and (best is None or (t.get("created_at") or 0) > (best.get("created_at") or 0)):
                best = t
        return best

    def submit(
        self,
        url: str,
        items: list[dict],
        options: dict,
        album_name: str,
        album_id: str | None,
    ) -> str:
        """创建下载任务；同源任务已存在时增量合并（只追加新文件），返回任务 ID。

        典型场景（X 站等）：解析 34 个视频先下载 → 界面"加载更多"到 53 个 →
        再次下载 → 只把新增的 19 个追加进原任务继续下，而不是新建 53 个任务。
        """
        # 同源增量合并：已取消的任务不复活（尊重用户取消），走新建
        existing = self._find_same_source_task(url, album_id)
        if existing:
            # 世界标记/落盘选项以本次提交为准：跨会话合并时旧任务可能带着
            # 上一会话的 inner 默认（表世界重下同一来源会被旧标记吞掉，
            # 落盘目录与下载管理视图全错）——当前提交显式带 options 才覆盖。
            # 必须放在"全部重复提前返回"之前，否则全重复提交永远刷不新世界标记。
            world_refreshed = False
            if options:
                merged_options = {**(existing.get("options") or {}), **options}
                if merged_options != (existing.get("options") or {}):
                    existing["options"] = merged_options
                    existing["world"] = str(merged_options.get("world")
                                            or existing.get("world") or "inner")
                    world_refreshed = True
            seen = {
                (f.get("item_page", ""), f.get("filename", ""))
                for f in existing.get("files", [])
            }
            new_items = [
                it for it in items
                if (str(it.get("item_page", "")), str(it.get("filename", ""))) not in seen
            ]
            task_name = existing.get("album") or album_name or album_id or "下载"
            if not new_items:
                # 全部重复：占位式批量的常态（每个文件一次增量提交）——不再刷日志；
                # 仅世界标记实际刷新时才落盘+推快照（表世界视图据此立即显示）
                if world_refreshed:
                    self._save(immediate=True)
                    self.emit_snapshot(immediate=True)
                return existing["id"]
            for it in new_items:
                existing["files"].append(_task_file_entry(it))
            existing["total"] = len(existing["files"])
            if existing.get("status") in ("running", "pending") and existing["id"] in self._runners:
                # 下载中的任务：本轮文件集合已固定，收尾后自动补跑新文件
                existing["_append_rounds"] = True
            elif existing.get("status") == "completed":
                existing["status"] = "pending"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)
            # 新增多于 1 个才记日志（占位式批量逐文件合并，逐条日志只会刷屏）
            if len(new_items) > 1:
                emit({"event": "log", "type": "下载",
                      "message": f"已合并到现有任务「{task_name}」：新增 {len(new_items)} 个文件（重复的已跳过），共 {existing['total']} 个"})
            logging.info("增量合并到任务 %s：新增 %d / 提交 %d 个文件",
                         existing["id"], len(new_items), len(items))
            return existing["id"]

        task_id = f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        # 条目字段以 TASK_FILE_FIELDS 为准（_task_file_entry 统一构造，
        # 此前手工白名单曾漏 media_type 导致 X 站图片/视频分类静默失效）
        files = [_task_file_entry(item) for item in items]
        task = {
            "id": task_id,
            "album": album_name or album_id or "下载",
            "album_id": album_id or "",
            "url": url,
            "status": "pending",
            "created_at": time.time(),
            "options": options,
            "files": files,
            "done": 0,
            "failed": 0,
            "total": len(files),
            # 世界标记：surface=表世界（正常内容，真实落盘 C 盘用户下载夹）/ inner=里世界
            "world": str(options.get("world") or "inner"),
        }
        self.tasks[task_id] = task
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)
        return task_id

    def record_local_file(
        self,
        album_name: str,
        file_path: str,
        page_url: str = "",
        world: str = "surface",
        media_type: str = "doc",
    ) -> str:
        """把一份「已经就位」的本地文件登记成完成态任务（不产生下载）。

        用途：表世界的「存为 Word」导出——用户在下载管理里应当看得到这次导出，
        并能一键打开所在文件夹（与媒体下载记录同一视图、同一套操作）。
        只登记真实存在的文件；文件不存在时返回空串，由调用方决定是否提示。
        """
        try:
            p = Path(file_path)
            if not p.is_file():
                logging.warning("record_local_file: 文件不存在，跳过登记 %s", file_path)
                return ""
            size = p.stat().st_size
        except OSError:
            logging.exception("record_local_file: 读取文件信息失败 %s", file_path)
            return ""
        task_id = f"local-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        entry = _task_file_entry({          # noqa: F821（包加载器注入）
            "filename": p.name,
            "media_type": media_type,
            "size": size,
        })
        entry["status"] = "completed"
        entry["completed"] = size
        entry["media_path"] = str(p)
        task = {
            "id": task_id,
            "album": album_name or "网页导出",
            "album_id": "",
            "url": page_url or "",
            "status": "completed",
            "created_at": time.time(),
            "finished_at": time.time(),
            "options": {"world": world},
            "files": [entry],
            "done": 1,
            "failed": 0,
            "total": 1,
            "world": world,
            # 前端「打开文件夹」按钮按它定位（转绝对路径，相对路径在 Electron
            # 进程 cwd 下会"找不到文件"）
            "save_dir": str(p.parent.resolve()),
        }
        self.tasks[task_id] = task
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)
        return task_id

    def start(self, task_id: str) -> None:
        """启动/继续一个任务的后台下载。"""
        task = self.tasks.get(task_id)
        if not task or task_id in self._runners:
            return
        if task.get("status") == "cancelled":
            return
        task["status"] = "running"
        self._save(immediate=True)
        self._runners[task_id] = asyncio.create_task(self._run(task_id))
        self.emit_snapshot(immediate=True)

    def pause(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task or task["status"] not in ("running", "pending"):
            return
        task["status"] = "paused"
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)
        emit({"event": "task_paused", "task_id": task_id,
              "message": f"任务「{task.get('album') or ''}」已暂停，正在停止下载中的文件..."})
        emit({
            "event": "log",
            "type": "下载",
            "message": f"任务「{task.get('album') or ''}」已暂停",
        })

    def resume(self, task_id: str) -> None:
        self.start(task_id)

    def retry(self, task_id: str) -> None:
        """重试任务：失败文件重置为待下载并重新启动下载。

        已完成的文件不动（本地校验机制会在启动时核对文件是否存在）；
        失败计数清零，任务状态回到 running。
        """
        task = self.tasks.get(task_id)
        if not task:
            return
        if task_id in self._runners:
            # 正在运行，无法重试：明确反馈给前端（此前静默返回，用户不知道有没有生效）
            emit({"event": "task_retry", "ok": False, "task_id": task_id,
                  "message": "任务正在下载中，等下载结束（或先暂停）后再重试失败文件"})
            return
        reset_count = 0
        for item in task.get("files", []):
            if item.get("status") == "failed":
                item["status"] = "pending"
                item["completed"] = 0
                reset_count += 1
        task["failed"] = 0
        task["status"] = "running"
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)
        msg = (f"任务「{task.get('album') or ''}」重试 {reset_count} 个失败文件"
               if reset_count else f"任务「{task.get('album') or ''}」没有失败文件，无需重试")
        emit({"event": "task_retry", "ok": True, "task_id": task_id,
              "reset": reset_count, "message": msg})
        emit({
            "event": "log",
            "type": "下载",
            "message": msg,
        })
        if not reset_count:
            # 没有失败文件：状态还原为 completed，不空跑一遍
            task["status"] = "completed"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)
            return
        self._runners[task_id] = asyncio.create_task(self._run(task_id))
        self.emit_snapshot(immediate=True)

    def retry_file(self, task_id: str, item_page: str) -> None:
        """重试单个文件：目标失败文件重置为待下载并重启任务。

        其他失败文件保持 failed（_run 的 run_one 会跳过它们）；
        已完成的文件不动。任务必须不在运行中（运行中无法插入新协程）。
        """
        task = self.tasks.get(task_id)
        if not task:
            return
        if task_id in self._runners:
            emit({"event": "task_retry", "ok": False, "task_id": task_id,
                  "message": "任务正在下载中，请等任务结束后再重试单个文件"})
            emit({
                "event": "log",
                "type": "下载",
                "message": "任务正在下载中，请等任务结束后再重试单个文件",
            })
            return
        item = next(
            (f for f in task.get("files", []) if f.get("item_page") == item_page),
            None,
        )
        if not item or item.get("status") != "failed":
            return
        item["status"] = "pending"
        item["completed"] = 0
        item.pop("error", None)
        task["failed"] = max(0, task.get("failed", 0) - 1)
        task["status"] = "running"
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)
        emit({"event": "task_retry", "ok": True, "task_id": task_id,
              "message": f"正在重试文件「{item.get('filename') or item_page}」"})
        emit({
            "event": "log",
            "type": "下载",
            "message": f"重试文件「{item.get('filename') or item_page}」（任务「{task.get('album') or ''}」）",
        })
        self._runners[task_id] = asyncio.create_task(self._run(task_id))
        self.emit_snapshot(immediate=True)

    def cancel(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        task["status"] = "cancelled"
        for item in task.get("files", []):
            if item.get("status") == "downloading":
                item["status"] = "pending"
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)

    def remove(self, task_id: str, delete_files: bool = False) -> None:
        """移除任务；delete_files=True 时同步删除已下载的文件与文件夹。

        目录清理只删空目录（rmdir）：任务文件夹内的未记录杂文件会让该层保留，
        避免误删非本任务产物。"""
        task = self.tasks.get(task_id)
        if not task:
            return
        task["status"] = "cancelled"
        removed_dirs: set = set()
        save_dir: Path | None = None
        if task.get("save_dir"):
            try:
                save_dir = Path(task["save_dir"])
            except OSError:
                save_dir = None
        if delete_files:
            for f in task.get("files", []):
                fp = f.get("_final_path")
                if not fp:
                    continue
                try:
                    p = Path(fp)
                    if p.exists():
                        p.unlink()
                        removed_dirs.add(p.parent)
                except OSError as exc:
                    logging.warning("删除文件失败 %s: %s", fp, exc)
            if save_dir is not None and save_dir.exists():
                removed_dirs.add(save_dir)
        self.tasks.pop(task_id, None)
        # 流媒体任务：一并清掉 cache/hls_parts/<task_id>（分片 + 续传状态）。
        # 不移除的话，用户删了任务分片还留在磁盘上，且下次同名任务会误命中旧断点。
        with contextlib.suppress(Exception):
            shutil.rmtree(_web_hls_task_dir(task_id), ignore_errors=True)   # noqa: F821
        if delete_files and removed_dirs:
            # 空目录逐级向上清理；边界 = 任务目录的上一级（即下载根，兼容
            # custom_path 自定义根——旧逻辑硬编码 cwd/Downloads 在自定义目录时失效）
            boundary = save_dir.parent if save_dir is not None else Path("Downloads").resolve()
            for d in list(removed_dirs):
                try:
                    probe = Path(d)
                    while probe.exists() and probe != boundary and boundary in probe.parents:
                        try:
                            probe.rmdir()  # 仅空目录可删
                        except OSError:
                            break
                        probe = probe.parent
                except OSError:
                    pass
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)

    def move_task_folder(self, task_id: str, dest_dir: str) -> tuple[bool, str]:
        """把任务文件夹整体移动到目标目录（迁移/集中资源用）。

        仅允许非下载中状态的任务；重名自动加序号。返回 (ok, message)。"""
        import shutil

        task = self.tasks.get(task_id)
        if not task:
            return False, "任务不存在"
        if task.get("status") in ("running", "pending"):
            return False, "任务下载中，请先暂停或等完成后移动"
        save_dir = task.get("save_dir")
        if not save_dir or not Path(save_dir).exists():
            return False, "任务文件夹不存在（可能已被移动或删除）"
        dest_root = Path(dest_dir)
        if not dest_root.is_dir():
            return False, "目标目录不存在"
        src = Path(save_dir).resolve()
        dest_root = dest_root.resolve()
        if dest_root == src or src in dest_root.parents:
            return False, "目标目录不能是任务文件夹自身或其子目录"
        target = dest_root / src.name
        n = 1
        while target.exists():
            target = dest_root / f"{src.name}_{n}"
            n += 1
        try:
            shutil.move(str(src), str(target))
        except Exception as exc:  # noqa: BLE001
            return False, f"移动失败: {exc}"
        task["save_dir"] = str(target)
        # 同步文件级最终路径记录（前缀替换）
        for f in task.get("files", []):
            fp = f.get("_final_path")
            if fp:
                fp_path = Path(fp)
                try:
                    rel = fp_path.relative_to(src)
                    f["_final_path"] = str(target / rel)
                except ValueError:
                    pass
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)
        logging.info("任务文件夹已移动: %s -> %s", src, target)
        return True, str(target)

    def clear_all(self, delete_files: bool = False) -> int:
        """清除全部任务（delete_files 同 remove）。返回清除数量。"""
        ids = list(self.tasks.keys())
        for tid in ids:
            try:
                self.remove(tid, delete_files=delete_files)
            except Exception:
                continue
        return len(ids)

    def set_shutdown_after_done(self, enabled: bool) -> None:
        self._shutdown_after_done = enabled
        emit({
            "event": "log",
            "type": "关机",
            "message": "已开启：全部下载完成后关机" if enabled else "已取消下载后关机",
        })

    # ---------- 下载执行 ----------
    async def _run(self, task_id: str) -> None:
        # 协程由 create_task 排期，真正开跑前任务可能已被移除（用户点了「清除记录」，
        # 或全失败清理）——用 get 取，缺失就直接退出，否则 KeyError 会在事件循环里
        # 变成"Task exception was never retrieved"噪音（下载其实已经结束了）。
        task = self.tasks.get(task_id)
        if task is None:
            self._runners.pop(task_id, None)
            return
        options = task.get("options", {})
        args = create_args(options)
        url = task.get("url", "")
        files = task.get("files", [])

        try:
            validated_url = normalize_url(url)

            if is_pawchive_url(validated_url):
                # Pawchive：直链永久有效，无需抓取页面；目录按画师名组织
                soup = None
                album_name = task.get("album") or await asyncio.to_thread(
                    _pawchive_album_name, validated_url, files,
                )
                album_id = task.get("album_id") or None
            elif is_exhentai_url(validated_url):
                # ExHentai：目录按画师 tag 组织（同一个画师同一文件夹）
                soup = None
                album_name = task.get("album") or next(
                    (f.get("artist") for f in files if f.get("artist")), None,
                ) or "ExHentai 下载"
                album_id = task.get("album_id") or None
            elif is_javdb_url(validated_url):
                # JavDB：封面/预览图直链下载（无需抓取页面），目录按番号组织
                soup = None
                album_name = task.get("album") or "JavDB 下载"
                album_id = task.get("album_id") or None
            elif is_coomer_url(validated_url):
                soup = await fetch_page(validated_url)
                if soup is None:
                    task["status"] = "failed"
                    self._save(immediate=True)
                    self.emit_snapshot(immediate=True)
                    return
                info = _coomer_parse_url(validated_url)
                album_name = (info or {}).get("username") or task.get("album") or "Coomer 下载"
                album_id = task.get("album_id") or None
            elif is_twitter_url(validated_url):
                # Twitter：目录按用户名组织（下载走独立函数，无需抓取页面）
                soup = None
                info = _twitter_parse_url(validated_url)
                album_name = task.get("album") or \
                    (info or {}).get("screen_name") or "Twitter 下载"
                album_id = task.get("album_id") or None
            else:
                # 按文件所属站点分流：iwara/hanime/asmr/oreno3d/erommd/xhamster/
                # pornhub/xvideos 等站点的下载走各自独立函数（_xxx_download_one），
                # 无需抓取任务 URL 页面；且这些 URL 不在 Bunkr 的 URL_TYPE_MAPPING
                # 中，check_url_type 会对它们报错（旧版甚至 sys.exit 杀死后端）。
                task_site = str(
                    (files[0].get("site") if files else "")
                    or options.get("site") or "",
                ).lower()
                if task_site and task_site not in ("bunkr",):
                    soup = None
                    album_name = task.get("album") or task_site
                    album_id = task.get("album_id") or None
                else:
                    soup = await fetch_page(validated_url)
                    if soup is None:
                        task["status"] = "failed"
                        self._save(immediate=True)
                        self.emit_snapshot(immediate=True)
                        return
                    is_album = check_url_type(validated_url)
                    album_name = get_album_name(soup)
                    album_id = task.get("album_id") or (
                        get_album_id(validated_url) if is_album else None
                    )
            # 批量下载母文件夹：非空时任务顶层目录 = 母文件夹名（各站子逻辑按画廊/番号分子文件夹）
            batch_parent = (options.get("batch_parent_folder") or "").strip()
            if batch_parent:
                album_path = build_album_directory(batch_parent, None, options)
            else:
                album_path = build_album_directory(album_name, album_id, options)
            # 记录任务实际保存目录（前端"打开对应文件夹"按钮使用；转绝对路径，
            # 相对路径在 Electron 进程 cwd 下会"找不到文件"）
            task["save_dir"] = str(Path(album_path).resolve())

            rate_limiter = RateLimiter(args.rate_limit * KB if args.rate_limit else None)
            session_info = SessionInfo(
                args=args,
                bunkr_status={},
                download_path=album_path,
                rate_limiter=rate_limiter,
            )
            max_retries = args.max_retries or MAX_RETRIES

            # 任务内多文件并发下载：用信号量控制并发数，避免触发反爬
            concurrent = max(1, int(getattr(args, "concurrent_files", 2) or 2))
            semaphore = asyncio.Semaphore(concurrent)

            async def run_one(item: dict) -> None:
                if task["status"] in ("paused", "cancelled"):
                    return
                if item.get("status") == "failed":
                    # 失败文件跳过：只有任务级/文件级重试把它们重置为 pending 后才会再下载
                    # （此前 failed 也重跑，导致单文件重试时其他失败文件被连带重下）
                    return
                if item.get("status") == "completed":
                    # 本地校验：记录的最终路径文件已被删除 → 重置为待下载（本地没有的重新下载）
                    fp = item.get("_final_path")
                    if fp and not Path(fp).exists():
                        logging.info("本地文件缺失，重新下载: %s", fp)
                        item["status"] = "pending"
                        item["completed"] = 0
                        task["done"] = max(0, task.get("done", 0) - 1)
                    else:
                        return
                async with semaphore:
                    await self._download_one_file(
                        task, item, args, session_info, album_path, task_id, max_retries,
                    )

            await asyncio.gather(*(run_one(item) for item in files))

            # 更新增量下载状态（记录已下载文件，下次解析时标记新文件）
            _update_download_state(task.get("album_id") or None, files)

            # 失败清单：任务内剩余文件全部结束后，把失败项（文件名 + 网页链接）写入 txt 供手动下载
            self._write_failure_report(task, files, album_path, task_id)

            # 全部失败自动清理：任务没有任何文件下载成功时，下载目录里只有失败清单/空目录，
            # 直接删除整个空文件夹并移除下载记录（用户要求：不留垃圾目录和无效任务）
            # 注意：暂停/取消收尾绝不清理（大量文件还是 pending，不是"全部失败"）；
            # 流媒体任务（sniffer_hls）同样豁免——失败后必须留在列表里，用户才能点
            # 「重试」从断点续传（分片都在 cache/hls_parts 里，记录删了就只能整片重下）
            is_hls_task = any(str(f.get("site") or "") == "sniffer_hls" for f in files)
            if (
                task["status"] not in ("paused", "cancelled")
                and files and not is_hls_task
                and not any(f.get("status") == "completed" for f in files)
            ):
                try:
                    album_dir = Path(album_path)
                    # 目录里除"下载失败清单"外还有真实文件 → 说明是历史内容，不清理
                    remaining = [
                        p for p in album_dir.rglob("*")
                        if p.is_file() and not p.name.startswith("下载失败清单_")
                    ]
                    if not remaining:
                        shutil.rmtree(album_dir, ignore_errors=True)
                        logging.info("任务全部失败，已自动清理空文件夹: %s", album_dir)
                        with self._lock:
                            self.tasks.pop(task_id, None)
                        self._save(immediate=True)
                        self.emit_snapshot(immediate=True)
                        emit({
                            "event": "log",
                            "type": "下载",
                            "message": f"任务「{task.get('album') or ''}」全部文件下载失败，已自动清理空文件夹并移除下载记录",
                        })
                        # 关机计划不因清理而跳过（与其他收尾路径一致）
                        if self._shutdown_after_done:
                            self._do_shutdown()
                        return
                except Exception:
                    logging.exception("清理全失败空文件夹出错: %s", task_id)

            # 收尾状态
            if task["status"] not in ("paused", "cancelled", "failed"):
                task["status"] = "completed"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)

            if task["status"] == "completed" and self._shutdown_after_done:
                self._do_shutdown()

        except asyncio.CancelledError:
            task["status"] = "cancelled"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)
            raise
        except SystemExit as exc:
            # src/ 残留的 sys.exit 不允许杀死后端：记为任务失败并继续存活
            logging.exception("下载任务触发 SystemExit(%s)（src 模块调用了 sys.exit）: %s", exc, task_id)
            task["status"] = "failed"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)
        except Exception as exc:
            logging.exception("下载任务出错: %s", task_id)
            task["status"] = "failed"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)
        finally:
            self._runners.pop(task_id, None)
            # 下载期间增量合并进来的新文件：本协程的文件集合已固定（gather 调用时展开），
            # 收尾后若还有待补跑的增量文件，重启协程继续下载（暂停/取消/失败则等用户操作）
            task_after = self.tasks.get(task_id)
            if task_after and task_after.pop("_append_rounds", False) \
                    and task_after.get("status") not in ("paused", "cancelled", "failed"):
                self._runners[task_id] = asyncio.create_task(self._run(task_id))

    def _write_failure_report(
        self, task: dict, files: list, album_path: str, task_id: str,
    ) -> None:
        """任务收尾：汇总失败文件生成 txt 清单（文件名 + 网页链接），供用户手动下载。"""
        # 暂停/取消收尾时不生成失败清单（任务还没真正结束，恢复后继续下载）
        if task.get("status") in ("paused", "cancelled"):
            return
        try:
            failed_items = [f for f in files if f.get("status") == "failed"]
            if not failed_items:
                return
            # 失败原因归类（error 字段可能由各站下载函数写入）
            lines = [
                "# 下载失败清单",
                f"# 任务: {task.get('album') or task.get('url', '')}",
                f"# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"# 失败数: {len(failed_items)} / {len(files)}",
                "",
                "格式: 文件名 | 网页链接 | 错误信息",
                "-" * 60,
            ]
            for f in failed_items:
                name = f.get("filename") or f.get("_final_name") or "（未知文件名）"
                link = f.get("item_page") or task.get("url", "")
                err = (f.get("error") or "").strip() or "下载失败（网络/解析错误）"
                lines.append(f"{name} | {link} | {err}")
            lines += ["-" * 60, "请复制链接到浏览器手动下载。"]
            report_name = f"下载失败清单_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            report_path = Path(album_path) / report_name
            # album_path 一定已存在（build_album_directory 创建）；防御性再建一次
            Path(album_path).mkdir(parents=True, exist_ok=True)
            report_path.write_text("\n".join(lines), encoding="utf-8-sig")  # BOM 让记事本正确识别 UTF-8
            logging.info("已生成失败清单: %s（%d 个失败文件）", report_path, len(failed_items))
            emit({
                "event": "log",
                "type": "下载",
                "message": f"本任务有 {len(failed_items)} 个文件下载失败，已生成清单: {report_name}",
            })
        except Exception as exc:
            logging.exception("生成失败清单出错: %s", task_id)

    async def _download_one_file(
        self,
        task: dict,
        item: dict,
        args,
        session_info,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个文件（供 _run 并发调用）。"""
        options = task.get("options", {})

        item["status"] = "downloading"
        item["completed"] = 0
        self._save()
        # 立即推送快照，让前端知道当前下载中的文件，进度才能正确联动
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id

        item_page = item.get("item_page", "")

        if item.get("site") == "sniffer_hls":
            # 流媒体「下载整片」：分片落盘 + 断点续传 + 合并为 MP4。进度单位是
            # 分片数而非字节数，暂停/续传语义也与普通文件不同，故走独立流程。
            await self._hls_task_download(task, item, task_id, album_path, options)
            return

        if item.get("site") == "pawchive":
            # Pawchive：直链永久有效，直接下载（站点对下载有限速，先节流）
            await _pawchive_throttle_download()
            download_link = item.get("media_url") or ""
            filename = item.get("filename") or "pawchive_file"
            if not download_link.startswith("http"):
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                return
        elif item.get("site") == "exhentai":
            # ExHentai：直链 keystamp 会过期，重新解析图片页；下载走独立函数
            await self._exhentai_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "twitter":
            # Twitter：媒体直链永久有效但需代理，下载走独立函数
            await self._twitter_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "iwara":
            # Iwara：视频直链带 expires 签名会过期，下载时重新解析最高画质源
            await self._iwara_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "hanime":
            # Hanime1：MP4 直链 secure 签名会过期，下载时重新解析最高画质源
            await self._hanime_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "xhamster":
            # xHamster：页面密文会过期，下载时重新解密最高画质直链（需 Referer + 代理）
            await self._xhamster_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "fc2":
            # FC2：mid 签名会过期 → 下载时重新解析播放源（ae 流程），mp4 直链 + Referer
            await self._fc2_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "pixiv":
            # Pixiv：i.pximg.net 直链永久有效但需 Referer；用户主页条目按 illust_id 解析直链
            await self._pixiv_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "asmr":
            # ASMR：文件直链永久有效（匿名可下载），filename 含文件夹相对路径
            await self._asmr_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") == "javdb":
            # JavDB：封面/预览图直链（jdbstatic CDN），filename 含番号子文件夹
            await self._javdb_download_one(
                task, item, album_path, task_id, max_retries,
            )
            return
        elif item.get("site") in ("fapello", "coomerfans"):
            # Fapello/CoomerFans：media_url 已是本地媒体代理直链（后端带 cookie/代理转发），无需重解析
            download_link = item.get("media_url") or ""
            filename = item.get("filename") or ""
            if not download_link:
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                return
        elif item.get("site") == "bilibili":
            # B站 DASH 下载（热门平台·专属方案）：视频/音频分轨直下 + ffmpeg 合并
            # （worker 在 site_bilibili.bili_download_one，finalize 后经 self 可达）
            await bili_download_one(task, item, album_path, task_id, max_retries)
            return
        elif item.get("site") == "bt":
            # BT 下载（磁力链接/.torrent）：aria2 RPC 集成，worker 在 bt_downloader.bt_download_one
            await bt_download_one(task, item, album_path, task_id, max_retries)
            return
        elif item.get("site") in ("sniffer", "leakedzone"):
            # 手动抓取（嗅探窗口/热门平台）/ Leakedzone：media_url 为已捕获/解析的直链，直接下载
            download_link = item.get("media_url") or ""
            filename = item.get("filename") or ""
            if not download_link.startswith("http"):
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                return
            # 嗅探 CDN 多带防盗链（B站 bilivideo 同时校验 bilibili Referer + 浏览器 UA，
            # 仅 Referer 仍 403）：用捕获时记录的来源页推断 Referer，并覆盖为浏览器 UA
            sniffer_referer = ""
            page = str(item.get("page_url") or "").strip()
            if not page.startswith(("http://", "https://")):
                # 条目缺来源页时回退任务 URL（sniffer.py 以首个 page_url 作为任务 url）
                turl = str(task.get("url") or "")
                if turl.startswith(("http://", "https://")) and "sniffer.local" not in turl:
                    page = turl
            if page.startswith(("http://", "https://")):
                try:
                    from urllib.parse import urlparse as _urlparse
                    _p = _urlparse(page)
                    if _p.netloc:
                        sniffer_referer = f"{_p.scheme}://{_p.netloc}/"
                except Exception:  # noqa: BLE001
                    sniffer_referer = ""
            sniffer_headers = None
            if sniffer_referer:
                sniffer_headers = {
                    **DOWNLOAD_HEADERS,
                    "Referer": sniffer_referer,
                    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/126.0.0.0 Safari/537.36"),
                }
        elif item.get("site") in ("coomer", "coomerst"):
            if item.get("site") == "coomerst":
                # Coomer.st：条目已带 /data 直链（302 → CDN 由下载机跟随）
                download_link, filename = coomerst_download_info(item)  # noqa: F821
            else:
                # Coomer（旧）：重新抓取帖子页获取新的媒体直链（视频链接带签名会过期）
                download_link, filename = await get_coomer_download_info(item)
            if not download_link:
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                return
        else:
            # 重新解析下载信息（下载链接会过期，必须重新请求）
            item_soup = await fetch_page(item_page)
            if item_soup is None:
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                return

            download_link, filename = await get_download_info(
                item_page, item_soup, clean_name=args.clean_name,
            )
            if not download_link:
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                return

        # 探测文件大小，用于进度和速度计算
        size = item.get("size")
        try:
            _, content_length = await asyncio.to_thread(
                detect_range_support, download_link, DOWNLOAD_HEADERS,
            )
            if content_length and content_length > 0:
                size = content_length
                item["size"] = size
        except Exception:
            pass

        # 应用改名弹窗回传的新文件名（手动改名后重新下载）
        filename = _apply_rename_map(options, item, filename)

        # 构建文件下载路径（Pawchive 专属子文件夹规则 + 按类型分类）
        if item.get("site") == "pawchive":
            base_dir = _pawchive_build_file_dir(album_path, item, options)
            file_download_path = build_file_download_path(base_dir, filename, options)
        else:
            file_download_path = build_file_download_path(album_path, filename, options)

        # 跳过重复项目（skip_duplicates）：同名同大小直接跳过；重名按改名规则处理
        filename, dup_action = _resolve_duplicate(file_download_path, filename, size, options)
        if dup_action == "skip":
            live_manager.update_log(event="跳过重复", details=f"{filename}（已存在相同大小的文件）")
            item["status"] = "completed"
            item["completed"] = 100
            item["_final_path"] = str(Path(file_download_path) / truncate_filename(filename))
            task["done"] = task.get("done", 0) + 1
            emit({"event": "file_complete", "filename": filename, "success": True,
                  "skipped": True, "size": size, "task_id": task_id})
            self._save()
            self.emit_snapshot()
            return
        if dup_action == "prompt":
            live_manager.update_log(event="重名待改名", details=f"{filename}（已存在同名但大小不同的文件，等待手动改名）")
            item["status"] = "completed"
            item["completed"] = 100
            task["done"] = task.get("done", 0) + 1
            emit({
                "event": "download_rename_prompt",
                "filename": filename,
                "path": str(file_download_path),
                "existing_size": Path(file_download_path, truncate_filename(filename)).stat().st_size
                if Path(file_download_path, truncate_filename(filename)).exists() else None,
                "new_size": size,
                "item": dict(item),
                "url": task.get("url", ""),
                "album": task.get("album") or "",
            })
            emit({"event": "file_complete", "filename": filename, "success": True,
                  "skipped": True, "task_id": task_id})
            self._save()
            self.emit_snapshot()
            return
        if dup_action == "download":
            # 重复添加的文件自动重命名，避免覆盖已存在/已下载文件
            filename = _unique_download_filename(file_download_path, filename)
        # 非 Bunkr 站点禁用"Bunkr 子域名离线"检测：
        # file.pawchive.pw 等非 Bunkr 域名的一次 5xx/超时会触发 mark_subdomain_as_offline，
        # 把整个子域名标记为离线，之后同域名的全部文件被"离线跳过"却返回成功（假完成）。
        file_args = args
        if str(item.get("site") or "").strip().lower() not in ("", "bunkr"):
            file_args = Namespace(**vars(args))
            file_args.disable_server_check = True
        file_session_info = replace(session_info, download_path=file_download_path, args=file_args)

        internal_task = live_manager.add_task()
        live_manager.set_task_info(internal_task, filename, size)

        media_downloader = MediaDownloader(
            session_info=file_session_info,
            download_info=DownloadInfo(
                item_url=item_page,
                download_link=download_link,
                filename=filename,
                task=internal_task,
            ),
            live_manager=live_manager,
            retry_config=RetryConfig(
                retries=max_retries,
                has_external_retry=False,
            ),
            # 暂停/取消任务时协同中止下载线程（立即停止网络传输）
            should_abort=lambda: task.get("status") in ("paused", "cancelled"),
            headers=sniffer_headers,
        )

        try:
            failed = await asyncio.to_thread(media_downloader.download)
        except DownloadInterrupted:
            # 任务暂停/取消：未完成文件复位为待下载，恢复时自动重新下载
            item["status"] = "pending"
            item["completed"] = 0
            self._save()
            self.emit_snapshot()
            return

        final_path = Path(file_download_path) / truncate_filename(filename)
        if failed:
            item["status"] = "failed"
            task["failed"] = task.get("failed", 0) + 1
        elif not final_path.exists():
            # 兜底校验：下载器报告成功但文件未落盘（离线跳过/异常路径）→ 记为失败，
            # 防止"648/649 完成、实际只有几张图"的假完成问题
            logging.warning("下载器返回成功但文件未落盘: %s", final_path)
            item["status"] = "failed"
            task["failed"] = task.get("failed", 0) + 1
        else:
            item["status"] = "completed"
            item["completed"] = 100
            task["done"] = task.get("done", 0) + 1
            item["_final_path"] = str(final_path)  # 持久化最终路径（续传时校验本地文件是否存在）
            _add_history_entry({
                "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                "filename": filename,
                "path": str(final_path),
                "size": item.get("size"),
                "album": task.get("album") or "下载",
                "time": datetime.now().isoformat(timespec="seconds"),
            })

        # 通知前端单文件完成（底部进度 tab + 下载管理器联动）
        emit({
            "event": "file_complete",
            "filename": filename,
            "success": not failed,
            "size": size,
            "task_id": task_id,
        })

        self._save()
        self.emit_snapshot()

    def _do_shutdown(self) -> None:
        """全部下载完成后关机（Windows）。"""
        try:
            if sys.platform.startswith("win"):
                os.system("shutdown /s /t 60")
                emit({"event": "log", "type": "关机", "message": "所有任务已完成，60 秒后关机"})
            else:
                emit({"event": "log", "type": "关机", "message": "当前系统不支持自动关机"})
        except Exception as exc:
            logging.warning("执行关机命令失败: %s", exc)

    async def _run_download_worker(self, item: dict, sync_fn) -> tuple[bool, str] | None:
        """线程池执行同步下载函数，统一处理暂停/取消与未捕获异常。

        返回 (success, final_path)；返回 None 表示任务暂停/取消（调用方直接 return）。
        """
        try:
            return await asyncio.to_thread(sync_fn)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return None
        except Exception as exc:
            logging.exception("下载线程异常: %s", exc)
            return (False, "")

    async def _finish_download_item(
        self,
        task: dict,
        item: dict,
        task_id: str,
        *,
        success: bool,
        final_path: str,
        default_name: str = "",
    ) -> None:
        """下载条目统一收尾：completed/failed 计数 + 历史记录 + file_complete 事件。

        站点方法在线程函数内设置 item["_final_name"]（实际落盘名）与
        item["_skip_history"]（跳过重复等场景不记历史、file_complete 标 skipped）。
        """
        final_name = item.pop("_final_name", default_name)
        skip_history = item.pop("_skip_history", False)
        if success:
            item["status"] = "completed"
            item["completed"] = 100
            task["done"] = task.get("done", 0) + 1
            if not skip_history and final_path:
                _add_history_entry({
                    "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                    "filename": final_name,
                    "path": final_path,
                    "size": item.get("size"),
                    "album": task.get("album") or "下载",
                    "time": datetime.now().isoformat(timespec="seconds"),
                })
        else:
            item["status"] = "failed"
            task["failed"] = task.get("failed", 0) + 1

        emit({
            "event": "file_complete",
            "filename": final_name,
            "success": success,
            "skipped": bool(skip_history),
            "size": item.get("size"),
            "task_id": task_id,
        })
        self._save()
        self.emit_snapshot()

    async def _hls_task_download(
        self,
        task: dict,
        item: dict,
        task_id: str,
        album_path: str,
        options: dict,
    ) -> None:
        """流媒体任务：分片落盘下载（可断点续传）→ 拼接合并为 MP4。

        与普通文件下载的差异：进度单位是「分片数」（一个视频通常几百个分片），
        暂停时立刻停下并**保留已下分片**，下次「继续」直接从断点续传，
        不必整片重下。分片与续传状态都放在 cache/hls_parts/<task_id>/。
        """
        hls_url = str(item.get("hls_url") or "").strip()
        if not hls_url.startswith("http"):
            item["status"] = "failed"
            item["error"] = "流媒体地址缺失（任务条目未带 hls_url）"
            task["failed"] = task.get("failed", 0) + 1
            self._save()
            self.emit_snapshot()
            return

        filename = _apply_rename_map(options, item, item.get("filename") or "stream.mp4")
        final_path = str(Path(album_path) / truncate_filename(filename))
        item["_final_path"] = final_path
        item["_final_name"] = Path(final_path).name
        referer = str(options.get("hls_referer") or item.get("item_page") or "")
        mute = bool(options.get("hls_mute"))
        task_dir = _web_hls_task_dir(task_id)              # noqa: F821（包加载器注入）

        def _stop_check() -> bool:
            # 暂停/取消：分片循环在每个批次边界查一次，立刻收手保留断点
            return task.get("status") in ("paused", "cancelled")

        def _progress_cb(done: int, total: int, phase: str, extra: dict) -> None:
            item["hls_done"] = int(done)
            item["hls_total"] = int(total)
            item["hls_phase"] = phase            # downloading / merging / done
            item["completed_bytes"] = int(extra.get("bytes") or 0)
            item["completed"] = int(done * 100 / total) if total else 0
            self.emit_snapshot()                 # 快照自带 0.5s 防抖，不会刷爆 IPC

        def _log_cb(msg: str) -> None:
            emit({"event": "log", "type": "下载", "message": msg})

        ok, message = await asyncio.to_thread(
            web_hls_fetch_segments, hls_url, referer, task_dir, final_path,  # noqa: F821
            mute=mute, stop_check=_stop_check,
            progress_cb=_progress_cb, log_cb=_log_cb,
        )
        if ok:
            with contextlib.suppress(OSError):
                item["size"] = os.path.getsize(final_path)
            item.pop("hls_phase", None)
            await self._finish_download_item(
                task, item, task_id, success=True, final_path=final_path)
            return
        # 暂停/取消：条目回到 pending，分片与 state.json 原样保留（这就是断点）
        if message == "__paused__":              # = webcapture.WEB_HLS_PAUSED
            item["status"] = "pending"
            item["completed"] = 0
            self._save()
            self.emit_snapshot()
            return
        item["error"] = message or "流媒体下载失败"
        await self._finish_download_item(
            task, item, task_id, success=False, final_path="")

    async def _exhentai_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单张 ExHentai 图片：重新解析直链（keystamp 时效）+ 节流流式下载。

        目录组织：下载根目录/画师名/画廊标题/图片文件（与 Pawchive 命名风格一致）。
        """
        item_page = item.get("item_page", "")
        filename = item.get("filename") or f"page_{item.get('_idx', 0):04d}.webp"
        options = task.get("options", {})
        # 应用改名弹窗回传的新文件名（手动改名后重新下载）
        filename = _apply_rename_map(options, item, filename)

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        def _open(attempt: int):
            """站点钩子：重新解析图片页拿直链并打开响应（keystamp 时效签名会过期）。

            重试策略（对应原站"图片加载失败点击刷新"）：第 1 次正常解析；后续重试走
            原站 reload broken image（?nl=token 强制换 H@H 节点，分辨率通常更低）。
            """
            page_url_eff = item_page
            if attempt > 0:
                if attempt == 1:
                    live_manager.update_log(
                        event="图片下载失败",
                        details=f"{filename}（尝试原站 reload broken image 兜底，请求更低分辨率版本）",
                    )
                try:
                    page_url_eff = _exhentai_image_page_with_nl(item_page)
                except Exception:
                    page_url_eff = item_page
            page_resp = _exhentai_fetch(page_url_eff)
            page_soup = BeautifulSoup(page_resp.text, "html.parser")
            img = page_soup.select_one("#img")
            download_link = (img.get("src") or "") if img else ""
            if not download_link.startswith("http"):
                raise PermissionError("无法解析图片直链（登录可能已失效）")
            _exhentai_throttle()
            headers = dict(_exhentai_session.headers)
            cookie = _exhentai_cookie_str()
            if cookie:
                headers["Cookie"] = cookie
            headers["Referer"] = item_page  # hath 服务器校验 Referer
            resp = _exhentai_session.get(
                download_link, stream=True, timeout=60, headers=headers,
            )
            resp.raise_for_status()
            return resp

        def _validate(final_path) -> None:
            # 校验文件头：H@H 节点故障时会返回错误页/截断内容，视为失败走 nl 重试
            if not _is_valid_cache_file(final_path):
                final_path.unlink(missing_ok=True)
                raise IOError("下载内容不是有效图片（H@H 节点故障，将换节点重试）")

        # 目录：画师名/"YYYY-MM-画廊标题"（自定义模板 exhentai_folder_template 优先）
        post_title = item.get("post_title") or ""
        template = (options.get("exhentai_folder_template") or "").strip()
        if template:
            sub = _render_folder_template(
                template, item.get("post_date") or "", post_title, item.get("post_id") or "",
            )
        elif post_title:
            g_date = (item.get("post_date") or "")[:7]
            g_title = sanitize_directory_name(post_title)
            sub = f"{g_date}-{g_title}" if g_date else g_title
        else:
            sub = ""
        gallery_dir = str(Path(album_path) / sub) if sub else album_path
        Path(gallery_dir).mkdir(parents=True, exist_ok=True)

        # 跳过重复项目（skip_duplicates）：同名同大小跳过 / 重名按改名规则
        final_name, dup_action = _resolve_duplicate(
            gallery_dir, filename, item.get("size"), options,
        )
        if dup_action == "skip":
            live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
            item["_final_path"] = str(Path(gallery_dir) / truncate_filename(final_name))
            item["_final_name"] = final_name
            result = (True, str(Path(gallery_dir) / truncate_filename(final_name)))
        elif dup_action == "prompt":
            existing = Path(gallery_dir) / truncate_filename(final_name)
            live_manager.update_log(event="重名待改名", details=f"{final_name}（已存在同名但大小不同的文件，等待手动改名）")
            emit({
                "event": "download_rename_prompt",
                "filename": final_name,
                "path": str(gallery_dir),
                "existing_size": existing.stat().st_size if existing.exists() else None,
                "new_size": item.get("size"),
                "item": dict(item),
                "url": task.get("url", ""),
                "album": task.get("album") or "",
            })
            item["_final_name"] = final_name
            item["_skip_history"] = True
            result = (True, "")
        else:
            final_name = final_name if dup_action == "renamed" else _unique_download_filename(gallery_dir, filename)
            final_path = Path(gallery_dir) / truncate_filename(final_name)

            def _download() -> tuple[bool, str]:
                try:
                    # 至少保证 1 次正常 + 1 次 reload 兜底（全部尝试失败才认定下载失败）
                    size, _md5 = _stream_to_file(
                        _exhentai_session, "", final_path,
                        final_name=final_name, task=task, task_id=task_id,
                        internal_task=internal_task, live_manager=live_manager,
                        max_retries=max(2, max(1, max_retries)),
                        open_response=_open, validate=_validate,
                        log_label="ExHentai 图片",
                    )
                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    item.pop("error", None)  # 成功：清除之前失败尝试留下的错误信息
                    return True, str(final_path)
                except (requests.RequestException, PermissionError, OSError) as exc:
                    item["error"] = str(exc) or exc.__class__.__name__
                    live_manager.update_log(
                        event="下载失败",
                        details=f"{filename}（含 reload 兜底多次尝试全部失败）",
                    )
                    # 清理残留的半截文件（避免下次误判"已存在同名文件"）
                    try:
                        final_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return False, ""

            result = await self._run_download_worker(item, _download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=filename,
        )

    async def _twitter_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 Twitter 媒体文件：直链（pbs/video.twimg.com）+ 代理流式下载。

        目录组织：下载根目录/博主名/图片|视频（媒体类型分类），
        文件名：发帖日期_帖子内容_序号.ext。
        """
        filename = item.get("filename") or f"twitter_{int(time.time())}.jpg"
        media_url = item.get("media_url") or ""

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        # 应用改名弹窗回传的新文件名（手动改名后重新下载）
        options = task.get("options", {})
        filename = _apply_rename_map(options, item, filename)

        # 跳过重复项目（skip_duplicates）：先 HEAD 预取大小，再对比本地同名文件
        expected_size = None
        if media_url.startswith("http"):
            expected_size = await asyncio.to_thread(_twitter_head_size, media_url)
        sub = _twitter_subfolder(item, options)
        file_dir = album_path if not sub else str(Path(album_path) / sub)
        filename, dup_action = _resolve_duplicate(file_dir, filename, expected_size, options)
        if dup_action == "skip":
            live_manager.update_log(event="跳过重复", details=f"{filename}（已存在相同大小的文件）")
            item["status"] = "completed"
            item["completed"] = 100
            item["_final_path"] = str(Path(file_dir) / truncate_filename(filename))
            task["done"] = task.get("done", 0) + 1
            emit({"event": "file_complete", "filename": filename, "success": True,
                  "skipped": True, "size": expected_size, "task_id": task_id})
            self._save()
            self.emit_snapshot()
            return
        if dup_action == "prompt":
            live_manager.update_log(event="重名待改名", details=f"{filename}（已存在同名但大小不同的文件，等待手动改名）")
            item["status"] = "completed"
            item["completed"] = 100
            task["done"] = task.get("done", 0) + 1
            existing_path = Path(file_dir) / truncate_filename(filename)
            emit({
                "event": "download_rename_prompt",
                "filename": filename,
                "path": str(file_dir),
                "existing_size": existing_path.stat().st_size if existing_path.exists() else None,
                "new_size": expected_size,
                "item": dict(item),
                "url": task.get("url", ""),
                "album": task.get("album") or "",
            })
            emit({"event": "file_complete", "filename": filename, "success": True,
                  "skipped": True, "task_id": task_id})
            self._save()
            self.emit_snapshot()
            return

        def _download() -> tuple[bool, str]:
            """同步执行：直链下载（带节流和重试）。"""
            if not media_url.startswith("http"):
                raise PermissionError("缺少媒体直链")

            # 1. 目录：按 twitter_subfolder 规则建子文件夹
            options = task.get("options", {})
            sub = _twitter_subfolder(item, options)
            file_dir = album_path if not sub else str(Path(album_path) / sub)
            if sub:
                Path(file_dir).mkdir(parents=True, exist_ok=True)

            # 2. 唯一文件名 + 流式下载（直链永久有效，走代理）
            final_name = _unique_download_filename(file_dir, filename)
            final_path = Path(file_dir) / truncate_filename(final_name)

            size, md5_hex = _stream_to_file(
                _twitter_session, media_url, final_path,
                final_name=final_name, task=task, task_id=task_id,
                internal_task=internal_task, live_manager=live_manager,
                max_retries=max_retries,
                headers={"Referer": TWITTER_HOST + "/"},
                timeout=60, throttle=_twitter_throttle_download,
                log_label="Twitter 媒体",
            )

            item["_final_path"] = str(final_path)
            item["_final_name"] = final_name
            item["size"] = size or None
            item["_md5"] = md5_hex  # MD5 查重（保留最早发布）用
            return True, str(final_path)

        result = await self._run_download_worker(item, _download)
        if result is None:
            return
        success, final_path = result

        final_name = item.pop("_final_name", filename)
        md5_hex = item.pop("_md5", "")
        if success and md5_hex and task.get("options", {}).get("twitter_md5_dedup", True):
            dedup = _twitter_md5_dedup(album_path, final_path, md5_hex, item)
            if dedup["action"] == "skip":
                # 目录里已有更早（或同级）发布的同内容副本，刚下载的重复文件已删除
                dup_name = Path(dedup["dup_path"]).name if dedup["dup_path"] else ""
                date_hint = f"（{dedup['dup_date']}）" if dedup["dup_date"] else ""
                live_manager.update_log(
                    event="MD5查重跳过",
                    details=(f"{filename} 与已保留的 {dup_name} 内容相同，"
                             f"重复副本已删除（保留最早发布{date_hint}）"))
                item["status"] = "completed"
                item["completed"] = 100
                # 指向保留下来的那份副本（当前重复文件已删除）
                if dedup["dup_path"]:
                    item["_final_path"] = dedup["dup_path"]
                task["done"] = task.get("done", 0) + 1
                emit({"event": "file_complete", "filename": filename, "success": True,
                      "skipped": True, "task_id": task_id})
                self._save()
                self.emit_snapshot()
                return
            if dedup["action"] == "replace":
                # 当前条目发布更早：目录里较晚发布的同内容副本已被删除，保留本文件
                dup_name = Path(dedup["dup_path"]).name if dedup["dup_path"] else ""
                live_manager.update_log(
                    event="MD5查重",
                    details=(f"删除较晚发布的重复文件 {dup_name}，"
                             f"保留最早发布（{item.get('post_date') or '未知日期'}）的 {filename}"))
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=final_name,
        )

    async def _pixiv_fetch_binary(self, url: str) -> bytes:
        """下载 Pixiv 图片二进制（i.pximg.net 必须带 Referer，代理走会话配置）。"""
        def _get():
            r = _pixiv_session.get(url, timeout=60,
                                   headers={"Referer": "https://www.pixiv.net/"})
            r.raise_for_status()
            return r.content
        return await asyncio.to_thread(_get)


    async def _pixiv_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 Pixiv 作品：i.pximg.net 直链（必须带 Referer）+ 代理流式下载。

        - 单作品条目（解析时已带 media_url）：直接下载全部页面（含动图 zip）；
        - 用户主页条目（media_url 为空）：按 illust_id 现场解析原图直链再下载，
          一个条目 = 一件作品，多页全部下载完成后才算完成（task done 计数不变）。
        目录：下载根目录/作者名/YYYY-MM-作品名/（subfolder 在解析时已生成）。
        """
        options = task.get("options", {})
        sub = item.get("subfolder") or ""
        file_dir = str(Path(album_path) / sub) if sub else album_path
        illust_id = str(item.get("illust_id") or "")
        title = item.get("post_title") or illust_id or "pixiv"

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        # ---------- 1. 解析直链：单作品条目直接用；用户主页条目现场解析 ----------
        # 小说条目：txt（纯文本）或 docx（python-docx 真文档：封面+正文插图原位嵌入）
        novel_id = str(item.get("novel_id") or "")
        if item.get("kind") == "novel" and novel_id:
            item["status"] = "downloading"
            self._save()
            novel_fmt = (item.get("pixiv_novel_fmt") or "txt").lower()
            live_manager.update_log(event="下载中", details=f"{title}（小说 {novel_fmt.upper()}）")

            # 拉 web 详情：正文 + 封面 + 插图映射（/v1/novel/text 已 404，直接 web；
            # 封面字段是 coverUrl——此前取 d["url"] 恒 None → 封面从未下载成功）
            novel_text = ""
            cover_bytes = b""
            d: dict = {}
            embedded: dict = {}
            try:
                d = await asyncio.to_thread(
                    _pixiv_api_get, f"/ajax/novel/{novel_id}")  # noqa: F821
                novel_text = _pixiv_novel_html_to_text(d.get("content") or "")  # noqa: F821
                cover_url = d.get("coverUrl") or d.get("url") or ""
                if cover_url:
                    try:
                        cover_bytes = await self._pixiv_fetch_binary(cover_url)  # noqa: F821
                    except Exception:
                        cover_bytes = b""
            except Exception as exc:
                logging.warning("Pixiv 小说 web 详情失败 %s: %s", novel_id, exc)
            if novel_fmt in ("docx", "doc", "word"):
                # 正文插图标记 → 直链（[uploadedimage:N] 直查映射 + [pixivimage:ID-p] 解析）
                try:
                    embedded = await _pixiv_novel_embedded_images(d)  # noqa: F821
                except Exception:
                    embedded = {}
                novel_fmt = "docx"
            if not novel_text:
                raise PermissionError("小说正文为空")
            try:
                Path(file_dir).mkdir(parents=True, exist_ok=True)
                fname = item.get("filename") or f"{sanitize_directory_name(title)}.txt"
                fname = _apply_rename_map(options, item, fname)
                if novel_fmt == "docx" and not fname.lower().endswith(".docx"):
                    fname = fname.rsplit(".", 1)[0] + ".docx"
                # 跳过重复（skip_duplicates）：同名同大小跳过 / 重名按改名规则
                fname, dup_action = _resolve_duplicate(file_dir, fname, None, options)
                if dup_action == "skip":
                    item["status"] = "completed"
                    item["completed"] = 100
                    item["filename"] = fname
                    item["_final_path"] = str(Path(file_dir) / fname)
                    task["done"] = task.get("done", 0) + 1
                    self._save()
                    self.emit_snapshot()
                    live_manager.update_log(event="跳过重复", details=f"{fname}（已存在）")
                    emit({"event": "file_complete", "filename": fname,
                          "success": True, "skipped": True, "task_id": task_id})
                    return
                fpath = str(Path(file_dir) / fname)

                if novel_fmt == "docx":
                    # 真 Word 文档（python-docx）：封面 + 正文插图按标记原位嵌入
                    import io
                    from docx import Document
                    from docx.shared import Inches
                    doc = Document()
                    doc.add_heading(title, level=0)
                    meta_line = f"作者：{item.get('artist') or ''}"
                    if item.get("post_date"):
                        meta_line += f"　发布：{item['post_date']}"
                    doc.add_paragraph(meta_line)
                    # 预取插图二进制（封面 + 全部标记位）
                    img_bins: dict[str, bytes] = {}
                    if cover_bytes:
                        img_bins["__cover__"] = cover_bytes
                    for marker, url in embedded.items():
                        try:
                            img_bins[marker] = await self._pixiv_fetch_binary(url)  # noqa: F821
                        except Exception:
                            continue

                    def _add_img(key: str) -> bool:
                        data = img_bins.get(key)
                        if not data:
                            return False
                        try:
                            doc.add_picture(io.BytesIO(data), width=Inches(5.8))
                            return True
                        except Exception:
                            return False

                    if cover_bytes:
                        _add_img("__cover__")
                    # 正文逐行写入；插图标记原位落图（一行多标记按序拆分）
                    for line in novel_text.split("\n"):
                        segs = _NOVEL_MARKER_RE.split(line)  # noqa: F821
                        for si, seg in enumerate(segs):
                            if si % 2 == 1:
                                _add_img(f"[{seg}]")
                            elif seg.strip():
                                doc.add_paragraph(seg)
                    tmp = fpath + ".part"
                    doc.save(tmp)
                    os.replace(tmp, fpath)
                else:
                    tmp = fpath + ".part"
                    Path(tmp).write_text(novel_text, encoding="utf-8")
                    os.replace(tmp, fpath)
                item["status"] = "completed"
                item["completed"] = 100
                item["filename"] = Path(fpath).name
                item["_final_path"] = fpath
                task["done"] = task.get("done", 0) + 1
                _add_history_entry({
                    "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                    "filename": Path(fpath).name,
                    "path": fpath,
                    "size": None,
                    "album": task.get("album") or "下载",
                    "time": datetime.now().isoformat(timespec="seconds"),
                })
                self._save()
                self.emit_snapshot()
                live_manager.update_log(event="完成", details=f"{title}（{novel_fmt.upper()} 已保存）")
                emit({"event": "file_complete", "filename": Path(fpath).name,
                      "success": True, "task_id": task_id})
            except Exception as exc:
                logging.warning("Pixiv 小说下载失败 %s: %s", novel_id, exc)
                live_manager.update_log(event="失败", details=f"{title}（{exc}）")
                item["status"] = "failed"
                task["failed"] = task.get("failed", 0) + 1
                self._save()
                self.emit_snapshot()
                emit({"event": "file_complete", "filename": title,
                      "success": False, "task_id": task_id})
            return

        pages: list[tuple[str, str]] = []  # (文件名, 原图直链)
        media_url = item.get("media_url") or ""
        if media_url.startswith("http"):
            fname = _apply_rename_map(options, item, item.get("filename") or "")
            pages.append((fname or _pixiv_filename(title, 0, 1, media_url), media_url))
        else:
            try:
                if item.get("ugoira"):
                    ugoira = await asyncio.to_thread(
                        _pixiv_api_get, f"/ajax/illust/{illust_id}/ugoira_meta")
                    zip_url = ugoira.get("originalSrc") or ""
                    if zip_url:
                        pages.append((_pixiv_filename(title + "_动图", 0, 1, zip_url), zip_url))
                if not pages:
                    detail = await asyncio.to_thread(_pixiv_api_get, f"/ajax/illust/{illust_id}")
                    page_count = int(detail.get("pageCount") or 1)
                    if page_count > 1:
                        page_list = await asyncio.to_thread(
                            _pixiv_api_get, f"/ajax/illust/{illust_id}/pages")
                        for i, p in enumerate(page_list or []):
                            u = (p.get("urls") or {}).get("original") or ""
                            if u:
                                pages.append((_pixiv_filename(title, i, page_count, u), u))
                    else:
                        u = (detail.get("urls") or {}).get("original") or ""
                        if u:
                            pages.append((_pixiv_filename(title, 0, 1, u), u))
            except Exception as exc:
                logging.warning("Pixiv 直链解析失败 %s: %s", illust_id, exc)

        if not pages:
            live_manager.update_log(event="解析失败", details=f"{title}（无法获取原图直链，请检查登录状态与代理）")
            item["status"] = "failed"
            task["failed"] = task.get("failed", 0) + 1
            emit({"event": "file_complete", "filename": title, "success": False, "task_id": task_id})
            self._save()
            self.emit_snapshot()
            return

        # ---------- 2. 逐页下载（每页独立去重/重试/原子写入） ----------
        results: list[tuple[str, str, bool]] = []  # (最终文件名, 路径, 是否成功)

        def _download_page(fname: str, furl: str) -> tuple[str, str, bool]:
            """同步执行：单页原图下载（重试退避在 _stream_to_file 内）。"""
            try:
                Path(file_dir).mkdir(parents=True, exist_ok=True)
                final_name, dup_action = _resolve_duplicate(file_dir, fname, None, options)
                if dup_action == "skip":
                    live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在）")
                    return final_name, str(Path(file_dir) / truncate_filename(final_name)), True
                if dup_action == "prompt":
                    live_manager.update_log(event="重名待改名", details=f"{final_name}（等待手动改名）")
                    return final_name, "", True
                final_path = Path(file_dir) / truncate_filename(final_name)

                size, _md5 = _stream_to_file(
                    _pixiv_session, furl, final_path,
                    final_name=final_name, task=task, task_id=task_id,
                    internal_task=internal_task, live_manager=live_manager,
                    max_retries=max(1, max_retries),
                    headers={"Referer": f"{PIXIV_BASE}/"},
                    timeout=60, throttle=_pixiv_throttle,
                    log_label="Pixiv 图片",
                )
                return final_name, str(final_path), True

            except InterruptedError:
                raise
            except (requests.RequestException, PermissionError, OSError) as exc:
                logging.warning(
                    "Pixiv 图片下载失败 %s: %s", fname, exc)
                return fname, "", False

        interrupted = False
        for fname, furl in pages:
            try:
                results.append(await asyncio.to_thread(_download_page, fname, furl))
            except InterruptedError:
                interrupted = True
                break
            except Exception as exc:
                logging.exception("Pixiv 下载出错: %s", exc)
                results.append((fname, "", False))

        if interrupted:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return

        # ---------- 3. 汇总：全部页面成功才算条目完成 ----------
        ok_count = sum(1 for _, _, ok in results if ok)
        last_name, last_path, _ = results[-1]
        if ok_count == len(results):
            item["status"] = "completed"
            item["completed"] = 100
            item["size"] = None
            task["done"] = task.get("done", 0) + 1
            # 每页写一条历史记录（本地收藏/最近下载数据源）
            for final_name, final_path, ok in results:
                if ok and final_path:
                    _add_history_entry({
                        "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                        "filename": final_name,
                        "path": final_path,
                        "size": None,
                        "album": task.get("album") or "下载",
                        "time": datetime.now().isoformat(timespec="seconds"),
                    })
        else:
            item["status"] = "failed"
            task["failed"] = task.get("failed", 0) + 1

        for final_name, _, ok in results:
            emit({
                "event": "file_complete",
                "filename": final_name,
                "success": ok,
                "size": None,
                "task_id": task_id,
            })
        if item.get("_final_path") is None and last_path:
            item["_final_path"] = last_path
        self._save()
        self.emit_snapshot()

    async def _iwara_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 Iwara 视频：重新解析最高画质源（直链 expires 会过期）+ 流式下载。

        目录组织：下载根目录/作者名/（可选月份子文件夹）视频标题.mp4。
        """
        filename = item.get("filename") or f"iwara_{item.get('video_id') or int(time.time())}.mp4"
        video_id = item.get("video_id") or ""

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        # 应用改名弹窗回传的新文件名（手动改名后重新下载）
        options = task.get("options", {})
        filename = _apply_rename_map(options, item, filename)

        # 目录：下载根目录/作者名/"YYYY-MM-标题"（可自定义模板 iwara_folder_template）
        def _iwara_file_dir() -> str:
            template = (options.get("iwara_folder_template") or "").strip()
            sub = ""
            if template:
                sub = _render_folder_template(
                    template, item.get("post_date") or "",
                    (item.get("post_title") or "").strip(), video_id,
                )
            else:
                parts = []
                date = (item.get("post_date") or "")[:7]  # YYYY-MM
                title = sanitize_directory_name((item.get("post_title") or "").strip())[:60]
                if date and title:
                    parts.append(f"{date}-{title}")
                elif date:
                    parts.append(date)
                sub = str(Path(*parts)) if parts else ""
            return str(Path(album_path) / sub) if sub else album_path

        def _resolve_and_download() -> tuple[bool, str]:
            """同步执行：重新解析最高画质源 + 流式下载（带重试）。

            直链 expires 签名会过期 → 每次尝试都重新解析（站点自身循环），
            单次尝试的节流/打开/进度/原子写入/完整性校验交给 _stream_to_file。
            """
            for attempt in range(max(1, max_retries)):
                try:
                    # 1. 重新解析视频源（fileUrl 的 expires 签名会过期）
                    if video_id:
                        data = _iwara_api_get(f"/video/{video_id}")
                        file_url = data.get("fileUrl") or ""
                    else:
                        file_url = item.get("media_url") or ""
                    download_link, mime = _iwara_resolve_best_url(file_url)
                    if not download_link.startswith("http"):
                        raise PermissionError("无法解析视频源（可能为私有视频或登录已失效）")

                    # 按真实 MIME 调整扩展名
                    ext = _iwara_video_ext(mime)
                    if not filename.lower().endswith(ext):
                        base = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename)
                        eff_name = base + ext
                    else:
                        eff_name = filename

                    file_dir = _iwara_file_dir()
                    Path(file_dir).mkdir(parents=True, exist_ok=True)

                    # 跳过重复项目（skip_duplicates）
                    final_name, dup_action = _resolve_duplicate(file_dir, eff_name, None, options)
                    if dup_action == "skip":
                        live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""
                    if dup_action == "prompt":
                        existing = Path(file_dir) / truncate_filename(final_name)
                        live_manager.update_log(event="重名待改名", details=f"{final_name}（已存在同名但大小不同的文件，等待手动改名）")
                        emit({
                            "event": "download_rename_prompt",
                            "filename": final_name,
                            "path": str(file_dir),
                            "existing_size": existing.stat().st_size if existing.exists() else None,
                            "new_size": None,
                            "item": dict(item),
                            "url": task.get("url", ""),
                            "album": task.get("album") or "",
                        })
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""

                    # 2. 唯一文件名 + 流式下载
                    final_name = final_name if dup_action == "renamed" else _unique_download_filename(file_dir, eff_name)
                    final_path = Path(file_dir) / truncate_filename(final_name)

                    def _open(_attempt: int, _link: str = download_link):
                        """媒体服务器（mikoto.iwara.tv 等）直连不通时用系统代理重试（对齐浏览器行为）。"""
                        try:
                            resp = _iwara_session.get(
                                _link, stream=True, timeout=(15, 60),
                                headers={"Referer": "https://www.iwara.tv/"},
                            )
                            resp.raise_for_status()
                            return resp
                        except requests.RequestException as dexc:
                            resp and resp.close()
                            for proxy in _system_proxies():
                                try:
                                    logging.info("媒体直连失败(%s)，尝试系统代理: %s", dexc, proxy)
                                    resp = _iwara_session.get(
                                        _link, stream=True, timeout=(15, 120),
                                        headers={"Referer": "https://www.iwara.tv/"},
                                        proxies={"http": proxy, "https": proxy},
                                    )
                                    resp.raise_for_status()
                                    logging.info("媒体下载经系统代理成功: %s", proxy)
                                    return resp
                                except requests.RequestException:
                                    resp and resp.close()
                            raise PermissionError(
                                f"媒体服务器无法连接（直连与系统代理都失败）: {dexc}"
                            )

                    size, _md5 = _stream_to_file(
                        _iwara_session, "", final_path,
                        final_name=final_name, task=task, task_id=task_id,
                        internal_task=internal_task, live_manager=live_manager,
                        max_retries=1, throttle=_iwara_throttle,
                        open_response=_open,
                        log_label="Iwara 视频",
                    )
                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    return True, str(final_path)

                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning(
                        "Iwara 视频下载失败(第 %d 次) %s: %s",
                        attempt + 1, filename, exc,
                    )
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        result = await self._run_download_worker(item, _resolve_and_download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=filename,
        )

    async def _hanime_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 Hanime1 视频：重新解析最高画质直链（secure 签名会过期）+ 流式下载。

        目录组织：下载根目录/上传者/（可选 YYYY-MM 子文件夹）视频标题.mp4。
        """
        filename = item.get("filename") or f"hanime_{item.get('video_id') or int(time.time())}.mp4"
        video_id = item.get("video_id") or ""

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        # 应用改名弹窗回传的新文件名（手动改名后重新下载）
        options = task.get("options", {})
        filename = _apply_rename_map(options, item, filename)

        # 目录：下载根目录/"YYYY-MM-上传者"（日期并入文件夹名，减少嵌套层级）
        def _hanime_file_dir() -> str:
            parts = []
            artist = sanitize_directory_name((item.get("artist") or "").strip())
            date = (item.get("post_date") or "")[:7]  # YYYY-MM
            if date and artist:
                parts.append(f"{date}-{artist}")
            elif artist:
                parts.append(artist)
            elif date:
                parts.append(date)
            sub = str(Path(*parts)) if parts else ""
            return str(Path(album_path) / sub) if sub else album_path

        def _resolve_and_download() -> tuple[bool, str]:
            """同步执行：重新解析最高画质直链 + 流式下载（带重试）。

            secure 签名会过期 → 每次尝试都重新解析（站点自身循环），
            单次尝试的打开/进度/原子写入/完整性校验交给 _stream_to_file。
            """
            for attempt in range(max(1, max_retries)):
                try:
                    # 1. 重新解析视频源（secure 签名会过期）
                    soup = _hanime_soup("/watch", {"v": video_id}) if video_id else None
                    sources = _hanime_parse_detail(soup, video_id)["sources"] if soup else []
                    if not sources:
                        download_link = item.get("media_url") or ""
                    else:
                        download_link = _hanime_best_source(sources).get("url") or ""
                    if not download_link.startswith("http"):
                        raise PermissionError("无法解析视频源（视频可能已下架）")

                    file_dir = _hanime_file_dir()
                    Path(file_dir).mkdir(parents=True, exist_ok=True)

                    # 跳过重复项目（skip_duplicates）
                    final_name, dup_action = _resolve_duplicate(file_dir, filename, None, options)
                    if dup_action == "skip":
                        live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""
                    if dup_action == "prompt":
                        existing = Path(file_dir) / truncate_filename(final_name)
                        live_manager.update_log(event="重名待改名", details=f"{final_name}（已存在同名但大小不同的文件，等待手动改名）")
                        emit({
                            "event": "download_rename_prompt",
                            "filename": final_name,
                            "path": str(file_dir),
                            "existing_size": existing.stat().st_size if existing.exists() else None,
                            "new_size": None,
                            "item": dict(item),
                            "url": task.get("url", ""),
                            "album": task.get("album") or "",
                        })
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""

                    # 2. 唯一文件名 + 流式下载
                    final_name = final_name if dup_action == "renamed" else _unique_download_filename(file_dir, filename)
                    final_path = Path(file_dir) / truncate_filename(final_name)

                    def _open(_attempt: int, _link: str = download_link):
                        resp = _hanime_session.get(
                            _link, stream=True, timeout=120,
                            headers={"Referer": f"{HANIME_BASE}/"},
                        )
                        resp.raise_for_status()
                        return resp

                    size, _md5 = _stream_to_file(
                        _hanime_session, "", final_path,
                        final_name=final_name, task=task, task_id=task_id,
                        internal_task=internal_task, live_manager=live_manager,
                        max_retries=1, throttle=_hanime_throttle,
                        open_response=_open, log_label="Hanime1 视频",
                    )
                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    return True, str(final_path)

                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning(
                        "Hanime1 视频下载失败(第 %d 次) %s: %s",
                        attempt + 1, filename, exc,
                    )
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        result = await self._run_download_worker(item, _resolve_and_download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=filename,
        )

    async def _fc2_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 FC2 视频：mid 签名会过期 → 下载时重新解析播放源（ae 流程）+ 流式下载。

        目录组织：下载根/{上传者}/视频/文件；mp4 直链（type 1），HLS（type 2）报错提示。
        """
        filename = item.get("filename") or f"fc2_{item.get('video_id') or int(time.time())}.mp4"
        options = task.get("options", {})
        filename = _apply_rename_map(options, item, filename)

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        def _fc2_file_dir() -> str:
            artist = sanitize_directory_name((item.get("artist") or "").strip()) or "FC2"
            return str(Path(album_path) / artist / "视频")

        def _resolve_and_download() -> tuple[bool, str]:
            for attempt in range(max(1, max_retries)):
                try:
                    vid = str(item.get("video_id") or "")
                    info = fc2_download_info(vid)  # noqa: F821 —— site_fc2 注入（下载时新签名）
                    if not info["url"].startswith("http"):
                        raise PermissionError("FC2 无可用播放源")

                    file_dir = _fc2_file_dir()
                    Path(file_dir).mkdir(parents=True, exist_ok=True)


                    final_name, dup_action = _resolve_duplicate(file_dir, filename, None, options)
                    if dup_action == "skip":
                        live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""
                    final_name = final_name if dup_action == "renamed" else _unique_download_filename(file_dir, filename)
                    final_path = Path(file_dir) / truncate_filename(final_name)

                    # FC2 type 2 (HLS): m3u8 -> segment download -> concat TS -> save as .mp4
                    if info.get('type') == '2' and info['url'].startswith('http'):
                        try:
                            m3u8_resp = _fc2_session.get(
                                info['url'], timeout=60,
                                headers={'Referer': 'https://video.fc2.com/'})
                            m3u8_resp.raise_for_status()
                            seg_urls = [ln.strip() for ln in m3u8_resp.text.splitlines()
                                        if ln.strip() and not ln.strip().startswith('#')]
                            if not seg_urls:
                                raise PermissionError('FC2 HLS no segments')
                            from urllib.parse import urljoin
                            seg_urls = [u if u.startswith('http') else
                                        ('https:' + u if u.startswith('//') else urljoin(info['url'], u))
                                        for u in seg_urls]
                            live_manager.set_task_info(internal_task, final_name)
                            part = final_path.with_suffix(final_path.suffix + '.hls.part')
                            total_segs = len(seg_urls)
                            with open(part, 'wb') as fh:
                                for si, seg in enumerate(seg_urls, 1):
                                    if task.get('status') in ('paused', 'cancelled'):
                                        raise InterruptedError()
                                    sr = None
                                    for st in range(3):
                                        try:
                                            sr = _fc2_session.get(seg, timeout=60, stream=True,
                                                                  headers={'Referer': 'https://video.fc2.com/'})
                                            sr.raise_for_status()
                                            break
                                        except requests.RequestException:
                                            if st < 2:
                                                time.sleep(2)
                                    if sr is None:
                                        raise PermissionError(f'HLS seg {si}/{total_segs} failed')
                                    for chunk in sr.iter_content(65536):
                                        fh.write(chunk)
                                    live_manager.update_task(internal_task, round(100.0 * si / total_segs, 1))
                            os.replace(part, final_path)
                            _hls_remux_mp4(final_path)
                            live_manager.update_log(event='HLS download done',
                                                    details=f'{final_name} ({total_segs} segments)')
                            item['_final_path'] = str(final_path)
                            item['_final_name'] = final_name
                            item['size'] = final_path.stat().st_size
                            return True, str(final_path)
                        except InterruptedError:
                            raise
                        except (requests.RequestException, PermissionError, OSError) as hls_exc:
                            logging.warning('FC2 HLS failed, falling to mp4 %s: %s', filename, hls_exc)

                    def _open(_attempt: int, _link: str = info['url']):
                        resp = _fc2_session.get(
                            _link, timeout=120,
                            headers={"Referer": "https://video.fc2.com/"},
                        )
                        resp.raise_for_status()
                        return resp

                    size, _md5 = _stream_to_file(
                        _fc2_session, "", final_path,
                        final_name=final_name, task=task, task_id=task_id,
                        internal_task=internal_task, live_manager=live_manager,
                        max_retries=1, open_response=_open, log_label="FC2 视频",
                    )
                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    return True, str(final_path)
                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:  # noqa: F821
                    logging.warning("FC2 视频下载失败(第 %d 次) %s: %s", attempt + 1, filename, exc)
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        result = await self._run_download_worker(item, _resolve_and_download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=filename,
        )

    async def _xhamster_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 xHamster 视频：重新解密最高画质直链（密文会过期）+ 流式下载。

        目录组织：下载根/{作者名}/{视频|短视频|画廊}/文件（用户指定两级，不再套日期）。
        下载必须带 Referer: jp.xhamster.com（CDN 校验），会话自带代理与登录 cookie。
        """
        filename = item.get("filename") or f"xhamster_{item.get('video_id') or int(time.time())}.mp4"

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        # 应用改名弹窗回传的新文件名（手动改名后重新下载）
        options = task.get("options", {})
        filename = _apply_rename_map(options, item, filename)

        # 目录：{作者名}/{视频|短视频|画廊}/
        def _xh_file_dir() -> str:
            artist = sanitize_directory_name((item.get("artist") or "").strip()) or "xHamster"
            kind = item.get("xh_kind") or item.get("media_type") or "video"
            folder = {"short": "短视频", "gallery": "画廊", "image": "画廊"}.get(kind, "视频")
            return str(Path(album_path) / artist / folder)

        def _resolve_and_download() -> tuple[bool, str]:
            """同步执行：重新解密直链 + 流式下载（带重试）。

            页面密文会过期 → 每次尝试都重新解密（站点自身循环），
            单次尝试的打开/进度/原子写入/完整性校验交给 _stream_to_file。
            """
            for attempt in range(max(1, max_retries)):
                try:
                    # 1. 重新解析（视频密文会过期；画廊取 imgSrc）
                    page = item.get("item_page") or ""
                    kind = item.get("xh_kind") or item.get("media_type") or "video"
                    download_link = item.get("media_url") or ""
                    hls_url = item.get("hls_url") or ""

                    def _xh_abs_url(u: str, base: str = "") -> str:
                        from urllib.parse import urljoin
                        u = (u or "").strip()
                        if u.startswith("//"):
                            u = "https:" + u
                        elif u and not u.startswith("http") and base:
                            u = urljoin(base, u)
                        return u

                    if kind in ("gallery", "image"):
                        init, _ = _xh_fetch(page)
                        gal = _xh_parse_gallery(init or {}, page)
                        for f in gal.get("files") or []:
                            if f.get("item_page") == page or f.get("filename") == filename:
                                download_link = f.get("media_url") or download_link
                                break
                        if not download_link.startswith("http") and (gal.get("files") or []):
                            download_link = gal["files"][0].get("media_url") or ""
                    else:
                        init, _ = _xh_fetch(page)
                        parsed = _xh_parse_detail(init or {}, page)
                        mp4_list = parsed.get("mp4_list") or []
                        # mp4_list 已按画质降序；令牌常 403，真正能下到的最高画质在 HLS
                        download_link = (mp4_list[0].get("url") if mp4_list else "") or download_link
                        hls_url = parsed.get("hls_url") or hls_url
                    download_link = _xh_abs_url(download_link)
                    hls_url = _xh_abs_url(hls_url)
                    if not download_link.startswith("http") and not hls_url.startswith("http"):
                        raise PermissionError("无法解析媒体源（可能已下架、需登录或为好友/私密内容）")

                    file_dir = _xh_file_dir()
                    Path(file_dir).mkdir(parents=True, exist_ok=True)

                    # 跳过重复项目（skip_duplicates）
                    final_name, dup_action = _resolve_duplicate(file_dir, filename, None, options)
                    if dup_action == "skip":
                        live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""
                    if dup_action == "prompt":
                        existing = Path(file_dir) / truncate_filename(final_name)
                        live_manager.update_log(event="重名待改名", details=f"{final_name}（已存在同名但大小不同的文件，等待手动改名）")
                        emit({
                            "event": "download_rename_prompt",
                            "filename": final_name,
                            "path": str(file_dir),
                            "existing_size": existing.stat().st_size if existing.exists() else None,
                            "new_size": None,
                            "item": dict(item),
                            "url": task.get("url", ""),
                            "album": task.get("album") or "",
                        })
                        item["_final_name"] = final_name
                        item["_skip_history"] = True
                        return True, ""

                    # 2. 唯一文件名 + 流式下载（Referer 必须 jp.xhamster.com，否则 CDN 403）
                    final_name = final_name if dup_action == "renamed" else _unique_download_filename(file_dir, filename)
                    final_path = Path(file_dir) / truncate_filename(final_name)

                    def _open(_attempt: int, _link: str = download_link):
                        resp = _xhamster_session.get(
                            _link, stream=True, timeout=120,
                            headers={"Referer": f"{XHAMSTER_BASE}/"},
                        )
                        resp.raise_for_status()
                        return resp

                    def _xh_hls_download(link: str, fpath: Path, fname: str) -> tuple[int, str]:
                        """mp4 直链 403 时的 HLS 回退：master→最高分辨率 variant→分片按序拼接 MPEG-TS。

                        mp4 令牌已死（CDN 403，09-09 播放切 HLS 同根因）；仓内无 ffmpeg，
                        直接拼 TS 流（主流播放器可直接播放，文件名保持 .mp4）。
                        分片级签名过期抛出 → 由外层重试整体重新解析页面取新签名。"""
                        from urllib.parse import urljoin

                        def _get(u: str, **kw):
                            r = _xhamster_session.get(
                                u, timeout=60,
                                headers={"Referer": f"{XHAMSTER_BASE}/"}, **kw)
                            r.raise_for_status()
                            return r

                        best_url, best_score, cur_score = "", (-1, -1), (0, 0)
                        for line in _get(link).text.splitlines():
                            line = line.strip()
                            if line.startswith("#EXT-X-STREAM-INF"):
                                m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
                                bw = re.search(r"BANDWIDTH=(\d+)", line)
                                area = (int(m.group(1)) * int(m.group(2))) if m else 0
                                cur_score = (area, int(bw.group(1)) if bw else 0)
                            elif line and not line.startswith("#"):
                                if cur_score > best_score:
                                    best_score, best_url = cur_score, line
                        if not best_url:
                            raise PermissionError("HLS master 无可用 variant")
                        variant_url = _xh_abs_url(best_url, link)
                        playlist = _get(variant_url).text
                        seg_urls = [l.strip() for l in playlist.splitlines()
                                    if l.strip() and not l.strip().startswith("#")]
                        if not seg_urls:
                            raise PermissionError("HLS variant 无分片")
                        map_m = re.search(r'#EXT-X-MAP:.*?URI="([^"]+)"', playlist)
                        if map_m:
                            seg_urls.insert(0, _xh_abs_url(map_m.group(1), variant_url))

                        live_manager.set_task_info(internal_task, fname)
                        part = fpath.with_name(fpath.name + ".hls.part")
                        md5 = hashlib.md5()
                        done = 0
                        total = len(seg_urls)
                        try:
                            with open(part, "wb") as fh:
                                for i, seg in enumerate(seg_urls, 1):
                                    if task.get("status") in ("paused", "cancelled"):
                                        raise InterruptedError()
                                    seg_url = _xh_abs_url(seg, variant_url)
                                    resp = None
                                    seg_exc: Exception | None = None
                                    for seg_try in range(3):
                                        try:
                                            resp = _get(seg_url, stream=True)
                                            break
                                        except requests.RequestException as exc:
                                            seg_exc = exc
                                            time.sleep(1 + seg_try)
                                    if resp is None:
                                        raise seg_exc or PermissionError(f"HLS 分片失败 {i}/{total}")
                                    for chunk in resp.iter_content(65536):
                                        fh.write(chunk)
                                        md5.update(chunk)
                                        done += len(chunk)
                                    live_manager.update_task(
                                        internal_task, round(100.0 * i / total, 1))
                            os.replace(part, fpath)
                            _hls_remux_mp4(fpath)
                        except InterruptedError:
                            raise
                        except Exception:
                            part.unlink(missing_ok=True)
                            raise
                        return done, md5.hexdigest()

                    last_exc: Exception | None = None
                    size = 0
                    if kind not in ("gallery", "image") and hls_url.startswith("http"):
                        # 默认最高画质：HLS 按 RESOLUTION×BANDWIDTH 取顶档（mp4 令牌已死，先 HLS）
                        try:
                            live_manager.update_log(
                                event="HLS 最高画质",
                                details=f"{final_name} → 分片下载（跳过已失效的 mp4 直链）")
                            size, _md5 = _xh_hls_download(hls_url, final_path, final_name)
                            last_exc = None
                        except InterruptedError:
                            raise
                        except (requests.RequestException, PermissionError, OSError) as hls_exc:
                            last_exc = hls_exc
                            logging.warning("xHamster HLS 失败，尝试 mp4 %s: %s", filename, hls_exc)
                    if not size and download_link.startswith("http"):
                        try:
                            size, _md5 = _stream_to_file(
                                _xhamster_session, "", final_path,
                                final_name=final_name, task=task, task_id=task_id,
                                internal_task=internal_task, live_manager=live_manager,
                                max_retries=1, open_response=_open, log_label="xHamster 视频",
                            )
                            last_exc = None
                        except InterruptedError:
                            raise
                        except (requests.RequestException, PermissionError) as mp4_exc:
                            last_exc = mp4_exc
                            logging.warning("xHamster mp4 直链失败 %s: %s", filename, mp4_exc)
                    if not size:
                        raise last_exc or PermissionError("xHamster 下载失败（HLS/mp4 均不可用）")
                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    return True, str(final_path)

                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning(
                        "xHamster 视频下载失败(第 %d 次) %s: %s",
                        attempt + 1, filename, exc,
                    )
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        result = await self._run_download_worker(item, _resolve_and_download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=filename,
        )

    async def _asmr_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 ASMR 音频/字幕文件（直链永久有效，保留文件夹相对路径）。

        目录组织：下载根目录/RJ号 标题/文件夹路径/文件名（与其他站点逻辑一致）。
        """
        rel = item.get("filename") or f"asmr_{int(time.time())}.mp3"
        download_link = item.get("media_url") or ""

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        options = task.get("options", {})
        # filename 含子路径：逐段清理非法字符，但保留目录分隔
        rel = "/".join(
            re.sub(r'[\\/:*?"<>|]', "_", seg).strip() for seg in rel.replace("\\", "/").split("/")
        ).strip("/")
        final_name = rel.split("/")[-1] or f"asmr_{int(time.time())}.mp3"

        def _resolve_and_download() -> tuple[bool, str]:
            if not download_link.startswith("http"):
                return False, ""
            file_dir = str(Path(album_path) / Path(rel).parent) if "/" in rel or "\\" in rel else album_path
            Path(file_dir).mkdir(parents=True, exist_ok=True)
            # 跳过重复
            _, dup_action = _resolve_duplicate(file_dir, final_name, item.get("size"), options)
            if dup_action == "skip":
                live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
                item["_final_name"] = final_name
                item["_skip_history"] = True
                return True, ""
            # 重试退避/进度/原子写入/完整性校验在 _stream_to_file（同名直接覆盖，原有语义）
            final_path = Path(file_dir) / truncate_filename(final_name)
            try:
                size, _md5 = _stream_to_file(
                    _asmr_session, download_link, final_path,
                    final_name=final_name, task=task, task_id=task_id,
                    internal_task=internal_task, live_manager=live_manager,
                    max_retries=max(1, max_retries), throttle=_asmr_throttle,
                    fallback_size=item.get("size"), log_label="ASMR 文件",
                )
                item["_final_path"] = str(final_path)
                item["_final_name"] = final_name
                item["size"] = size
                return True, str(final_path)
            except (requests.RequestException, PermissionError, OSError):
                return False, ""

        result = await self._run_download_worker(item, _resolve_and_download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=final_name,
        )

    async def _javdb_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 JavDB 图片（封面/预览，直链长期有效，走 javdb 会话代理）。

        目录组织：下载根目录/任务文件夹/番号/文件名（filename 含番号子文件夹）。
        """
        rel = item.get("filename") or f"javdb_{int(time.time())}.jpg"
        download_link = item.get("media_url") or ""

        item["status"] = "downloading"
        self._save()
        self.emit_snapshot()

        live_manager = GuiLiveManager()
        live_manager.task_id = task_id
        internal_task = live_manager.add_task()

        options = task.get("options", {})
        # filename 含子路径：逐段清理非法字符，但保留目录分隔
        rel = "/".join(
            re.sub(r'[\\/:*?"<>|]', "_", seg).strip() for seg in rel.replace("\\", "/").split("/")
        ).strip("/")
        final_name = rel.split("/")[-1] or f"javdb_{int(time.time())}.jpg"

        def _resolve_and_download() -> tuple[bool, str]:
            if not download_link.startswith("http"):
                return False, ""
            file_dir = str(Path(album_path) / Path(rel).parent) if "/" in rel else album_path
            Path(file_dir).mkdir(parents=True, exist_ok=True)
            # 跳过重复
            _, dup_action = _resolve_duplicate(file_dir, final_name, item.get("size"), options)
            if dup_action == "skip":
                live_manager.update_log(event="跳过重复", details=f"{final_name}（已存在相同大小的文件）")
                item["_final_name"] = final_name
                item["_skip_history"] = True
                return True, ""
            # 重试退避/进度/原子写入/完整性校验在 _stream_to_file（同名直接覆盖，原有语义）
            final_path = Path(file_dir) / truncate_filename(final_name)
            try:
                size, _md5 = _stream_to_file(
                    _javdb_session, download_link, final_path,
                    final_name=final_name, task=task, task_id=task_id,
                    internal_task=internal_task, live_manager=live_manager,
                    max_retries=max(1, max_retries), throttle=_javdb_throttle,
                    headers={"Referer": JAVDB_BASE + "/"},
                    fallback_size=item.get("size"), log_label="JavDB 图片",
                )
                item["_final_path"] = str(final_path)
                item["_final_name"] = final_name
                item["size"] = size
                return True, str(final_path)
            except (requests.RequestException, PermissionError, OSError):
                return False, ""

        result = await self._run_download_worker(item, _resolve_and_download)
        if result is None:
            return
        success, final_path = result
        await self._finish_download_item(
            task, item, task_id,
            success=success, final_path=final_path, default_name=final_name,
        )


# 全局下载管理器单例
download_manager = DownloadManager()
