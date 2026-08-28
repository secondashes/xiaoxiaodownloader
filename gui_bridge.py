"""GUI 桥接模块：通过 stdin/stdout NDJSON 协议与 Electron 前端通信。

协议说明:
  前端 -> 后端 (stdin, 每行一个 JSON):
    {"cmd": "inspect", "url": "...", "options": {...}}
    {"cmd": "download", "url": "...", "items": ["item_page_url", ...], "options": {...}}
    {"cmd": "cancel"}
    {"cmd": "pawchive_login", "username": "...", "password": "..."}
    {"cmd": "pawchive_logout"}
    {"cmd": "pawchive_favorites"}

  后端 -> 前端 (stdout, 每行一个 JSON):
    {"event": "inspect_start", "url": "..."}
    {"event": "inspect_progress", "current": 3, "total": 10, "filename": "..."}
    {"event": "inspect_complete", "album_name": "...", "album_id": "...", "items": [...]}
    {"event": "inspect_error", "message": "..."}
    {"event": "download_start", "total_files": 5, "album_name": "..."}
    {"event": "file_start", "filename": "...", "index": 0, "size": 12345}
    {"event": "file_progress", "filename": "...", "completed": 45.2}
    {"event": "file_complete", "filename": "...", "success": true, "size": 12345}
    {"event": "download_complete", "summary": {...}}
    {"event": "download_error", "message": "..."}
    {"event": "pawchive_login_result", "success": true, "username": "...", "message": "..."}
    {"event": "log", "type": "...", "message": "..."}
    {"event": "ready"}
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import re
import shutil
import sys
import threading
import time
from argparse import Namespace
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

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


def emit(event: dict) -> None:
    """向 stdout 输出一行 JSON 事件（线程安全）。

    使用 ensure_ascii=True 输出纯 ASCII，避免 Windows 下 stdout 默认 GBK 编码
    遇到非 GBK 字符（如 ¹）时抛 UnicodeEncodeError；前端 JSON.parse 会还原 \\uXXXX。
    """
    line = json.dumps(event, ensure_ascii=True)
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


def _secure_store_write(data: dict) -> None:
    try:
        Path(SECURE_STORE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(SECURE_STORE_FILE).write_bytes(_secure_store_encrypt(data))
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


# ============================
# Coomer 站点支持 (xxxcoomer.com)
# ============================
COOMER_HOST = "https://xxxcoomer.com"
# 图片扩展名：用于判断媒体直链是否可直接当缩略图展示
COOMER_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")


def is_coomer_url(url: str) -> bool:
    """判断 URL 是否属于 Coomer 站点（xxxcoomer.com 及其子域名）。"""
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    return netloc == "xxxcoomer.com" or netloc.endswith(".xxxcoomer.com")


def _coomer_parse_url(url: str) -> dict | None:
    """解析 Coomer URL，返回页面信息。

    支持的格式:
      /creator/{service}/{user_id}/{username}          作者页（类似相册）
      /post/{post_id}/{user_id}/{service}/{username}   帖子页（类似单文件）
    """
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]

    if len(parts) >= 4 and parts[0] == "creator":
        return {
            "kind": "creator",
            "service": parts[1],
            "user_id": parts[2],
            "username": parts[3],
            "post_id": None,
        }
    if len(parts) >= 5 and parts[0] == "post":
        return {
            "kind": "post",
            "service": parts[3],
            "user_id": parts[2],
            "username": parts[4],
            "post_id": parts[1],
        }
    return None


def _coomer_creator_avatar(user_id: str) -> str:
    """返回作者头像 URL（作为视频等无预览媒体的缩略图兜底）。"""
    return f"{COOMER_HOST}/istorage/{user_id}.jpg"


def _coomer_extract_media_urls(soup: BeautifulSoup) -> list[str]:
    """从帖子页 .post-body 中提取媒体直链（图片 img / 视频 source）。"""
    body = soup.find("div", class_="post-body")
    if body is None:
        return []

    urls: list[str] = []
    for tag in body.find_all(["img", "source"]):
        src = (tag.get("src") or "").strip()
        # 排除作者头像（istorage）等非媒体图片
        if src.startswith("http") and "/istorage/" not in src:
            urls.append(src)
    return urls


def _coomer_post_title(soup: BeautifulSoup) -> str:
    """提取帖子标题（用于生成对用户友好的文件名）。"""
    wrap = soup.find("div", class_="post-wrap")
    h1 = (wrap.find("h1") if wrap else None) or soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _coomer_build_filename(title: str, media_url: str, index: int, total: int) -> str:
    """根据帖子标题和媒体 URL 生成下载文件名。

    优先使用帖子标题（更友好），无标题时退回 URL 文件名；
    一个帖子包含多个文件时追加序号区分。
    """
    media_path = urlparse(media_url).path
    ext = Path(media_path).suffix
    url_name = Path(media_path).stem

    base = remove_invalid_characters(title).strip()
    base = re.sub(r"\s+", " ", base)
    if not base:
        base = url_name
    if len(base) > 80:
        base = base[:80].rstrip()

    if total > 1:
        base = f"{base}_{index}"

    return f"{base}{ext}"


def _coomer_is_image(media_url: str) -> bool:
    """根据扩展名判断媒体是否为图片（图片直链可兼作缩略图）。"""
    return Path(urlparse(media_url).path).suffix.lower() in COOMER_IMAGE_EXTS


def _coomer_extract_post_pages(soup: BeautifulSoup) -> list[str]:
    """从作者页提取所有帖子链接。"""
    posts_list = soup.find("div", class_="posts-list")
    if posts_list is None:
        return []

    links: list[str] = []
    for a in posts_list.find_all("a", class_="view-post", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = COOMER_HOST + href
        if href.startswith("http") and href not in links:
            links.append(href)
    return links


def _coomer_next_page_url(soup: BeautifulSoup) -> str | None:
    """提取作者页底部的下一页链接（分页），无分页时返回 None。"""
    pagination = soup.find("div", class_="pagination-bottom")
    if pagination is None:
        return None

    next_link = pagination.find("a", class_="next")
    if next_link is None:
        return None

    href = (next_link.get("href") or "").strip()
    if not href:
        return None
    if href.startswith("/"):
        href = COOMER_HOST + href
    return href if href.startswith("http") else None


def _coomer_make_items(
    post_page: str,
    media_urls: list[str],
    title: str,
    avatar: str,
) -> list[dict]:
    """把一个帖子的媒体直链转换为文件列表条目。"""
    items: list[dict] = []
    for index, media_url in enumerate(media_urls, 1):
        items.append({
            "filename": _coomer_build_filename(title, media_url, index, len(media_urls)),
            "size": None,
            "item_page": post_page,
            "status": "ok",
            "site": "coomer",
            "media_url": media_url,
            "media_path": urlparse(media_url).path,
            "thumbnail": media_url if _coomer_is_image(media_url) else avatar,
        })
    return items


async def coomer_inspect(url: str, options: dict) -> None:
    """解析 Coomer 作者页/帖子页，返回媒体文件列表。"""
    info = _coomer_parse_url(url)
    if info is None:
        emit({
            "event": "inspect_error",
            "message": "无法识别的 Coomer 链接，请粘贴作者页或帖子页链接",
        })
        return

    avatar = _coomer_creator_avatar(info["user_id"])

    try:
        # ---------- 帖子页：单帖解析 ----------
        if info["kind"] == "post":
            soup = await fetch_page(url)
            if soup is None:
                emit({"event": "inspect_error", "message": f"无法获取页面: {url}"})
                return

            media_urls = _coomer_extract_media_urls(soup)
            if not media_urls:
                emit({"event": "inspect_error", "message": "帖子中没有找到可下载的媒体文件"})
                return

            items = _coomer_make_items(url, media_urls, _coomer_post_title(soup), avatar)
            _apply_cached_thumbnails(items)

            emit({
                "event": "inspect_complete",
                "album_name": info["username"],
                "album_id": f"coomer_{info['service']}_{info['user_id']}",
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Coomer 帖子解析完成: %s (%d 个文件)", url, len(items))
            return

        # ---------- 作者页：遍历分页收集所有帖子 ----------
        identifier = f"coomer_{info['service']}_{info['user_id']}"

        # 命中缓存则直接返回
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or info["username"],
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 Coomer 作者信息: %s (%d 个文件)", identifier, len(items))
            return

        post_pages: list[str] = []
        page_url: str | None = url
        visited: set[str] = set()
        while page_url and page_url not in visited:
            visited.add(page_url)
            soup = await fetch_page(page_url)
            if soup is None:
                break
            for link in _coomer_extract_post_pages(soup):
                if link not in post_pages:
                    post_pages.append(link)
            page_url = _coomer_next_page_url(soup)

        if not post_pages:
            emit({
                "event": "inspect_error",
                "message": "没有找到任何帖子，请确认链接是否正确",
            })
            return

        total = len(post_pages)
        emit({
            "event": "inspect_progress",
            "current": 0,
            "total": total,
            "filename": "",
        })
        logging.info("Coomer 作者 '%s' 共 %d 个帖子", info["username"], total)

        semaphore = asyncio.Semaphore(INSPECT_CONCURRENCY)
        results: list[dict] = []
        completed_count = 0
        count_lock = asyncio.Lock()

        async def resolve_one(post_page: str) -> None:
            nonlocal completed_count
            async with semaphore:
                post_soup = await fetch_page(post_page)
                if post_soup is None:
                    result = {
                        "filename": post_page.rstrip("/").rsplit("/", 1)[-1],
                        "size": None,
                        "item_page": post_page,
                        "status": "fetch_failed",
                        "site": "coomer",
                        "thumbnail": avatar,
                    }
                    results.append(result)
                else:
                    # 纯文字帖子（无媒体）直接跳过，不生成条目
                    media_urls = _coomer_extract_media_urls(post_soup)
                    if media_urls:
                        results.extend(_coomer_make_items(
                            post_page, media_urls, _coomer_post_title(post_soup), avatar,
                        ))

                async with count_lock:
                    completed_count += 1
                    emit({
                        "event": "inspect_progress",
                        "current": completed_count,
                        "total": total,
                        "filename": results[-1]["filename"] if results else "",
                    })

        await asyncio.gather(*(resolve_one(page) for page in post_pages))

        _apply_cached_thumbnails(results)

        # 增量标记：上次下载之后新增的帖子文件标 is_new
        _mark_items_new(identifier, results)

        _save_album_cache(identifier, {
            "album_name": info["username"],
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })

        emit({
            "event": "inspect_complete",
            "album_name": info["username"],
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })
        asyncio.create_task(_cache_thumbnails(results))
        logging.info("Coomer 作者解析完成: %s, 共 %d 个文件", info["username"], len(results))

    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("Coomer 解析过程出错")


async def get_coomer_download_info(item: dict) -> tuple[str | None, str]:
    """为 Coomer 条目解析下载直链，返回 (下载链接, 文件名)。

    视频直链带签名参数（e/hash）会过期，必须重新抓取帖子页获取新链接；
    图片直链永久有效，帖子页抓取失败时可直接回退到解析时保存的直链。
    """
    item_page = item.get("item_page", "")
    filename = item.get("filename", "") or "coomer_file"
    media_path = item.get("media_path", "")
    media_name = Path(media_path).name if media_path else ""

    if item_page:
        soup = await fetch_page(item_page)
        if soup is not None:
            media_urls = _coomer_extract_media_urls(soup)
            # 优先按媒体路径精确匹配（去掉签名参数后的路径）
            for media_url in media_urls:
                if urlparse(media_url).path == media_path:
                    return media_url, filename
            # 路径匹配失败（帖子可能已更新），按文件名兜底
            for media_url in media_urls:
                if Path(urlparse(media_url).path).name == media_name:
                    return media_url, filename
            # 仍匹配失败：帖子只剩一个文件时直接使用
            if len(media_urls) == 1:
                return media_urls[0], filename

    # 回退：图片直链永久有效
    fallback = item.get("media_url", "")
    if fallback.startswith("http"):
        return fallback, filename

    return None, filename


# ============================
# Pawchive 站点支持 (pawchive.pw)
# ============================
PAWCHIVE_HOST = "https://pawchive.pw"
PAWCHIVE_FILE_HOST = "https://file.pawchive.pw"
PAWCHIVE_IMG_HOST = "https://img.pawchive.pw"
PAWCHIVE_PAGE_SIZE = 50

PAWCHIVE_CREATORS_CACHE = Path("cache") / "pawchive_creators.json"
PAWCHIVE_CREATORS_TTL = 24 * 3600  # 创作者列表缓存有效期（秒）
PAWCHIVE_DOWNLOAD_GAP = 1.0        # 两次下载之间的最小间隔（秒），站点对下载有限速


def is_pawchive_url(url: str) -> bool:
    """判断 URL 是否属于 Pawchive 站点（pawchive.pw 及其子域名）。"""
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    return netloc == "pawchive.pw" or netloc.endswith(".pawchive.pw")


def _pawchive_parse_url(url: str) -> dict | None:
    """解析 Pawchive URL，返回页面信息。

    支持的格式:
      /{service}/user/{user_id}                    画师页（类似相册）
      /{service}/user/{user_id}/post/{post_id}     帖子页（类似单文件）
    """
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]

    if len(parts) >= 3 and parts[1] == "user":
        info = {
            "kind": "artist",
            "service": parts[0],
            "user_id": parts[2],
            "post_id": None,
        }
        if len(parts) >= 5 and parts[3] == "post":
            info["kind"] = "post"
            info["post_id"] = parts[4]
        return info
    return None


# Pawchive 会话（登录后用于收藏等功能；未登录也可用于普通浏览请求）
# 注意：UA 字符串直接写死，不能引用 SEARCH_HEADERS（它定义在文件更靠后的位置）
_pawchive_session = requests.Session()
_pawchive_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": PAWCHIVE_HOST + "/",
})
_pawchive_username: str | None = None

# 下载节流（站点对下载有限速，控制请求频率避免被封）
_pawchive_download_lock = asyncio.Lock()
_pawchive_last_download_time = 0.0


async def _pawchive_throttle_download() -> None:
    """确保两次 Pawchive 下载请求之间至少间隔 PAWCHIVE_DOWNLOAD_GAP 秒。"""
    global _pawchive_last_download_time
    async with _pawchive_download_lock:
        elapsed = time.monotonic() - _pawchive_last_download_time
        if elapsed < PAWCHIVE_DOWNLOAD_GAP:
            await asyncio.sleep(PAWCHIVE_DOWNLOAD_GAP - elapsed)
        _pawchive_last_download_time = time.monotonic()


def _pawchive_load_session() -> None:
    """启动时恢复已保存的登录会话（加密账号存储）。"""
    global _pawchive_username
    data = _secure_store_read_cred("pawchive")
    for name, value in (data.get("cookies") or {}).items():
        _pawchive_session.cookies.set(name, value)
    _pawchive_username = data.get("username")
    if _pawchive_username:
        logging.info("已恢复 Pawchive 登录会话: %s", _pawchive_username)


def _pawchive_save_session() -> None:
    """持久化登录会话（加密存储）。"""
    cookies = {c.name: c.value for c in _pawchive_session.cookies}
    _secure_store_write_cred("pawchive", {"username": _pawchive_username, "cookies": cookies})


def _pawchive_logged_in() -> bool:
    return bool(_pawchive_session.cookies.get("session"))


async def pawchive_login(username: str, password: str) -> None:
    """登录 pawchive.pw，成功后保存会话 cookie。"""
    global _pawchive_username
    if not username or not password:
        emit({"event": "pawchive_login_result", "success": False, "message": "请输入用户名和密码"})
        return

    def _do_login() -> requests.Response:
        _pawchive_session.cookies.clear()
        # 先访问登录页获取初始 cookie
        _pawchive_session.get(f"{PAWCHIVE_HOST}/account/login", timeout=15)
        return _pawchive_session.post(
            f"{PAWCHIVE_HOST}/account/login",
            data={"username": username, "password": password, "location": "/"},
            timeout=15,
            allow_redirects=False,
        )

    try:
        response = await asyncio.to_thread(_do_login)
        # 登录成功：302 跳转到 /；失败：302 跳回 /account/login
        location = (response.headers.get("location") or "").lower()
        if response.status_code in (302, 303) and "login" not in location and _pawchive_logged_in():
            _pawchive_username = username
            _pawchive_save_session()
            _record_login_ok("pawchive")
            emit({
                "event": "pawchive_login_result",
                "success": True,
                "username": username,
                "message": f"登录成功: {username}",
            })
            logging.info("Pawchive 登录成功: %s", username)
        else:
            _pawchive_username = None
            emit({
                "event": "pawchive_login_result",
                "success": False,
                "message": "登录失败：用户名或密码错误",
            })
            logging.warning("Pawchive 登录失败: %s", username)
    except requests.RequestException as exc:
        emit({
            "event": "pawchive_login_result",
            "success": False,
            "message": f"登录请求失败: {exc}",
            "network_issue": True,
        })
        logging.exception("Pawchive 登录请求失败")
    _emit_login_info()


def pawchive_logout() -> None:
    """退出登录，清除会话。"""
    global _pawchive_username
    try:
        _pawchive_session.get(f"{PAWCHIVE_HOST}/account/logout", timeout=10)
    except requests.RequestException:
        pass
    _pawchive_session.cookies.clear()
    _pawchive_username = None
    _secure_store_clear_cred("pawchive")
    emit({"event": "pawchive_login_result", "success": False, "logout": True, "username": "", "message": "已退出登录"})
    logging.info("Pawchive 已退出登录")
    _emit_login_info()


def _pawchive_check_login() -> tuple[bool, str | None, str]:
    """检查 Pawchive 登录状态（用收藏 API 验证会话是否有效）。"""
    if not _pawchive_logged_in():
        return False, None, "未配置 Pawchive 登录信息"
    try:
        response = _pawchive_session.get(f"{PAWCHIVE_HOST}/api/v1/account/favorites", timeout=15)
        if response.status_code == 200:
            return True, _pawchive_username, "Pawchive 登录有效"
        if response.status_code == 401:
            return False, None, "Pawchive 登录已过期，请重新登录"
        return False, None, f"Pawchive 状态异常: HTTP {response.status_code}"
    except requests.RequestException as exc:
        return False, None, f"Pawchive 连接失败: {exc}"


def pawchive_set_cookies(cookie_str: str, username: str = "") -> None:
    """用 cookie 字符串恢复 Pawchive 会话（一键抓取 Cookie / 账号切换用）。"""
    global _pawchive_username
    cookies: dict = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            if name.strip():
                cookies[name.strip()] = value.strip()
    if not cookies.get("session"):
        emit({
            "event": "pawchive_login_result",
            "success": False,
            "message": "Cookie 缺少 session，请确认已在浏览器登录 pawchive.pw",
        })
        return
    _pawchive_session.cookies.clear()
    for name, value in cookies.items():
        _pawchive_session.cookies.set(name, value)
    _pawchive_username = username or ""
    _pawchive_save_session()
    ok, uname, msg = _pawchive_check_login()
    if ok:
        _record_login_ok("pawchive")
        if uname:
            _pawchive_username = uname
            _pawchive_save_session()
    emit({
        "event": "pawchive_login_result",
        "success": ok,
        "username": (uname if ok else _pawchive_username) or "",
        "message": msg,
        "network_issue": (not ok) and _login_network_issue("pawchive"),
    })
    _emit_login_info()


async def pawchive_get_favorites() -> None:
    """获取登录账号的收藏画师列表，以搜索结果事件返回（点击卡片即可解析）。"""
    emit({"event": "search_start", "query": "我的收藏", "page": 1})

    def _fetch_api() -> requests.Response:
        return _pawchive_session.get(f"{PAWCHIVE_HOST}/api/v1/account/favorites", timeout=20)

    items: list[dict] = []
    try:
        response = await asyncio.to_thread(_fetch_api)
        if response.status_code == 401:
            emit({"event": "search_error", "message": "登录已过期，请重新登录 Pawchive"})
            return
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                for creator in data:
                    if not isinstance(creator, dict):
                        continue
                    cid = str(creator.get("id") or "")
                    service = creator.get("service") or ""
                    if not cid or not service:
                        continue
                    items.append({
                        "album_name": creator.get("name") or cid,
                        "album_url": f"{PAWCHIVE_HOST}/{service}/user/{cid}",
                        "thumbnail": f"{PAWCHIVE_HOST}/icons/{service}/{cid}",
                        "files": None,
                        "site": "pawchive",
                        "service": service,
                    })
    except (requests.RequestException, ValueError):
        logging.exception("Pawchive 收藏 API 请求失败")

    # API 未返回数据时回退解析 /favorites HTML（SSR 画师卡片）
    if not items and _pawchive_logged_in():
        try:
            response = await asyncio.to_thread(
                lambda: _pawchive_session.get(f"{PAWCHIVE_HOST}/favorites", timeout=20),
            )
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                seen: set[str] = set()
                for link in soup.find_all("a", href=True):
                    href = link.get("href") or ""
                    m = re.match(r"^/([\w-]+)/user/(\d+)/?$", href)
                    if not m:
                        continue
                    service, uid = m.groups()
                    url = f"{PAWCHIVE_HOST}/{service}/user/{uid}"
                    if url in seen:
                        continue
                    seen.add(url)
                    name = link.get_text(strip=True) or uid
                    items.append({
                        "album_name": name,
                        "album_url": url,
                        "thumbnail": f"{PAWCHIVE_HOST}/icons/{service}/{uid}",
                        "files": None,
                        "site": "pawchive",
                        "service": service,
                    })
        except requests.RequestException:
            logging.exception("Pawchive 收藏页解析失败")

    if not items:
        emit({"event": "search_error", "message": "未获取到收藏，请先登录或先在网页上添加收藏"})
        return

    _apply_cached_thumbnails(items)
    emit({
        "event": "search_result",
        "query": "我的收藏",
        "page": 1,
        "total_pages": 1,
        "has_more": False,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 收藏获取完成: %d 个画师", len(items))


# ============================
# Pawchive 搜索
# ============================
def _fetch_pawchive_creators() -> list[dict] | None:
    """拉取全量创作者列表（约 12MB），本地缓存 24 小时。"""
    if PAWCHIVE_CREATORS_CACHE.exists():
        try:
            data = json.loads(PAWCHIVE_CREATORS_CACHE.read_text(encoding="utf-8"))
            if time.time() - data.get("fetched_at", 0) < PAWCHIVE_CREATORS_TTL:
                return data.get("creators")
        except (OSError, json.JSONDecodeError):
            pass

    try:
        response = _pawchive_session.get(f"{PAWCHIVE_HOST}/api/v1/creators", timeout=60)
        response.raise_for_status()
        creators = response.json()
        if not isinstance(creators, list):
            return None
        PAWCHIVE_CREATORS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PAWCHIVE_CREATORS_CACHE.write_text(
            json.dumps({"fetched_at": time.time(), "creators": creators}, ensure_ascii=False),
            encoding="utf-8",
        )
        logging.info("Pawchive 创作者列表已更新: %d 个", len(creators))
        return creators
    except (requests.RequestException, ValueError, OSError):
        logging.exception("Pawchive 创作者列表拉取失败")
        return None


async def pawchive_search_artist(query: str, page: int) -> None:
    """画师搜索：本地过滤创作者列表。"""
    emit({"event": "search_start", "query": query, "page": page})
    logging.info("Pawchive 画师搜索: '%s' (第 %d 页)", query, page)

    creators = await asyncio.to_thread(_fetch_pawchive_creators)
    if creators is None:
        emit({"event": "search_error", "message": "无法获取 Pawchive 创作者列表，请稍后重试"})
        return

    q = query.strip().lower()
    matched = [c for c in creators if q in (c.get("name") or "").lower()]

    total_pages = max(1, -(-len(matched) // PAWCHIVE_PAGE_SIZE))
    start = (page - 1) * PAWCHIVE_PAGE_SIZE
    page_creators = matched[start:start + PAWCHIVE_PAGE_SIZE]

    items = [{
        "album_name": c.get("name") or c.get("id"),
        "album_url": f"{PAWCHIVE_HOST}/{c.get('service')}/user/{c.get('id')}",
        "thumbnail": f"{PAWCHIVE_HOST}/icons/{c.get('service')}/{c.get('id')}",
        "files": None,
        "site": "pawchive",
        "service": c.get("service"),
    } for c in page_creators]

    _apply_cached_thumbnails(items)
    emit({
        "event": "search_result",
        "query": query,
        "page": page,
        "total_pages": total_pages,
        "total_results": len(matched),
        "has_more": page < total_pages,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 画师搜索完成: '%s' 匹配 %d 个", query, len(matched))


def _fetch_pawchive_tag_page(tag: str, offset: int) -> BeautifulSoup | None:
    """抓取标签搜索结果页（SSR 渲染，每页 50 个）。"""
    response = _pawchive_session.get(
        f"{PAWCHIVE_HOST}/posts",
        params={"tags": tag, "o": offset},
        timeout=20,
    )
    if response.status_code != 200:
        return None
    return BeautifulSoup(response.content, "html.parser")


def _parse_pawchive_post_cards(soup: BeautifulSoup) -> list[dict]:
    """解析 SSR 帖子卡片为搜索结果条目。"""
    items: list[dict] = []
    for card in soup.find_all("article", class_="post-card"):
        link = card.find("a", href=True)
        if link is None:
            continue
        href = (link.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = PAWCHIVE_HOST + href

        header = card.find("header", class_="post-card__header")
        title = header.get_text(strip=True) if header else ""

        thumbnail = ""
        img = card.find("img", class_="post-card__image")
        if img:
            thumbnail = (img.get("src") or "").strip()

        # 附件数提示
        files = None
        footer = card.find("footer")
        if footer:
            m = re.search(r"(\d+)\s+attachments?", footer.get_text())
            if m:
                files = int(m.group(1))

        items.append({
            "album_name": title or "未命名帖子",
            "album_url": href,
            "thumbnail": thumbnail,
            "files": files,
            "site": "pawchive",
        })
    return items


async def pawchive_search_tag(tag: str, page: int) -> None:
    """标签搜索：全站帖子搜索（SSR 分页，每页 50）。"""
    emit({"event": "search_start", "query": tag, "page": page})
    logging.info("Pawchive 标签搜索: '%s' (第 %d 页)", tag, page)

    offset = (page - 1) * PAWCHIVE_PAGE_SIZE
    soup = await asyncio.to_thread(_fetch_pawchive_tag_page, tag, offset)
    if soup is None:
        emit({"event": "search_error", "message": "搜索失败，无法访问 pawchive.pw"})
        return

    items = _parse_pawchive_post_cards(soup)
    _apply_cached_thumbnails(items)
    # 有结果就认为可能还有下一页（末页由前端"加载全部"兜底）
    emit({
        "event": "search_result",
        "query": tag,
        "page": page,
        "total_pages": page + 1 if len(items) >= PAWCHIVE_PAGE_SIZE else page,
        "has_more": len(items) >= PAWCHIVE_PAGE_SIZE,
        "items": items,
    })
    asyncio.create_task(_cache_thumbnails(items))
    logging.info("Pawchive 标签搜索完成: '%s' 第 %d 页，%d 个结果", tag, page, len(items))


# ============================
# Pawchive 解析 (inspect)
# ============================
def _pawchive_fetch_json(path: str, params: dict | None = None) -> dict | list | None:
    """同步请求 Pawchive API 并返回 JSON。"""
    try:
        response = _pawchive_session.get(
            f"{PAWCHIVE_HOST}{path}", params=params, timeout=30,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def _pawchive_fetch_profile(service: str, user_id: str) -> dict | None:
    """获取画师资料（画师名等）。"""
    data = _pawchive_fetch_json(f"/api/v1/{service}/user/{user_id}/profile")
    return data if isinstance(data, dict) else None


def _pawchive_make_item(
    post: dict,
    file_info: dict,
    artist_name: str,
    service: str,
    user_id: str,
) -> dict:
    """把帖子中的一个文件转换为下载条目（直链永久有效）。"""
    path = file_info.get("path") or ""
    name = file_info.get("name") or Path(path).name
    post_id = str(post.get("id") or "")
    return {
        "filename": name,
        "size": None,
        "item_page": f"{PAWCHIVE_HOST}/{service}/user/{user_id}/post/{post_id}",
        "status": "ok",
        "site": "pawchive",
        "media_url": PAWCHIVE_FILE_HOST + "/data" + path,
        "media_path": path,
        "thumbnail": PAWCHIVE_IMG_HOST + "/thumbnail/data" + path,
        "post_title": post.get("title") or "",
        "post_date": post.get("published") or "",
        "artist": artist_name,
        "service": service,
        "post_id": post_id,
    }


def _pawchive_post_items(post: dict, artist_name: str, service: str, user_id: str) -> list[dict]:
    """帖子 → 文件条目列表（主文件 + 附件）。"""
    items: list[dict] = []
    main_file = post.get("file") or {}
    if main_file.get("path"):
        items.append(_pawchive_make_item(post, main_file, artist_name, service, user_id))
    for att in post.get("attachments") or []:
        if isinstance(att, dict) and att.get("path"):
            items.append(_pawchive_make_item(post, att, artist_name, service, user_id))
    return items


def _pawchive_post_has_attachments(post: dict) -> bool:
    """判断帖子列表数据里的附件信息是否完整（列表 API 有时只给空占位）。"""
    for att in post.get("attachments") or []:
        if isinstance(att, dict) and att.get("path"):
            return True
    return False


async def pawchive_inspect(url: str, options: dict) -> None:
    """解析 Pawchive 画师页/帖子页，返回文件列表。"""
    info = _pawchive_parse_url(url)
    if info is None:
        emit({
            "event": "inspect_error",
            "message": "无法识别的 Pawchive 链接，请粘贴画师页或帖子页链接",
        })
        return

    service = info["service"]
    user_id = info["user_id"]

    try:
        # ---------- 帖子页：单帖解析 ----------
        if info["kind"] == "post":
            post = await asyncio.to_thread(
                _pawchive_fetch_json,
                f"/api/v1/{service}/user/{user_id}/post/{info['post_id']}",
            )
            if not isinstance(post, dict) or not post.get("id"):
                emit({"event": "inspect_error", "message": f"无法获取帖子: {url}"})
                return

            profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
            artist_name = (profile or {}).get("name") or user_id

            items = _pawchive_post_items(post, artist_name, service, user_id)
            if not items:
                emit({"event": "inspect_error", "message": "帖子中没有找到可下载的文件"})
                return

            _apply_cached_thumbnails(items)
            _mark_items_new(f"pawchive_{service}_{user_id}", items)
            emit({
                "event": "inspect_complete",
                "album_name": artist_name,
                "album_id": f"pawchive_{service}_{user_id}",
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Pawchive 帖子解析完成: %s (%d 个文件)", url, len(items))
            return

        # ---------- 画师页：分页拉全部帖子 ----------
        identifier = f"pawchive_{service}_{user_id}"

        # 命中缓存则直接返回
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or user_id,
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 Pawchive 画师信息: %s (%d 个文件)", identifier, len(items))
            return

        profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
        artist_name = (profile or {}).get("name") or user_id

        # 分页拉取帖子列表
        posts: list[dict] = []
        offset = 0
        while True:
            page_data = await asyncio.to_thread(
                _pawchive_fetch_json,
                f"/api/v1/{service}/user/{user_id}/posts",
                {"o": offset},
            )
            if not isinstance(page_data, list) or not page_data:
                break
            posts.extend(page_data)
            if len(page_data) < PAWCHIVE_PAGE_SIZE:
                break
            offset += PAWCHIVE_PAGE_SIZE

        if not posts:
            emit({"event": "inspect_error", "message": "没有找到任何帖子，请确认链接是否正确"})
            return

        total = len(posts)
        emit({
            "event": "inspect_progress",
            "current": 0,
            "total": total,
            "filename": "",
        })
        logging.info("Pawchive 画师 '%s' 共 %d 个帖子", artist_name, total)

        semaphore = asyncio.Semaphore(INSPECT_CONCURRENCY)
        results: list[dict] = []
        completed_count = 0
        count_lock = asyncio.Lock()

        async def resolve_one(post: dict) -> None:
            nonlocal completed_count
            async with semaphore:
                # 列表 API 附件信息完整时直接使用，否则拉帖子详情
                if _pawchive_post_has_attachments(post) or (post.get("file") or {}).get("path"):
                    post_items = _pawchive_post_items(post, artist_name, service, user_id)
                else:
                    detail = await asyncio.to_thread(
                        _pawchive_fetch_json,
                        f"/api/v1/{service}/user/{user_id}/post/{post.get('id')}",
                    )
                    if isinstance(detail, dict):
                        post_items = _pawchive_post_items(detail, artist_name, service, user_id)
                    else:
                        post_items = []

                if post_items:
                    results.extend(post_items)

                async with count_lock:
                    completed_count += 1
                    if completed_count % 10 == 0 or completed_count == total:
                        emit({
                            "event": "inspect_progress",
                            "current": completed_count,
                            "total": total,
                            "filename": post_items[0]["filename"] if post_items else "",
                        })

        await asyncio.gather(*(resolve_one(p) for p in posts))

        _apply_cached_thumbnails(results)

        # 增量标记：上次下载之后新增的帖子文件标 is_new
        _mark_items_new(identifier, results)

        _save_album_cache(identifier, {
            "album_name": artist_name,
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })

        emit({
            "event": "inspect_complete",
            "album_name": artist_name,
            "album_id": identifier,
            "is_album": True,
            "items": results,
        })
        asyncio.create_task(_cache_thumbnails(results))
        logging.info("Pawchive 画师解析完成: %s, 共 %d 个文件", artist_name, len(results))

    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("Pawchive 解析过程出错")


async def pawchive_post_info(url: str) -> None:
    """获取 Pawchive 帖子完整信息（标题/画师/时间/正文/标签/附件预览）。"""
    info = _pawchive_parse_url(url)
    if info is None or info.get("kind") != "post":
        emit({"event": "pa_post_info_error", "message": "无效的 Pawchive 帖子链接"})
        return
    service = info["service"]
    user_id = info["user_id"]
    post_id = info["post_id"]
    try:
        post = await asyncio.to_thread(
            _pawchive_fetch_json,
            f"/api/v1/{service}/user/{user_id}/post/{post_id}",
        )
        if not isinstance(post, dict):
            emit({"event": "pa_post_info_error", "message": "获取帖子信息失败，请稍后重试"})
            return

        # 画师名（帖子 API 通常含 user 字段；缺失时拉 profile）
        artist_name = ""
        if isinstance(post.get("user"), dict):
            artist_name = post["user"].get("name") or ""
        if not artist_name:
            profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
            if profile:
                artist_name = profile.get("name") or ""
        artist_name = artist_name or user_id

        # 标签（Kemono 架构：可能是列表或逗号分隔字符串）
        raw_tags = post.get("tags") or []
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]

        # 附件预览（主文件 + 附件，直链缩略图永久有效）
        previews: list[dict] = []
        for fi in [post.get("file") or {}] + [
            a for a in (post.get("attachments") or []) if isinstance(a, dict)
        ]:
            path = fi.get("path") or ""
            if not path:
                continue
            previews.append({
                "name": fi.get("name") or Path(path).name,
                "thumbnail": PAWCHIVE_IMG_HOST + "/thumbnail/data" + path,
                "media_url": PAWCHIVE_FILE_HOST + "/data" + path,
            })

        _apply_cached_thumbnails(previews)
        emit({
            "event": "pa_post_info",
            "url": url,
            "title": post.get("title") or "未命名帖子",
            "artist": artist_name,
            "artist_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}",
            "posted": (post.get("published") or "")[:10],
            "content": post.get("content") or "",
            "tags": tags,
            "previews": previews,
        })
        asyncio.create_task(_cache_thumbnails(previews))
        logging.info("Pawchive 帖子信息: %s", (post.get("title") or "")[:50])

    except PermissionError as exc:
        emit({"event": "pa_post_info_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "pa_post_info_error", "message": f"获取帖子信息失败: {exc}"})
        logging.exception("Pawchive 帖子信息获取失败")


# ============================
# Pawchive 画师子项目列表（点开画师 → 按日期展示全部帖子）
# ============================
PAWCHIVE_POSTS_CACHE_DIR = Path("cache") / "pawchive_posts"
PAWCHIVE_POSTS_CACHE_TTL = 24 * 60 * 60  # 帖子列表缓存 24 小时


def _pa_posts_cache_path(identifier: str) -> Path:
    return PAWCHIVE_POSTS_CACHE_DIR / f"{identifier}.json"


def _load_pa_posts_cache(identifier: str) -> dict | None:
    path = _pa_posts_cache_path(identifier)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not (isinstance(data, dict) and data.get("posts")):
            return None
        if time.time() - float(data.get("fetched_at") or 0) > PAWCHIVE_POSTS_CACHE_TTL:
            return None
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _save_pa_posts_cache(identifier: str, data: dict) -> None:
    try:
        PAWCHIVE_POSTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data["fetched_at"] = time.time()
        _pa_posts_cache_path(identifier).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8",
        )
    except OSError as exc:
        logging.warning("保存 Pawchive 帖子列表缓存失败: %s", exc)


def _pawchive_map_post(post: dict, service: str, user_id: str) -> dict:
    """帖子列表条目 → 子项目卡片数据（含悬浮详情所需信息）。"""
    post_id = str(post.get("id") or "")
    main_file = post.get("file") or {}
    attachments = [a for a in (post.get("attachments") or []) if isinstance(a, dict)]
    file_names = []
    if main_file.get("name") or main_file.get("path"):
        file_names.append(main_file.get("name") or Path(main_file.get("path") or "").name)
    for att in attachments:
        if att.get("path"):
            file_names.append(att.get("name") or Path(att["path"]).name)
    content = (post.get("content") or "").strip()
    return {
        "post_id": post_id,
        "title": post.get("title") or "未命名帖子",
        "published": post.get("published") or "",
        "content": content[:200],
        "file_count": len(file_names),
        "files": file_names[:20],
        "has_video": any(
            str(n).lower().endswith((".mp4", ".webm", ".mov", ".m4v"))
            for n in file_names
        ),
        "has_archive": any(
            str(n).lower().endswith((".zip", ".rar", ".7z", ".tar", ".gz"))
            for n in file_names
        ),
        "thumbnail": (
            PAWCHIVE_IMG_HOST + "/thumbnail/data" + main_file["path"]
            if main_file.get("path") else ""
        ),
        "post_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}/post/{post_id}",
    }


async def pawchive_artist_posts(url: str) -> None:
    """获取画师全部帖子列表（子项目视图：按发布日期倒序）。"""
    info = _pawchive_parse_url(url)
    if info is None:
        emit({"event": "pa_artist_posts_error", "message": "无法识别的 Pawchive 画师链接"})
        return
    if info.get("kind") != "artist":
        emit({"event": "pa_artist_posts_error", "message": "请粘贴画师主页链接"})
        return

    service = info["service"]
    user_id = info["user_id"]
    identifier = f"pawchive_{service}_{user_id}"

    try:
        # 命中缓存直接返回
        cached = _load_pa_posts_cache(identifier)
        if cached:
            _apply_cached_thumbnails(cached.get("posts") or [])
            emit({
                "event": "pa_artist_posts",
                "url": url,
                "artist": cached.get("artist") or user_id,
                "artist_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}",
                "posts": cached.get("posts") or [],
                "cached": True,
            })
            asyncio.create_task(_cache_thumbnails(cached.get("posts") or []))
            return

        profile = await asyncio.to_thread(_pawchive_fetch_profile, service, user_id)
        artist_name = (profile or {}).get("name") or user_id

        # 分页拉取全部帖子（列表 API：每页 50）
        raw_posts: list[dict] = []
        offset = 0
        while True:
            page_data = await asyncio.to_thread(
                _pawchive_fetch_json,
                f"/api/v1/{service}/user/{user_id}/posts",
                {"o": offset},
            )
            if not isinstance(page_data, list) or not page_data:
                break
            raw_posts.extend(page_data)
            if len(page_data) < PAWCHIVE_PAGE_SIZE:
                break
            offset += PAWCHIVE_PAGE_SIZE

        # 列表 API 附件字段可能为空占位：文件数为 0 的帖子拉详情补全
        async def _fill_detail(post: dict) -> dict:
            if not (post.get("file") or {}).get("path") and \
                    not [a for a in (post.get("attachments") or []) if isinstance(a, dict) and a.get("path")]:
                detail = await asyncio.to_thread(
                    _pawchive_fetch_json,
                    f"/api/v1/{service}/user/{user_id}/post/{post.get('id')}",
                )
                if isinstance(detail, dict) and detail.get("id"):
                    return detail
            return post

        semaphore = asyncio.Semaphore(4)

        async def _fill_one(post: dict) -> dict:
            async with semaphore:
                return await _fill_detail(post)

        raw_posts = list(await asyncio.gather(*(_fill_one(p) for p in raw_posts)))

        # 按发布日期倒序（子项目按"哪一天发的内容"浏览）
        posts = [_pawchive_map_post(p, service, user_id) for p in raw_posts]
        posts.sort(key=lambda p: p.get("published") or "", reverse=True)

        _apply_cached_thumbnails(posts)
        emit({
            "event": "pa_artist_posts",
            "url": url,
            "artist": artist_name,
            "artist_url": f"{PAWCHIVE_HOST}/{service}/user/{user_id}",
            "posts": posts,
            "cached": False,
        })
        asyncio.create_task(_cache_thumbnails(posts))
        _save_pa_posts_cache(identifier, {
            "artist": artist_name,
            "posts": posts,
        })
        logging.info("Pawchive 画师帖子列表: %s 共 %d 个帖子", artist_name, len(posts))

    except Exception as exc:
        emit({"event": "pa_artist_posts_error", "message": f"获取帖子列表失败: {exc}"})
        logging.exception("Pawchive 画师帖子列表获取失败")


# ============================
# Pawchive 下载目录规则
# ============================
def _render_folder_template(template: str, date: str, title: str, post_id: str = "") -> str:
    """自定义子文件夹模板 → 相对子目录（每站点独立设置，长期持久化）。

    变量：{date}=YYYY-MM、{date_full}=YYYY-MM-DD、{title}=帖子/画廊标题、{id}=帖子ID。
    模板示例："{date}/{title}" → "2026-08/帖子名"；每段自动清洗非法字符。
    """
    if not template or not template.strip():
        return ""
    mapping = {
        "date": (date or "")[:7],
        "date_full": (date or "")[:10],
        "title": title or "",
        "id": post_id or "",
    }
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace("{" + key + "}", value)
    parts = [sanitize_directory_name(seg.strip())[:80] for seg in rendered.split("/")]
    parts = [p for p in parts if p]
    return str(Path(*parts)) if parts else ""


def _pawchive_subfolder(item: dict, options: dict) -> str:
    """Pawchive 专属子文件夹规则（父文件夹为画师名，由相册目录承担）。

    模式 pawchive_subfolder:
      - none:       不建子文件夹
      - date:       按发布月份 YYYY-MM
      - post:       按帖子标题
      - date_post:  YYYY-MM/帖子标题（默认）
    自定义模板 pawchive_folder_template 非空时优先。
    """
    template = (options.get("pawchive_folder_template") or "").strip()
    if template:
        return _render_folder_template(
            template,
            item.get("post_date") or "",
            (item.get("post_title") or "").strip(),
            item.get("post_id") or "",
        )
    mode = options.get("pawchive_subfolder", "date_post")
    parts: list[str] = []
    date = (item.get("post_date") or "")[:7]  # YYYY-MM
    title = sanitize_directory_name((item.get("post_title") or "").strip())[:60]

    if mode == "date" and date:
        parts.append(date)
    elif mode == "post" and title:
        parts.append(title)
    elif mode == "date_post":
        if date:
            parts.append(date)
        if title:
            parts.append(title)
    return str(Path(*parts)) if parts else ""


def _pawchive_build_file_dir(album_path: str, item: dict, options: dict) -> str:
    """构建 Pawchive 文件的下载子目录（画师名已作为相册目录）。"""
    sub = _pawchive_subfolder(item, options)
    if not sub:
        return album_path
    directory = str(Path(album_path) / sub)
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
    except OSError:
        return album_path
    return directory


def _pawchive_album_name(url: str, items: list[dict], fallback: str = "Pawchive") -> str:
    """从 URL 或下载条目推断画师名（作为下载目录名）。"""
    info = _pawchive_parse_url(url)
    if info:
        profile = _pawchive_fetch_profile(info["service"], info["user_id"])
        if profile and profile.get("name"):
            return str(profile["name"])
    for item in items:
        if item.get("artist"):
            return str(item["artist"])
    return fallback


# ============================
# ExHentai 站点支持 (exhentai.org)
# ============================
# 站点特点：
# - 需要 e-hentai 账号 cookie（ipb_member_id + ipb_pass_hash）才能访问
# - igneous 是 exhentai 的通行证，会过期；带着失效的 igneous 访问会被拒（返回空页 + igneous=mystery）
# - 正确做法：请求时不带 igneous，服务器验证账号 cookie 后自动下发新 igneous
# - 图片直链在 *.hath.network，带 keystamp 时效签名，下载时需重新解析图片页
# - 请求过快会触发 509 带宽限制，需严格节流
# - 需要 HTTP 代理访问（站点在国内不可直连）
EXHENTAI_HOST = "https://exhentai.org"
EXHENTAI_GALLERY_PAGE_SIZE = 40    # 画廊页每页缩略图数量
EXHENTAI_REQUEST_INTERVAL = 0.4    # 请求最小间隔（秒），防 509（实测 2.5 req/s 安全）
EXHENTAI_DEFAULT_PROXY = "http://127.0.0.1:10809"

_exhentai_session = requests.Session()
_exhentai_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Referer": EXHENTAI_HOST + "/",
})
_exhentai_proxy: str | None = None
_exhentai_logged_in: bool = False
_exhentai_last_request = 0.0
_exhentai_lock = threading.Lock()


def exhentai_set_proxy(proxy: str | None) -> None:
    """设置 ExHentai 访问代理（如 http://127.0.0.1:10809）。"""
    global _exhentai_proxy
    _exhentai_proxy = (proxy or "").strip() or None
    if _exhentai_proxy:
        _exhentai_session.proxies.update({"http": _exhentai_proxy, "https": _exhentai_proxy})
    else:
        _exhentai_session.proxies.clear()
    logging.info("ExHentai 代理已设置: %s", _exhentai_proxy or "（直连）")


def _exhentai_cookie_str() -> str:
    """把账号 cookie + igneous 拼成 Cookie 请求头（不带失效的 igneous）。"""
    cookies: dict = _exhentai_load_cookies()
    parts = []
    if cookies.get("ipb_member_id"):
        parts.append(f"ipb_member_id={cookies['ipb_member_id']}")
    if cookies.get("ipb_pass_hash"):
        parts.append(f"ipb_pass_hash={cookies['ipb_pass_hash']}")
    if cookies.get("ipb_coppa"):
        parts.append(f"ipb_coppa={cookies['ipb_coppa']}")
    igneous = cookies.get("_igneous")  # 后端自动刷新的 igneous（带下划线前缀区分）
    if igneous:
        parts.append(f"igneous={igneous}")
    return "; ".join(parts)


def _exhentai_save_cookies(cookies: dict) -> None:
    """保存 ExHentai cookie（长期保持登录状态，加密存储）。"""
    data = _exhentai_load_cookies()
    data.update({k: v for k, v in cookies.items() if v})
    data["_saved_at"] = time.time()
    _secure_store_write_cred("exhentai", data)


def _exhentai_load_cookies() -> dict:
    """读取已保存的 ExHentai cookie（加密账号存储）。"""
    return _secure_store_read_cred("exhentai")


def exhentai_set_cookies(cookie_str: str) -> None:
    """前端 webview 登录后同步 cookie 字符串（或用户手动粘贴）。"""
    cookies: dict = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            if name.strip():
                cookies[name.strip()] = value.strip()
    if not cookies.get("ipb_member_id") or not cookies.get("ipb_pass_hash"):
        emit({
            "event": "exhentai_login_result",
            "success": False,
            "message": "Cookie 缺少 ipb_member_id 或 ipb_pass_hash，请确认已在浏览器中登录",
        })
        return
    # 丢弃旧 igneous（由后端自动重新获取）
    saved = _exhentai_load_cookies()
    saved = {k: v for k, v in saved.items() if k == "_igneous"}
    saved.update(cookies)
    _exhentai_save_cookies(saved)
    # 立即验证
    ok, username, msg = _exhentai_check_login()
    if ok:
        _record_login_ok("exhentai")
    emit({
        "event": "exhentai_login_result",
        "success": ok,
        "username": username or cookies.get("ipb_member_id", ""),
        "message": msg,
        "network_issue": (not ok) and _login_network_issue("exhentai"),
    })
    _emit_login_info()


def exhentai_clear_cookies() -> None:
    """清除已保存的 ExHentai 登录信息（加密存储）。"""
    global _exhentai_logged_in
    _secure_store_clear_cred("exhentai")
    _exhentai_logged_in = False
    emit({"event": "exhentai_login_result", "success": False, "logout": True, "username": "", "message": "已退出登录"})
    _emit_login_info()


def _exhentai_throttle() -> None:
    """ExHentai 请求节流（防止触发 509 限制）。"""
    global _exhentai_last_request
    with _exhentai_lock:
        elapsed = time.time() - _exhentai_last_request
        wait = EXHENTAI_REQUEST_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)
        _exhentai_last_request = time.time()


def _exhentai_fetch(url: str, params: dict | None = None, timeout: int = 25) -> requests.Response:
    """带节流和 cookie 管理的 ExHentai 请求。

    igneous 处理策略：请求带缓存的 igneous；若返回空页（sadpanda/mystery），
    去掉 igneous 重试一次，让服务器重新下发有效 igneous。
    """
    _exhentai_throttle()
    cookie = _exhentai_cookie_str()
    headers = dict(_exhentai_session.headers)
    if cookie:
        headers["Cookie"] = cookie

    response = _exhentai_session.get(url, params=params, timeout=timeout, headers=headers)

    # 509 带宽限制：退避后重试一次
    if response.status_code == 509:
        logging.warning("ExHentai 返回 509（带宽限制），退避 10 秒后重试")
        time.sleep(10)
        _exhentai_throttle()
        response = _exhentai_session.get(url, params=params, timeout=timeout, headers=headers)

    # 检查是否返回了新 igneous（服务器每次都可能刷新）
    new_igneous = None
    for sc in response.headers.get("Set-Cookie", "").split(","):
        m = re.search(r"igneous=(\w+)", sc)
        if m:
            new_igneous = m.group(1)
            break

    if new_igneous == "mystery" or (not response.text and response.status_code == 200):
        # igneous 失效：去掉 igneous 重试，让服务器重新下发
        cookies = _exhentai_load_cookies()
        auth_parts = []
        for key in ("ipb_member_id", "ipb_pass_hash", "ipb_coppa"):
            if cookies.get(key):
                auth_parts.append(f"{key}={cookies[key]}")
        headers["Cookie"] = "; ".join(auth_parts)
        _exhentai_throttle()
        response = _exhentai_session.get(url, params=params, timeout=timeout, headers=headers)
        for sc in response.headers.get("Set-Cookie", "").split(","):
            m = re.search(r"igneous=(\w+)", sc)
            if m:
                new_igneous = m.group(1)
                break
        # 认证失败（依然空页）
        if new_igneous == "mystery" or (not response.text and response.status_code == 200):
            raise PermissionError(
                "ExHentai 登录已失效，请在 ExHentai 页面重新登录（浏览器视图）后重试"
            )

    if new_igneous and new_igneous != "mystery":
        cookies = _exhentai_load_cookies()
        if cookies.get("_igneous") != new_igneous:
            cookies["_igneous"] = new_igneous
            _exhentai_save_cookies(cookies)

    return response


def _exhentai_check_login() -> tuple[bool, str | None, str]:
    """检查 ExHentai 登录状态，返回 (是否成功, 用户名/IPB ID, 消息)。"""
    global _exhentai_logged_in
    cookies = _exhentai_load_cookies()
    if not cookies.get("ipb_member_id"):
        return False, None, "未配置 ExHentai 登录信息"
    try:
        response = _exhentai_fetch(EXHENTAI_HOST + "/")
        if response.status_code == 200 and len(response.text) > 5000:
            soup = BeautifulSoup(response.text, "html.parser")
            # 登录后页面顶部有 Favorites/My Uploads 链接
            logged = bool(soup.select_one("a[href*='favorites.php'], #userlinks"))
            _exhentai_logged_in = logged
            if logged:
                return True, cookies.get("ipb_member_id", ""), "ExHentai 登录有效"
        _exhentai_logged_in = False
        return False, None, "ExHentai 登录已失效，请重新同步 Cookie"
    except PermissionError:
        _exhentai_logged_in = False
        return False, None, "ExHentai 登录已失效，请重新同步 Cookie"
    except requests.RequestException as exc:
        _exhentai_logged_in = False
        return False, None, f"ExHentai 连接失败: {exc}（请检查代理设置）"


def is_exhentai_url(url: str) -> bool:
    """判断是否为 ExHentai 画廊链接。"""
    return bool(re.search(r"(e-hentai|exhentai)\.org/g/\d+/[0-9a-f]+", url, re.I))


def _exhentai_parse_gallery_url(url: str) -> dict | None:
    """解析画廊 URL，返回 {gid, token, host}。"""
    m = re.search(r"(https?://(?:e-hentai|exhentai)\.org)/g/(\d+)/([0-9a-f]+)/?", url, re.I)
    if not m:
        return None
    return {"host": m.group(1), "gid": m.group(2), "token": m.group(3)}


def _exhentai_parse_tags(soup: BeautifulSoup) -> dict[str, list[str]]:
    """解析画廊页 tag 表，返回 {分类: [tag, ...]}。"""
    tags: dict[str, list[str]] = {}
    for tr in soup.select("#taglist table tr"):
        tds = tr.select("td")
        if len(tds) < 2:
            continue
        cat = tds[0].get_text(strip=True).rstrip(":").lower()
        values = [a.get_text(strip=True) for a in tds[1].select("a") if a.get_text(strip=True)]
        if cat and values:
            tags[cat] = values
    return tags


def _exhentai_parse_posted_date(soup: BeautifulSoup) -> str:
    """解析画廊发布时间（ISO 格式），解析失败返回空串。"""
    for tr in soup.select("#gdd table tr"):
        text = tr.get_text(" ", strip=True)
        m = re.search(r"Posted:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", text)
        if m:
            return f"{m.group(1)}T{m.group(2)}:00"
    return ""


def _exhentai_artist_folder(tags: dict[str, list[str]], gallery_title: str) -> str:
    """根据画师/社团 tag 推断父文件夹名（同一个画师归到同一文件夹）。"""
    artists = tags.get("artist") or []
    if artists:
        return artists[0]
    groups = tags.get("group") or []
    if groups:
        return groups[0]
    # 无画师/社团 tag：用画廊标题前缀 [社团 (画师)] 提取
    m = re.match(r"\[([^\]]+)\]", gallery_title)
    if m:
        return m.group(1)[:60]
    return "Unknown Artist"


def _exhentai_image_filename(image_url: str, page_no: int, total: int) -> str:
    """从 hath 直链提取文件名；提取失败时用页码命名。"""
    # URL 形如 https://xxx.hath.network:44000/h/<hash>/keystamp=...;fileindex=...;xres=.../name.webp
    m = re.search(r"/([^/?;]+?)(?:\?|$)", image_url)
    name = m.group(1) if m else ""
    if name and Path(name).suffix:
        return name
    return f"page_{page_no:04d}.webp"


async def exhentai_inspect(url: str, options: dict) -> None:
    """解析 ExHentai 画廊：标题/tags/日期 + 全部图片直链（增量标记 is_new）。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "inspect_error", "message": "无法识别的 ExHentai 画廊链接（格式: /g/{id}/{token}/）"})
        return

    gallery_key = f"exhentai_{info['gid']}"
    try:
        # ---------- 缓存 ----------
        cached = _load_album_cache(gallery_key)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or gallery_key, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or info["gid"],
                "album_id": cached.get("album_id") or gallery_key,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 ExHentai 画廊信息: %s (%d 个文件)", gallery_key, len(items))
            return

        # ---------- 画廊首页 ----------
        gallery_url = f"{info['host']}/g/{info['gid']}/{info['token']}/"
        response = await asyncio.to_thread(_exhentai_fetch, gallery_url)
        soup = BeautifulSoup(response.text, "html.parser")

        gn = soup.select_one("#gn")
        gallery_title = gn.get_text(strip=True) if gn else f"Gallery {info['gid']}"
        tags = _exhentai_parse_tags(soup)
        posted_date = _exhentai_parse_posted_date(soup)
        artist_folder = _exhentai_artist_folder(tags, gallery_title)

        # 页数信息（"Showing 1 - 40 of 92 images"）
        total_pages_count = 0
        gpc = soup.select_one(".gpc")
        if gpc:
            m = re.search(r"of\s+(\d+)\s+images", gpc.get_text())
            if m:
                total_pages_count = int(m.group(1))

        # ---------- 翻页收集全部图片页链接（附带画廊缩略图页上的稳定小图） ----------
        # 缩略图（ehgt.org / e-hentai.org 域名，长期有效）用于文件列表展示；
        # 直链（*.hath.network 带 keystamp 时效签名）仅用于下载。
        image_pages: list[tuple[str, str]] = []   # (图片页链接, 稳定缩略图)
        page_no = 0
        while True:
            page_url = gallery_url if page_no == 0 else f"{gallery_url}?p={page_no}"
            if page_no > 0:
                response = await asyncio.to_thread(_exhentai_fetch, page_url)
                soup = BeautifulSoup(response.text, "html.parser")
            page_entries: list[tuple[str, str]] = []
            for a in soup.select("#gdt a"):
                href = a.get("href", "")
                if not href.startswith("http"):
                    continue
                img_el = a.select_one("img")
                thumb = ""
                if img_el:
                    thumb = img_el.get("data-src") or img_el.get("src") or ""
                page_entries.append((href, thumb))
            if not page_entries:
                break
            image_pages.extend(page_entries)
            if len(page_entries) < EXHENTAI_GALLERY_PAGE_SIZE or (
                total_pages_count and len(image_pages) >= total_pages_count
            ):
                break
            page_no += 1

        if not image_pages:
            emit({"event": "inspect_error", "message": "画廊中没有找到图片（可能需要登录或画廊已被删除）"})
            return

        # 去重（缩略图页可能重复出现）
        seen = set()
        image_pages = [e for e in image_pages if not (e[0] in seen or seen.add(e[0]))]

        # ---------- 并发解析图片直链（并发调度 + 全局节流限速，比逐张串行快数倍） ----------
        total = len(image_pages)
        emit({"event": "inspect_progress", "current": 0, "total": total, "filename": ""})
        logging.info("ExHentai 画廊 '%s' 共 %d 张图片", gallery_title, total)

        semaphore = asyncio.Semaphore(4)
        progress_lock = asyncio.Lock()
        completed = 0

        async def fetch_one(idx: int, entry: tuple[str, str]) -> dict | None:
            nonlocal completed
            page_url, gdt_thumb = entry
            async with semaphore:
                try:
                    page_resp = await asyncio.to_thread(_exhentai_fetch, page_url)
                    page_soup = BeautifulSoup(page_resp.text, "html.parser")
                    img = page_soup.select_one("#img")
                    src = img.get("src", "") if img else ""
                    if not src.startswith("http"):
                        return None
                    filename = _exhentai_image_filename(src, idx + 1, total)
                    return {
                        "filename": filename,
                        "size": None,
                        "item_page": page_url,
                        "status": "ok",
                        # 展示用稳定缩略图（ehgt.org），下载时重新解析直链
                        "thumbnail": gdt_thumb or src,
                        "media_url": src,
                        "site": "exhentai",
                        "post_title": gallery_title,
                        "post_date": posted_date,
                        "artist": artist_folder,
                        "gallery_url": gallery_url,
                    }
                except (requests.RequestException, PermissionError) as exc:
                    logging.warning("ExHentai 图片页解析失败 %s: %s", page_url, exc)
                    return None
                finally:
                    async with progress_lock:
                        completed += 1
                        if completed % 5 == 0 or completed == total:
                            emit({
                                "event": "inspect_progress",
                                "current": completed,
                                "total": total,
                                "filename": "",
                            })

        results = await asyncio.gather(
            *(fetch_one(i, e) for i, e in enumerate(image_pages))
        )
        # 保持画廊顺序
        items: list[dict] = [r for r in results if r]

        if not items:
            emit({"event": "inspect_error", "message": "无法解析画廊图片（登录可能已失效）"})
            return

        _apply_cached_thumbnails(items)
        _mark_items_new(gallery_key, items)

        _save_album_cache(gallery_key, {
            "album_name": gallery_title,
            "album_id": gallery_key,
            "is_album": True,
            "items": items,
        })

        emit({
            "event": "inspect_complete",
            "album_name": gallery_title,
            "album_id": gallery_key,
            "is_album": True,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 画廊解析完成: %s, 共 %d 个文件", gallery_title, len(items))

    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "inspect_error", "message": f"ExHentai 访问失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 解析出错")
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("ExHentai 解析过程出错")


# ============================
# ExHentai 磁力链接（torrent）
# ============================
def _bdecode(data: bytes, pos: int = 0):
    """简易 bencode 解码器（解析 .torrent 文件用）。"""
    c = data[pos:pos + 1]
    if c == b"i":
        end = data.index(b"e", pos)
        return int(data[pos + 1:end]), end + 1
    if c == b"l":
        pos += 1
        result = []
        while data[pos:pos + 1] != b"e":
            v, pos = _bdecode(data, pos)
            result.append(v)
        return result, pos + 1
    if c == b"d":
        pos += 1
        result = {}
        while data[pos:pos + 1] != b"e":
            k, pos = _bdecode(data, pos)
            v, pos = _bdecode(data, pos)
            result[k] = v
        return result, pos + 1
    colon = data.index(b":", pos)
    length = int(data[pos:colon])
    start = colon + 1
    return data[start:start + length], start + length


def _torrent_infohash(torrent_data: bytes) -> str | None:
    """从 .torrent 文件字节中提取 infohash（构造磁力链接用）。"""
    try:
        idx = torrent_data.find(b"4:infod")
        if idx < 0:
            idx = torrent_data.find(b"4:infol")
        if idx < 0:
            return None
        pos = idx + 6
        _, end = _bdecode(torrent_data, pos)
        info_bytes = torrent_data[pos:end]
        return hashlib.sha1(info_bytes).hexdigest()
    except (ValueError, IndexError):
        return None


async def exhentai_get_torrents(url: str) -> None:
    """获取画廊的种子列表（弹窗选择用）。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "exhentai_torrents_error", "message": "无效的画廊链接"})
        return
    try:
        response = await asyncio.to_thread(
            _exhentai_fetch,
            f"{EXHENTAI_HOST}/gallerytorrents.php",
            {"gid": info["gid"], "t": info["token"]},
        )
        soup = BeautifulSoup(response.text, "html.parser")

        torrents = []
        # 每个种子一行：.torrent 下载链接 + 名称/大小/做种信息
        forms = soup.select("form")
        rows = soup.select("tr")
        # 通用解析：找所有 .torrent 链接，按行关联信息
        torrent_links = [a for a in soup.select("a[href$='.torrent']")]
        for link in torrent_links:
            href = link.get("href", "")
            if href.startswith("/"):
                href = EXHENTAI_HOST + href
            # 从所在行提取信息
            row = link.find_parent("tr") or link.find_parent("div")
            row_text = row.get_text(" ", strip=True) if row else ""
            size_m = re.search(r"Size:\s*([\d.]+\s*[KMG]?i?B)", row_text)
            posted_m = re.search(r"Posted:\s*([\d-]+\s+[\d:]+)", row_text)
            seeds_m = re.search(r"Seeds:\s*(\d+)", row_text)
            peers_m = re.search(r"Peers:\s*(\d+)", row_text)
            # 种子名：链接文本或行内长文本
            name = link.get_text(strip=True)
            if not name and row:
                # 名称通常是行里最长的文本块
                texts = [t.strip() for t in row.stripped_strings if len(t.strip()) > 8]
                name = texts[0] if texts else "torrent"
            torrents.append({
                "name": name or "torrent",
                "url": href,
                "size": size_m.group(1) if size_m else "",
                "posted": posted_m.group(1) if posted_m else "",
                "seeds": int(seeds_m.group(1)) if seeds_m else 0,
                "peers": int(peers_m.group(1)) if peers_m else 0,
            })

        if not torrents:
            emit({"event": "exhentai_torrents", "torrents": [], "message": "该画廊没有可用的种子"})
            return

        emit({"event": "exhentai_torrents", "torrents": torrents})
        logging.info("ExHentai 种子列表: %d 个", len(torrents))

    except PermissionError as exc:
        emit({"event": "exhentai_torrents_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "exhentai_torrents_error", "message": f"获取种子失败: {exc}"})
        logging.exception("ExHentai 获取种子失败")


async def exhentai_get_magnet(torrent_url: str) -> None:
    """下载 .torrent 文件并解析出磁力链接。"""
    try:
        response = await asyncio.to_thread(_exhentai_fetch, torrent_url)
        if response.status_code != 200 or not response.content[:1] == b"d":
            emit({"event": "exhentai_magnet_error", "message": "种子文件下载失败"})
            return
        infohash = _torrent_infohash(response.content)
        if not infohash:
            emit({"event": "exhentai_magnet_error", "message": "无法解析种子文件"})
            return
        # 从种子文件内提取真实名称（info.name）
        dn = ""
        try:
            data, _ = _bdecode(response.content)
            if isinstance(data, dict):
                info = data.get(b"info")
                if isinstance(info, dict) and info.get(b"name"):
                    dn = info[b"name"].decode("utf-8", "replace")
        except (ValueError, IndexError):
            pass
        magnet = f"magnet:?xt=urn:btih:{infohash}"
        if dn:
            from urllib.parse import quote
            magnet += f"&dn={quote(dn)}"
        magnet += "&tr=http://ehtracker.org/announce"
        emit({"event": "exhentai_magnet", "magnet": magnet, "infohash": infohash, "name": dn})
        logging.info("ExHentai 磁力链接: %s (%s)", infohash, dn)
    except PermissionError as exc:
        emit({"event": "exhentai_magnet_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "exhentai_magnet_error", "message": f"种子下载失败: {exc}"})
        logging.exception("ExHentai 磁力解析失败")


async def exhentai_favorites(page: int = 1) -> None:
    """获取我的收藏列表（favorites.php，next 游标分页，复用搜索结果视图）。"""
    page = max(1, int(page))
    try:
        emit({"event": "search_start", "query": "__ex_favorites__", "page": page})
        cursors = _load_ex_cursors()
        entry = cursors.get("__ex_favorites__", {})
        if not isinstance(entry, dict):
            entry = {}
        pages_map = {int(k): v for k, v in entry.items() if str(k).isdigit()}

        cur = 1
        for p in sorted(pages_map):
            if p <= page:
                cur = max(cur, p)

        html = ""
        items: list[dict] = []
        while cur <= page:
            params: dict = {}
            if cur > 1:
                cursor = pages_map.get(cur)
                if cursor is None:
                    break
                params["next"] = cursor
            response = await asyncio.to_thread(_exhentai_fetch, EXHENTAI_HOST + "/favorites.php", params)
            html = response.text
            gids = _parse_ex_gallery_ids(html)
            if cur == page:
                items = _parse_ex_search_page(html)
                if gids:
                    pages_map[page + 1] = gids[-1]
                break
            if not gids:
                break
            pages_map[cur + 1] = gids[-1]
            cur += 1

        if page > 1 and not items and not pages_map.get(page):
            emit({"event": "search_error", "message": f"收藏第 {page} 页不存在或超出范围"})
            return

        # 收藏页无总数提示："Showing 1 - 25 of 89"（无 about）
        total_results = entry.get("total_results") or 0
        m = re.search(r"(?:of|about)\s+([\d,]+)\s+(?:results|entries)", html)
        if m:
            try:
                total_results = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        per_page = len(items) or 25
        # 无总数提示（单页放得下）时 total_pages=0（未知），分页栏仅靠 has_more 翻页
        total_pages = max(1, -(-total_results // per_page)) if total_results > 0 else 0
        has_next = bool(re.search(r"[?&]next=\d+", html)) and bool(items)

        entry = {"total_results": total_results}
        for p, gid in sorted(pages_map.items()):
            entry[str(p)] = gid
        cursors["__ex_favorites__"] = entry
        _save_ex_cursors(cursors)

        # 隐藏标签过滤（用户手动标记的 tags 不显示）
        items, hidden_count = _exhentai_filter_hidden_tags(items)

        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": "__ex_favorites__",
            "page": page,
            "total_pages": total_pages,
            "total_results": total_results,
            "has_more": has_next,
            "hidden_count": hidden_count,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 我的收藏: 第 %d 页，%d 个（隐藏 %d）", page, len(items), hidden_count)

    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "search_error", "message": f"获取收藏失败: {exc}（请检查登录状态和代理）"})
        logging.exception("ExHentai 收藏获取失败")


def _exhentai_parse_image_entries(soup: BeautifulSoup) -> list[dict]:
    """解析画廊缩略图页的 #gdt：图片页链接 + 稳定缩略图（详情页图片列表用）。"""
    entries = []
    for a in soup.select("#gdt a"):
        page_url = a.get("href", "")
        if not page_url.startswith("http"):
            continue
        img_el = a.select_one("img")
        thumb = ""
        if img_el:
            thumb = img_el.get("data-src") or img_el.get("src") or ""
        entries.append({"page_url": page_url, "thumb": thumb})
    return entries


def _exhentai_gallery_pages(soup: BeautifulSoup) -> int:
    """从分页表 .ptt 解析画廊缩略图页总数。"""
    nums = []
    for td in soup.select(".ptt td"):
        t = td.get_text(strip=True)
        if t.isdigit():
            nums.append(int(t))
    return max(nums) if nums else 1


async def exhentai_gallery_info(url: str) -> None:
    """获取画廊完整信息（标题/上传者/发布时间/父画廊/大小/页数/收藏数/评分/全部分组标签）。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "ex_gallery_info_error", "message": "无效的画廊链接"})
        return
    try:
        gallery_url = f"{info['host']}/g/{info['gid']}/{info['token']}/"
        response = await asyncio.to_thread(_exhentai_fetch, gallery_url)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("#gn")
        title = title.get_text(strip=True) if title else f"Gallery {info['gid']}"
        title_jp = soup.select_one("#gj")
        title_jp = title_jp.get_text(strip=True) if title_jp else ""

        uploader = ""
        gdn = soup.select_one("#gdn a")
        if gdn:
            uploader = gdn.get_text(strip=True)

        posted = ""
        posted_raw = _exhentai_parse_posted_date(soup)
        if posted_raw:
            posted = posted_raw.replace("T", " ")[:16]

        # 元数据表（#gdd）：Parent / Visible / Language / File Size / Length / Favorited
        parent = ""
        visible = ""
        language = ""
        file_size = ""
        length = ""
        favorited = ""
        for tr in soup.select("#gdd tr"):
            label_td = tr.select_one("td.gdt1")
            value_td = tr.select_one("td.gdt2")
            if not label_td or not value_td:
                continue
            label = label_td.get_text(strip=True).rstrip(":").lower()
            value = value_td.get_text(strip=True)
            if label == "parent":
                link = value_td.select_one("a#parent_link") or value_td.select_one("a")
                parent = link.get("href", "") if link else ""
            elif label == "visible":
                visible = value
            elif label == "language":
                language = value
            elif label == "file size":
                file_size = value
            elif label == "length":
                length = value
            elif label == "favorited":
                favorited = value

        # 评分：#rating_label "Average: 4.70" + #rating_count "146"
        rating = ""
        rating_count = ""
        rating_label = soup.select_one("#rating_label")
        if rating_label:
            text = rating_label.get_text(strip=True)
            m = re.search(r"Average:\s*([\d.]+)", text)
            if m:
                rating = m.group(1)
        rating_count_el = soup.select_one("#rating_count")
        if rating_count_el:
            rating_count = rating_count_el.get_text(strip=True)

        # 分组标签（female:/male:/mixed:/artist:/group:/parody: 等）
        tags = _exhentai_parse_tags(soup)

        # 图片列表（缩略图页第 0 页的 #gdt 稳定缩略图，tag 下方展示 + 翻页浏览）
        images = _exhentai_parse_image_entries(soup)
        gallery_pages = _exhentai_gallery_pages(soup)
        image_count = 0
        gpc_text = soup.select_one(".gpc")
        if gpc_text:
            m_cnt = re.search(r"of\s+(\d+)\s+images", gpc_text.get_text())
            if m_cnt:
                image_count = int(m_cnt.group(1))
        if not image_count:
            image_count = len(images)
        if images:
            # 稳定缩略图走本地缓存（ehgt.org 需带 cookie + 代理）
            thumb_items = [{"thumbnail": e["thumb"]} for e in images]
            _apply_cached_thumbnails(thumb_items)
            for e, ti in zip(images, thumb_items):
                if ti.get("thumbnail").startswith("thumb://"):
                    e["thumb"] = ti["thumbnail"]
            asyncio.create_task(_cache_thumbnails(thumb_items))

        # 封面缩略图（同步下载到本地缓存：前端 img 无法带 EX cookie 加载远程封面）
        # 两种形式：#gd1 内 img 标签，或 #gd1 div 的 background:url() 样式
        thumb = ""
        gd1 = soup.select_one("#gd1")
        if gd1:
            img_el = gd1.select_one("img")
            if img_el:
                thumb = img_el.get("data-src") or img_el.get("src") or ""
            else:
                style = gd1.select_one("div").get("style", "") if gd1.select_one("div") else ""
                m_bg = re.search(r"url\((https?://[^)]+)\)", style or "")
                if m_bg:
                    thumb = m_bg.group(1)
        if thumb:
            try:
                cache_path = _thumbnail_cache_path(thumb)
                if not cache_path.exists() or not _is_valid_cache_file(cache_path):
                    Path(THUMBNAIL_CACHE_DIR).mkdir(parents=True, exist_ok=True)
                    headers = dict(THUMB_HEADERS)
                    headers["Referer"] = f"{EXHENTAI_HOST}/"
                    cookie = _exhentai_cookie_str()
                    if cookie:
                        headers["Cookie"] = cookie
                    img_resp = _exhentai_session.get(thumb, timeout=10, headers=headers)
                    if img_resp.ok and img_resp.content[:1] in (b"\xff", b"\x89", b"G"):
                        cache_path.write_bytes(img_resp.content)
                if cache_path.exists() and _is_valid_cache_file(cache_path):
                    thumb = f"thumb://local/{cache_path.name}"
            except requests.RequestException as exc:
                logging.warning("画廊封面下载失败: %s", exc)

        emit({
            "event": "ex_gallery_info",
            "url": gallery_url,
            "title": title,
            "title_jp": title_jp,
            "uploader": uploader,
            "posted": posted,
            "parent": parent,
            "visible": visible,
            "language": language,
            "file_size": file_size,
            "length": length,
            "favorited": favorited,
            "rating": rating,
            "rating_count": rating_count,
            "tags": tags,
            "thumbnail": thumb,
            "images": images,
            "image_count": image_count,
            "gallery_page": 0,
            "gallery_pages": gallery_pages,
        })
        logging.info("ExHentai 画廊信息: %s", title[:50])

    except PermissionError as exc:
        emit({"event": "ex_gallery_info_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "ex_gallery_info_error", "message": f"获取画廊信息失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 画廊信息获取失败")


async def exhentai_gallery_page(url: str, page: int = 0) -> None:
    """画廊详情页图片列表翻页：解析指定缩略图页的 #gdt 稳定缩略图。"""
    info = _exhentai_parse_gallery_url(url)
    if info is None:
        emit({"event": "ex_gallery_page_error", "message": "无效的画廊链接"})
        return
    try:
        gallery_url = f"{info['host']}/g/{info['gid']}/{info['token']}/"
        target = gallery_url if page <= 0 else f"{gallery_url}?p={page}"
        response = await asyncio.to_thread(_exhentai_fetch, target)
        soup = BeautifulSoup(response.text, "html.parser")
        images = _exhentai_parse_image_entries(soup)
        gallery_pages = _exhentai_gallery_pages(soup)
        thumb_items = [{"thumbnail": e["thumb"]} for e in images]
        _apply_cached_thumbnails(thumb_items)
        for e, ti in zip(images, thumb_items):
            if ti.get("thumbnail").startswith("thumb://"):
                e["thumb"] = ti["thumbnail"]
        asyncio.create_task(_cache_thumbnails(thumb_items))
        emit({
            "event": "ex_gallery_page",
            "url": gallery_url,
            "page": max(0, page),
            "pages": gallery_pages,
            "images": images,
        })
    except PermissionError as exc:
        emit({"event": "ex_gallery_page_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "ex_gallery_page_error", "message": f"获取画廊图片页失败: {exc}"})
        logging.exception("ExHentai 画廊图片页获取失败")


def _exhentai_image_page_with_nl(page_url: str) -> str:
    """解析图片页，返回带 ?nl=token 的刷新链接（原站"图片加载失败点击刷新"）。

    H@H 节点故障时，带 nl 参数重新请求图片页会换一个节点返回新直链。
    """
    response = _exhentai_fetch(page_url)
    m = re.search(r"nl\(['\"]([^'\"]+)['\"]\)", response.text)
    token = m.group(1) if m else ""
    if not token:
        return page_url
    sep = "&" if "?" in page_url else "?"
    return f"{page_url}{sep}nl={token}"


async def exhentai_reload_image(item_page: str) -> None:
    """刷新失效图片：走原站 nl 链接强制换 H@H 节点，重新解析直链。"""
    if not item_page.startswith("http"):
        emit({"event": "ex_image_reloaded", "item_page": item_page, "media_url": "", "success": False,
              "message": "无效的图片页链接"})
        return

    def _reload() -> str:
        reload_url = _exhentai_image_page_with_nl(item_page)
        resp = _exhentai_fetch(reload_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        img = soup.select_one("#img")
        src = (img.get("src") or "") if img else ""
        return src if src.startswith("http") else ""

    try:
        media_url = await asyncio.to_thread(_reload)
        emit({
            "event": "ex_image_reloaded",
            "item_page": item_page,
            "media_url": media_url,
            "thumbnail": media_url,
            "success": bool(media_url),
            "message": "" if media_url else "刷新失败：未能解析出新直链（登录可能已失效）",
        })
    except Exception as exc:
        emit({
            "event": "ex_image_reloaded",
            "item_page": item_page,
            "media_url": "",
            "success": False,
            "message": f"刷新失败: {exc}",
        })


async def exhentai_save_torrent(torrent_url: str, name: str = "") -> None:
    """下载 .torrent 种子文件并保存到 downloads/torrents/。"""
    try:
        response = await asyncio.to_thread(_exhentai_fetch, torrent_url)
        if response.status_code != 200 or not response.content[:1] == b"d":
            emit({"event": "ex_torrent_saved", "success": False, "message": "种子文件下载失败"})
            return
        # 文件名：优先种子内名称，其次传入名称，最后时间戳
        dn = name
        if not dn:
            try:
                data, _ = _bdecode(response.content)
                if isinstance(data, dict):
                    info = data.get(b"info")
                    if isinstance(info, dict) and info.get(b"name"):
                        dn = info[b"name"].decode("utf-8", "replace")
            except (ValueError, IndexError):
                pass
        safe = re.sub(r'[\\/:*?"<>|]', "_", (dn or f"torrent_{int(time.time())}").strip())[:150]
        save_dir = Path("downloads") / "torrents"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"{safe}.torrent"
        save_path.write_bytes(response.content)
        emit({
            "event": "ex_torrent_saved",
            "success": True,
            "path": str(save_path),
            "message": f"种子已保存: {save_path}",
        })
        logging.info("ExHentai 种子已保存: %s", save_path)

    except PermissionError as exc:
        emit({"event": "ex_torrent_saved", "success": False, "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "ex_torrent_saved", "success": False, "message": f"种子下载失败: {exc}"})
        logging.exception("ExHentai 种子保存失败")


# ============================
# Twitter/X 站点支持 (x.com)
# ============================
# 站点特点（参考 X-Spider 项目的实现）：
# - API 走 GraphQL，需要账号 cookie（auth_token + ct0）+ 网页版公开 Bearer Token + X-Csrf-Token
# - 国内需代理访问（x.com / pbs.twimg.com / video.twimg.com 均被墙）
# - 媒体直链（pbs.twimg.com 图片 / video.twimg.com 视频）永久有效、无需 cookie，但下载需走代理
# - 单条推文可用公开的 syndication API（cdn.syndication.twimg.com）免登录解析
TWITTER_HOST = "https://x.com"
TWITTER_REQUEST_INTERVAL = 0.8    # GraphQL 请求最小间隔（秒），顺序请求仍远低于浏览器并发量
TWITTER_DOWNLOAD_INTERVAL = 0.5   # 媒体下载最小间隔（秒）
TWITTER_DEFAULT_PROXY = "http://127.0.0.1:10809"
# 网页版公开 Bearer Token（所有浏览器一致，非机密）
TWITTER_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

_twitter_session = requests.Session()
_twitter_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": TWITTER_HOST + "/",
    "Origin": TWITTER_HOST,
})
_twitter_proxy: str | None = None
_twitter_last_request = 0.0
_twitter_last_download = 0.0
_twitter_lock = threading.Lock()

# GraphQL queryId 注册表（X 每隔数周轮换，404 时自动从 x.com main.js 刷新）
TWITTER_QIDS_FILE = "cache/twitter_qids.json"
TWITTER_QID_DEFAULTS = {
    "Viewer": "5XShkXk2oO2J7SYmTu6pvw",
    "UserByScreenName": "NimuplG1OB7Fd2btCLdBOw",
    "UserMedia": "cEjpJXA15Ok78yO4TUQPeQ",
    "TweetDetail": "xOhkmRac04ABXieVxwgAUg",
    # 内容搜索（404 时自动从 main.js 刷新）
    "SearchTimeline": "hyPfJYJ_XAtDYoslQc-Rgg",
    # 关注/取关 mutation（v1.1 失效时的 GraphQL 回退，queryId 由 main.js 自动刷新）
    "CreateFollower": "",
    "DeleteFollower": "",
}
_twitter_query_ids: dict = {}


def _twitter_qid(op: str) -> str:
    """取 GraphQL queryId（优先用缓存刷新过的值，无则用内置默认）。"""
    if not _twitter_query_ids:
        _twitter_query_ids.update(TWITTER_QID_DEFAULTS)
        try:
            with open(TWITTER_QIDS_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                _twitter_query_ids.update({k: v for k, v in cached.items() if v})
        except (OSError, json.JSONDecodeError):
            pass
    return _twitter_query_ids.get(op) or ""


def _twitter_refresh_qids(include_mutations: bool = False) -> bool:
    """从 x.com 首页 main.js 抓取最新 queryId（queryId 过期 404 时自动恢复）。

    include_mutations=True 时同时抓取 mutation（关注/取关等写操作）的 queryId。
    """
    import re

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
        }
        # 必须带登录 Cookie：未登录首页不含 main.js 引用，无法提取 queryId
        cookie = _twitter_cookie_str()
        if cookie:
            headers["Cookie"] = cookie
        response = requests.get(
            TWITTER_HOST, headers=headers,
            proxies=_twitter_session.proxies or None, timeout=20,
        )
        m = re.search(
            r'https://abs\.twimg\.com/responsive-web/client-web/main\.[0-9a-f]+\.js',
            response.text,
        )
        if not m:
            return False
        js = _twitter_session.get(m.group(0), timeout=60).text
        op_types = r'query|mutation' if include_mutations else 'query'
        pairs = re.findall(
            r'queryId:"([^"]{10,30})",operationName:"([^"]+)",operationType:"(?:%s)"' % op_types,
            js,
        )
        updated = False
        for qid, name in pairs:
            if name in TWITTER_QID_DEFAULTS:
                _twitter_qid(name)  # 确保已初始化
                if _twitter_query_ids.get(name) != qid:
                    _twitter_query_ids[name] = qid
                    updated = True
        if updated:
            logging.info("Twitter GraphQL queryId 已刷新: %s",
                         {k: v for k, v in _twitter_query_ids.items()
                          if k in TWITTER_QID_DEFAULTS})
            try:
                Path("cache").mkdir(parents=True, exist_ok=True)
                with open(TWITTER_QIDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(_twitter_query_ids, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
        return updated
    except (requests.RequestException, OSError) as exc:
        logging.warning("刷新 Twitter queryId 失败: %s", exc)
        return False


def twitter_set_proxy(proxy: str | None) -> None:
    """设置 Twitter 访问代理（API 和媒体下载都走此代理）。"""
    global _twitter_proxy
    _twitter_proxy = (proxy or "").strip() or None
    if _twitter_proxy:
        _twitter_session.proxies.update({"http": _twitter_proxy, "https": _twitter_proxy})
    else:
        _twitter_session.proxies.clear()
    logging.info("Twitter 代理已设置: %s", _twitter_proxy or "（直连）")


def _twitter_load_cookies() -> dict:
    """读取已保存的 Twitter cookie（加密账号存储）。"""
    return _secure_store_read_cred("twitter")


def _twitter_save_cookies(cookies: dict) -> None:
    """保存 Twitter cookie（长期保持登录状态，加密存储）。"""
    data = dict(cookies)
    data["_saved_at"] = time.time()
    _secure_store_write_cred("twitter", data)


def _twitter_cookie_str() -> str:
    """拼接 API 请求所需的 Cookie 头（auth_token + ct0）。"""
    cookies = _twitter_load_cookies()
    parts = []
    if cookies.get("auth_token"):
        parts.append(f"auth_token={cookies['auth_token']}")
    if cookies.get("ct0"):
        parts.append(f"ct0={cookies['ct0']}")
    return "; ".join(parts)


def _twitter_throttle() -> None:
    """GraphQL 请求节流。"""
    global _twitter_last_request
    with _twitter_lock:
        elapsed = time.time() - _twitter_last_request
        wait = TWITTER_REQUEST_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)
        _twitter_last_request = time.time()


def _twitter_throttle_download() -> None:
    """媒体下载节流。"""
    global _twitter_last_download
    with _twitter_lock:
        elapsed = time.time() - _twitter_last_download
        wait = TWITTER_DOWNLOAD_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)
        _twitter_last_download = time.time()


def _twitter_head_size(media_url: str) -> int | None:
    """HEAD 预取媒体文件大小（用于下载去重的大小对比）。"""
    try:
        _twitter_throttle_download()
        resp = _twitter_session.head(
            media_url, timeout=20, headers={"Referer": TWITTER_HOST + "/"},
        )
        if resp.status_code == 200:
            return int(resp.headers.get("Content-Length") or 0) or None
    except (requests.RequestException, ValueError):
        pass
    return None


def is_twitter_url(url: str) -> bool:
    """判断是否为 Twitter/X 链接（x.com / twitter.com 用户页或推文页）。"""
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    return netloc in ("x.com", "twitter.com", "www.x.com", "www.twitter.com") or \
        netloc.endswith(".x.com") or netloc.endswith(".twitter.com")


def _twitter_parse_url(url: str) -> dict | None:
    """解析 Twitter URL。

    支持的格式：
      https://x.com/{screen_name}            用户主页（解析全部媒体）
      https://x.com/{screen_name}/status/{id}   单条推文
    """
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    if "intent" in parts or "i" == parts[0]:
        return None
    if len(parts) >= 3 and parts[1] == "status":
        try:
            status_id = int(parts[2])
        except ValueError:
            return None
        return {"kind": "status", "screen_name": parts[0], "status_id": str(status_id)}
    if len(parts) == 1:
        return {"kind": "user", "screen_name": parts[0], "status_id": None}
    return None


def _twitter_api_get(query_id: str, endpoint: str, features: dict, variables: dict,
                     extra_params: dict | None = None, use_post: bool = False) -> dict:
    """调用 x.com GraphQL API（带 Bearer + cookie + csrf；queryId 过期 404 时自动刷新重试）。

    use_post=True 时改用 POST 方式（部分端点如 SearchTimeline 对 GET 请求
    强制校验 x-client-transaction-id 头，缺失直接 404；POST 可绕过）。
    """
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise PermissionError("未登录 Twitter，请先在设置中填写 Cookie")
    qid = _twitter_qid(endpoint) or query_id
    params = {
        "features": json.dumps(features),
        "variables": json.dumps(variables),
    }
    if extra_params:
        params.update(extra_params)
    while True:
        _twitter_throttle()
        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Cookie": _twitter_cookie_str(),
            "X-Csrf-Token": cookies["ct0"],
            "Referer": TWITTER_HOST + "/",
            "Origin": TWITTER_HOST,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }
        if use_post:
            # POST 方式：variables/features 放请求体（网页端同款结构）
            headers["Content-Type"] = "application/json"
            payload = {"queryId": qid, "variables": variables, "features": features}
            response = _twitter_session.post(
                f"{TWITTER_HOST}/i/api/graphql/{qid}/{endpoint}",
                json=payload, headers=headers, timeout=20,
            )
        else:
            response = _twitter_session.get(
                f"{TWITTER_HOST}/i/api/graphql/{qid}/{endpoint}",
                params=params, headers=headers, timeout=20,
            )
        if response.status_code == 404:
            # queryId 被 X 轮换过期：从 main.js 刷新后重试一次
            if _twitter_refresh_qids():
                new_qid = _twitter_qid(endpoint)
                if new_qid and new_qid != qid:
                    qid = new_qid
                    continue
            raise requests.HTTPError(
                f"404：GraphQL 查询 {endpoint} 不存在（queryId 可能已过期）",
                response=response,
            )
        if response.status_code in (401, 403):
            raise PermissionError("Twitter 登录已失效，请重新填写 Cookie")
        if response.status_code == 429:
            raise PermissionError("Twitter API 被限流，请稍后再试")
        response.raise_for_status()
        return response.json()


# GraphQL features 常量（复刻 X-Spider：每个查询用专属 features，混用会 400/漏数据）
# UserByScreenName 专属（X-Spider src/twitter/api.ts getUser）
_TW_USER_FEATURES = {
    "hidden_profile_likes_enabled": True,
    "hidden_profile_subscriptions_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
# UserMedia 专属（X-Spider src/twitter/api.ts getUserMedias）
_TW_MEDIA_FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}
# TweetDetail 专用（X-Spider 无此查询，保留网页版 features）
_TW_FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}
# SearchTimeline 专属（GET 方式会被 x-client-transaction-id 校验拦截返回 404，
# 必须用 POST + 此 features 集合调用）
_TW_SEARCH_FEATURES = {
    "blue_business_profile_image_shape_enabled": False,
    "responsive_web_graphql_exclude_directive_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def _twitter_check_login() -> tuple[bool, str | None, str]:
    """检查 Twitter 登录状态：GraphQL Viewer 查询（返回当前登录用户）。

    旧的 v1.1 verify_credentials 端点已被 X 下线（404），改用 Viewer。
    """
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token"):
        return False, None, "未配置 Twitter 登录信息"
    if not cookies.get("ct0"):
        return False, None, "Cookie 缺少 ct0，请复制完整 Cookie"
    try:
        data = _twitter_api_get(
            _twitter_qid("Viewer"), "Viewer", _TW_USER_FEATURES, {},
        )
        result = ((((data.get("data") or {}).get("viewer") or {})
                   .get("user_results") or {}).get("result")) or {}
        screen_name = ((result.get("core") or {}).get("screen_name")) or ""
        if screen_name:
            return True, screen_name, "Twitter 登录有效"
        return False, None, "Twitter 返回数据异常，请稍后重试"
    except PermissionError as exc:
        return False, None, str(exc)
    except (requests.RequestException, ValueError) as exc:
        return False, None, f"Twitter 连接失败: {exc}（请检查代理设置）"


def twitter_set_cookies(cookie_str: str) -> None:
    """用户手动粘贴 cookie 字符串（auth_token=...; ct0=...），保存并验证。"""
    cookies: dict = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            if name.strip():
                cookies[name.strip()] = value.strip()
    if not cookies.get("auth_token"):
        emit({
            "event": "twitter_login_result",
            "success": False,
            "message": "Cookie 缺少 auth_token，请在浏览器登录 x.com 后复制 Cookie",
        })
        return
    _twitter_save_cookies({k: v for k, v in cookies.items() if k in ("auth_token", "ct0")})
    ok, screen_name, msg = _twitter_check_login()
    if ok and screen_name:
        # 记录账号名（账号档案展示/多账号区分用）
        saved = _twitter_load_cookies()
        saved["screen_name"] = screen_name
        _twitter_save_cookies(saved)
        _record_login_ok("twitter")
    emit({
        "event": "twitter_login_result",
        "success": ok,
        "username": screen_name or "",
        "message": msg,
        "network_issue": (not ok) and _login_network_issue("twitter"),
    })
    _emit_login_info()


def twitter_clear_cookies() -> None:
    """清除已保存的 Twitter 登录信息（加密存储）。"""
    _secure_store_clear_cred("twitter")
    emit({"event": "twitter_login_result", "success": False, "logout": True,
          "username": "", "message": "已退出登录"})
    _emit_login_info()


# ============================
# Twitter 关注列表 / 关注管理 / 关注分类（v1.1 接口，无需 queryId 轮换）
# ============================
TWITTER_FOLLOW_TAGS_FILE = "cache/twitter_follow_tags.json"
TWITTER_FOLLOWS_FILE = "cache/twitter_follows.json"


def _twitter_v11(method: str, path: str, params: dict | None = None) -> dict:
    """调用 x.com v1.1 接口（关注列表/关注操作）。

    v1.1 端点路径稳定（不像 GraphQL 每隔数周轮换 queryId），
    需要 Bearer + Cookie + csrf（ct0）三件套。
    """
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise PermissionError("未登录 Twitter，请先在左侧设置中登录")
    _twitter_throttle()
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER}",
        "Cookie": _twitter_cookie_str(),
        "X-Csrf-Token": cookies["ct0"],
        "Referer": TWITTER_HOST + "/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }
    url = f"{TWITTER_HOST}/i/api/1.1/{path}"
    if method.upper() == "GET":
        response = _twitter_session.get(url, params=params, headers=headers, timeout=20)
    else:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        response = _twitter_session.post(url, data=params, headers=headers, timeout=20)
    if response.status_code in (401, 403):
        raise PermissionError("Twitter 登录已失效，请重新填写 Cookie")
    if response.status_code == 429:
        raise PermissionError("Twitter API 被限流，请稍后再试")
    if response.status_code == 404:
        raise requests.HTTPError(
            f"v1.1 接口 {path} 不可用（X 可能已下线该接口）", response=response,
        )
    response.raise_for_status()
    return response.json()


def _twitter_current_user_id() -> str:
    """获取当前登录用户的 user_id（Viewer GraphQL）。"""
    data = _twitter_api_get(_twitter_qid("Viewer"), "Viewer", _TW_USER_FEATURES, {})
    result = ((((data.get("data") or {}).get("viewer") or {})
              .get("user_results") or {}).get("result")) or {}
    return str(result.get("rest_id") or "")


def _twitter_map_v11_user(user: dict, following: bool | None = None) -> dict:
    """v1.1 用户对象 → 前端展示条目（关注列表卡片）。"""
    screen_name = user.get("screen_name") or ""
    name = user.get("name") or screen_name
    avatar = user.get("profile_image_url_https") or ""
    if avatar:
        avatar = avatar.replace("_normal.", "_400x400.")
    if following is None:
        following = bool(user.get("following"))
    return {
        "album_name": f"{name} (@{screen_name})",
        "album_url": f"{TWITTER_HOST}/{screen_name}",
        "thumbnail": avatar,
        "files": user.get("media_count"),
        "site": "twitter",
        "user_id": str(user.get("id_str") or user.get("id") or ""),
        "screen_name": screen_name,
        "name": name,
        "description": (user.get("description") or "")[:120],
        "followers_count": user.get("followers_count"),
        "friends_count": user.get("friends_count"),
        "statuses_count": user.get("statuses_count"),
        "verified": bool(user.get("verified")),
        "following": following,
    }


def _load_twitter_follow_tags() -> list[dict]:
    """读取关注分类（母子 tag）：[{"name": 母类, "children": [子类, ...]}]。"""
    try:
        data = json.loads(Path(TWITTER_FOLLOW_TAGS_FILE).read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [p for p in data if isinstance(p, dict) and p.get("name")]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_twitter_follow_tags(tags: list[dict]) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(TWITTER_FOLLOW_TAGS_FILE).write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError as exc:
        logging.warning("保存关注分类失败: %s", exc)


def _emit_twitter_follow_tags() -> None:
    emit({"event": "twitter_follow_tags", "tags": _load_twitter_follow_tags()})


def _load_twitter_follows() -> dict:
    """读取已归类的关注链接：{user_id: {screen_name, name, avatar, url, parent, child, saved_at}}。"""
    try:
        data = json.loads(Path(TWITTER_FOLLOWS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_twitter_follows(follows: dict) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(TWITTER_FOLLOWS_FILE).write_text(
            json.dumps(follows, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError as exc:
        logging.warning("保存关注归类失败: %s", exc)


def _emit_twitter_follows() -> None:
    follows = _load_twitter_follows()
    tags = _load_twitter_follow_tags()
    valid = set()
    for p in tags:
        valid.add(p["name"])
        for c in p.get("children") or []:
            valid.add(f"{p['name']}/{c}")
    items = []
    for uid, entry in follows.items():
        tag = entry.get("parent") or ""
        if entry.get("child"):
            tag = f"{tag}/{entry['child']}" if tag else entry["child"]
        items.append({
            "user_id": uid,
            "screen_name": entry.get("screen_name") or "",
            "name": entry.get("name") or "",
            "album_url": entry.get("url") or "",
            "thumbnail": entry.get("avatar") or "",
            "parent": entry.get("parent") or "",
            "child": entry.get("child") or "",
            "tag": tag,
            "saved_at": entry.get("saved_at"),
        })
    items.sort(key=lambda x: (x["parent"], x["child"], x["screen_name"].lower()))
    emit({"event": "twitter_follows", "items": items})


TWITTER_USER_LISTS_DIR = "cache/twitter_user_lists"
TWITTER_BROWSE_CACHE_FILE = "cache/twitter_browse_cache.json"


def _twitter_user_list_cache_path(mode: str, screen_name: str) -> Path:
    """关注列表缓存路径（按 模式+用户 区分；自己用 self）。"""
    key = (screen_name or "self").strip().lstrip("@").replace("/", "_") or "self"
    return Path(TWITTER_USER_LISTS_DIR) / f"{mode}_{key}.json"


def _load_twitter_user_list(mode: str, screen_name: str) -> dict | None:
    try:
        data = json.loads(
            _twitter_user_list_cache_path(mode, screen_name).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_twitter_user_list(mode: str, screen_name: str, payload: dict) -> None:
    try:
        Path(TWITTER_USER_LISTS_DIR).mkdir(parents=True, exist_ok=True)
        _twitter_user_list_cache_path(mode, screen_name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logging.warning("保存 Twitter 关注列表缓存失败: %s", exc)


async def twitter_follow_list(mode: str, cursor: str = "",
                              screen_name: str = "") -> None:
    """拉取关注列表（我关注的人/关注我的人/指定用户的）。

    mode: "following"=关注列表 / "followers"=关注我的人。
    screen_name: 指定用户（空 = 当前登录用户）。
    v1.1 friends/list / followers/list，每页最多 200 人，cursor 翻页。
    首页结果缓存到 cache/twitter_user_lists/；重新打开时：
      1) 先显示缓存（界面立即有内容）
      2) 完整刷新：翻页拉取全部（上限 10 页防限流），与缓存对比后重建缓存
         （新增/取消关注的人员都会体现），追加加载的页也会合并进缓存。
    """
    emit({"event": "twitter_follow_loading", "mode": mode, "loading": True})
    label = "关注我的人" if mode == "followers" else "关注列表"
    if screen_name:
        label = f"@{screen_name.lstrip('@')} 的{label}"
    # 先发缓存（仅首页），让界面立即有内容
    if not cursor:
        cached = _load_twitter_user_list(mode, screen_name)
        if cached and cached.get("items"):
            items = list(cached["items"])
            _apply_cached_thumbnails(items)
            emit({"event": "twitter_follow_list", "mode": mode, "label": label,
                  "items": items, "next_cursor": cached.get("next_cursor") or "",
                  "has_more": bool(cached.get("has_more")), "append": False,
                  "cached": True})
    try:
        if mode == "followers":
            path = "followers/list.json"
        else:
            mode, path = "following", "friends/list.json"

        def _apply_tags(items: list[dict]) -> None:
            # 合并已归类的分类 tag（卡片上显示）
            follows = _load_twitter_follows()
            for it in items:
                saved = follows.get(it["user_id"])
                if saved:
                    it["follow_tag"] = f"{saved.get('parent') or ''}/{saved.get('child') or ''}".strip("/")
                    it["has_tag"] = True

        if cursor:
            # ---------- 追加加载（cursor 翻页），同时把新页合并进缓存 ----------
            params: dict = {"count": 200, "skip_status": True, "include_user_entities": False}
            if screen_name:
                params["screen_name"] = screen_name.lstrip("@")
            params["cursor"] = cursor
            data = await asyncio.to_thread(_twitter_v11, "GET", path, params)
            users = data.get("users") or []
            items = [_twitter_map_v11_user(u) for u in users]
            _apply_tags(items)
            next_cursor = str(data.get("next_cursor") or "")
            has_more = bool(next_cursor and next_cursor != "0")
            # 合并进缓存：重新打开时能看到全部已加载过的人
            cached = _load_twitter_user_list(mode, screen_name) or {}
            merged = list(cached.get("items") or [])
            ids = {str(i.get("user_id")) for i in merged}
            for it in items:
                if str(it["user_id"]) not in ids:
                    merged.append(it)
            _save_twitter_user_list(mode, screen_name, {
                "items": merged, "next_cursor": next_cursor if has_more else "",
                "has_more": has_more, "updated_at": time.time(),
            })
            if items:
                _apply_cached_thumbnails(items)
                asyncio.create_task(_cache_thumbnails(items))
            emit({
                "event": "twitter_follow_list",
                "mode": mode,
                "label": label,
                "items": items,
                "next_cursor": next_cursor if has_more else "",
                "has_more": has_more,
                "append": True,
            })
        else:
            # ---------- 重新打开：完整刷新（翻页拉全部，上限 10 页防限流），对比缓存增删 ----------
            all_items: list[dict] = []
            cur = ""
            seen_ids = set()
            for _page in range(10):
                params = {"count": 200, "skip_status": True, "include_user_entities": False}
                if screen_name:
                    params["screen_name"] = screen_name.lstrip("@")
                if cur:
                    params["cursor"] = cur
                data = await asyncio.to_thread(_twitter_v11, "GET", path, params)
                users = data.get("users") or []
                if not users:
                    break
                for u in users:
                    it = _twitter_map_v11_user(u)
                    if str(it["user_id"]) not in seen_ids:
                        seen_ids.add(str(it["user_id"]))
                        all_items.append(it)
                cur = str(data.get("next_cursor") or "")
                if not cur or cur == "0":
                    break
            _apply_tags(all_items)
            has_more = bool(cur and cur != "0")
            next_cursor = cur if has_more else ""
            # 对比旧缓存：统计新增/移除的人员数（写日志 + 事件带差异信息）
            old = _load_twitter_user_list(mode, screen_name) or {}
            old_ids = {str(i.get("user_id")) for i in (old.get("items") or [])}
            new_ids = {str(i.get("user_id")) for i in all_items}
            added = len(new_ids - old_ids)
            removed = len(old_ids - new_ids)
            if old_ids:
                logging.info("Twitter %s 刷新完成: 新增 %d 人, 移除 %d 人", mode, added, removed)
            if all_items:
                _apply_cached_thumbnails(all_items)
                asyncio.create_task(_cache_thumbnails(all_items))
            _save_twitter_user_list(mode, screen_name, {
                "items": all_items, "next_cursor": next_cursor,
                "has_more": has_more, "updated_at": time.time(),
            })
            emit({
                "event": "twitter_follow_list",
                "mode": mode,
                "label": label,
                "items": all_items,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "append": False,
                "added": added,
                "removed": removed,
            })
    except PermissionError as exc:
        emit({"event": "twitter_follow_list", "mode": mode, "items": [],
              "next_cursor": "", "has_more": False, "append": bool(cursor),
              "error": str(exc)})
    except Exception as exc:
        logging.exception("Twitter 关注列表获取失败")
        msg = f"获取关注列表失败: {exc}（请检查登录状态与代理）"
        # 已展示缓存时不报错误横幅，只记日志
        if cursor or not _load_twitter_user_list(mode, screen_name):
            emit({"event": "twitter_follow_list", "mode": mode, "items": [],
                  "next_cursor": "", "has_more": False, "append": bool(cursor),
                  "error": msg})
        else:
            emit({"event": "twitter_follow_list", "mode": mode, "items": [],
                  "next_cursor": "", "has_more": False, "append": True, "refresh_failed": msg})
    finally:
        emit({"event": "twitter_follow_loading", "mode": mode, "loading": False})


async def twitter_browse(offset: int = 0) -> None:
    """浏览模式：聚合我关注博主的最近媒体更新（类似 X 首页时间线）。

    取关注列表（首页缓存），逐个拉 UserMedia 最新一页，每人最多取 2 条，
    按推文时间倒序合并成信息流。结果缓存到 cache/twitter_browse_cache.json，
    重新点击时先显示缓存再后台刷新。
    offset > 0 时为"加载更多"：跳过已拉取的博主，只追加新内容（append 模式）。
    """
    cached = None
    try:
        data = json.loads(Path(TWITTER_BROWSE_CACHE_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("items"):
            cached = data
    except (OSError, json.JSONDecodeError):
        pass
    if cached and not offset:
        items = list(cached["items"])
        _apply_cached_thumbnails(
            [m for it in items for m in it.get("media") or []] or items)
        emit({"event": "twitter_browse_feed", "items": items,
              "updated_at": cached.get("updated_at"), "cached": True})

    emit({"event": "twitter_browse_loading", "loading": True, "offset": offset})
    try:
        # 1. 关注列表（优先用缓存避免重复请求；缓存不足时再拉一页）
        follow_cache = _load_twitter_user_list("following", "")
        if follow_cache and follow_cache.get("items") and (
                offset == 0 or len(follow_cache.get("items") or []) > offset):
            users = list(follow_cache["items"])
        else:
            data = await asyncio.to_thread(
                _twitter_v11, "GET", "friends/list.json",
                {"count": 200, "skip_status": True, "include_user_entities": False},
            )
            users = [_twitter_map_v11_user(u) for u in (data.get("users") or [])]
            _save_twitter_user_list("following", "", {
                "items": users, "next_cursor": str(data.get("next_cursor") or ""),
                "has_more": bool(data.get("next_cursor")), "updated_at": time.time(),
            })
        if not users:
            emit({"event": "twitter_browse_feed", "items": [], "updated_at": time.time()})
            return
        # 有推文的博主优先；offset 为已拉取人数，每批 30 人（节流 1.2s/请求）
        candidates = [u for u in users if (u.get("statuses_count") or 0) > 0]
        candidates = candidates or users
        candidates = candidates[offset:offset + 30]
        has_more = (offset + 30) < len([u for u in users if (u.get("statuses_count") or 0) > 0] or users)
        total = len(candidates)
        if not candidates:
            emit({"event": "twitter_browse_feed", "items": [],
                  "updated_at": time.time(), "append": True, "no_more": True})
            return
        feed: list[dict] = []
        done = 0
        for u in candidates:
            user_id = str(u.get("user_id") or "")
            if not user_id:
                continue
            try:
                variables = {
                    "userId": user_id, "count": 20,
                    "includePromotedContent": False,
                    "withClientEventToken": False, "withBirdwatchNotes": False,
                    "withVoice": True, "withV2Timeline": True,
                }
                data = await asyncio.to_thread(
                    _twitter_api_get,
                    _twitter_qid("UserMedia"), "UserMedia",
                    _TW_MEDIA_FEATURES, variables,
                )
                instructions = ((((data.get("data") or {}).get("user") or {})
                                .get("result") or {}).get("timeline_v2")
                               or {}).get("timeline", {}).get("instructions") or []
                posts = _twitter_extract_posts(instructions)[:2]  # 每人最多 2 条
                for post in posts:
                    legacy = post.get("legacy") or {}
                    if legacy.get("retweeted_status_result"):
                        continue
                    medias = legacy.get("entities", {}).get("media") or []
                    media_items = []
                    for idx, m in enumerate(medias, start=1):
                        mtype = m.get("type")
                        media_url, thumb = "", ""
                        if mtype == "photo":
                            base = m.get("media_url_https") or ""
                            media_url = f"{base}?name=orig" if base else ""
                            thumb = f"{base}?name=small" if base else ""
                        elif mtype in ("video", "animated_gif"):
                            variants = (m.get("video_info") or {}).get("variants") or []
                            mp4s = [v for v in variants
                                    if v.get("content_type") == "video/mp4" and v.get("url")]
                            if mp4s:
                                media_url = max(mp4s, key=lambda v: v.get("bitrate") or 0)["url"]
                            elif variants:
                                media_url = variants[0].get("url") or ""
                            thumb = m.get("media_url_https") or ""
                        if media_url:
                            media_items.append({
                                "media_url": media_url,
                                "thumbnail": thumb,
                                "type": "video" if mtype != "photo" else "photo",
                                "index": idx,
                            })
                    if not media_items:
                        continue
                    created_at = legacy.get("created_at") or ""
                    post_date = ""
                    if created_at:
                        try:
                            post_date = datetime.strptime(
                                created_at, "%a %b %d %H:%M:%S %z %Y",
                            ).strftime("%Y-%m-%d %H:%M")
                        except ValueError:
                            pass
                    tweet_id = post.get("rest_id") or legacy.get("id_str") or ""
                    feed.append({
                        "tweet_id": tweet_id,
                        "item_page": f"{TWITTER_HOST}/{u.get('screen_name')}/status/{tweet_id}",
                        "text": (legacy.get("full_text") or "").strip()[:200],
                        "post_date": post_date,
                        "created_ts": _tw_created_ts(created_at),
                        "user": {
                            "user_id": user_id,
                            "screen_name": u.get("screen_name") or "",
                            "name": u.get("name") or "",
                            "thumbnail": u.get("thumbnail") or "",
                            "album_url": u.get("album_url") or "",
                            "following": u.get("following"),
                        },
                        "media": media_items,
                    })
            except Exception as exc:
                logging.debug("浏览模式拉取 @%s 失败: %s", u.get("screen_name"), exc)
            finally:
                done += 1
                emit({"event": "twitter_browse_progress", "done": done, "total": total})
        # 按发布时间倒序（无时间的排最后）；追加模式合并旧缓存后统一排序
        feed.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
        if offset:
            # 加载更多：与旧缓存合并去重（按推文 id）
            old = (cached or {}).get("items") or []
            seen_ids = {t.get("tweet_id") for t in feed}
            merged = list(feed)
            for t in old:
                if t.get("tweet_id") not in seen_ids:
                    seen_ids.add(t.get("tweet_id"))
                    merged.append(t)
            merged.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
            feed = merged
        feed = feed[:600]
        if feed:
            _apply_cached_thumbnails([m for it in feed for m in it["media"]])
            asyncio.create_task(_cache_thumbnails(
                [m for it in feed for m in it["media"]]))
        updated_at = time.time()
        try:
            Path("cache").mkdir(parents=True, exist_ok=True)
            Path(TWITTER_BROWSE_CACHE_FILE).write_text(
                json.dumps({"items": feed, "updated_at": updated_at,
                            "offset": offset + total},
                           ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logging.warning("保存浏览模式缓存失败: %s", exc)
        emit({"event": "twitter_browse_feed", "items": feed,
              "updated_at": updated_at, "append": bool(offset),
              "has_more": has_more, "next_offset": offset + total})
    except PermissionError as exc:
        emit({"event": "twitter_browse_feed", "items": [], "error": str(exc)})
    except Exception as exc:
        logging.exception("Twitter 浏览模式失败")
        emit({"event": "twitter_browse_feed", "items": [],
              "error": f"获取最近更新失败: {exc}（请检查登录状态与代理）"})
    finally:
        emit({"event": "twitter_browse_loading", "loading": False})


def _tw_created_ts(created_at: str) -> int:
    """推文 created_at 文本 → Unix 时间戳（失败返回 0）。"""
    if not created_at:
        return 0
    try:
        return int(datetime.strptime(
            created_at, "%a %b %d %H:%M:%S %z %Y").timestamp())
    except ValueError:
        return 0


def twitter_clear_cache() -> None:
    """清除 Twitter 专属缓存（保留登录 Cookie 与关注分类数据）。

    清理项：queryId 缓存 / 关注列表缓存 / 浏览模式缓存 / 用户媒体解析缓存。
    """
    removed = 0
    targets: list[Path] = [
        Path("cache/twitter_qids.json"),
        Path(TWITTER_BROWSE_CACHE_FILE),
    ]
    # 关注列表缓存目录
    lists_dir = Path(TWITTER_USER_LISTS_DIR)
    if lists_dir.is_dir():
        targets.extend(p for p in lists_dir.iterdir() if p.is_file())
    # 用户媒体解析缓存（identifier 以 twitter_ 开头）
    albums_dir = Path(ALBUM_CACHE_DIR)
    if albums_dir.is_dir():
        targets.extend(p for p in albums_dir.glob("twitter_*.json"))
    for p in targets:
        try:
            if p.exists():
                p.unlink()
                removed += 1
        except OSError:
            pass
    emit({"event": "twitter_cache_cleared", "removed": removed,
          "message": f"已清除 Twitter 缓存（{removed} 项）；登录信息与关注分类已保留"})


async def twitter_follow(user_id: str, screen_name: str = "") -> None:
    """关注用户（v1.1 friendships/create；失败时回退 GraphQL CreateFollower）。"""
    try:
        data = await asyncio.to_thread(
            _twitter_v11, "POST", "friendships/create.json", {"user_id": user_id},
        )
        ok = bool(data.get("following"))
        msg = f"已关注 @{data.get('screen_name') or screen_name or user_id}"
    except requests.HTTPError:
        # v1.1 接口不可用时的 GraphQL 回退（queryId 自动刷新）
        try:
            data = await asyncio.to_thread(
                _twitter_api_post, "CreateFollower", "CreateFollower",
                {"user_id": user_id},
            )
            ok = bool(((data.get("data") or {}).get("create_follower") or {})
                      .get("following"))
            msg = f"已关注 @{screen_name or user_id}"
        except Exception as exc:
            emit({"event": "twitter_follow_result", "user_id": user_id,
                  "screen_name": screen_name, "success": False, "following": False,
                  "message": f"关注失败: {exc}"})
            return
    except PermissionError as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": False,
              "message": str(exc)})
        return
    except Exception as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": False,
              "message": f"关注失败: {exc}"})
        return
    emit({"event": "twitter_follow_result", "user_id": user_id,
          "screen_name": screen_name, "success": True, "following": True,
          "message": msg})


async def twitter_unfollow(user_id: str, screen_name: str = "") -> None:
    """取消关注用户（v1.1 friendships/destroy；失败时回退 GraphQL DeleteFollower）。"""
    try:
        data = await asyncio.to_thread(
            _twitter_v11, "POST", "friendships/destroy.json", {"user_id": user_id},
        )
        ok = not bool(data.get("following"))
        msg = f"已取消关注 @{data.get('screen_name') or screen_name or user_id}"
    except requests.HTTPError:
        try:
            data = await asyncio.to_thread(
                _twitter_api_post, "DeleteFollower", "DeleteFollower",
                {"user_id": user_id},
            )
            ok = True
            msg = f"已取消关注 @{screen_name or user_id}"
        except Exception as exc:
            emit({"event": "twitter_follow_result", "user_id": user_id,
                  "screen_name": screen_name, "success": False, "following": True,
                  "message": f"取消关注失败: {exc}"})
            return
    except PermissionError as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": True,
              "message": str(exc)})
        return
    except Exception as exc:
        emit({"event": "twitter_follow_result", "user_id": user_id,
              "screen_name": screen_name, "success": False, "following": True,
              "message": f"取消关注失败: {exc}"})
        return
    emit({"event": "twitter_follow_result", "user_id": user_id,
          "screen_name": screen_name, "success": True, "following": False,
          "message": msg})


def _twitter_api_post(query_id: str, endpoint: str, variables: dict,
                      features: dict | None = None) -> dict:
    """调用 x.com GraphQL mutation（POST，用于关注/取关等写操作）。"""
    cookies = _twitter_load_cookies()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise PermissionError("未登录 Twitter，请先在设置中填写 Cookie")
    qid = _twitter_qid(endpoint) or query_id
    if not qid or not re.fullmatch(r"[0-9a-zA-Z_-]{10,30}", qid or ""):
        # mutation 的 queryId 未缓存（默认值为空），先从 main.js 抓取
        _twitter_refresh_qids(True)
        qid = _twitter_qid(endpoint) or query_id
    if not qid:
        raise requests.HTTPError(f"未找到 GraphQL 操作 {endpoint} 的 queryId")
    payload = {"variables": variables, "queryId": qid}
    if features:
        payload["features"] = features
    while True:
        _twitter_throttle()
        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Cookie": _twitter_cookie_str(),
            "X-Csrf-Token": cookies["ct0"],
            "Content-Type": "application/json",
            "Referer": TWITTER_HOST + "/",
        }
        response = _twitter_session.post(
            f"{TWITTER_HOST}/i/api/graphql/{qid}/{endpoint}",
            json=payload, headers=headers, timeout=20,
        )
        if response.status_code == 404:
            if _twitter_refresh_qids(True):
                new_qid = _twitter_qid(endpoint)
                if new_qid and new_qid != qid:
                    qid = new_qid
                    payload["queryId"] = qid
                    continue
            raise requests.HTTPError(
                f"404：GraphQL 操作 {endpoint} 不存在（queryId 可能已过期）",
                response=response,
            )
        if response.status_code in (401, 403):
            raise PermissionError("Twitter 登录已失效，请重新填写 Cookie")
        if response.status_code == 429:
            raise PermissionError("Twitter API 被限流，请稍后再试")
        response.raise_for_status()
        return response.json()


def _twitter_add_follow_tag(parent: str, child: str = "") -> None:
    """新增关注分类（母类，或已有母类下加子类）。"""
    parent = (parent or "").strip()
    child = (child or "").strip()
    if not parent and not child:
        emit({"event": "account_error", "message": "分类名不能为空"})
        return
    tags = _load_twitter_follow_tags()
    names = {t["name"] for t in tags}
    if not parent:
        emit({"event": "account_error", "message": "请先填写母类名"})
        return
    if not child:
        if parent in names:
            emit({"event": "account_error", "message": f"母类「{parent}」已存在"})
            return
        tags.append({"name": parent, "children": []})
        _save_twitter_follow_tags(tags)
        _emit_twitter_follow_tags()
        emit({"event": "account_saved", "message": f"已新增母类「{parent}」"})
        return
    for t in tags:
        if t["name"] == parent:
            if child not in (t.get("children") or []):
                t.setdefault("children", []).append(child)
                _save_twitter_follow_tags(tags)
                _emit_twitter_follow_tags()
                emit({"event": "account_saved", "message": f"「{parent}」下已新增子类「{child}」"})
            else:
                emit({"event": "account_error", "message": f"子类「{child}」已存在"})
            return
    tags.append({"name": parent, "children": [child]})
    _save_twitter_follow_tags(tags)
    _emit_twitter_follow_tags()
    emit({"event": "account_saved", "message": f"已新增分类「{parent}/{child}」"})


def _twitter_delete_follow_tag(parent: str, child: str = "") -> None:
    """删除关注分类（母类或子类）。删除母类时其下子类一并删除。"""
    tags = _load_twitter_follow_tags()
    if not child:
        new_tags = [t for t in tags if t["name"] != parent]
        if len(new_tags) == len(tags):
            emit({"event": "account_error", "message": f"母类「{parent}」不存在"})
            return
        _save_twitter_follow_tags(new_tags)
        _emit_twitter_follow_tags()
        emit({"event": "account_saved", "message": f"已删除母类「{parent}」"})
        return
    for t in tags:
        if t["name"] == parent:
            children = t.get("children") or []
            if child not in children:
                emit({"event": "account_error", "message": f"子类「{child}」不存在"})
                return
            t["children"] = [c for c in children if c != child]
            _save_twitter_follow_tags(tags)
            _emit_twitter_follow_tags()
            emit({"event": "account_saved", "message": f"已删除「{parent}/{child}」"})
            return
    emit({"event": "account_error", "message": f"母类「{parent}」不存在"})


def _twitter_set_follow_tag(user: dict, parent: str, child: str) -> None:
    """保存/更新关注用户的分类归属（parent 为空 = 移除归类）。"""
    follows = _load_twitter_follows()
    user_id = str(user.get("user_id") or "")
    if not user_id:
        emit({"event": "account_error", "message": "缺少用户信息，无法归类"})
        return
    parent = (parent or "").strip()
    child = (child or "").strip()
    if not parent:
        if follows.pop(user_id, None) is not None:
            _save_twitter_follows(follows)
            _emit_twitter_follows()
            emit({"event": "account_saved",
                  "message": f"已移除 @{user.get('screen_name') or ''} 的分类"})
        else:
            emit({"event": "account_error", "message": "该用户尚未归类"})
        return
    # 校验分类存在（不存在则自动创建，方便快速录入）
    tags = _load_twitter_follow_tags()
    entry = next((t for t in tags if t["name"] == parent), None)
    if entry is None:
        tags.append({"name": parent, "children": [child] if child else []})
        _save_twitter_follow_tags(tags)
        _emit_twitter_follow_tags()
    elif child and child not in (entry.get("children") or []):
        entry.setdefault("children", []).append(child)
        _save_twitter_follow_tags(tags)
        _emit_twitter_follow_tags()
    avatar = user.get("thumbnail") or user.get("avatar") or ""
    if avatar and "_400x400" in avatar:
        avatar = avatar.replace("_400x400.", "_normal.")
    follows[user_id] = {
        "screen_name": user.get("screen_name") or "",
        "name": user.get("name") or "",
        "avatar": avatar,
        "url": user.get("album_url") or f"{TWITTER_HOST}/{user.get('screen_name', '')}",
        "parent": parent,
        "child": child,
        "saved_at": time.time(),
    }
    _save_twitter_follows(follows)
    _emit_twitter_follows()
    tag_text = f"{parent}/{child}" if child else parent
    emit({"event": "account_saved",
          "message": f"已将 @{user.get('screen_name') or ''} 归类到「{tag_text}」"})


def _twitter_extract_posts(instructions: list) -> list[dict]:
    """从 GraphQL timeline instructions 中提取推文 result 列表。"""
    posts: list[dict] = []

    def _unwrap(result: dict | None) -> dict | None:
        """解包推文结果：TweetWithVisibilityResults 需取 .tweet（X-Spider 同款）。"""
        if not result:
            return None
        if result.get("__typename") == "TweetWithVisibilityResults":
            return result.get("tweet") or result
        return result

    for inst in instructions or []:
        if inst.get("type") not in ("TimelineAddEntries", "TimelineAddToModule"):
            continue
        entries = inst.get("entries") or []
        # TimelineAddToModule：线程追加（moduleItems）
        if not entries and inst.get("moduleItems"):
            for mi in inst["moduleItems"]:
                r = _unwrap((mi.get("item", {}).get("itemContent", {})
                             .get("tweet_results", {}).get("result")))
                if r:
                    posts.append(r)
            continue
        for entry in entries:
            entry_id = entry.get("entryId", "")
            content = entry.get("content", {})
            if entry_id.startswith("tweet-"):
                r = _unwrap(content.get("itemContent", {})
                            .get("tweet_results", {}).get("result"))
                if r:
                    posts.append(r)
            elif entry_id.startswith(("profile-conversation", "conversationthread")):
                # 线程中的多条推文（TimelineTimelineModule）
                for it in content.get("items", []):
                    r = _unwrap((it.get("item", {}).get("itemContent", {})
                                 .get("tweet_results", {}).get("result")))
                    if r:
                        posts.append(r)
            elif content.get("entryType") == "TimelineTimelineModule":
                # X-Spider v2.2.2 修复解析中断的关键路径：
                # UserMedia 时间线以 module entry 组织推文（不限 entryId 前缀）
                for it in content.get("items", []):
                    r = _unwrap((it.get("item", {}).get("itemContent", {})
                                 .get("tweet_results", {}).get("result")))
                    if r:
                        posts.append(r)
    return posts


def _twitter_map_tweet(result: dict) -> list[dict]:
    """把单条推文的 GraphQL result 转成下载条目（跳过转推/无媒体）。

    图片取 orig 原图质量；视频取最高码率 mp4。
    """
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet") or result
    legacy = result.get("legacy") or {}
    # 跳过转推（原推会在自己的时间线里出现）
    if legacy.get("retweeted_status_result"):
        return []
    medias = legacy.get("entities", {}).get("media") or []
    if not medias:
        return []

    tweet_id = result.get("rest_id") or legacy.get("id_str") or ""
    screen_name = ((result.get("core", {}).get("user_results", {})
                    .get("result", {}).get("legacy", {}) or {}).get("screen_name")) or ""
    full_text = (legacy.get("full_text") or "").strip()
    created_at = legacy.get("created_at") or ""
    post_date = ""
    if created_at:
        try:
            post_date = datetime.strptime(
                created_at, "%a %b %d %H:%M:%S %z %Y",
            ).strftime("%Y-%m-%d")
        except ValueError:
            pass

    items: list[dict] = []
    for idx, m in enumerate(medias, start=1):
        mtype = m.get("type")
        media_url = ""
        ext = "jpg"
        thumb = m.get("media_url_https") or ""
        if mtype == "photo":
            base = m.get("media_url_https") or ""
            if base:
                ext = base.rsplit(".", 1)[-1].lower() if "." in base else "jpg"
                if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                    ext = "jpg"
                # X-Spider 同款：URL 本身带扩展名，只加 name 参数（orig=原图）
                media_url = f"{base}?name=orig"
                thumb = f"{base}?name=small"
        elif mtype in ("video", "animated_gif"):
            variants = (m.get("video_info") or {}).get("variants") or []
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bitrate") or 0)
                media_url = best["url"]
                ext = "mp4"
            elif variants:
                media_url = variants[0].get("url") or ""
                ext = "webm"
        if not media_url:
            continue
        filename = f"{post_date}_{tweet_id}_{idx:02d}.{ext}" if post_date \
            else f"{tweet_id}_{idx:02d}.{ext}"
        items.append({
            "filename": filename,
            "size": None,
            "item_page": f"https://x.com/{screen_name}/status/{tweet_id}" if screen_name else "",
            "status": "pending",
            "site": "twitter",
            "media_url": media_url,
            "thumbnail": thumb,
            "post_date": post_date,
            "post_title": full_text[:80],
        })
    return items


async def twitter_search(query: str) -> None:
    """X 搜索：
    - "@用户名"（仅限博主）→ 验证用户后直接解析 TA 的全部媒体（下载内容）；
    - 其他任意关键词 → SearchTimeline 内容搜索，返回带媒体的推文卡片。
    """
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "请输入搜索内容（关键词，或 @用户名）"})
        return
    emit({"event": "search_start", "query": query, "page": 1})

    # ---------- 仅限博主（@用户名）：直接解析该博主的全部媒体 ----------
    if query.startswith("@"):
        await _twitter_search_user(query.lstrip("@"))
        return

    # ---------- 内容搜索：SearchTimeline ----------
    try:
        raw_query = f"{query} filter:media"  # 只搜带媒体的内容（本工具用于下载）
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("SearchTimeline"), "SearchTimeline",
            _TW_SEARCH_FEATURES,
            {
                "rawQuery": raw_query,
                "count": 20,
                "querySource": "typed_query",
                "product": "Top",
            },
            None,
            True,  # use_post：GET 会被 x-client-transaction-id 校验拦截 404
        )
        instructions = ((((data.get("data") or {}).get("search_by_raw_query") or {})
                        .get("search_timeline") or {}).get("timeline")
                       or {}).get("instructions") or []
        posts = _twitter_extract_posts(instructions)
        items: list[dict] = []
        for post in posts:
            mapped = _twitter_map_tweet(post)
            if not mapped:
                continue
            first = mapped[0]
            user = post.get("core", {}).get("user_results", {}).get("result") or {}
            user_legacy = user.get("legacy") or {}
            screen_name = user_legacy.get("screen_name") or ""
            text = (post.get("legacy", {}).get("full_text") or "").strip()
            # 卡片标题：作者 + 推文摘要
            snippet = text.split("https://t.co/")[0].strip()[:40]
            tweet_id = post.get("rest_id") or ""
            items.append({
                "album_name": f"@{screen_name}: {snippet}" if snippet else f"@{screen_name} 的推文",
                "album_url": f"{TWITTER_HOST}/{screen_name}/status/{tweet_id}",
                "thumbnail": first.get("thumbnail") or "",
                "files": len(mapped),
                "site": "twitter",
                "post_date": first.get("post_date") or "",
            })
        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": query,
            "page": 1,
            "total_pages": 1,
            "total_results": len(items),
            "has_more": False,
            "items": items,
        })
        if items:
            asyncio.create_task(_cache_thumbnails(items))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"搜索出错: {exc}（需登录后才能进行内容搜索）"})
        logging.exception("Twitter 内容搜索出错")


async def _twitter_search_user(query: str) -> None:
    """@用户名 搜索：验证用户存在后直接解析其全部媒体。"""
    query = (query or "").strip().lstrip("@")
    if not query:
        emit({"event": "search_error", "message": "请输入用户名（如 @xxx）"})
        return
    try:
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("UserByScreenName"), "UserByScreenName",
            _TW_USER_FEATURES,
            {"screen_name": query, "withSafetyModeUserFields": True},
            {"fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})},
        )
        legacy = (((data.get("data") or {}).get("user") or {})
                  .get("result") or {}).get("legacy") or {}
        if not legacy:
            emit({"event": "search_result", "query": f"@{query}", "page": 1,
                  "total_pages": 1, "total_results": 0, "has_more": False, "items": []})
            return
        screen_name = legacy.get("screen_name") or query
        # 仅限博主：直接解析该博主的全部媒体（下载内容）
        await twitter_inspect(f"{TWITTER_HOST}/{screen_name}", dict(DEFAULT_SETTINGS))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"搜索出错: {exc}"})
        logging.exception("Twitter 用户搜索出错")


def _twitter_fetch_syndication(status_id: str) -> dict | None:
    """用公开 syndication API 获取单条推文（免登录）。"""
    try:
        token = int(int(status_id) / 40503) & 0xFFFFFFFF
        response = _twitter_session.get(
            "https://cdn.syndication.twimg.com/tweet-result",
            params={"id": status_id, "lang": "en", "token": str(token)},
            timeout=20,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None


async def twitter_inspect(url: str, options: dict) -> None:
    """解析 Twitter 用户主页（全部媒体）或单条推文，返回文件列表。"""
    info = _twitter_parse_url(url)
    if info is None:
        emit({"event": "inspect_error", "message": "无法识别的 Twitter 链接，请粘贴用户主页或推文链接"})
        return

    try:
        # ---------- 单条推文 ----------
        if info["kind"] == "status":
            items: list[dict] = []
            # 优先 TweetDetail GraphQL（需 cookie，结果与网页一致）
            try:
                data = await asyncio.to_thread(
                    _twitter_api_get,
                    _twitter_qid("TweetDetail"), "TweetDetail",
                    _TW_FEATURES,
                    {
                        "focalTweetId": info["status_id"],
                        "with_rux_injections": False,
                        "rankingMode": "Relevance",
                        "includePromotedContent": True,
                        "withCommunity": True,
                    },
                    {"fieldToggles": json.dumps({
                        "withArticleRichContentState": True,
                        "withArticlePlainText": False,
                        "withGrokAnalyze": False,
                        "withDisallowedReplyControls": False,
                    })},
                )
                instructions = ((data.get("data") or {})
                                .get("threaded_conversation_with_injections")
                                or {}).get("instructions") or []
                # 只取 focal 推文（避免把整条对话串都收进来）
                focal = "tweet-" + info["status_id"]
                for inst in instructions:
                    if inst.get("type") != "TimelineAddEntries":
                        continue
                    for entry in inst.get("entries") or []:
                        if entry.get("entryId") == focal:
                            r = (entry.get("content", {}).get("itemContent", {})
                                 .get("tweet_results", {}).get("result"))
                            if r:
                                items = _twitter_map_tweet(r)
                                break
                    if items:
                        break
            except (PermissionError, requests.RequestException, ValueError):
                pass
            # 回退：公开 syndication API（免登录，部分推文可用）
            if not items:
                data = await asyncio.to_thread(_twitter_fetch_syndication, info["status_id"])
                if data:
                    screen_name = (data.get("user") or {}).get("screen_name") or info["screen_name"]
                    tweet_id = str(data.get("id") or info["status_id"])
                    created = data.get("created_at") or ""
                    post_date = ""
                    if created:
                        try:
                            post_date = datetime.strptime(
                                created, "%a %b %d %H:%M:%S %z %Y",
                            ).strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                    text = (data.get("text") or "").strip()
                    idx = 0
                    for photo in data.get("photos") or []:
                        idx += 1
                        base = photo.get("url") or ""
                        if not base:
                            continue
                        ext = base.rsplit(".", 1)[-1].lower() if "." in base else "jpg"
                        items.append({
                            "filename": f"{post_date}_{tweet_id}_{idx:02d}.{ext}" if post_date
                            else f"{tweet_id}_{idx:02d}.{ext}",
                            "size": None,
                            "item_page": f"https://x.com/{screen_name}/status/{tweet_id}",
                            "status": "pending",
                            "site": "twitter",
                            "media_url": f"{base}?name=orig",
                            "thumbnail": f"{base}?name=small",
                            "post_date": post_date,
                            "post_title": text[:80],
                        })
                    video = data.get("video") or {}
                    for variant in video.get("variants") or []:
                        src = variant.get("src") or ""
                        if not src or variant.get("type") != "video/mp4":
                            continue
                        idx += 1
                        items.append({
                            "filename": f"{post_date}_{tweet_id}_{idx:02d}.mp4" if post_date
                            else f"{tweet_id}_{idx:02d}.mp4",
                            "size": None,
                            "item_page": f"https://x.com/{screen_name}/status/{tweet_id}",
                            "status": "pending",
                            "site": "twitter",
                            "media_url": src,
                            "thumbnail": video.get("poster") or "",
                            "post_date": post_date,
                            "post_title": text[:80],
                        })
            if not items:
                emit({"event": "inspect_error", "message": "推文中没有找到可下载的媒体文件"})
                return
            _apply_cached_thumbnails(items)
            emit({
                "event": "inspect_complete",
                "album_name": info["screen_name"],
                "album_id": f"twitter_status_{info['status_id']}",
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("Twitter 推文解析完成: %s (%d 个文件)", url, len(items))
            return

        # ---------- 用户主页：UserMedia 时间线翻页收集全部媒体 ----------
        screen_name = info["screen_name"]
        # 先取用户 ID
        data = await asyncio.to_thread(
            _twitter_api_get,
            _twitter_qid("UserByScreenName"), "UserByScreenName",
            _TW_USER_FEATURES,
            {"screen_name": screen_name, "withSafetyModeUserFields": True},
            {"fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})},
        )
        user_result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
        user_id = user_result.get("rest_id") or ""
        legacy = user_result.get("legacy") or {}
        if not user_id:
            emit({"event": "inspect_error", "message": f"找不到用户 @{screen_name}"})
            return
        display_name = legacy.get("name") or screen_name

        identifier = f"twitter_{user_id}"
        # 命中缓存则直接返回
        cached = _load_album_cache(identifier)
        if cached:
            items = cached.get("items", [])
            _apply_cached_thumbnails(items)
            _mark_items_new(cached.get("album_id") or identifier, items)
            emit({
                "event": "inspect_complete",
                "album_name": cached.get("album_name") or display_name,
                "album_id": cached.get("album_id") or identifier,
                "is_album": True,
                "items": items,
            })
            asyncio.create_task(_cache_thumbnails(items))
            logging.info("使用缓存的 Twitter 用户信息: %s (%d 个文件)", identifier, len(items))
            return

        all_items: list[dict] = []
        cursor = ""
        seen_media: set[str] = set()
        seen_cursors: set[str] = set()
        while True:
            variables = {
                "userId": user_id, "count": 20,
                "includePromotedContent": False,
                "withClientEventToken": False, "withBirdwatchNotes": False,
                "withVoice": True, "withV2Timeline": True,
            }
            if cursor:
                variables["cursor"] = cursor
            data = await asyncio.to_thread(
                _twitter_api_get,
                _twitter_qid("UserMedia"), "UserMedia",
                _TW_MEDIA_FEATURES, variables,
            )
            instructions = ((((data.get("data") or {}).get("user") or {})
                            .get("result") or {}).get("timeline_v2")
                           or {}).get("timeline", {}).get("instructions") or []
            posts = _twitter_extract_posts(instructions)
            new_count = 0
            for post in posts:
                mapped = _twitter_map_tweet(post)
                for it in mapped:
                    if it["media_url"] not in seen_media:
                        seen_media.add(it["media_url"])
                        all_items.append(it)
                        new_count += 1
            # 提取底部游标
            next_cursor = ""
            for inst in instructions:
                if inst.get("type") != "TimelineAddEntries":
                    continue
                for entry in inst.get("entries") or []:
                    c = entry.get("content") or {}
                    if c.get("cursorType") == "Bottom" and c.get("value"):
                        next_cursor = c["value"]
            if not next_cursor or next_cursor in seen_cursors or new_count == 0:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            emit({
                "event": "inspect_progress",
                "current": len(all_items),
                "total": len(all_items) + 20,
                "filename": all_items[-1]["filename"] if all_items else "",
            })

        if not all_items:
            emit({"event": "inspect_error", "message": "没有找到任何媒体（用户可能没有图片/视频）"})
            return

        _apply_cached_thumbnails(all_items)
        _mark_items_new(identifier, all_items)
        _save_album_cache(identifier, {
            "album_name": display_name,
            "album_id": identifier,
            "is_album": True,
            "items": all_items,
        })
        emit({
            "event": "inspect_complete",
            "album_name": display_name,
            "album_id": identifier,
            "is_album": True,
            "items": all_items,
        })
        asyncio.create_task(_cache_thumbnails(all_items))
        logging.info("Twitter 用户解析完成: @%s, 共 %d 个文件", screen_name, len(all_items))

    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"解析过程出错: {exc}"})
        logging.exception("Twitter 解析过程出错")


def _twitter_subfolder(item: dict, options: dict) -> str:
    """Twitter 专属子文件夹规则（父文件夹为用户名，由相册目录承担）。

    模式 twitter_subfolder:
      - none:       不建子文件夹
      - date:       按发布月份 YYYY-MM
      - post:       按推文（推文id）
      - date_post:  YYYY-MM/推文id（默认）
    自定义模板 twitter_folder_template 非空时优先。
    """
    template = (options.get("twitter_folder_template") or "").strip()
    if template:
        return _render_folder_template(
            template,
            item.get("post_date") or "",
            (item.get("post_title") or "").strip(),
            item.get("post_id") or "",
        )
    mode = options.get("twitter_subfolder", "date_post")
    parts: list[str] = []
    date = (item.get("post_date") or "")[:7]  # YYYY-MM
    title = sanitize_directory_name((item.get("post_title") or "").strip())[:60]

    if mode == "date" and date:
        parts.append(date)
    elif mode == "post" and title:
        parts.append(title)
    elif mode == "date_post":
        if date:
            parts.append(date)
        if title:
            parts.append(title)
    return str(Path(*parts)) if parts else ""


# ============================
# Iwara 站点支持 (iwara.tv，MMD 视频站)
# ============================
# - API v2: https://api.iwara.tv/（JSON）
# - 登录: POST /user/login {email, password} → Bearer token（约3周有效）
#   媒体 token: POST /user/token（Bearer 用户 token）→ accessToken（约1小时，解析视频源需要）
# - 视频: GET /video/{id} → fileUrl → 带 X-Version 头请求 fileUrl 得画质列表
#   X-Version = sha1("{路径末段}_{expires参数}_{盐}")
#   画质优先级 Source(最高) > 540 > 360，默认下载最高画质
# - 搜索: GET /videos?query=关键词&sort=date&page={n}&limit=32
# - 用户: GET /profile/{username} → user.id → GET /videos?user={id}&sort=date&page={n}
# - 缩略图: https://files.iwara.tv/image/thumbnail/{file.id}/thumbnail-00.jpg
# - 视频直链带 expires 签名会过期：下载时必须重新解析
# - 可选代理（默认直连，国内不稳时可配置）

IWARA_API = "https://api.iwara.tv"
IWARA_SITE_FILE = "cache/iwara_site.json"
IWARA_SALT = "mSvL05GfEmeEmsEYfGCnVpEjYgTJraJN"
IWARA_QUALITY_PREF = {"source": 0, "540": 1, "360": 2, "preview": 3}
# IW站 / AI站（www.iwara.ai = 同一 API + X-Site 请求头区分内容）
IWARA_SITES = {"iwara": "www.iwara.tv", "ai": "www.iwara.ai"}

_iwara_proxy = ""  # 形如 http://127.0.0.1:10809，空 = 直连

_iwara_session = requests.Session()
_iwara_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.iwara.tv",
    "Referer": "https://www.iwara.tv/",
})


def iwara_set_proxy(proxy: str) -> None:
    """设置 Iwara 代理（空 = 直连）。"""
    global _iwara_proxy
    _iwara_proxy = (proxy or "").strip()
    if _iwara_proxy and not _iwara_proxy.startswith(("http://", "https://", "socks5://")):
        _iwara_proxy = "http://" + _iwara_proxy
    proxies = {"http": _iwara_proxy, "https": _iwara_proxy} if _iwara_proxy else None
    _iwara_session.proxies = proxies or {}
    emit({"event": "iwara_proxy_set", "proxy": _iwara_proxy})


def iwara_current_site() -> str:
    """读取当前 Iwara 站点（iwara | ai）。"""
    try:
        data = json.loads(Path(IWARA_SITE_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("site") in IWARA_SITES:
            return data["site"]
    except (OSError, json.JSONDecodeError):
        pass
    return "iwara"


def iwara_set_site(site: str) -> None:
    """切换 IW站 / AI站（同一 API，通过 X-Site 请求头区分内容；登录信息共用）。"""
    site = "ai" if str(site) == "ai" else "iwara"
    _iwara_session.headers["X-Site"] = IWARA_SITES[site]
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(IWARA_SITE_FILE).write_text(
            json.dumps({"site": site}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    emit({"event": "iwara_site_changed", "site": site,
          "message": "已切换到 AI 站 (iwara.ai)" if site == "ai" else "已切换到 IW 站 (iwara.tv)"})


# 启动时按持久化的站点初始化请求头
_iwara_session.headers["X-Site"] = IWARA_SITES[iwara_current_site()]


def _iwara_load_token() -> dict:
    """读取已保存的 Iwara 登录信息（加密账号存储，长期保持登录状态）。"""
    return _secure_store_read_cred("iwara")


def _iwara_save_token(data: dict) -> None:
    """保存 Iwara 登录信息（加密存储：user_token 长期有效 + media_token 短期）。"""
    _secure_store_write_cred("iwara", dict(data))


def _iwara_jwt_exp(token: str) -> float:
    """解析 JWT 的 exp 过期时间（解析失败返回 0）。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(__import__("base64").urlsafe_b64decode(payload)).get("exp") or 0)
    except Exception:
        return 0.0


def _iwara_media_token(force: bool = False) -> str:
    """获取媒体 token（约1小时有效，解析视频源列表必需；自动刷新）。"""
    data = _iwara_load_token()
    media = data.get("media_token") or ""
    exp = _iwara_jwt_exp(media)
    if media and not force and exp > time.time() + 120:
        return media
    user_token = data.get("user_token") or ""
    if not user_token:
        return ""
    resp = _iwara_session.post(
        f"{IWARA_API}/user/token", timeout=20,
        headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    media = resp.json().get("accessToken") or ""
    if media:
        data["media_token"] = media
        _iwara_save_token(data)
    return media


def _iwara_auth_headers() -> dict:
    """带媒体 token 的请求头（未登录返回空 dict，公开内容可直接访问）。"""
    try:
        token = _iwara_media_token()
    except Exception:
        token = ""
    return {"Authorization": f"Bearer {token}"} if token else {}


def _iwara_auto_relogin() -> str:
    """用已保存的邮箱密码自动重新登录（token 过期时续期）。成功返回新 token。

    密码与 token 一起加密保存在本地（theme_cache.dat），长期有效；
    token 过期后无需用户重新输入密码。
    """
    data = _iwara_load_token()
    email = data.get("email") or ""
    password = data.get("password") or ""
    if not email or not password:
        return ""
    try:
        resp = _iwara_session.post(
            f"{IWARA_API}/user/login", timeout=20,
            json={"email": email, "password": password},
        )
        payload = resp.json() if resp.content else {}
        token = payload.get("token") or ""
        if token:
            data["user_token"] = token
            data.pop("media_token", None)  # 旧媒体 token 一并失效
            _iwara_save_token(data)
            logging.info("Iwara token 已自动续期（保存的密码重新登录）")
            return token
    except requests.RequestException as exc:
        logging.warning("Iwara 自动续期失败: %s", exc)
    return ""


def _iwara_me_user(me) -> dict:
    """解析 GET /user 的响应（新版 API 返回 {"balance":.., "user":{...}}，旧版直接返回用户对象）。"""
    if not isinstance(me, dict):
        return {}
    if isinstance(me.get("user"), dict):
        return me["user"]
    return me


def iwara_login(email: str, password: str) -> None:
    """Iwara 登录（邮箱 + 密码 → Bearer token 长期保存；密码也加密保存用于自动续期）。"""
    try:
        resp = _iwara_session.post(
            f"{IWARA_API}/user/login", timeout=20,
            json={"email": email, "password": password},
        )
        data = resp.json() if resp.content else {}
        token = data.get("token") or ""
        if not token:
            msg = data.get("message") or "登录失败（账号或密码错误）"
            emit({"event": "iwara_login_result", "success": False, "message": msg})
            return
        # 密码一并加密保存：token 过期后自动用密码续期，长期免登录
        cred = {"user_token": token, "email": email, "password": password}
        # 立即取用户信息验证
        try:
            me = _iwara_me_user(_iwara_session.get(
                f"{IWARA_API}/user", timeout=20,
                headers={"Authorization": f"Bearer {token}"},
            ).json())
            cred.update({
                "user_id": me.get("id") or "",
                "name": me.get("name") or me.get("username") or "",
                "username": me.get("username") or "",
            })
        except Exception:
            pass
        _iwara_save_token(cred)
        _emit_login_info()
        emit({"event": "iwara_login_result", "success": True, "email": email,
              "username": _iwara_load_token().get("username") or email,
              "message": "Iwara 登录成功"})
    except requests.RequestException as exc:
        emit({"event": "iwara_login_result", "success": False,
              "message": f"连接失败: {exc}（国内建议在设置里配置 Iwara 代理）",
              "network_issue": True})


def iwara_logout() -> None:
    """退出 Iwara 登录（清除加密存储中的凭据）。"""
    _secure_store_clear_cred("iwara")
    _emit_login_info()
    emit({"event": "iwara_login_result", "success": False, "logout": True,
          "message": "已退出 Iwara 登录"})


def iwara_check_login(silent: bool = False) -> None:
    """检查 Iwara 登录状态（token 是否有效；过期时用保存的密码自动续期）。"""
    data = _iwara_load_token()
    token = data.get("user_token") or ""
    if not token:
        emit({"event": "iwara_login_result", "success": False, "silent": silent,
              "message": "未登录" if not silent else ""})
        return
    if _iwara_jwt_exp(token) and _iwara_jwt_exp(token) < time.time():
        # token 过期：优先用保存的密码自动续期（长期免登录）
        new_token = _iwara_auto_relogin()
        if new_token:
            data = _iwara_load_token()
            token = new_token
        else:
            emit({"event": "iwara_login_result", "success": False, "silent": silent,
                  "message": "登录已过期，且自动续期失败（未保存密码或密码已更改），请重新登录"})
            return
    try:
        me = _iwara_me_user(_iwara_session.get(
            f"{IWARA_API}/user", timeout=(8, 20),  # 连接超时 8s：直连不通时避免阻塞 20s
            headers={"Authorization": f"Bearer {token}"},
        ).json())
        if me.get("id"):
            data.update({"user_id": me.get("id") or "",
                         "name": me.get("name") or me.get("username") or "",
                         "username": me.get("username") or ""})
            _iwara_save_token(data)
            _emit_login_info()
            emit({"event": "iwara_login_result", "success": True, "silent": silent,
                  "username": me.get("username") or data.get("username") or "",
                  "message": "Iwara 登录有效"})
        else:
            # token 被服务器拒绝：先尝试密码自动续期再重试一次
            new_token = _iwara_auto_relogin()
            if new_token:
                iwara_check_login(silent=silent)
                return
            emit({"event": "iwara_login_result", "success": False, "silent": silent,
                  "message": "登录已失效，请重新登录"})
    except requests.RequestException as exc:
        # 连接异常 = 网络问题（token 未被服务器拒绝），前端保留登录显示，
        # 避免把国内直连超时误报成"登录失效"
        emit({"event": "iwara_login_result", "success": False, "silent": silent,
              "message": f"连接失败: {exc}（请检查网络或代理设置，国内建议配置 Iwara 代理）",
              "network_issue": True})


def is_iwara_url(url: str) -> bool:
    """判断是否为 Iwara 链接（视频页 / 用户主页 / 图片页，含 iwara.ai AI站）。"""
    return bool(re.search(r"iwara\.(tv|ai)/(video|profile|user|image)s?/[A-Za-z0-9_-]+", url, re.I))


def _iwara_api_get(path: str, params: dict | None = None) -> dict | list:
    """Iwara API GET（带登录态 + 节流；401 时自动续期重试一次）。"""
    _iwara_throttle()
    resp = _iwara_session.get(
        f"{IWARA_API}{path}", params=params, timeout=20,
        headers=_iwara_auth_headers(),
    )
    if resp.status_code == 401:
        # 登录失效：用保存的密码自动续期后重试一次
        if _iwara_auto_relogin():
            _iwara_throttle()
            resp = _iwara_session.get(
                f"{IWARA_API}{path}", params=params, timeout=20,
                headers=_iwara_auth_headers(),
            )
        if resp.status_code == 401:
            raise PermissionError("Iwara 登录已失效（自动续期失败），请在左侧重新登录")
    resp.raise_for_status()
    return resp.json() if resp.content else {}


_iwara_last_request = 0.0
_iwara_lock = threading.Lock()


def _iwara_throttle() -> None:
    """Iwara 请求节流（间隔 ≥0.5s，防限流惩罚）。"""
    global _iwara_last_request
    with _iwara_lock:
        wait = 0.5 - (time.time() - _iwara_last_request)
        if wait > 0:
            time.sleep(wait)
        _iwara_last_request = time.time()


def _iwara_map_user(u: dict) -> dict:
    """API 用户对象 → 前端用户卡片（关注列表/好友列表/作者信息通用）。"""
    av = u.get("avatar") or {}
    avatar = ""
    if av.get("name"):
        stem = str(av["name"]).rsplit(".", 1)[0]
        avatar = f"https://www.iwara.tv/image/avatar/{av.get('path')}/{stem}"
    return {
        "user_id": u.get("id") or "",
        "name": u.get("name") or u.get("username") or "",
        "username": u.get("username") or "",
        "avatar": avatar,
        "thumbnail": avatar,  # 复用缩略图缓存（thumb://local/）
        "following": bool(u.get("following")),
        "friend": bool(u.get("friend")),
        "premium": bool(u.get("premium")),
    }


def _iwara_map_video(v: dict) -> dict:
    """API 视频对象 → 前端搜索结果卡片。"""
    user = v.get("user") or {}
    file = v.get("file") or {}
    thumb = ""
    if file.get("id"):
        thumb = f"https://files.iwara.tv/image/thumbnail/{file['id']}/thumbnail-00.jpg"
    author = _iwara_map_user(user)
    return {
        "album_name": v.get("title") or "未命名视频",
        "album_url": f"https://www.iwara.tv/video/{v.get('id')}",
        "thumbnail": thumb,
        "files": 1,
        "site": "iwara",
        "video_id": v.get("id") or "",
        "author": author["name"] or user.get("username") or "",
        "author_id": author["user_id"],
        "author_username": author["username"],
        "author_avatar": author["avatar"],
        "author_following": author["following"],
        "post_date": (v.get("createdAt") or "")[:10],
        "created_at": v.get("createdAt") or "",
        "views": v.get("numViews"),
        "likes": v.get("numLikes"),
        "num_comments": v.get("numComments"),
        "rating": v.get("rating") or "",
        "duration": file.get("duration"),
        "file_size": file.get("size"),
    }


def _iwara_my_user_id() -> str:
    """获取当前登录用户的 user_id（优先缓存，缺则调 /user 并缓存）。"""
    data = _iwara_load_token()
    uid = data.get("user_id") or ""
    if uid:
        return uid
    token = data.get("user_token") or ""
    if not token:
        return ""
    try:
        me = _iwara_me_user(_iwara_session.get(
            f"{IWARA_API}/user", timeout=(8, 20),  # 连接超时 8s：直连不通时避免阻塞 20s
            headers={"Authorization": f"Bearer {token}"},
        ).json())
        uid = me.get("id") or ""
        if uid:
            data.update({"user_id": uid, "name": me.get("name") or "",
                         "username": me.get("username") or ""})
            _iwara_save_token(data)
        return uid
    except requests.RequestException:
        return ""


def _iwara_map_comment(c: dict) -> dict:
    """评论对象 → 前端评论卡片。"""
    return {
        "id": c.get("id") or "",
        "body": c.get("body") or "",
        "num_replies": c.get("numReplies") or 0,
        "created_at": c.get("createdAt") or "",
        "user": _iwara_map_user(c.get("user") or {}),
    }


async def iwara_home(page: int = 1, mode: str = "") -> None:
    """Iwara 主页：最近更新的视频（进入站点时自动加载，与官网首页一致）。

    mode='subscribed'：我关注的更新（订阅流，只看已关注作者的最新投稿，需登录）。
    """
    emit({"event": "iwara_home_loading", "loading": True})
    try:
        if mode == "subscribed" and not _iwara_load_token().get("user_token"):
            emit({"event": "iwara_home", "items": [], "page": 1, "has_more": False,
                  "mode": mode, "error": "订阅更新需要登录：请在左侧登录 Iwara 账号"})
            return
        api_page = max(0, (page or 1) - 1)
        params = {"page": api_page, "limit": 32, "sort": "date", "rating": "all"}
        if mode == "subscribed":
            params["subscribed"] = "true"  # 只看已关注用户的视频（订阅流）
        data = await asyncio.to_thread(_iwara_api_get, "/videos", params)
        items = [_iwara_map_video(v) for v in (data.get("results") or [])]
        count = data.get("count") or 0
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "iwara_home", "items": items, "page": max(1, page),
              "has_more": (api_page + 1) * 32 < count, "total": count,
              "mode": mode, "site": iwara_current_site()})
        logging.info("Iwara 主页第 %d 页 (mode=%s): %d 个视频", page, mode or "home", len(items))
    except Exception as exc:
        emit({"event": "iwara_home", "items": [], "page": max(1, page), "has_more": False,
              "mode": mode, "error": f"获取主页内容失败: {exc}（请检查网络或代理设置）"})
        logging.exception("Iwara 主页获取失败")
    finally:
        emit({"event": "iwara_home_loading", "loading": False})


async def iwara_following_list(page: int = 1) -> None:
    """我的关注列表（登录后可用；点用户可查看内容 / 取消关注）。"""
    emit({"event": "iwara_follow_loading", "loading": True})
    data = _iwara_load_token()
    if not data.get("user_token"):
        emit({"event": "iwara_follow_list", "items": [], "page": 1, "has_more": False,
              "error": "未登录：请在左侧登录 Iwara 账号后查看关注列表"})
        emit({"event": "iwara_follow_loading", "loading": False})
        return
    try:
        uid = await asyncio.to_thread(_iwara_my_user_id)
        if not uid:
            emit({"event": "iwara_follow_list", "items": [], "page": 1, "has_more": False,
                  "error": "获取用户信息失败（登录可能已失效）"})
            return
        api_page = max(0, (page or 1) - 1)
        data = await asyncio.to_thread(
            _iwara_api_get, f"/user/{uid}/following",
            {"page": api_page, "limit": 50},
        )
        items = [_iwara_map_user(it.get("user") or {}) for it in (data.get("results") or [])]
        count = data.get("count") or 0
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "iwara_follow_list", "items": items, "page": max(1, page),
              "has_more": (api_page + 1) * 50 < count, "total": count,
              "site": iwara_current_site()})
        logging.info("Iwara 关注列表第 %d 页: %d 人", page, len(items))
    except PermissionError as exc:
        emit({"event": "iwara_follow_list", "items": [], "page": max(1, page),
              "has_more": False, "error": str(exc), "site": iwara_current_site()})
    except Exception as exc:
        emit({"event": "iwara_follow_list", "items": [], "page": max(1, page),
              "has_more": False, "error": f"获取关注列表失败: {exc}", "site": iwara_current_site()})
        logging.exception("Iwara 关注列表获取失败")
    finally:
        emit({"event": "iwara_follow_loading", "loading": False})


async def iwara_friend_list(page: int = 1) -> None:
    """我的好友列表（登录后可用）。"""
    emit({"event": "iwara_friend_loading", "loading": True})
    data = _iwara_load_token()
    if not data.get("user_token"):
        emit({"event": "iwara_friend_list", "items": [], "page": 1, "has_more": False,
              "error": "未登录：请在左侧登录 Iwara 账号后查看好友列表"})
        emit({"event": "iwara_friend_loading", "loading": False})
        return
    try:
        uid = await asyncio.to_thread(_iwara_my_user_id)
        if not uid:
            emit({"event": "iwara_friend_list", "items": [], "page": 1, "has_more": False,
                  "error": "获取用户信息失败（登录可能已失效）"})
            return
        api_page = max(0, (page or 1) - 1)
        data = await asyncio.to_thread(
            _iwara_api_get, f"/user/{uid}/friends",
            {"page": api_page, "limit": 50},
        )
        items = [_iwara_map_user(it.get("user") or it.get("friend") or {}) for it in (data.get("results") or [])]
        count = data.get("count") or 0
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "iwara_friend_list", "items": items, "page": max(1, page),
              "has_more": (api_page + 1) * 50 < count, "total": count,
              "site": iwara_current_site()})
        logging.info("Iwara 好友列表第 %d 页: %d 人", page, len(items))
    except PermissionError as exc:
        emit({"event": "iwara_friend_list", "items": [], "page": max(1, page),
              "has_more": False, "error": str(exc), "site": iwara_current_site()})
    except Exception as exc:
        emit({"event": "iwara_friend_list", "items": [], "page": max(1, page),
              "has_more": False, "error": f"获取好友列表失败: {exc}", "site": iwara_current_site()})
        logging.exception("Iwara 好友列表获取失败")
    finally:
        emit({"event": "iwara_friend_loading", "loading": False})


def iwara_follow(user_id: str, follow: bool = True) -> None:
    """关注 / 取消关注用户（POST/DELETE /user/{id}/followers）。"""
    data = _iwara_load_token()
    token = data.get("user_token") or ""
    if not token:
        emit({"event": "iwara_follow_result", "user_id": user_id, "success": False,
              "following": follow, "message": "未登录：请先登录 Iwara 账号"})
        return
    try:
        _iwara_throttle()
        method = "POST" if follow else "DELETE"
        resp = _iwara_session.request(
            method, f"{IWARA_API}/user/{user_id}/followers", timeout=20,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code in (200, 201, 204):
            emit({"event": "iwara_follow_result", "user_id": user_id, "success": True,
                  "following": follow,
                  "message": "已关注" if follow else "已取消关注"})
        else:
            msg = ""
            try:
                msg = resp.json().get("message") or ""
            except Exception:
                pass
            emit({"event": "iwara_follow_result", "user_id": user_id, "success": False,
                  "following": not follow,
                  "message": f"操作失败: {resp.status_code} {msg}".strip()})
    except requests.RequestException as exc:
        emit({"event": "iwara_follow_result", "user_id": user_id, "success": False,
              "following": not follow, "message": f"连接失败: {exc}"})


async def iwara_video_detail(video_id: str) -> None:
    """视频详情：完整信息（简介/tags/统计/作者关注状态）+ 首页评论。"""
    emit({"event": "iwara_detail_loading", "loading": True})
    try:
        v = await asyncio.to_thread(_iwara_api_get, f"/video/{video_id}")
        video = _iwara_map_video(v)
        # 可播放直链（fileUrl 签名解析最高画质；协议相对地址 //xxx 补 https:）
        play_url = ""
        try:
            fu = v.get("fileUrl") or ""
            if fu:
                play_url, _mime = await asyncio.to_thread(_iwara_resolve_best_url, fu)
                if play_url.startswith("//"):
                    play_url = "https:" + play_url
        except Exception:
            play_url = ""
        # tag 的 id 即标签名（如 musclegirl），可直接展示与搜索
        video.update({
            "body": v.get("body") or "",
            "tags": [{"id": t.get("id") or "", "name": t.get("id") or "",
                      "type": t.get("type") or "", "sensitive": bool(t.get("sensitive"))}
                     for t in (v.get("tags") or [])],
            "video_url": play_url,
        })
        # 首页评论（最新一页）
        comments = []
        try:
            cdata = await asyncio.to_thread(
                _iwara_api_get, f"/video/{video_id}/comments", {"limit": 20, "page": 0})
            comments = [_iwara_map_comment(c) for c in (cdata.get("results") or [])]
        except Exception:
            pass
        _apply_cached_thumbnails([video])
        _apply_cached_thumbnails([c["user"] for c in comments])
        asyncio.create_task(_cache_thumbnails([video] + [c["user"] for c in comments]))
        emit({"event": "iwara_video_detail", "video": video, "comments": comments,
              "comment_count": v.get("numComments") or 0, "site": iwara_current_site()})
        logging.info("Iwara 视频详情: %s", video_id)
    except PermissionError as exc:
        emit({"event": "iwara_video_detail", "video": None, "comments": [], "error": str(exc),
              "site": iwara_current_site()})
    except Exception as exc:
        emit({"event": "iwara_video_detail", "video": None, "comments": [],
              "error": f"获取视频详情失败: {exc}", "site": iwara_current_site()})
        logging.exception("Iwara 视频详情获取失败")
    finally:
        emit({"event": "iwara_detail_loading", "loading": False})


async def iwara_video_comments(video_id: str, page: int = 1) -> None:
    """视频评论翻页加载。"""
    try:
        api_page = max(0, (page or 1) - 1)
        data = await asyncio.to_thread(
            _iwara_api_get, f"/video/{video_id}/comments",
            {"limit": 20, "page": api_page},
        )
        comments = [_iwara_map_comment(c) for c in (data.get("results") or [])]
        count = data.get("count") or 0
        emit({"event": "iwara_comments", "video_id": video_id, "comments": comments,
              "page": max(1, page), "has_more": (api_page + 1) * 20 < count, "total": count})
    except Exception as exc:
        emit({"event": "iwara_comments", "video_id": video_id, "comments": [],
              "page": max(1, page), "has_more": False, "error": f"获取评论失败: {exc}"})


async def _iwara_collect_user_items(username: str) -> tuple[str, str, list[dict]]:
    """拉取指定用户的全部视频并构建下载条目（返回 作者名, user_id, items）。"""
    profile = await asyncio.to_thread(_iwara_api_get, f"/profile/{username}", None)
    user = profile.get("user") or {}
    user_id = user.get("id") or ""
    if not user_id:
        raise PermissionError(f"找不到 Iwara 用户 @{username}")
    album_name = user.get("name") or username
    video_ids: list[str] = []
    for p in range(20):
        data = await asyncio.to_thread(
            _iwara_api_get, "/videos",
            {"user": user_id, "page": p, "limit": 32, "sort": "date"},
        )
        page_videos = data.get("results") or []
        if not page_videos:
            break
        video_ids.extend(v.get("id") for v in page_videos if v.get("id"))
        if len(page_videos) < 32:
            break
    items = await _iwara_build_items(video_ids)
    return album_name, user_id, items


async def _iwara_build_items(video_ids: list) -> list[dict]:
    """按视频 ID 列表逐个取详情构建下载条目（与单视频解析一致的元数据）。"""
    items: list[dict] = []
    for vid in video_ids:
        try:
            data = await asyncio.to_thread(_iwara_api_get, f"/video/{vid}", None)
        except Exception as exc:
            logging.warning("Iwara 视频 %s 获取失败: %s", vid, exc)
            continue
        if data.get("message") or not data.get("fileUrl"):
            continue
        user = data.get("user") or {}
        file = data.get("file") or {}
        thumb = f"https://files.iwara.tv/image/thumbnail/{file['id']}/thumbnail-00.jpg" if file.get("id") else ""
        title = sanitize_directory_name((data.get("title") or f"iwara_{vid}").strip())
        items.append({
            "filename": f"{title}.mp4",
            "size": None,
            "item_page": f"https://www.iwara.tv/video/{vid}",
            "status": "ok",
            "thumbnail": thumb,
            "media_url": data.get("fileUrl"),
            "site": "iwara",
            "video_id": vid,
            "post_title": data.get("title") or title,
            "post_date": (data.get("createdAt") or "")[:10],
            "artist": user.get("name") or user.get("username") or "",
        })
    return items


async def iwara_batch_download(usernames: list, video_ids: list, options: dict) -> None:
    """批量解析下载：关注/好友列表勾选多个用户（或主页勾选多个视频），逐个解析并提交下载任务。

    - 用户：每个用户单独一个下载任务（目录 = 作者名/...，与其他站点逻辑一致）
    - 视频：所有勾选视频合并为一个任务
    """
    usernames = [str(u).strip().lstrip("@") for u in (usernames or []) if str(u).strip()]
    video_ids = [str(v).strip() for v in (video_ids or []) if str(v).strip()]
    total = len(usernames) + (1 if video_ids else 0)
    done = 0
    failed: list[str] = []

    def _progress(done_: int, msg: str) -> None:
        emit({"event": "iwara_batch_progress", "done": done_, "total": total, "message": msg})

    if not total:
        _progress(0, "请先勾选要下载的用户或视频")
        emit({"event": "iwara_batch_done", "done": 0, "total": 0, "failed": []})
        return

    try:
        for uname in usernames:
            _progress(done, f"正在解析 @{uname} 的全部视频...")
            try:
                album_name, user_id, items = await _iwara_collect_user_items(uname)
                if not items:
                    failed.append(f"@{uname}（无视频）")
                else:
                    task_id = download_manager.submit(
                        f"https://www.iwara.tv/profile/{uname}", items, options,
                        album_name, f"iwara_{user_id}",
                    )
                    download_manager.start(task_id)
                    logging.info("批量下载：@%s 已提交 %d 个视频", uname, len(items))
            except Exception as exc:
                failed.append(f"@{uname}（{exc}）")
                logging.exception("批量下载解析失败: %s", uname)
            done += 1
            _progress(done, f"@{uname} 完成（{done}/{total}）")

        if video_ids:
            _progress(done, f"正在解析勾选的 {len(video_ids)} 个视频...")
            try:
                items = await _iwara_build_items(video_ids)
                if not items:
                    failed.append("勾选的视频（全部解析失败）")
                else:
                    task_id = download_manager.submit(
                        "https://www.iwara.tv/", items, options, "Iwara 批量下载", "iwara_batch",
                    )
                    download_manager.start(task_id)
                    logging.info("批量下载：已提交 %d 个视频", len(items))
            except Exception as exc:
                failed.append(f"勾选的视频（{exc}）")
                logging.exception("批量下载视频解析失败")
            done += 1
            _progress(done, f"视频解析完成（{done}/{total}）")

        summary = f"批量下载已提交：{done}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "iwara_batch_done", "done": done, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "iwara_batch_done", "done": done, "total": total, "failed": failed,
              "message": f"批量下载中断: {exc}"})
        logging.exception("Iwara 批量下载出错")


async def iwara_search(query: str, page: int = 0) -> None:
    """Iwara 视频搜索（关键词 → 视频卡片；@用户名 → 该用户的视频列表）。

    关键词搜索走官方搜索端点 GET /search（/videos 的 query 参数会被服务端忽略，
    之前"搜索成功但结果不对"的根因）。
    注意：type 必须是复数 "videos"（Iwara 官网搜索页就是此参数），
    单数 "video" 或附加 sort/rating 参数会触发服务端 500。
    """
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    try:
        if query.startswith("@"):
            await iwara_user_videos(query.lstrip("@").strip(), page, emit_result=True)
            return
        emit({"event": "search_loading", "loading": True})
        page = max(1, page or 1)
        api_page = page - 1  # 前端页码从 1 开始，API 从 0 开始
        data = await asyncio.to_thread(
            _iwara_api_get, "/search",
            {"query": query, "type": "videos", "page": api_page, "limit": 32},
        )
        raw = data.get("results")
        if isinstance(raw, dict):
            raw = raw.get("video") or raw.get("videos") or []
        if not isinstance(raw, list):
            raw = []
        results = [_iwara_map_video(v) for v in raw]
        count = data.get("count")
        if not isinstance(count, int):
            count = len(results)
        emit({"event": "search_result", "query": query, "site": "iwara",
              "items": results, "page": page,
              "has_more": (page - 1) * 32 + len(results) < count, "total_results": count})
        if results:
            asyncio.create_task(_cache_thumbnails(results))
        logging.info("Iwara 搜索 '%s': %d 个结果", query, len(results))
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"Iwara 搜索失败: {exc}（请检查网络或代理设置）"})
        logging.exception("Iwara 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


async def iwara_user_videos(username: str, page: int = 0, emit_result: bool = False) -> None:
    """获取指定用户上传的全部视频（分页）。"""
    try:
        if emit_result:
            emit({"event": "search_loading", "loading": True})
        profile = await asyncio.to_thread(_iwara_api_get, f"/profile/{username}", None)
        user = profile.get("user") or {}
        user_id = user.get("id") or ""
        if not user_id:
            emit({"event": "search_error", "message": f"找不到 Iwara 用户 @{username}"})
            return
        data = await asyncio.to_thread(
            _iwara_api_get, "/videos",
            {"user": user_id, "page": max(0, (page or 1) - 1), "limit": 32, "sort": "date"},
        )
        results = [_iwara_map_video(v) for v in (data.get("results") or [])]
        count = data.get("count") or len(results)
        if emit_result:
            emit({"event": "search_result", "query": f"@{username}", "site": "iwara",
                  "items": results, "page": max(1, page),
                  "has_more": max(0, (page or 1) - 1) + 1 < (count + 31) // 32, "total_results": count,
                  "label": f"@{username} 的视频（{user.get('name') or username}）"})
        else:
            emit({"event": "iwara_user_videos", "username": username,
                  "videos": results, "page": max(0, page),
                  "has_more": max(0, (page or 1) - 1) + 1 < (count + 31) // 32})
    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "search_error", "message": f"获取用户视频失败: {exc}"})
        logging.exception("Iwara 用户视频获取失败")
    finally:
        if emit_result:
            emit({"event": "search_loading", "loading": False})


def _iwara_x_version(file_url: str) -> str:
    """计算 fileUrl 的 X-Version 签名（sha1(路径末段_expires_盐)）。"""
    from urllib.parse import parse_qs
    up = urlparse(file_url)
    params = parse_qs(up.query)
    paths = up.path.rstrip("/").split("/")
    expires = (params.get("expires") or [""])[0]
    return hashlib.sha1("_".join((paths[-1], expires, IWARA_SALT)).encode()).hexdigest()


def _iwara_resolve_best_url(file_url: str) -> tuple[str, str]:
    """解析视频源列表，返回 (最高画质直链, MIME)。画质优先级 Source > 540 > 360。"""
    if not file_url:
        return "", ""
    headers = {"X-Version": _iwara_x_version(file_url)}
    auth = _iwara_auth_headers()
    if auth:
        headers.update(auth)
    resp = _iwara_session.get(file_url, timeout=20, headers=headers)
    resp.raise_for_status()
    files = resp.json() if resp.content else []
    if not isinstance(files, list) or not files:
        return "", ""
    best = min(
        files,
        key=lambda f: IWARA_QUALITY_PREF.get(str(f.get("name") or "").lower(), 9),
    )
    src = best.get("src") or {}
    url = src.get("download") or src.get("view") or ""
    return url, best.get("type") or "video/mp4"


def _iwara_video_ext(mime: str) -> str:
    return {"video/mp4": ".mp4", "video/webm": ".webm"}.get(mime, ".mp4")


async def iwara_inspect(url: str, options: dict) -> None:
    """解析 Iwara 视频页 / 用户主页 → 文件列表（视频直链下载时重新解析）。"""
    m_video = re.search(r"iwara\.(?:tv|ai)/video/([A-Za-z0-9_-]+)", url, re.I)
    m_user = re.search(r"iwara\.(?:tv|ai)/(?:profile|user)/([A-Za-z0-9_-]+)", url, re.I)
    if not m_video and not m_user:
        emit({"event": "inspect_error", "message": "无法识别的 Iwara 链接（支持 /video/{id} 与 /profile/{用户名}）"})
        return
    try:
        album_name = ""
        if m_video:
            video_ids = [m_video.group(1)]
        else:
            # 用户主页：翻页拉取全部视频 ID（上限 20 页 = 640 个防滥用）
            username = m_user.group(1)
            profile = await asyncio.to_thread(_iwara_api_get, f"/profile/{username}", None)
            user = profile.get("user") or {}
            user_id = user.get("id") or ""
            if not user_id:
                emit({"event": "inspect_error", "message": f"找不到 Iwara 用户 @{username}"})
                return
            album_name = user.get("name") or username
            emit({"event": "inspect_progress", "current": 0, "total": 0, "filename": f"获取 @{username} 的视频列表..."})
            video_ids = []
            for p in range(20):
                data = await asyncio.to_thread(
                    _iwara_api_get, "/videos",
                    {"user": user_id, "page": p, "limit": 32, "sort": "date"},
                )
                page_videos = data.get("results") or []
                if not page_videos:
                    break
                video_ids.extend(v.get("id") for v in page_videos if v.get("id"))
                if len(page_videos) < 32:
                    break
            if not video_ids:
                emit({"event": "inspect_error", "message": f"@{username} 没有可下载的视频"})
                return

        items: list[dict] = []
        total = len(video_ids)
        emit({"event": "inspect_progress", "current": 0, "total": total, "filename": ""})
        for idx, vid in enumerate(video_ids):
            data = await asyncio.to_thread(_iwara_api_get, f"/video/{vid}", None)
            errmsg = data.get("message")
            if errmsg:
                logging.warning("Iwara 视频 %s 跳过: %s", vid, errmsg)
                continue
            if not data.get("fileUrl"):
                logging.warning("Iwara 视频 %s 无文件源", vid)
                continue
            user = data.get("user") or {}
            file = data.get("file") or {}
            thumb = ""
            if file.get("id"):
                thumb = f"https://files.iwara.tv/image/thumbnail/{file['id']}/thumbnail-00.jpg"
            title = sanitize_directory_name((data.get("title") or f"iwara_{vid}").strip())
            items.append({
                "filename": f"{title}.mp4",
                "size": None,
                "item_page": f"https://www.iwara.tv/video/{vid}",
                "status": "ok",
                "thumbnail": thumb,
                "media_url": data.get("fileUrl"),
                "site": "iwara",
                "video_id": vid,
                "post_title": data.get("title") or title,
                "post_date": (data.get("createdAt") or "")[:10],
                "artist": user.get("name") or user.get("username") or "",
            })
            emit({"event": "inspect_progress", "current": idx + 1, "total": total, "filename": title})
        if not items:
            emit({"event": "inspect_error", "message": "没有解析到可下载的视频（可能为私有或需登录）"})
            return
        album = album_name or items[0].get("artist") or items[0].get("post_title") or "Iwara"
        album_id = f"iwara_{video_ids[0] if m_video else (user_id or '')}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        if m_user:
            _save_album_cache(f"iwara_user_{m_user.group(1)}", {
                "album_name": album, "album_id": album_id,
                "is_album": True, "items": items,
            })
        emit({
            "event": "inspect_complete",
            "album_name": album,
            "album_id": album_id,
            "is_album": True,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("Iwara 解析完成: %s, 共 %d 个视频", album, len(items))
    except PermissionError as exc:
        emit({"event": "inspect_error", "message": str(exc)})
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"Iwara 解析失败: {exc}（请检查网络或代理设置）"})
        logging.exception("Iwara 解析过程出错")


# ============================
# 增量下载状态（全站点通用）
# ============================
DOWNLOAD_STATE_FILE = "cache/download_state.json"


def _load_download_state() -> dict:
    """读取各相册的下载进度状态。"""
    try:
        with open(DOWNLOAD_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_download_state(state: dict) -> None:
    """保存下载进度状态。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(DOWNLOAD_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存下载状态失败: %s", exc)


def _mark_items_new(album_id: str | None, items: list[dict]) -> None:
    """给解析出的文件列表标记 is_new（上次下载之后新增的文件）。

    判定规则（满足任一即为新）：
    - 该文件的 item_page 不在上次已下载集合中
    - 文件带 post_date 且晚于上次下载时间
    """
    if not album_id or not items:
        return
    state = _load_download_state()
    album_state = state.get(album_id) or {}
    downloaded = set(album_state.get("downloaded", []))
    last_date = album_state.get("last_downloaded", "")

    new_count = 0
    for item in items:
        key = item.get("item_page", "")
        is_new = key not in downloaded
        post_date = item.get("post_date") or ""
        if not is_new and post_date and last_date and post_date > last_date:
            is_new = True
        item["is_new"] = is_new
        if is_new:
            new_count += 1
    if new_count:
        logging.info("增量标记: %s 有 %d 个新文件", album_id, new_count)


def _update_download_state(album_id: str | None, items: list[dict]) -> None:
    """下载成功后更新相册的下载进度（记录已下载文件和最后下载时间）。"""
    if not album_id or not items:
        return
    state = _load_download_state()
    album_state = state.get(album_id) or {"downloaded": [], "last_downloaded": ""}
    downloaded = set(album_state.get("downloaded", []))
    for item in items:
        key = item.get("item_page", "")
        if key:
            downloaded.add(key)
    album_state["downloaded"] = sorted(downloaded)[-3000:]  # 防止无限增长
    album_state["last_downloaded"] = datetime.now().isoformat(timespec="seconds")
    state[album_id] = album_state
    _save_download_state(state)
    logging.info("下载状态已更新: %s (累计 %d 个文件)", album_id, len(downloaded))


# ============================
# Hanime1 站点支持 (hanime1.me，里番视频站，X站类型)
# ============================
# - 服务端渲染 HTML（Laravel），无公开 JSON API
# - 登录: GET /login 取 _token → POST /login {email,password,submit:login}
#   会话 cookie（remember_token）长期有效；密码一并加密保存用于自动重登
# - 搜索: GET /search?query=&genre=&sort=&page=N（Laravel 分页，rel="next" 翻页）
# - 视频页: GET /watch?v={id} → <video><source> MP4 直链（480/720/1080，secure 签名会过期）
# - 评论: GET /loadComment?id={vid}&type=video（JSON 内嵌 HTML）；发表 POST /createComment
#   注意：网站本身不提供删除评论功能（/deleteComment 服务端已损坏，任何参数都 500）
# - 收藏: POST /save {input_id:"save", video_id, is_checked}（"稍後觀看"播放清单）
# - 国内需代理（默认 http://127.0.0.1:10809）

HANIME_BASE = "https://hanime1.me"
HANIME_DEFAULT_PROXY = "http://127.0.0.1:10809"
# 分类（与官网导航一致；"新番預告"是独立页面 /previews/{YYYYMM}，不在此列）
HANIME_GENRES = ["裏番", "泡麵番", "Motion Anime", "3DCG", "2.5D", "2D動畫", "AI生成", "MMD", "Cosplay"]
# 排序方式（官网排序下拉的 data-value）
HANIME_SORTS = ["最新上市", "最新上傳", "本日排行", "本週排行", "本月排行", "觀看次數", "讚好比例", "時長最長"]

_hanime_proxy = HANIME_DEFAULT_PROXY
_hanime_last_req = 0.0
_hanime_username = ""

_hanime_session = requests.Session()
_hanime_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
})


def hanime_set_proxy(proxy: str) -> None:
    """设置 Hanime1 代理（空 = 直连）。"""
    global _hanime_proxy
    _hanime_proxy = (proxy or "").strip()
    if _hanime_proxy and not _hanime_proxy.startswith(("http://", "https://", "socks5://")):
        _hanime_proxy = "http://" + _hanime_proxy
    proxies = {"http": _hanime_proxy, "https": _hanime_proxy} if _hanime_proxy else {}
    _hanime_session.proxies = proxies
    emit({"event": "hanime_proxy_set", "proxy": _hanime_proxy})


def _hanime_throttle(min_interval: float = 0.6) -> None:
    """请求节流：连续请求过快会被 Cloudflare 拦截。"""
    global _hanime_last_req
    wait = _hanime_last_req + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _hanime_last_req = time.time()


def _hanime_load_cred() -> dict:
    """读取已保存的 Hanime1 登录信息（加密存储：cookies + 邮箱 + 密码）。"""
    return _secure_store_read_cred("hanime")


def _hanime_save_cred(data: dict) -> None:
    _secure_store_write_cred("hanime", dict(data))


def _hanime_restore_session() -> None:
    """启动时从加密存储恢复会话 cookie。"""
    global _hanime_username
    cred = _hanime_load_cred()
    cookies = cred.get("cookies") or {}
    for name, value in cookies.items():
        try:
            _hanime_session.cookies.set(name, value, domain=".hanime1.me")
        except Exception:
            pass
    _hanime_username = cred.get("username") or ""


def _hanime_sync_cookies(cred: dict) -> dict:
    """把当前会话 cookie 写回凭据（XSRF-TOKEN / remember_token 会刷新）。"""
    cred["cookies"] = {c.name: c.value for c in _hanime_session.cookies}
    return cred


def _hanime_get(path: str, params: dict | None = None) -> requests.Response:
    """带节流的 GET（返回原始 Response）。"""
    _hanime_throttle()
    return _hanime_session.get(f"{HANIME_BASE}{path}", params=params, timeout=25)


def _hanime_soup(path: str, params: dict | None = None) -> BeautifulSoup | None:
    resp = _hanime_get(path, params)
    if resp.status_code != 200:
        raise PermissionError(f"Hanime1 返回 HTTP {resp.status_code}")
    return BeautifulSoup(resp.text, "html.parser")


def _hanime_csrf(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]
    inp = soup.find("input", attrs={"name": "_token"})
    return (inp.get("value") if inp else "") or ""


def _hanime_logged_in(soup: BeautifulSoup) -> bool:
    """页面里是否处于登录状态（右上角用户弹窗存在）。"""
    return bool(soup.find(id="user-modal-name") or soup.select_one("form[action*='/logout']"))


def _hanime_parse_card(card: BeautifulSoup) -> dict | None:
    """列表卡片（video-item-container）→ 前端视频卡片。"""
    link = card.select_one("a.video-link") or card.find("a", href=re.compile(r"watch\?v="))
    if not link:
        return None
    m = re.search(r"watch\?v=(\w+)", link.get("href") or "")
    if not m:
        return None
    vid = m.group(1)
    img = card.select_one("img.main-thumb") or card.find("img")
    duration = card.select_one(".duration")
    stats = [s.get_text(strip=True) for s in card.select(".stat-item")]
    rating = ""
    views = ""
    for s in stats:
        if "%" in s:
            rating = s
        else:
            views = s
    title = (card.select_one(".title") or {}).get_text(strip=True) if card.select_one(".title") else ""
    if not title:
        title = card.get("title") or ""
    author_el = card.select_one(".subtitle a")
    author = author_el.get_text(strip=True) if author_el else ""
    time_el = card.select_one(".subtitle-time")
    return {
        "album_name": title or f"hanime_{vid}",
        "album_url": f"{HANIME_BASE}/watch?v={vid}",
        "thumbnail": (img.get("src") or "") if img else "",
        "files": 1,
        "site": "hanime",
        "video_id": vid,
        "author": author,
        "duration": duration.get_text(strip=True) if duration else "",
        "rating": rating,
        "views": views,
        "posted": time_el.get_text(strip=True).lstrip("• ").strip() if time_el else "",
    }


def _hanime_parse_cards(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for card in soup.select("div.video-item-container"):
        item = _hanime_parse_card(card)
        if item:
            items.append(item)
    return items


def _hanime_has_next(soup: BeautifulSoup) -> bool:
    return bool(soup.find("a", rel="next") or soup.select_one("a.page-link[rel='next']"))


def hanime_login(email: str, password: str) -> None:
    """Hanime1 登录（邮箱 + 密码；会话 cookie 与密码一起加密保存）。"""
    global _hanime_username
    try:
        soup = _hanime_soup("/login")
        token = _hanime_csrf(soup)
        resp = _hanime_session.post(
            f"{HANIME_BASE}/login", timeout=25,
            data={"_token": token, "email": email, "password": password, "submit": "login"},
        )
        home = _hanime_soup("/")
        if not _hanime_logged_in(home):
            emit({"event": "hanime_login_result", "success": False,
                  "message": "登录失败（邮箱或密码错误）"})
            return
        name_el = home.find(id="user-modal-name")
        username = name_el.get_text(strip=True) if name_el else email
        # 从用户中心链接提取 user_id
        uid = ""
        um = home.select_one("a.user-modal-link[href*='/user/']")
        if um:
            mm = re.search(r"/user/(\d+)", um.get("href") or "")
            if mm:
                uid = mm.group(1)
        _hanime_username = username
        cred = {"email": email, "password": password, "username": username, "user_id": uid}
        _hanime_save_cred(_hanime_sync_cookies(cred))
        _emit_login_info()
        emit({"event": "hanime_login_result", "success": True, "username": username,
              "message": "Hanime1 登录成功"})
    except requests.RequestException as exc:
        emit({"event": "hanime_login_result", "success": False,
              "message": f"连接失败: {exc}（国内建议在设置里配置 Hanime1 代理）",
              "network_issue": True})
    except Exception as exc:
        emit({"event": "hanime_login_result", "success": False, "message": f"登录失败: {exc}"})


def hanime_logout() -> None:
    global _hanime_username
    _secure_store_clear_cred("hanime")
    _hanime_session.cookies.clear()
    _hanime_username = ""
    _emit_login_info()
    emit({"event": "hanime_login_result", "success": False, "logout": True,
          "message": "已退出 Hanime1 登录"})


def hanime_check_login(silent: bool = False) -> None:
    """检查 Hanime1 登录状态（会话失效时用保存的密码自动重登）。"""
    global _hanime_username
    cred = _hanime_load_cred()
    if not cred.get("cookies"):
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": "" if silent else "未登录"})
        return
    try:
        home = _hanime_soup("/")
        if _hanime_logged_in(home):
            name_el = home.find(id="user-modal-name")
            username = name_el.get_text(strip=True) if name_el else (cred.get("username") or "")
            _hanime_username = username
            cred["username"] = username
            if not cred.get("user_id"):
                um = home.select_one("a.user-modal-link[href*='/user/']")
                if um:
                    mm = re.search(r"/user/(\d+)", um.get("href") or "")
                    if mm:
                        cred["user_id"] = mm.group(1)
            _hanime_save_cred(_hanime_sync_cookies(cred))
            _emit_login_info()
            emit({"event": "hanime_login_result", "success": True, "silent": silent,
                  "username": username, "message": "Hanime1 登录有效"})
            return
        # 会话失效 → 用保存的密码自动重登
        if cred.get("email") and cred.get("password"):
            _hanime_session.cookies.clear()
            hanime_login(cred["email"], cred["password"])
            return
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": "登录已失效，请重新登录"})
    except requests.RequestException as exc:
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": f"连接失败: {exc}（请检查网络或 Hanime1 代理设置）",
              "network_issue": True})
    except Exception as exc:
        emit({"event": "hanime_login_result", "success": False, "silent": silent,
              "message": f"检查登录失败: {exc}"})


async def hanime_home() -> None:
    """Hanime1 主页：各分区（最新上市/最新上傳 + 每个分类）的视频，每区最多 20 条。"""
    emit({"event": "hanime_home_loading", "loading": True})
    try:
        soup = await asyncio.to_thread(_hanime_soup, "/")
        sections: list[dict] = []
        # 每个 home-rows-videos-wrapper 前面最近的 h3 是分区标题
        for wrapper in soup.select("div.home-rows-videos-wrapper"):
            # 向上找分区标题（h3 在 wrapper 的同级/祖先前面）
            title = ""
            prev = wrapper.find_previous("h3")
            if prev:
                # 去掉"查看更多"链接文字与 material 图标文字残留
                title = re.sub(r"(查看更多|arrow_forward_ios)+\s*$", "", prev.get_text(strip=True)).strip()
            items = _hanime_parse_cards(wrapper)[:20]
            if items:
                sections.append({"title": title or "推荐", "items": items})
        all_items = [it for sec in sections for it in sec["items"]]
        _apply_cached_thumbnails(all_items)
        asyncio.create_task(_cache_thumbnails(all_items))
        emit({"event": "hanime_home", "sections": sections,
              "genres": HANIME_GENRES, "sorts": HANIME_SORTS})
        logging.info("Hanime1 主页: %d 个分区", len(sections))
    except Exception as exc:
        emit({"event": "hanime_home", "sections": [],
              "error": f"获取主页失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 主页获取失败")
    finally:
        emit({"event": "hanime_home_loading", "loading": False})


async def hanime_search(query: str, page: int = 1, genre: str = "",
                        sort: str = "", tags: list | None = None) -> None:
    """Hanime1 搜索（关键词 + 可选分类/排序/标签过滤，Laravel 分页）。"""
    query = (query or "").strip()
    genre = genre or ""
    if not query and not genre and not tags:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if query:
            params["query"] = query
        if genre and genre != "全部":
            params["genre"] = genre
        if sort:
            params["sort"] = sort
        soup = await asyncio.to_thread(_hanime_soup, "/search", params)
        results = _hanime_parse_cards(soup)
        label_parts = [query] if query else []
        if genre:
            label_parts.append(genre)
        emit({
            "event": "search_result", "query": query or genre, "site": "hanime",
            "items": results, "page": page,
            "has_more": _hanime_has_next(soup),
            "genre": genre, "sort": sort,
            "label": " · ".join(label_parts) or "Hanime1",
        })
        if results:
            asyncio.create_task(_cache_thumbnails(results))
        logging.info("Hanime1 搜索 '%s' (genre=%s page=%d): %d 个结果",
                     query, genre, page, len(results))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"Hanime1 搜索失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


def _hanime_best_source(sources: list[dict]) -> dict:
    """选最高画质（1080 > 720 > 480 > 其他）。"""
    def rank(s: dict) -> int:
        try:
            return -int(s.get("quality") or 0)
        except (ValueError, TypeError):
            return 0
    return sorted(sources, key=rank)[0] if sources else {}


def _hanime_parse_detail(soup: BeautifulSoup, video_id: str) -> dict:
    """watch 页 → 视频详情字典。"""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    title = (og_title.get("content") if og_title else "") or ""
    title = re.sub(r"\s*-\s*Hanime1\.me\s*$", "", title).strip()
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    description = (og_desc.get("content") if og_desc else "") or ""
    # 上传者（video-details-wrapper 内第一个 /user/ 链接）
    uploader = ""
    uploader_id = ""
    up_el = soup.select_one(".video-details-wrapper a[href*='/user/'] span")
    if up_el:
        uploader = up_el.get_text(strip=True)
    up_link = soup.select_one(".video-details-wrapper a[href*='/user/']")
    if up_link:
        mm = re.search(r"/user/(\d+)", up_link.get("href") or "")
        if mm:
            uploader_id = mm.group(1)
    # 观看数 + 日期（"觀看次數：209.7萬次  2026-08-08"）
    views = ""
    date = ""
    for div in soup.select(".video-details-wrapper div"):
        text = div.get_text(" ", strip=True)
        if "觀看次數" in text or "观看次数" in text:
            mm = re.search(r"[觀观]看次數[：:]\s*([^\s]+)", text)
            if mm:
                views = mm.group(1)
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", text)
            if dm:
                date = dm.group(1)
            break
    # 标签
    tags = []
    for tag_el in soup.select(".single-video-tag a"):
        name = tag_el.get_text(strip=True)
        name = re.sub(r"\s*\(\d+\)$", "", name)
        if name:
            tags.append(name)
    # 播放源（<source src="...mp4?secure=..." size="720">）
    sources = []
    for src in soup.select("#player source"):
        url = src.get("src") or ""
        if url.startswith("//"):
            url = "https:" + url
        if url:
            sources.append({"quality": src.get("size") or "", "url": url})
    # 缩略图（player 的 poster）
    player = soup.find(id="player")
    poster = (player.get("poster") or "") if player else ""
    # 收藏状态（"稍後觀看" checkbox 是否勾选）
    saved = False
    save_cb = soup.find("input", id="save")
    if save_cb and save_cb.has_attr("checked"):
        saved = True
    return {
        "album_name": title or f"hanime_{video_id}",
        "album_url": f"{HANIME_BASE}/watch?v={video_id}",
        "video_id": video_id,
        "site": "hanime",
        "title": title,
        "description": description,
        "thumbnail": poster,
        "uploader": uploader,
        "uploader_id": uploader_id,
        "views": views,
        "post_date": date,
        "tags": tags,
        "sources": sources,
        "saved": saved,
    }


def _hanime_parse_comments_html(html: str) -> list[dict]:
    """loadComment 返回的评论 HTML → 评论列表（含回复，缩进标记）。"""
    soup = BeautifulSoup(html or "", "html.parser")
    comments: list[dict] = []
    for wrapper in soup.select("div.report-btn-wrapper"):
        # 判断是否为回复（祖先有 reply-section-wrapper）
        is_reply = False
        parent = wrapper.parent
        while parent is not None:
            pid = parent.get("id") or "" if hasattr(parent, "get") else ""
            if str(pid).startswith("reply-section-wrapper"):
                is_reply = True
                break
            parent = parent.parent
        texts = wrapper.select("div.comment-index-text")
        if len(texts) < 2:
            continue
        head = texts[0].get_text(" ", strip=True)
        body = texts[1].get_text(strip=True)
        # 用户名 + 相对时间（"yuejiaxiaosi  1分鐘前"）
        username = head
        posted = ""
        tm = re.search(r"(\d+\s*(?:秒|分鐘|小時|天|週|月|年)前)", head)
        if tm:
            posted = tm.group(1)
            username = head[:tm.start()].strip()
        report = wrapper.select_one("span.report-btn")
        avatar_el = wrapper.find_previous("img", class_="img-circle")
        comments.append({
            "id": (report.get("data-reportable-id") or "") if report else "",
            "username": username,
            "text": body,
            "posted": posted,
            "avatar": (avatar_el.get("src") or "") if avatar_el else "",
            "is_reply": is_reply,
        })
    return comments


async def hanime_video_detail(video_id: str) -> None:
    """Hanime1 视频详情：名称/视频源/tags/评论/收藏状态。"""
    emit({"event": "hanime_detail_loading", "loading": True})
    try:
        soup = await asyncio.to_thread(_hanime_soup, "/watch", {"v": video_id})
        video = _hanime_parse_detail(soup, video_id)
        # 在线播放：最高画质直链经本地媒体代理（带代理转发）
        best = _hanime_best_source(video["sources"])
        video["video_url"] = best.get("url") or ""
        # 评论（loadComment 需登录后才返回内容）
        comments: list[dict] = []
        comment_count = 0
        try:
            _hanime_throttle()
            resp = await asyncio.to_thread(
                lambda: _hanime_session.get(
                    f"{HANIME_BASE}/loadComment",
                    params={"id": video_id, "type": "video",
                            "content": "comment-tabcontent"},
                    timeout=30,
                ))
            data = {}
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    data = {}
            comments = _hanime_parse_comments_html(data.get("comments") or "")
            comment_count = data.get("comment_count") or len(comments)
        except Exception:
            pass
        _apply_cached_thumbnails([video])
        avatars = [{"thumbnail": c["avatar"]} for c in comments if c.get("avatar")]
        _apply_cached_thumbnails(avatars)
        asyncio.create_task(_cache_thumbnails([video] + avatars))
        video.pop("sources", None)
        emit({"event": "hanime_video_detail", "video": video, "comments": comments,
              "comment_count": comment_count})
        logging.info("Hanime1 视频详情: %s", video_id)
    except Exception as exc:
        emit({"event": "hanime_video_detail", "video": None,
              "error": f"获取视频详情失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 视频详情获取失败")
    finally:
        emit({"event": "hanime_detail_loading", "loading": False})


async def hanime_comments(video_id: str) -> None:
    """刷新视频评论列表。"""
    try:
        data = {}
        try:
            _hanime_throttle()
            resp = await asyncio.to_thread(
                lambda: _hanime_session.get(
                    f"{HANIME_BASE}/loadComment",
                    params={"id": video_id, "type": "video",
                            "content": "comment-tabcontent"},
                    timeout=30,
                ))
            if resp.status_code == 200:
                data = resp.json()
        except Exception:
            data = {}
        comments = _hanime_parse_comments_html(data.get("comments") or "")
        avatars = [{"thumbnail": c["avatar"]} for c in comments if c.get("avatar")]
        _apply_cached_thumbnails(avatars)
        asyncio.create_task(_cache_thumbnails(avatars))
        emit({"event": "hanime_comments", "video_id": video_id, "items": comments,
              "comment_count": data.get("comment_count") or len(comments)})
    except Exception as exc:
        emit({"event": "hanime_comments", "video_id": video_id, "items": [],
              "error": f"获取评论失败: {exc}"})


def hanime_add_comment(video_id: str, text: str) -> None:
    """发表评论（POST /createComment，表单字段与官网一致）。"""
    text = (text or "").strip()
    if not text:
        emit({"event": "hanime_comment_result", "success": False, "message": "评论内容为空"})
        return
    cred = _hanime_load_cred()
    if not cred.get("cookies"):
        emit({"event": "hanime_comment_result", "success": False,
              "message": "未登录：请先登录 Hanime1 账号"})
        return
    try:
        soup = _hanime_soup("/watch", {"v": video_id})
        if not _hanime_logged_in(soup):
            # 会话失效 → 自动重登一次
            if cred.get("email") and cred.get("password"):
                _hanime_session.cookies.clear()
                hanime_login(cred["email"], cred["password"])
                cred = _hanime_load_cred()
                soup = _hanime_soup("/watch", {"v": video_id})
            if not _hanime_logged_in(soup):
                emit({"event": "hanime_comment_result", "success": False,
                      "message": "登录已失效，评论失败"})
                return
        token = _hanime_csrf(soup)
        user_id = cred.get("user_id") or ""
        count_el = soup.find("input", id="comment-count")
        count = count_el.get("value") if count_el else "0"
        _hanime_throttle()
        resp = _hanime_session.post(
            f"{HANIME_BASE}/createComment", timeout=25,
            data={
                "_token": token,
                "comment-user-id": user_id,
                "comment-type": "video",
                "comment-foreign-id": video_id,
                "comment-count": count,
                "comment-text": text,
            },
            headers={"Referer": f"{HANIME_BASE}/watch?v={video_id}",
                     "X-Requested-With": "XMLHttpRequest"},
        )
        if resp.status_code == 200:
            _hanime_save_cred(_hanime_sync_cookies(_hanime_load_cred()))
            emit({"event": "hanime_comment_result", "success": True,
                  "message": "评论已发表", "video_id": video_id})
        else:
            emit({"event": "hanime_comment_result", "success": False,
                  "message": f"评论失败: HTTP {resp.status_code}"})
    except requests.RequestException as exc:
        emit({"event": "hanime_comment_result", "success": False,
              "message": f"连接失败: {exc}"})
    except Exception as exc:
        emit({"event": "hanime_comment_result", "success": False,
              "message": f"评论失败: {exc}"})


def hanime_save_video(video_id: str, saved: bool) -> None:
    """收藏 / 取消收藏视频（"稍後觀看"播放清单，POST /save）。"""
    cred = _hanime_load_cred()
    if not cred.get("cookies"):
        emit({"event": "hanime_save_result", "success": False, "saved": saved,
              "message": "未登录：请先登录 Hanime1 账号"})
        return
    try:
        soup = _hanime_soup("/watch", {"v": video_id})
        token = _hanime_csrf(soup)
        _hanime_throttle()
        resp = _hanime_session.post(
            f"{HANIME_BASE}/save", timeout=25,
            data={"input_id": "save", "user_id": cred.get("user_id") or "",
                  "video_id": video_id, "is_checked": "true" if saved else "false"},
            headers={"Referer": f"{HANIME_BASE}/watch?v={video_id}",
                     "X-Requested-With": "XMLHttpRequest", "X-CSRF-TOKEN": token},
        )
        if resp.status_code == 200:
            _hanime_save_cred(_hanime_sync_cookies(_hanime_load_cred()))
            emit({"event": "hanime_save_result", "success": True, "saved": saved,
                  "video_id": video_id,
                  "message": "已加入稍後觀看" if saved else "已取消收藏"})
        else:
            emit({"event": "hanime_save_result", "success": False, "saved": not saved,
                  "message": f"操作失败: HTTP {resp.status_code}"})
    except Exception as exc:
        emit({"event": "hanime_save_result", "success": False, "saved": not saved,
              "message": f"操作失败: {exc}"})


# 用户中心各 tab 对应的路径后缀（官网账号功能）
HANIME_USER_TABS = {
    "history": ("histories", "觀看紀錄"),
    "saves": ("saves", "稍後觀看"),
    "likes": ("likes", "讚好的影片"),
    "uploaded": ("uploaded", "上傳的影片"),
    "uploading": ("uploading", "審核中的影片"),
}


async def hanime_user_videos(tab: str, page: int = 1) -> None:
    """用户中心的视频列表（觀看紀錄/稍後觀看/讚好的影片/上傳的影片/審核中的影片）。"""
    cred = _hanime_load_cred()
    uid = cred.get("user_id") or ""
    tab = tab or "saves"
    path, label = HANIME_USER_TABS.get(tab, HANIME_USER_TABS["saves"])
    if not uid:
        emit({"event": "hanime_user_videos", "tab": tab, "items": [], "page": 1,
              "has_more": False, "error": "未登录或缺少用户信息：请先登录 Hanime1 账号"})
        return
    emit({"event": "hanime_user_loading", "loading": True})
    try:
        page = max(1, page or 1)
        soup = await asyncio.to_thread(
            _hanime_soup, f"/user/{uid}/{path}", {"page": page})
        items = _hanime_parse_cards(soup)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "hanime_user_videos", "tab": tab, "items": items,
              "page": page, "has_more": _hanime_has_next(soup),
              "label": f"我的{label}"})
        logging.info("Hanime1 用户列表 %s 第 %d 页: %d 个", tab, page, len(items))
    except Exception as exc:
        emit({"event": "hanime_user_videos", "tab": tab, "items": [], "page": page,
              "has_more": False, "error": f"获取列表失败: {exc}"})
    finally:
        emit({"event": "hanime_user_loading", "loading": False})


async def hanime_batch_download(video_ids: list, options: dict) -> None:
    """批量下载 Hanime1 视频（逐个解析详情取标题，下载时重新解析最高画质直链）。"""
    video_ids = [str(v).strip() for v in (video_ids or []) if str(v).strip()]
    if not video_ids:
        emit({"event": "hanime_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "请先勾选要下载的视频"})
        return
    total = len(video_ids)
    failed: list[str] = []
    items: list[dict] = []
    emit({"event": "hanime_batch_progress", "done": 0, "total": total,
          "message": f"正在解析 {total} 个视频..."})
    try:
        for i, vid in enumerate(video_ids):
            try:
                soup = await asyncio.to_thread(_hanime_soup, "/watch", {"v": vid})
                detail = _hanime_parse_detail(soup, vid)
                title = sanitize_directory_name((detail["title"] or f"hanime_{vid}").strip())
                items.append({
                    "filename": f"{title}.mp4",
                    "size": None,
                    "item_page": f"{HANIME_BASE}/watch?v={vid}",
                    "status": "ok",
                    "thumbnail": "",
                    "media_url": _hanime_best_source(detail["sources"]).get("url") or "",
                    "site": "hanime",
                    "video_id": vid,
                    "post_title": detail["title"] or title,
                    "post_date": detail.get("post_date") or "",
                    "artist": detail.get("uploader") or "",
                })
            except Exception as exc:
                failed.append(f"{vid}（{exc}）")
                logging.warning("Hanime1 视频 %s 解析失败: %s", vid, exc)
            emit({"event": "hanime_batch_progress", "done": i + 1, "total": total,
                  "message": f"解析进度 {i + 1}/{total}"})
        if items:
            album = "Hanime1 批量下载" if len(items) > 1 else (items[0].get("post_title") or "Hanime1")
            task_id = download_manager.submit(
                f"{HANIME_BASE}/", items, options, album, "hanime_batch",
            )
            download_manager.start(task_id)
        summary = f"批量下载已提交：{len(items)}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "hanime_batch_done", "done": len(items), "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "hanime_batch_done", "done": len(items), "total": total,
              "failed": failed, "message": f"批量下载中断: {exc}"})


# ============================
# Oreno3D 站点支持 (oreno3d.com，MMD 视频聚合索引站，纯资源站类型)
# ============================
# - 服务端渲染 HTML（Laravel），无需登录，裸请求可访问全部内容
# - 列表: GET /（默认人気排序）?sort=hot|favorites|latest|popularity&page=N
# - 搜索: GET /search?keyword=关键词（可与 sort 组合）
# - 标签: GET /tags/{id}；作者: GET /authors/{id}；标签索引: GET /tags
# - 详情: GET /movies/{id} → "この動画を見る" 按钮 → iwara.tv 视频链接
#   下载/播放复用 Iwara 逻辑（api.iwara.tv 解析最高画质）
# - 视频本体在 iwara，站内仅缩略图（/storage/thumbnails_small/）
ORENO_BASE = "https://oreno3d.com"
EROMMD_BASE = "https://erommdtube.com"
# 四排序（与站点页面上 急上昇/高評価/新着/人気 一一对应）
ORENO_SORTS = {"hot": "急上昇", "favorites": "高評価", "latest": "新着", "popularity": "人気"}

# 两站同库同路由（oreno3d / erommdtube），仅 CSS 选择器不同：一套解析逻辑 + 选择器映射
ORENO_SITES: dict[str, dict] = {
    "oreno3d": {
        "base": ORENO_BASE,
        "label": "Oreno3D",
        "sel_card": "a.box.pop_separate",
        "sel_title": "h2.box-h2",
        "sel_img": "img.main-thumbnail",
        "sel_stats": ".figure-text-in",
        "sel_texts": ".box-text-in",
        "sel_iwara_btn": "a.video-watch-btn2",
        "sel_iwara_fig": None,  # oreno3d 用按钮即可
        "sel_h1_detail": "h1.video-h1",
        "sel_img_detail": "img.video-img",
        "sel_author_link": "section.video-section-tag a[href*='/authors/']",
        # 本视频元数据：标签区(ul.video-tag) + 面包屑(原作/角色)
        "sel_tag_links": "ul.video-tag a[href], ol.breadcrumb a[href]",
        "sel_tag_text": None,
        "sel_stat_text": "div.video-text",
        "sel_comment": "blockquote.video-information-comment",
        "sel_related": "section.g-main-video-related",
        "sel_group_li": "li.group-list-li",
        "sel_group_link": "a.group-list-li-a",
        "sel_group_chara": "div.group-list-li-a-chara",
        "sel_group_number": "div.group-list-li-a-number",
        "sel_pagination": "a.page-link",
    },
    "erommdtube": {
        "base": EROMMD_BASE,
        "label": "EroMMDTube",
        "sel_card": "a.main__list-link",
        "sel_title": "h2.main__list-title",
        "sel_img": "img.main__list-thumbnail",
        "sel_stats": None,  # 统计在 description 文本里
        "sel_texts": None,
        "sel_iwara_btn": None,
        "sel_iwara_fig": "figure.show__figure > a[href*='iwara.tv/video/']",
        "sel_h1_detail": "h1.show__h1",
        "sel_img_detail": "img.show__header-img",
        "sel_author_link": "div.show__authors-link a[href*='/authors/']",
        # 本视频元数据：标签区(含原作/角色/标签混排) + 面包屑
        "sel_tag_links": "ul.show__tag-ul a.show__tag-link, ol.main__breadcrumb a[href]",
        "sel_tag_text": None,
        "sel_stat_text": "ul.show__count li",
        "sel_comment": "blockquote.show__comment-blockquote",
        "sel_related": "section.show__related",
        "sel_group_li": "li.aside__li",
        "sel_group_link": "a.aside__li-link",
        "sel_group_chara": "div.aside__li-chara",
        "sel_group_number": "div.aside__ranking",
        "sel_pagination": "a.main__pagination-link",
    },
}

_oreno_proxy = ""
_erommd_proxy = ""
_oreno_last_req = 0.0

_oreno_session = requests.Session()
_erommd_session = requests.Session()
for _s in (_oreno_session, _erommd_session):
    _s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })


def _oreno_conf(site_key: str) -> dict:
    return ORENO_SITES.get(site_key) or ORENO_SITES["oreno3d"]


def _oreno_session_of(site_key: str) -> requests.Session:
    return _erommd_session if site_key == "erommdtube" else _oreno_session


def _oreno_site_proxy(site_key: str) -> str:
    return _erommd_proxy if site_key == "erommdtube" else _oreno_proxy


def oreno_set_proxy(proxy: str, site_key: str = "oreno3d") -> None:
    """设置 Oreno3D / EroMMDTube 代理（空 = 直连）。"""
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    global _oreno_proxy, _erommd_proxy
    if site_key == "erommdtube":
        _erommd_proxy = proxy
    else:
        _oreno_proxy = proxy
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    _oreno_session_of(site_key).proxies = proxies
    emit({"event": "oreno_proxy_set", "proxy": proxy, "site_key": site_key})


def _oreno_throttle(min_interval: float = 0.5) -> None:
    global _oreno_last_req
    wait = _oreno_last_req + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _oreno_last_req = time.time()


def _oreno_soup(path: str, params: dict | None = None, site_key: str = "oreno3d") -> BeautifulSoup:
    conf = _oreno_conf(site_key)
    _oreno_throttle()
    resp = _oreno_session_of(site_key).get(f"{conf['base']}{path}", params=params, timeout=25)
    if resp.status_code != 200:
        raise PermissionError(f"{conf['label']} 返回 HTTP {resp.status_code}")
    return BeautifulSoup(resp.text, "html.parser")


def _oreno_link_text(a) -> str:
    """链接纯文本（剔除 <i class="material-icons">face/local_offer 等图标文字）。"""
    parts = []
    for s in a.find_all(string=True):
        if s.parent and s.parent.name == "i":
            continue
        parts.append(str(s))
    return "".join(parts).strip()


def _oreno_parse_card(card: BeautifulSoup, site_key: str = "oreno3d") -> dict | None:
    """列表卡片 → 前端视频卡片（oreno3d: a.box.pop_separate / erommdtube: a.main__list-link）。"""
    conf = _oreno_conf(site_key)
    m = re.search(r"/movies/(\d+)", card.get("href") or "")
    if not m:
        return None
    mid = m.group(1)
    h2 = card.select_one(conf["sel_title"])
    img = card.select_one(conf["sel_img"])
    views = ""
    likes = ""
    author = ""
    tags: list[str] = []
    if site_key == "erommdtube":
        # 统计与作者混在 description 文本：person 作者 / play_arrow 再生 / favorite 数
        desc = card.select_one("div.main__list-description")
        text = desc.get_text("|", strip=True) if desc else ""
        parts = [p.strip() for p in text.split("|") if p.strip()]
        nums = [p for p in parts if re.fullmatch(r"[\d.,]+[km]?", p, re.I)]
        author = parts[0] if parts else ""
        if len(nums) >= 1:
            views = nums[0]
        if len(nums) >= 2:
            likes = nums[1]
        # 标签行（sell icon 后的文本）
        tag_el = card.select_one("div.main__list-tag")
        if tag_el:
            tags = tag_el.get_text(" ", strip=True).split()
    else:
        # 播放数/点赞数（figure-text-in，顺序固定：先播放后点赞）
        stats = [d.get_text(strip=True) for d in card.select(conf["sel_stats"])]
        views = stats[0] if len(stats) > 0 else ""
        likes = stats[1] if len(stats) > 1 else ""
        texts = card.select(conf["sel_texts"])
        author = texts[0].get_text(strip=True) if len(texts) > 0 else ""
        tags = (texts[1].get_text(strip=True) if len(texts) > 1 else "").split()
    thumb = (img.get("src") or "") if img else ""
    if thumb.startswith("/"):
        thumb = _oreno_conf(site_key)["base"] + thumb
    return {
        "album_name": (h2.get_text(strip=True) if h2 else "") or f"{site_key}_{mid}",
        "album_url": f"{_oreno_conf(site_key)['base']}/movies/{mid}",
        "thumbnail": thumb,
        "files": 1,
        "site": "oreno" if site_key == "oreno3d" else "erommd",
        "site_key": site_key,
        "video_id": mid,
        "author": author,
        "views": views,
        "likes": likes,
        "tags": tags,
    }


def _oreno_parse_cards(soup: BeautifulSoup, site_key: str = "oreno3d") -> list[dict]:
    items: list[dict] = []
    for card in soup.select(_oreno_conf(site_key)["sel_card"]):
        item = _oreno_parse_card(card, site_key)
        if item:
            items.append(item)
    return items


def _oreno_has_next(soup: BeautifulSoup, site_key: str = "oreno3d") -> bool:
    if soup.find("a", rel="next"):
        return True
    # erommdtube 分页无 rel=next：看 pagination 里是否有比当前页大的页码/省略号
    links = soup.select(_oreno_conf(site_key)["sel_pagination"])
    for a in links:
        href = a.get("href") or ""
        m = re.search(r"[?&]page=(\d+)", href)
        if m and a.get_text(strip=True) in (">", "»", "次へ", "次"):
            return True
    return False


async def oreno_home(page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """Oreno3D / EroMMDTube 主页/列表（默认人気排序，四排序可切换，Laravel 分页）。"""
    emit({"event": "oreno_home_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, "/", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_home", "items": items, "page": page,
              "has_more": _oreno_has_next(soup, site_key), "sort": sort,
              "sorts": ORENO_SORTS, "site_key": site_key})
        logging.info("%s 主页第 %d 页 (sort=%s): %d 个视频",
                     _oreno_conf(site_key)["label"], page, sort, len(items))
    except Exception as exc:
        emit({"event": "oreno_home", "items": [], "page": max(1, page), "has_more": False,
              "sort": sort, "site_key": site_key,
              "error": f"获取列表失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 主页获取失败", _oreno_conf(site_key)["label"])
    finally:
        emit({"event": "oreno_home_loading", "loading": False, "site_key": site_key})


async def oreno_search(query: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """Oreno3D / EroMMDTube 关键词搜索（/search?keyword=）。"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        params: dict = {"keyword": query, "page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, "/search", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        site_tag = "oreno" if site_key == "oreno3d" else "erommd"
        emit({"event": "search_result", "query": query, "site": site_tag,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key),
              "sort": sort, "label": query})
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("%s 搜索 '%s': %d 个结果", _oreno_conf(site_key)["label"], query, len(items))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"{_oreno_conf(site_key)['label']} 搜索失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 搜索失败", _oreno_conf(site_key)["label"])
    finally:
        emit({"event": "search_loading", "loading": False})


async def oreno_tag(tag_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """标签页视频列表。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/tags/{tag_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        tag_name = ""
        h1 = soup.find("h1")
        if h1:
            tag_name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "tag", "id": tag_id, "name": tag_name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "tag", "id": tag_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取标签视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_author(author_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """作者页视频列表。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/authors/{author_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        author_name = ""
        h1 = soup.find("h1")
        if h1:
            author_name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "author", "id": author_id, "name": author_name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "author", "id": author_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取作者视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_character(character_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """角色页视频列表（/characters/{id}）。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/characters/{character_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        name = ""
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "character", "id": character_id, "name": name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "character", "id": character_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取角色视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_origin(origin_id: str, page: int = 1, sort: str = "", site_key: str = "oreno3d") -> None:
    """原作页视频列表（/origins/{id}）。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        params: dict = {"page": page}
        if sort in ORENO_SORTS:
            params["sort"] = sort
        soup = await asyncio.to_thread(_oreno_soup, f"/origins/{origin_id}", params, site_key)
        items = _oreno_parse_cards(soup, site_key)
        name = ""
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "origin", "id": origin_id, "name": name,
              "site_key": site_key,
              "items": items, "page": page, "has_more": _oreno_has_next(soup, site_key), "sort": sort})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "origin", "id": origin_id, "site_key": site_key,
              "items": [], "page": page, "has_more": False, "error": f"获取原作视频失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_characters(site_key: str = "oreno3d") -> None:
    """角色列表（单页全量：人気排序 + 五十音分组均静态内嵌）。"""
    emit({"event": "oreno_chars_loading", "loading": True, "site_key": site_key})
    try:
        soup = await asyncio.to_thread(_oreno_soup, "/characters", None, site_key)
        conf = _oreno_conf(site_key)
        popular: list[dict] = []
        kana_groups: dict[str, list[dict]] = {}
        seen: set[str] = set()
        # 人気区
        for li in soup.select(f"div.sorted-popularity {conf['sel_group_li']}"):
            a = li.select_one(conf["sel_group_link"])
            if not a:
                continue
            m = re.search(r"/characters/(\d+)", a.get("href") or "")
            if not m:
                continue
            cid = m.group(1)
            if cid in seen:
                continue
            seen.add(cid)
            chara_el = a.select_one(conf["sel_group_chara"])
            name = ""
            origin = ""
            if chara_el:
                name = chara_el.get_text(strip=True)
                span = chara_el.find("span")
                if span:
                    origin = span.get_text(strip=True).strip("()")
                    name = chara_el.get_text(strip=True).replace(span.get_text(strip=True), "").strip()
            nums = [d.get_text(strip=True) for d in a.select(conf["sel_group_number"])]
            popular.append({
                "id": cid, "name": name, "origin": origin,
                "rank": nums[0] if nums else "",
                "count": nums[-1] if len(nums) > 1 else "",
            })
        # 五十音区（oreno3d: div.sorted-kana > ul#sort-{行}；erommdtube 同结构）
        for ul in soup.select("div.sorted-kana ul[id]"):
            row = re.sub(r"^sort-", "", ul.get("id") or "")
            for li in ul.select(conf["sel_group_li"]):
                a = li.select_one(conf["sel_group_link"])
                if not a:
                    continue
                m = re.search(r"/characters/(\d+)", a.get("href") or "")
                if not m:
                    continue
                cid = m.group(1)
                chara_el = a.select_one(conf["sel_group_chara"])
                name = ""
                origin = ""
                if chara_el:
                    name = chara_el.get_text(strip=True)
                    span = chara_el.find("span")
                    if span:
                        origin = span.get_text(strip=True).strip("()")
                        name = chara_el.get_text(strip=True).replace(span.get_text(strip=True), "").strip()
                nums = [d.get_text(strip=True) for d in a.select(conf["sel_group_number"])]
                kana_groups.setdefault(row or "?", []).append({
                    "id": cid, "name": name, "origin": origin,
                    "count": nums[-1] if nums else "",
                })
        emit({"event": "oreno_characters", "popular": popular[:300],
              "kana_groups": kana_groups, "site_key": site_key})
        logging.info("%s 角色列表: 人気 %d 个 / %d 个五十音组",
                     conf["label"], len(popular), len(kana_groups))
    except Exception as exc:
        emit({"event": "oreno_characters", "popular": [], "kana_groups": {},
              "site_key": site_key, "error": f"获取角色列表失败: {exc}"})
        logging.exception("角色列表获取失败")
    finally:
        emit({"event": "oreno_chars_loading", "loading": False, "site_key": site_key})


async def oreno_authors_index(page: int = 1, site_key: str = "oreno3d") -> None:
    """人気作者列表（/authors 分页，oreno3d 共约 1919 页）。"""
    emit({"event": "oreno_authors_loading", "loading": True, "site_key": site_key})
    try:
        page = max(1, page or 1)
        soup = await asyncio.to_thread(_oreno_soup, "/authors", {"page": page}, site_key)
        conf = _oreno_conf(site_key)
        authors: list[dict] = []
        seen: set[str] = set()
        for li in soup.select(conf["sel_group_li"]):
            a = li.select_one(conf["sel_group_link"])
            if not a:
                continue
            m = re.search(r"/authors/(\d+)", a.get("href") or "")
            if not m:
                continue
            aid = m.group(1)
            if aid in seen:
                continue
            seen.add(aid)
            chara_el = a.select_one(conf["sel_group_chara"])
            name = chara_el.get_text(strip=True) if chara_el else a.get_text(strip=True)[:30]
            nums = [d.get_text(strip=True) for d in a.select(conf["sel_group_number"])]
            authors.append({"id": aid, "name": name, "rank": nums[0] if nums else ""})
        # 该页内嵌的作者热门视频（可顺带返回给前端直接看）
        items = _oreno_parse_cards(soup, site_key)
        emit({"event": "oreno_authors", "authors": authors, "items": items, "page": page,
              "has_more": _oreno_has_next(soup, site_key), "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_authors", "authors": [], "items": [], "page": page,
              "has_more": False, "site_key": site_key, "error": f"获取作者列表失败: {exc}"})
    finally:
        emit({"event": "oreno_authors_loading", "loading": False, "site_key": site_key})


def _oreno_fav_path() -> Path:
    return Path("cache/oreno_favorites.json")


def _oreno_fav_load() -> dict:
    """本地收藏（两站通用，按 site_key 分组）：{site_key: {movie_id: 卡片dict}}。"""
    try:
        data = json.loads(_oreno_fav_path().read_text("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _oreno_fav_save(data: dict) -> None:
    _oreno_fav_path().parent.mkdir(parents=True, exist_ok=True)
    _oreno_fav_path().write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


async def oreno_toggle_favorite(movie_id: str, card: dict, site_key: str = "oreno3d") -> None:
    """本地收藏/取消收藏（站点无服务端账号体系，收藏保存在本地）。"""
    try:
        data = _oreno_fav_load()
        group = data.setdefault(site_key, {})
        movie_id = str(movie_id)
        if movie_id in group:
            group.pop(movie_id)
            saved = False
        else:
            card = dict(card or {})
            card["video_id"] = movie_id
            card["site_key"] = site_key
            card["saved_at"] = int(time.time())
            group[movie_id] = card
            saved = True
        _oreno_fav_save(data)
        emit({"event": "oreno_fav_result", "video_id": movie_id, "saved": saved,
              "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_fav_result", "video_id": str(movie_id), "saved": False,
              "site_key": site_key, "error": f"收藏操作失败: {exc}"})


async def oreno_favorites(site_key: str = "oreno3d") -> None:
    """本地收藏列表。"""
    emit({"event": "oreno_list_loading", "loading": True, "site_key": site_key})
    try:
        group = (_oreno_fav_load().get(site_key)) or {}
        items = sorted(group.values(), key=lambda x: -(x.get("saved_at") or 0))
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        emit({"event": "oreno_list", "type": "favorites", "id": "", "name": "我的收藏",
              "site_key": site_key, "items": items, "page": 1, "has_more": False, "sort": ""})
    except Exception as exc:
        emit({"event": "oreno_list", "type": "favorites", "id": "", "site_key": site_key,
              "items": [], "page": 1, "has_more": False, "error": f"获取收藏失败: {exc}"})
    finally:
        emit({"event": "oreno_list_loading", "loading": False, "site_key": site_key})


async def oreno_tags_index(site_key: str = "oreno3d") -> None:
    """标签列表 + 热门分类组（tag-groups，名称含作品总数）。"""
    emit({"event": "oreno_tags_loading", "loading": True, "site_key": site_key})
    try:
        soup = await asyncio.to_thread(_oreno_soup, "/tags", None, site_key)
        tags: list[dict] = []
        for a in soup.select("a[href^='/tags/']"):
            m = re.search(r"/tags/(\d+)", a.get("href") or "")
            if not m:
                continue
            name = _oreno_link_text(a)
            if name:
                tags.append({"id": m.group(1), "name": name})
        # 去重
        seen = set()
        unique = []
        for t in tags:
            if t["id"] not in seen:
                seen.add(t["id"])
                unique.append(t)
        # 热门分类组：文本形如 "キャラクター設定 5タグ 171477 作品" → 名称 + 作品总数
        groups: list[dict] = []
        for a in soup.select("a[href*='/tag-groups/']"):
            m = re.search(r"/tag-groups/(\d+)", a.get("href") or "")
            if not m:
                continue
            text = " ".join(_oreno_link_text(a).split())
            if not text:
                continue
            cnt = ""
            pm = re.search(r"([\d.,]+)\s*作品", text)
            if pm:
                cnt = pm.group(1)
            # 名称 = 首个 "Nタグ/N作品" 数字段之前的文本
            nm = re.search(r"\s*[\d.,]+\s*(?:タグ|本|作品)", text)
            name = (text[:nm.start()].strip() if nm else "").strip() or text
            groups.append({"id": m.group(1), "name": name, "count": cnt})
        emit({"event": "oreno_tags", "tags": unique[:500], "groups": groups,
              "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_tags", "tags": [], "groups": [], "site_key": site_key,
              "error": f"获取标签列表失败: {exc}"})
    finally:
        emit({"event": "oreno_tags_loading", "loading": False, "site_key": site_key})


async def oreno_tag_group(group_id: str, site_key: str = "oreno3d") -> None:
    """热门分类组内的标签列表（/tag-groups/{id}）。"""
    emit({"event": "oreno_tags_loading", "loading": True, "site_key": site_key})
    try:
        soup = await asyncio.to_thread(
            _oreno_soup, f"/tag-groups/{group_id}", None, site_key)
        h = soup.select_one("h1, h2")
        title = _oreno_link_text(h) if h else f"分类组 {group_id}"
        tags: list[dict] = []
        seen = set()
        for a in soup.select("a[href^='/tags/']"):
            m = re.search(r"/tags/(\d+)", a.get("href") or "")
            if not m or m.group(1) in seen:
                continue
            name = _oreno_link_text(a)
            if name:
                seen.add(m.group(1))
                tags.append({"id": m.group(1), "name": name})
        emit({"event": "oreno_tags", "tags": tags, "groups": [],
              "group_title": title, "site_key": site_key})
    except Exception as exc:
        emit({"event": "oreno_tags", "tags": [], "groups": [], "site_key": site_key,
              "error": f"获取分类组失败: {exc}"})
    finally:
        emit({"event": "oreno_tags_loading", "loading": False, "site_key": site_key})


def _oreno_extract_iwara_id(soup: BeautifulSoup, site_key: str = "oreno3d") -> str:
    """详情页提取 iwara 视频 ID（oreno3d: a.video-watch-btn2 / erommdtube: figure.show__figure>a）。"""
    conf = _oreno_conf(site_key)
    hrefs: list[str] = []
    btn = soup.select_one(conf["sel_iwara_btn"]) if conf["sel_iwara_btn"] else None
    if btn:
        hrefs.append(btn.get("href") or "")
    if conf["sel_iwara_fig"]:
        fig = soup.select_one(conf["sel_iwara_fig"])
        if fig:
            hrefs.append(fig.get("href") or "")
    for href in hrefs:
        m = re.search(r"iwara\.tv/video/([A-Za-z0-9]+)", href)
        if m:
            return m.group(1)
    m = re.search(r"https?://www\.iwara\.tv/video/([A-Za-z0-9]+)", soup.get_text() or "")
    return m.group(1) if m else ""


async def oreno_detail(movie_id: str, site_key: str = "oreno3d") -> None:
    """视频详情：标题/作者/原作/角色/标签/统计/作者描述(含网盘链接)/相关推荐 + iwara 源。"""
    emit({"event": "oreno_detail_loading", "loading": True, "site_key": site_key})
    try:
        conf = _oreno_conf(site_key)
        soup = await asyncio.to_thread(_oreno_soup, f"/movies/{movie_id}", None, site_key)
        h1 = soup.select_one(conf["sel_h1_detail"])
        img = soup.select_one(conf["sel_img_detail"])
        thumb = (img.get("src") or "") if img else ""
        if thumb.startswith("/"):
            thumb = conf["base"] + thumb
        # 作者（链接内 <i class="material-icons">face</i><div>hadoru</div> → 取 div 或去图标文本）
        author = ""
        author_id = ""
        for a in soup.select(conf["sel_author_link"]):
            div = a.select_one("div.video-center, div.c-txt, span")
            author = (div.get_text(strip=True) if div else _oreno_link_text(a)) or ""
            author = _oreno_link_text(a) if not author else author
            m = re.search(r"/authors/(\d+)", a.get("href") or "")
            if m:
                author_id = m.group(1)
            break
        # 标签 / 原作 / 角色（按 href 前缀区分；名称去掉 material icon 文本；按 id 去重）
        tags: list[dict] = []
        origins: list[dict] = []
        characters: list[dict] = []
        _seen_meta: set[str] = set()
        for a in soup.select(conf["sel_tag_links"]):
            name_el = a.select_one(conf["sel_tag_text"]) if conf["sel_tag_text"] else None
            name = (name_el.get_text(strip=True) if name_el else "") or _oreno_link_text(a)
            href = a.get("href") or ""
            tm = re.search(r"/tags/(\d+)", href)
            om = re.search(r"/origins/(\d+)", href)
            cm = re.search(r"/characters/(\d+)", href)
            mid = (tm or om or cm)
            if not mid or not name:
                continue
            key = f"{mid.re.pattern}|{mid.group(1)}"
            if key in _seen_meta:
                continue
            _seen_meta.add(key)
            if tm:
                tags.append({"id": tm.group(1), "name": name})
            elif om:
                origins.append({"id": om.group(1), "name": name})
            elif cm:
                characters.append({"id": cm.group(1), "name": name})
        # 统计（日期 / 时长 / 观看数 / 点赞数）
        date = ""
        views = ""
        likes = ""
        text_el = soup.select_one(conf["sel_stat_text"])
        if text_el:
            text = text_el.get_text(" ", strip=True)
            dm = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
            if dm:
                date = dm.group(1).replace("/", "-")
        stat_texts = [d.get_text(" ", strip=True) for d in soup.select("div.video-text, div.video-text-in, ul.show__count li")]
        # erommdtube: "投稿日：2018/11/19" / "151032 再生" / "1300 お気に入り"
        for t in stat_texts:
            if not date:
                dm = re.search(r"(?:投稿日|投稿)\s*[：:]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", t)
                if dm:
                    date = dm.group(1).replace("/", "-")
            vm = re.search(r"(?:再生|再生数|閲覧)\s*[：:]?\s*([\d.,]+[km]?)", t) or \
                re.search(r"([\d.,]+[km]?)\s*(?:再生|再生数|閲覧)", t)
            if vm:
                views = vm.group(1)
            lm = re.search(r"(?:お気に入り|ファボ|いいね)\s*[：:]?\s*([\d.,]+[km]?)", t) or \
                re.search(r"([\d.,]+[km]?)\s*(?:お気に入り|ファボ|いいね)", t)
            if lm:
                likes = lm.group(1)
        # oreno3d: video-text 为纯数字序列（日期/时长/再生数/评论标签/收藏数）
        if not views or not likes:
            nums = [t for t in stat_texts if re.fullmatch(r"[\d.,]+[km]?", t)]
            if len(nums) >= 1 and not views:
                views = nums[0]
            if len(nums) >= 2 and not likes:
                likes = nums[1]
        # 作者描述（常含 MEGA/Patreon 等网盘链接）
        comment = ""
        megas: list[str] = []
        bq = soup.select_one(conf["sel_comment"])
        if bq:
            comment = bq.get_text("\n", strip=True)
            for href in re.findall(r"https?://[^\s\"'<>]+", bq.decode() if hasattr(bq, "decode") else str(bq)):
                if any(k in href.lower() for k in ("mega.nz", "mega.co", "patreon", "drive.google", "pixeldrain", "kemono")):
                    megas.append(href)
            if not megas:
                for href in re.findall(r"https?://[^\s\"'<>]+", comment):
                    if any(k in href.lower() for k in ("mega.nz", "mega.co", "patreon", "drive.google", "pixeldrain", "kemono")):
                        megas.append(href)
        iwara_id = _oreno_extract_iwara_id(soup, site_key)
        video = {
            "album_name": (h1.get_text(strip=True) if h1 else "") or f"{site_key}_{movie_id}",
            "album_url": f"{conf['base']}/movies/{movie_id}",
            "video_id": movie_id,
            "site": "oreno" if site_key == "oreno3d" else "erommd",
            "site_key": site_key,
            "thumbnail": thumb,
            "author": author,
            "author_id": author_id,
            "tags": tags,
            "origins": origins,
            "characters": characters,
            "post_date": date,
            "views": views,
            "likes": likes,
            "comment": comment,
            "mega_links": megas,
            "iwara_id": iwara_id,
            "iwara_url": f"https://www.iwara.tv/video/{iwara_id}" if iwara_id else "",
            "related": [],
        }
        # 相关视频推荐（同列表卡片结构）
        related_sec = soup.select_one(conf["sel_related"])
        if related_sec:
            video["related"] = _oreno_parse_cards(related_sec, site_key)[:12]
        # 通过 Iwara API 解析播放直链（最高画质）
        iwara_info: dict = {}
        if iwara_id:
            try:
                data = await asyncio.to_thread(_iwara_api_get, f"/video/{iwara_id}", None)
                fu = data.get("fileUrl") or ""
                if fu:
                    play_url, mime = await asyncio.to_thread(_iwara_resolve_best_url, fu)
                    if play_url.startswith("//"):
                        play_url = "https:" + play_url
                    iwara_info = {
                        "title": data.get("title") or "",
                        "views": data.get("numViews"),
                        "likes": data.get("numLikes"),
                        "duration": (data.get("file") or {}).get("duration"),
                        "video_url": play_url,
                    }
            except Exception as exc:
                logging.warning("%s iwara 源解析失败: %s", conf["label"], exc)
        video.update(iwara_info)
        # 收藏状态（本地）
        video["saved"] = str(movie_id) in ((_oreno_fav_load().get(site_key)) or {})
        _apply_cached_thumbnails([video])
        asyncio.create_task(_cache_thumbnails([video]))
        emit({"event": "oreno_video_detail", "video": video, "site_key": site_key})
        logging.info("%s 视频详情: %s (iwara=%s)", conf["label"], movie_id, iwara_id)
    except Exception as exc:
        emit({"event": "oreno_video_detail", "video": None, "site_key": site_key,
              "error": f"获取视频详情失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 视频详情获取失败", _oreno_conf(site_key)["label"])
    finally:
        emit({"event": "oreno_detail_loading", "loading": False, "site_key": site_key})


async def oreno_batch_download(video_ids: list, options: dict, site_key: str = "oreno3d") -> None:
    """批量下载视频：解析 iwara ID 后复用 Iwara 下载逻辑（最高画质）。"""
    conf = _oreno_conf(site_key)
    video_ids = [str(v).strip() for v in (video_ids or []) if str(v).strip()]
    if not video_ids:
        emit({"event": "oreno_batch_done", "done": 0, "total": 0, "failed": [],
              "site_key": site_key, "message": "请先勾选要下载的视频"})
        return
    total = len(video_ids)
    failed: list[str] = []
    iwara_ids: list[str] = []
    try:
        for i, mid in enumerate(video_ids):
            try:
                soup = await asyncio.to_thread(_oreno_soup, f"/movies/{mid}", None, site_key)
                iwara_id = _oreno_extract_iwara_id(soup, site_key)
                if iwara_id:
                    iwara_ids.append(iwara_id)
                else:
                    failed.append(f"{mid}（未找到 iwara 源）")
            except Exception as exc:
                failed.append(f"{mid}（{exc}）")
            emit({"event": "oreno_batch_progress", "done": i + 1, "total": total,
                  "site_key": site_key, "message": f"解析进度 {i + 1}/{total}"})
        items: list[dict] = []
        if iwara_ids:
            items = await _iwara_build_items(iwara_ids)
        if items:
            task_id = download_manager.submit(
                f"{conf['base']}/", items, options, f"{conf['label']} 批量下载", "oreno_batch",
            )
            download_manager.start(task_id)
        summary = f"批量下载已提交：{len(items)}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "oreno_batch_done", "done": len(items), "total": total,
              "site_key": site_key, "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "oreno_batch_done", "done": 0, "total": total, "site_key": site_key,
              "failed": failed, "message": f"批量下载中断: {exc}"})


def is_hanime_url(url: str) -> bool:
    """判断是否为 Hanime1 链接（视频页 watch?v=）。"""
    return bool(re.search(r"hanime1\.me/watch\?v=\w+", url, re.I))


def is_oreno_url(url: str) -> str | None:
    """判断是否为 Oreno3D / EroMMDTube 链接（/movies/{id}），返回 site_key 或 None。"""
    if re.search(r"oreno3d\.com/movies/\d+", url, re.I):
        return "oreno3d"
    if re.search(r"erommdtube\.com/movies/\d+", url, re.I):
        return "erommdtube"
    return None


def is_asmr_url(url: str) -> bool:
    """判断是否为 ASMR 站链接（asmr-100.com / asmr.one 作品页 /work/{id}）。"""
    return bool(re.search(r"asmr-100\.com/work/\d+|asmr\.one/work/\d+", url, re.I))


async def hanime_inspect(url: str, options: dict) -> None:
    """解析 Hanime1 视频页 → 文件列表（下载时重新解析最高画质直链）。"""
    m = re.search(r"watch\?v=(\w+)", url)
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 Hanime1 链接（支持 /watch?v={id}）"})
        return
    vid = m.group(1)
    try:
        soup = await asyncio.to_thread(_hanime_soup, "/watch", {"v": vid})
        detail = _hanime_parse_detail(soup, vid)
        if not detail["sources"]:
            emit({"event": "inspect_error", "message": "视频没有可用的播放源"})
            return
        title = sanitize_directory_name((detail["title"] or f"hanime_{vid}").strip())
        items = [{
            "filename": f"{title}.mp4",
            "size": None,
            "item_page": f"{HANIME_BASE}/watch?v={vid}",
            "status": "ok",
            "thumbnail": detail.get("thumbnail") or "",
            "media_url": _hanime_best_source(detail["sources"]).get("url") or "",
            "site": "hanime",
            "video_id": vid,
            "post_title": detail["title"] or title,
            "post_date": detail.get("post_date") or "",
            "artist": detail.get("uploader") or "",
        }]
        album_id = f"hanime_{vid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": detail["title"] or f"hanime_{vid}",
            "album_id": album_id,
            "is_album": False,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("Hanime1 解析完成: %s", vid)
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"Hanime1 解析失败: {exc}（请检查网络或 Hanime1 代理设置）"})
        logging.exception("Hanime1 解析过程出错")


async def oreno_inspect(url: str, options: dict) -> None:
    """解析 Oreno3D / EroMMDTube 视频页 → iwara 源文件列表（复用 Iwara 下载逻辑）。"""
    site_key = is_oreno_url(url) or "oreno3d"
    conf = _oreno_conf(site_key)
    m = re.search(r"/movies/(\d+)", url)
    if not m:
        emit({"event": "inspect_error", "message": f"无法识别的 {conf['label']} 链接（支持 /movies/{{id}}）"})
        return
    mid = m.group(1)
    try:
        soup = await asyncio.to_thread(_oreno_soup, f"/movies/{mid}", None, site_key)
        iwara_id = _oreno_extract_iwara_id(soup, site_key)
        if not iwara_id:
            emit({"event": "inspect_error", "message": "该视频没有找到 iwara 源，无法下载"})
            return
        items = await _iwara_build_items([iwara_id])
        if not items:
            emit({"event": "inspect_error", "message": "iwara 源解析失败（视频可能已删除或需登录）"})
            return
        h1 = soup.select_one(conf["sel_h1_detail"])
        album = (h1.get_text(strip=True) if h1 else "") or items[0].get("post_title") or f"{site_key}_{mid}"
        album_id = f"oreno_{mid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": album,
            "album_id": album_id,
            "is_album": False,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("%s 解析完成: %s (iwara=%s)", conf["label"], mid, iwara_id)
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"{conf['label']} 解析失败: {exc}（请检查网络或代理设置）"})
        logging.exception("%s 解析过程出错", conf["label"])


# ============================
# asmr-100.com（音声站，Kikoeru 系统，API 网关 + 多域名容灾）
# ============================
# - API：https://api.asmr-200.com（可容灾切换 api.asmr.one / api.asmr-100.com / api.asmr-300.com，token 互通）
# - 登录：POST /api/auth/me {name, password}（勿带 Authorization 头）→ JWT（365 天）
# - 热门：POST /api/recommender/popular {page, pageSize}（勿传空数组参数，会 400）
# - 列表：GET /api/works（order/sort/page/pageSize/subtitle，支持 circleId/tagId/vaId 筛选）
# - 详情：GET /api/work/{id}；音轨树：GET /api/tracks/{id}?v=2（folder/audio/text 三种节点）
# - 音频：GET /api/media/stream/{workId}/{fileId}（播放）/api/media/download/{workId}/{fileId}（下载）
#   → 匿名可用、无签名、支持 Range 断点续传
# - 收藏：PUT /api/review {work_id, progress:"marked"} / DELETE /api/review?work_id=
# - 收藏列表：GET /api/review?filter=marked
ASMR_API_BASES = [
    "https://api.asmr-200.com",
    "https://api.asmr.one",
    "https://api.asmr-100.com",
    "https://api.asmr-300.com",
]
ASMR_SITE = "https://asmr-100.com"
ASMR_ORDERS = {
    "release": "发售日", "create_date": "最新入库", "dl_count": "下载量",
    "price": "价格", "rate_average_2dp": "评分", "review_count": "评论数",
}

_asmr_proxy = ""
_asmr_token = ""
_asmr_username = ""
_asmr_api_base = ASMR_API_BASES[0]
_asmr_last_req = 0.0
_asmr_session = requests.Session()
_asmr_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Origin": ASMR_SITE,
    "Referer": ASMR_SITE + "/",
})


def asmr_set_proxy(proxy: str) -> None:
    """设置 ASMR 站代理（空 = 直连）。"""
    global _asmr_proxy
    _asmr_proxy = (proxy or "").strip()
    if _asmr_proxy and not _asmr_proxy.startswith(("http://", "https://", "socks5://")):
        _asmr_proxy = "http://" + _asmr_proxy
    proxies = {"http": _asmr_proxy, "https": _asmr_proxy} if _asmr_proxy else {}
    _asmr_session.proxies = proxies
    emit({"event": "asmr_proxy_set", "proxy": _asmr_proxy})


def _asmr_throttle(min_interval: float = 0.3) -> None:
    global _asmr_last_req
    wait = _asmr_last_req + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _asmr_last_req = time.time()


def _asmr_load_cred() -> dict:
    return _secure_store_read_cred("asmr")


def _asmr_save_cred(cred: dict) -> None:
    _secure_store_write_cred("asmr", cred)


def _asmr_auth_headers() -> dict:
    if _asmr_token:
        return {"Authorization": f"Bearer {_asmr_token}"}
    return {}


def _asmr_api(
    method: str,
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
    auth: bool = True,
) -> dict | list:
    """ASMR API 请求（JSON），多域名容灾：主域名失败依次切换备用域名。"""
    global _asmr_api_base
    headers = dict(_asmr_session.headers)
    if auth and _asmr_token:
        headers["Authorization"] = f"Bearer {_asmr_token}"
    bases = [_asmr_api_base] + [b for b in ASMR_API_BASES if b != _asmr_api_base]
    last_exc: Exception | None = None
    for base in bases:
        _asmr_throttle()
        try:
            resp = _asmr_session.request(
                method, f"{base}{path}", json=json_body, params=params,
                headers=headers, timeout=30,
            )
            if resp.status_code in (200, 201):
                _asmr_api_base = base
                return resp.json() if resp.content else {}
            last_exc = PermissionError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            # 401 = token 失效，切换域名无意义
            if resp.status_code == 401:
                break
        except requests.RequestException as exc:
            last_exc = exc
    raise last_exc or PermissionError("ASMR API 请求失败")


def _asmr_work_card(w: dict) -> dict:
    """API work 对象 → 前端作品卡片。"""
    tags = [t.get("name") or t.get("i18n", {}).get("zh-cn") or "" for t in (w.get("tags") or [])]
    vas = [v.get("name") or "" for v in (w.get("vas") or [])]
    return {
        "album_name": w.get("title") or "",
        "album_url": f"{ASMR_SITE}/work/{w.get('id')}",
        "thumbnail": w.get("mainCoverUrl") or "",
        "files": (w.get("duration") and 1) or 1,
        "site": "asmr",
        "video_id": str(w.get("id") or ""),
        "author": w.get("name") or "",  # 社团名
        "circle_id": str(w.get("circle_id") or ""),
        "views": w.get("dl_count"),
        "likes": w.get("rate_average_2dp"),
        "rating": w.get("rate_average_2dp"),
        "price": w.get("price"),
        "nsfw": bool(w.get("nsfw")),
        "duration": w.get("duration"),  # 分钟
        "has_subtitle": bool(w.get("has_subtitle")),
        "post_date": (w.get("release") or "")[:10],
        "source_id": w.get("source_id") or "",
        "tags": [t for t in tags if t],
        "vas": [v for v in vas if v],
        "review_count": w.get("review_count"),
    }


def asmr_login(name: str, password: str, silent: bool = False) -> None:
    """登录 ASMR 站（用户名+密码 → JWT，365 天有效）。"""
    global _asmr_token, _asmr_username
    name = (name or "").strip()
    password = password or ""
    if not name or not password:
        if not silent:
            emit({"event": "asmr_login_result", "success": False, "message": "请输入用户名和密码"})
        return
    try:
        _asmr_throttle()
        # 登录请求勿带 Authorization 头
        resp = _asmr_session.post(
            f"{_asmr_api_base}/api/auth/me",
            json={"name": name, "password": password}, timeout=30,
        )
        if resp.status_code != 200:
            msg = "用户名或密码错误" if resp.status_code in (401, 422) else f"登录失败（HTTP {resp.status_code}）"
            emit({"event": "asmr_login_result", "success": False, "message": msg,
                  "network_issue": resp.status_code >= 500})
            return
        data = resp.json()
        token = data.get("token") or ""
        user = data.get("user") or {}
        if not token or not user.get("loggedIn"):
            emit({"event": "asmr_login_result", "success": False, "message": "登录失败（服务器未返回有效 token）"})
            return
        _asmr_token = token
        _asmr_username = user.get("name") or name
        # token + 密码一起加密持久化（失效自动重登）
        _asmr_save_cred({"token": token, "username": _asmr_username, "password": password})
        emit({"event": "asmr_login_result", "success": True, "silent": silent,
              "username": _asmr_username, "message": f"已登录：{_asmr_username}"})
        _emit_login_info()
        logging.info("ASMR 登录成功: %s", _asmr_username)
    except requests.RequestException as exc:
        emit({"event": "asmr_login_result", "success": False, "network_issue": True,
              "silent": silent, "message": f"网络错误：登录请求失败（{exc}），请检查网络或代理设置"})
    except Exception as exc:
        emit({"event": "asmr_login_result", "success": False, "network_issue": True,
              "silent": silent, "message": f"登录出错：{exc}"})


def asmr_logout() -> None:
    """退出登录（清除本地 token）。"""
    global _asmr_token, _asmr_username
    _asmr_token = ""
    _asmr_username = ""
    _secure_store_clear_cred("asmr")
    emit({"event": "asmr_login_result", "success": True, "logout": True, "username": "",
          "message": "已退出登录"})
    _emit_login_info()


def asmr_check_login(silent: bool = False) -> None:
    """检查登录状态；token 失效时用保存的密码自动重登。"""
    global _asmr_token, _asmr_username
    cred = _asmr_load_cred()
    token = cred.get("token") or ""
    if not token:
        if not silent:
            emit({"event": "asmr_login_result", "success": False, "message": "未登录"})
        return
    _asmr_token = token
    _asmr_username = cred.get("username") or ""
    try:
        data = _asmr_api("GET", "/api/auth/me")
        user = data.get("user") or {}
        if user.get("loggedIn"):
            _asmr_username = user.get("name") or _asmr_username
            emit({"event": "asmr_login_result", "success": True, "silent": silent,
                  "username": _asmr_username})
            _emit_login_info()
            return
    except Exception as exc:
        logging.warning("ASMR 登录检查失败: %s", exc)
    # token 失效 → 用保存的密码重登
    if cred.get("password"):
        asmr_login(cred.get("username") or "", cred.get("password"), silent=True)
    elif not silent:
        emit({"event": "asmr_login_result", "success": False,
              "message": "登录已失效，请重新登录"})


def _asmr_tracks_flatten(nodes: list, parent: str = "") -> list[dict]:
    """音轨树 → 平铺文件列表（保留文件夹相对路径）。"""
    files: list[dict] = []
    for node in nodes or []:
        ntype = node.get("type")
        title = node.get("title") or ""
        if ntype == "folder":
            sub = f"{parent}/{title}" if parent else title
            files.extend(_asmr_tracks_flatten(node.get("children") or [], sub))
        elif ntype in ("audio", "text"):
            hash_ = node.get("hash") or ""
            if not hash_:
                continue
            work_id, file_id = hash_.split("/", 1) if "/" in hash_ else ("", hash_)
            media_url = node.get("mediaDownloadUrl") or (
                f"{_asmr_api_base}/api/media/download/{hash_}")
            if media_url.startswith("//"):
                media_url = "https:" + media_url
            files.append({
                "title": title,
                "path": parent,
                "type": ntype,
                "duration": node.get("duration"),
                "size": node.get("size"),
                "work_id": work_id,
                "file_id": file_id,
                "media_url": media_url,
                "stream_url": f"{_asmr_api_base}/api/media/stream/{hash_}",
            })
    return files


async def asmr_popular(page: int = 1, subtitle: bool = False) -> None:
    """热门作品（每页 100，可翻页抓取 100+；可勾选仅带字幕客户端过滤）。"""
    emit({"event": "asmr_list_loading", "loading": True, "view": "popular"})
    try:
        page = max(1, page or 1)
        data = await asyncio.to_thread(
            _asmr_api, "POST", "/api/recommender/popular",
            {"page": page, "pageSize": 100}, None, False,
        )
        works = data.get("works") or data or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        if subtitle:
            items = [i for i in items if i.get("has_subtitle")]
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        pagination = data.get("pagination") or {}
        emit({"event": "asmr_list", "view": "popular", "items": items, "page": page,
              "has_more": page < max(1, (pagination.get("totalCount") or 0) // 100 + 1),
              "label": "热门作品"})
        logging.info("ASMR 热门第 %d 页: %d 个作品", page, len(items))
    except Exception as exc:
        emit({"event": "asmr_list", "view": "popular", "items": [], "page": page,
              "has_more": False, "error": f"获取热门作品失败: {exc}（请检查网络或代理设置）"})
        logging.exception("ASMR 热门获取失败")
    finally:
        emit({"event": "asmr_list_loading", "loading": False, "view": "popular"})


async def asmr_works(
    page: int = 1, order: str = "create_date", sort: str = "desc",
    subtitle: bool = False, circle_id: str = "", tag_id: str = "", va_id: str = "",
    view: str = "works", label: str = "",
) -> None:
    """作品列表（最新入库等排序 + 社团/标签/声优筛选 + 可勾选仅带字幕）。"""
    emit({"event": "asmr_list_loading", "loading": True, "view": view})
    try:
        page = max(1, page or 1)
        params: dict = {
            "page": page, "pageSize": 50,
            "order": order or "create_date", "sort": sort or "desc",
        }
        if subtitle:
            params["subtitle"] = 1
        if circle_id:
            params["circleId"] = circle_id
        if tag_id:
            params["tagId"] = tag_id
        if va_id:
            params["vas"] = va_id
        data = await asyncio.to_thread(_asmr_api, "GET", "/api/works", None, params, False)
        works = data.get("works") or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        pagination = data.get("pagination") or {}
        total = pagination.get("totalCount") or 0
        has_more = page * 50 < total
        emit({"event": "asmr_list", "view": view, "items": items, "page": page,
              "has_more": has_more, "total": total, "label": label or "作品列表",
              "orders": ASMR_ORDERS})
    except Exception as exc:
        emit({"event": "asmr_list", "view": view, "items": [], "page": page,
              "has_more": False, "error": f"获取作品列表失败: {exc}"})
        logging.exception("ASMR 作品列表获取失败")
    finally:
        emit({"event": "asmr_list_loading", "loading": False, "view": view})


async def asmr_search(query: str, page: int = 1, subtitle: bool = False) -> None:
    """关键词搜索（支持 RJ 号 / 标题 / 社团名 / 标签）。"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_loading", "loading": True})
    try:
        page = max(1, page or 1)
        params: dict = {
            "page": page, "pageSize": 50,
            "orderBy": "create_date", "sort": "desc",
        }
        if subtitle:
            params["subtitle"] = 1
        from urllib.parse import quote
        data = await asyncio.to_thread(
            _asmr_api, "GET", f"/api/search/{quote(query)}", None, params, False)
        works = data.get("works") or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        emit({"event": "search_result", "query": query, "site": "asmr",
              "items": items, "page": page,
              "has_more": page * 50 < (data.get("pagination") or {}).get("totalCount", 0),
              "label": query})
        if items:
            asyncio.create_task(_cache_thumbnails(items))
        logging.info("ASMR 搜索 '%s': %d 个结果", query, len(items))
    except Exception as exc:
        emit({"event": "search_error",
              "message": f"ASMR 搜索失败: {exc}（请检查网络或代理设置）"})
        logging.exception("ASMR 搜索失败")
    finally:
        emit({"event": "search_loading", "loading": False})


async def asmr_work_detail(work_id: str) -> None:
    """作品详情：元数据 + 音轨树（在线播放走本地媒体代理）+ 收藏状态。"""
    emit({"event": "asmr_detail_loading", "loading": True})
    try:
        work = await asyncio.to_thread(_asmr_api, "GET", f"/api/work/{work_id}", None, None, False)
        try:
            extra = await asyncio.to_thread(
                _asmr_api, "GET", f"/api/workInfo/{work_id}", None, None, False)
            if isinstance(extra, dict):
                work.update({k: v for k, v in extra.items() if k not in work})
        except Exception:
            pass
        tracks = await asyncio.to_thread(
            _asmr_api, "GET", f"/api/tracks/{work_id}", None, {"v": 2}, False)
        files = _asmr_tracks_flatten(tracks if isinstance(tracks, list) else [])
        # 播放/下载地址转本地媒体代理（前端直接用）
        for f in files:
            f["play_url"] = media_proxy_url(f["stream_url"])
        card = _asmr_work_card(work)
        # 中文附加信息
        card.update({
            "description": (work.get("work_attributes") or {}),
            "sam_cover": work.get("samCoverUrl") or "",
            "circle": (work.get("circle") or {}),
            "source_url": work.get("source_url") or "",
            "create_date": (work.get("create_date") or "")[:10],
            "file_count": len(files),
        })
        emit({"event": "asmr_video_detail", "video": card, "files": files,
              "logged_in": bool(_asmr_token)})
        asyncio.create_task(_cache_thumbnails([card]))
        logging.info("ASMR 作品详情: %s (%d 个文件)", work_id, len(files))
    except Exception as exc:
        emit({"event": "asmr_video_detail", "video": None, "files": [],
              "error": f"获取作品详情失败: {exc}（请检查网络或代理设置）"})
        logging.exception("ASMR 作品详情获取失败")
    finally:
        emit({"event": "asmr_detail_loading", "loading": False})


def _asmr_cache_list(kind: str) -> list[dict]:
    """社团/标签/声优全量列表（API 返回全量，本地缓存 7 天）。"""
    cache_file = Path(f"cache/asmr_{kind}.json")
    if cache_file.exists():
        try:
            age = time.time() - cache_file.stat().st_mtime
            if age < 7 * 86400:
                data = json.loads(cache_file.read_text("utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    path = {"circles": "/api/circles/", "tags": "/api/tags/", "vas": "/api/vas/"}[kind]
    data = _asmr_api("GET", path, None, None, False)
    data = data if isinstance(data, list) else []
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return data


async def asmr_browse_index(kind: str) -> None:
    """社团/标签/声优索引（全量，含作品数与多语言名）。"""
    event = {"circles": "asmr_circles", "tags": "asmr_tags", "vas": "asmr_vas"}[kind]
    emit({"event": f"{event}_loading", "loading": True})
    try:
        data = await asyncio.to_thread(_asmr_cache_list, kind)
        out: list[dict] = []
        for item in data:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            i18n = item.get("i18n") or {}
            name = item.get("name") or i18n.get("zh-cn") or i18n.get("en-us") or ""
            if not name:
                continue
            out.append({"id": str(item["id"]), "name": name,
                        "count": item.get("count") or 0})
        out.sort(key=lambda x: -int(x["count"] or 0))
        emit({"event": event, "items": out})
        logging.info("ASMR %s 索引: %d 项", kind, len(out))
    except Exception as exc:
        emit({"event": event, "items": [], "error": f"获取{kind}列表失败: {exc}"})
    finally:
        emit({"event": f"{event}_loading", "loading": False})


async def asmr_toggle_favorite(work_id: str, card: dict) -> None:
    """收藏/取消收藏作品（PUT/DELETE /api/review，需登录）。"""
    try:
        if not _asmr_token:
            emit({"event": "asmr_fav_result", "video_id": str(work_id), "saved": False,
                  "error": "请先登录"})
            return
        # 查询当前是否已收藏
        cur = _asmr_api("GET", "/api/review", None,
                        {"order": "updated_at", "sort": "desc", "page": 1,
                         "pageSize": 100, "filter": "marked"})
        cur_ids = {str(w.get("id")) for w in (cur.get("works") or [])}
        wid = str(work_id)
        if wid in cur_ids:
            _asmr_api("DELETE", "/api/review", None, {"work_id": work_id})
            saved = False
        else:
            _asmr_api("PUT", "/api/review",
                      {"work_id": int(work_id), "rating": 0,
                       "review_text": "", "progress": "marked"})
            saved = True
        emit({"event": "asmr_fav_result", "video_id": wid, "saved": saved})
    except Exception as exc:
        emit({"event": "asmr_fav_result", "video_id": str(work_id), "saved": False,
              "error": f"收藏操作失败: {exc}"})


async def asmr_favorites(page: int = 1) -> None:
    """我的收藏列表（需登录）。"""
    emit({"event": "asmr_list_loading", "loading": True, "view": "favorites"})
    try:
        if not _asmr_token:
            emit({"event": "asmr_list", "view": "favorites", "items": [], "page": 1,
                  "has_more": False, "error": "请先登录"})
            return
        page = max(1, page or 1)
        data = await asyncio.to_thread(
            _asmr_api, "GET", "/api/review",
            None, {"order": "updated_at", "sort": "desc", "page": page,
                   "pageSize": 50, "filter": "marked"})
        works = data.get("works") or []
        items = [_asmr_work_card(w) for w in works if isinstance(w, dict) and w.get("id")]
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        total = (data.get("pagination") or {}).get("totalCount") or 0
        emit({"event": "asmr_list", "view": "favorites", "items": items, "page": page,
              "has_more": page * 50 < total, "label": "我的收藏"})
    except Exception as exc:
        emit({"event": "asmr_list", "view": "favorites", "items": [], "page": page,
              "has_more": False, "error": f"获取收藏失败: {exc}"})
    finally:
        emit({"event": "asmr_list_loading", "loading": False, "view": "favorites"})


async def asmr_batch_download(work_ids: list, options: dict) -> None:
    """批量下载作品（整包）：每个作品遍历音轨树，逐文件下载（保留文件夹结构）。"""
    work_ids = [str(v).strip() for v in (work_ids or []) if str(v).strip()]
    if not work_ids:
        emit({"event": "asmr_batch_done", "done": 0, "total": 0, "failed": [],
              "message": "请先勾选要下载的作品"})
        return
    total = len(work_ids)
    failed: list[str] = []
    submitted = 0
    try:
        for i, wid in enumerate(work_ids):
            try:
                work = await asyncio.to_thread(
                    _asmr_api, "GET", f"/api/work/{wid}", None, None, False)
                tracks = await asyncio.to_thread(
                    _asmr_api, "GET", f"/api/tracks/{wid}", None, {"v": 2}, False)
                files = _asmr_tracks_flatten(tracks if isinstance(tracks, list) else [])
                if not files:
                    failed.append(f"{wid}（无文件）")
                    continue
                title = sanitize_directory_name(
                    (work.get("title") or "").strip() or f"asmr_{wid}")
                rj = work.get("source_id") or ""
                album_name = f"{rj} {title}".strip() if rj else title
                items: list[dict] = []
                for f in files:
                    rel = "/".join(p for p in [f["path"], f["title"]] if p)
                    items.append({
                        "filename": rel,
                        "size": f.get("size"),
                        "item_page": f"{ASMR_SITE}/work/{wid}",
                        "status": "ok",
                        "media_url": f["media_url"],
                        "site": "asmr",
                        "post_title": title,
                        "post_date": (work.get("release") or "")[:10],
                        "artist": work.get("name") or "",
                    })
                task_id = download_manager.submit(
                    f"{ASMR_SITE}/work/{wid}", items, options,
                    album_name, f"asmr_{wid}")
                download_manager.start(task_id)
                submitted += 1
            except Exception as exc:
                failed.append(f"{wid}（{exc}）")
            emit({"event": "asmr_batch_progress", "done": i + 1, "total": total,
                  "message": f"解析进度 {i + 1}/{total}"})
        summary = f"批量下载已提交 {submitted}/{total} 个作品"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "asmr_batch_done", "done": submitted, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "asmr_batch_done", "done": submitted, "total": total,
              "failed": failed, "message": f"批量下载中断: {exc}"})


async def asmr_inspect(url: str, options: dict) -> None:
    """解析 ASMR 作品页 → 全部音轨文件列表（在线播放走本地媒体代理）。"""
    m = re.search(r"/work/(\d+)", url)
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 ASMR 链接（支持 /work/{id}）"})
        return
    wid = m.group(1)
    try:
        work = await asyncio.to_thread(_asmr_api, "GET", f"/api/work/{wid}", None, None, False)
        tracks = await asyncio.to_thread(
            _asmr_api, "GET", f"/api/tracks/{wid}", None, {"v": 2}, False)
        files = _asmr_tracks_flatten(tracks if isinstance(tracks, list) else [])
        if not files:
            emit({"event": "inspect_error", "message": "该作品没有可下载的文件"})
            return
        title = sanitize_directory_name((work.get("title") or "").strip() or f"asmr_{wid}")
        rj = work.get("source_id") or ""
        album_name = f"{rj} {title}".strip() if rj else title
        items: list[dict] = []
        for f in files:
            rel = "/".join(p for p in [f["path"], f["title"]] if p)
            items.append({
                "filename": rel,
                "size": f.get("size"),
                "item_page": f"{ASMR_SITE}/work/{wid}",
                "status": "ok",
                "media_url": f["media_url"],
                "play_url": media_proxy_url(f["stream_url"]),
                "site": "asmr",
                "post_title": title,
                "post_date": (work.get("release") or "")[:10],
                "artist": work.get("name") or "",
            })
        album_id = f"asmr_{wid}"
        _apply_cached_thumbnails(items)
        _mark_items_new(album_id, items)
        emit({
            "event": "inspect_complete",
            "album_name": album_name,
            "album_id": album_id,
            "is_album": True,
            "items": items,
        })
        logging.info("ASMR 作品解析完成: %s (%d 个文件)", wid, len(items))
    except Exception as exc:
        emit({"event": "inspect_error",
              "message": f"ASMR 作品解析失败: {exc}（请检查网络或 ASMR 代理设置）"})
        logging.exception("ASMR 作品解析过程出错")


# ============================
# 搜索历史（日常 tags 快速搜索）
# ============================
SEARCH_HISTORY_FILE = "cache/search_history.json"
SEARCH_HISTORY_MAX = 100


def _load_search_history() -> list[dict]:
    """读取搜索历史（最近在前）。"""
    try:
        with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_search_history(history: list[dict]) -> None:
    """保存搜索历史。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[:SEARCH_HISTORY_MAX], f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存搜索历史失败: %s", exc)


def add_search_history(query: str, site: str, search_mode: str = "") -> None:
    """记录一次搜索（同关键词+站点去重，移到最前）。"""
    query = (query or "").strip()
    if not query:
        return
    history = _load_search_history()
    history = [
        h for h in history
        if not (h.get("query") == query and h.get("site") == site)
    ]
    history.insert(0, {
        "query": query,
        "site": site or "bunkr",
        "search_mode": search_mode or "",
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    _save_search_history(history)


def delete_search_history(query: str, site: str) -> None:
    """删除一条搜索历史。"""
    history = _load_search_history()
    history = [
        h for h in history
        if not (h.get("query") == query and h.get("site") == site)
    ]
    _save_search_history(history)


def clear_search_history() -> None:
    """清空搜索历史。"""
    _save_search_history([])


# ============================
# 本地收藏（跨站点快速打开）
# ============================
LOCAL_FAVORITES_FILE = "cache/local_favorites.json"


def _load_local_favorites() -> list[dict]:
    """读取本地收藏列表。"""
    try:
        with open(LOCAL_FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_local_favorites(favorites: list[dict]) -> None:
    """保存本地收藏列表。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(LOCAL_FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存本地收藏失败: %s", exc)


def add_local_favorite(item: dict) -> None:
    """添加本地收藏（作者/画集/标签等，按 URL 去重）。"""
    url = (item.get("url") or "").strip()
    if not url:
        emit({"event": "local_favorites_error", "message": "收藏缺少 URL"})
        return
    favorites = _load_local_favorites()
    if any(f.get("url") == url for f in favorites):
        emit({"event": "local_favorites_saved", "message": "已在收藏中", "duplicate": True})
        return
    favorites.insert(0, {
        "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
        "type": item.get("type", "gallery"),
        "title": item.get("title", "") or url,
        "url": url,
        "site": item.get("site", ""),
        "search_query": item.get("search_query", ""),
        "thumbnail": item.get("thumbnail", ""),
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    _save_local_favorites(favorites)
    emit({"event": "local_favorites_saved", "message": "已收藏到本地"})


def delete_local_favorite(fav_id: str) -> None:
    """删除一条本地收藏。"""
    favorites = _load_local_favorites()
    favorites = [f for f in favorites if f.get("id") != fav_id]
    _save_local_favorites(favorites)
    emit({"event": "local_favorites", "items": favorites})


# ============================
# ExHentai 搜索（画廊关键词搜索，游标分页）
# ============================
# ExHentai 搜索页的 page= 参数无效，翻页必须用 next=<上页最后画廊ID> 游标。
# 游标缓存到 cache/exhentai_cursors.json，支持上一页/下一页/任意跳页（跳页时顺序推进）。
EX_CURSORS_FILE = "cache/exhentai_cursors.json"


def _load_ex_cursors() -> dict:
    """读取游标缓存：{query: {"2": gid, "3": gid, "total_pages": N}}。"""
    try:
        with open(EX_CURSORS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_ex_cursors(data: dict) -> None:
    try:
        os.makedirs("cache", exist_ok=True)
        with open(EX_CURSORS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        logging.exception("ExHentai 游标缓存保存失败")


def _parse_ex_gallery_ids(html: str) -> list[str]:
    """按出现顺序提取页面里的画廊 ID 列表（游标用）。"""
    return re.findall(r"/g/(\d+)/[0-9a-f]+/?", html)


def _parse_ex_search_page(html: str) -> list[dict]:
    """解析搜索结果页的画廊列表（含标题/缩略图/标签/页数/日期/发布者）。"""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    # 直接取所有画廊链接（Minimal/Compact/Extended 布局通用）
    for link in soup.select("a[href*='/g/']"):
        href = (link.get("href") or "")
        if not href.startswith("http") or "/g/" not in href:
            continue
        # 跳过缩略图/广告位等非画廊行链接：画廊链接格式 /g/数字/token/
        if not re.search(r"/g/\d+/[0-9a-f]+/?", href):
            continue

        # 画廊所在行（Extended/Compact 为 tr，Minimal 为 div）
        row = link.find_parent("tr") or link.find_parent("div")

        # 标题：优先 .glink 节点（列表布局的标准标题），否则取链接文本
        title = ""
        if row:
            glink = row.select_one(".glink")
            if glink:
                title = glink.get_text(strip=True)
        if not title:
            title = link.get_text(strip=True) or link.get("title", "")
        if not title:
            title = href.rstrip("/").rsplit("/", 1)[-1]

        # 缩略图（懒加载属性优先）
        thumb = ""
        if row:
            img = row.select_one("img")
            if img:
                thumb = img.get("data-src") or img.get("src") or ""
                if not thumb.startswith("http"):
                    thumb = ""

        # 标签（.gt 节点，title 属性形如 "Artist:xxx"）
        tags: list[str] = []
        if row:
            for gt in row.select(".gt"):
                t = gt.get("title") or gt.get_text(strip=True)
                if t:
                    tags.append(t)

        # 行文本提取：页数 / 发布时间 / 发布者
        pages = ""
        posted = ""
        uploader = ""
        if row:
            row_text = row.get_text(" ", strip=True)
            m = re.search(r"(\d+)\s*pages?", row_text, re.I)
            if m:
                pages = m.group(1)
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", row_text)
            if m:
                posted = m.group(1)
            up = row.select_one("a[href*='/uploader/']")
            if up:
                uploader = up.get_text(strip=True)

        items.append({
            "title": title,
            "album_name": title,
            "album_url": href,
            "url": href,
            "thumbnail": thumb,
            "site": "exhentai",
            "type": "gallery",
            "tags": tags[:8],
            "pages": pages,
            "posted": posted,
            "uploader": uploader,
        })

    # 去重
    seen: set[str] = set()
    return [i for i in items if not (i["url"] in seen or seen.add(i["url"]))]


# ============================
# ExHentai 隐藏 tags（用户手动标记，解析/收藏结果中不显示）
# ============================
EXHENTAI_HIDDEN_TAGS_FILE = "cache/exhentai_hidden_tags.json"


def _load_ex_hidden_tags() -> list[str]:
    """读取隐藏标签列表（长期保存）。"""
    try:
        with open(EXHENTAI_HIDDEN_TAGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data = data.get("tags") or []
            if isinstance(data, list):
                return [str(t).strip() for t in data if str(t).strip()]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_ex_hidden_tags(tags: list[str]) -> None:
    """保存隐藏标签列表。"""
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        with open(EXHENTAI_HIDDEN_TAGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"tags": tags}, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存隐藏标签失败: %s", exc)


def _ex_hidden_tag_matched(item_tag: str, hidden_tags: list[str]) -> bool:
    """判断画廊标签是否命中隐藏列表。

    匹配规则（不区分大小写）：
    - 隐藏 "xxx"        → 命中任何命名空间的 "Namespace:xxx"
    - 隐藏 "female:xxx"  → 仅命中 "female:xxx"
    """
    if not item_tag:
        return False
    t = item_tag.strip().lower()
    for hidden in hidden_tags:
        h = hidden.strip().lower()
        if not h:
            continue
        if t == h or t.endswith(":" + h):
            return True
    return False


def _exhentai_filter_hidden_tags(items: list[dict]) -> tuple[list[dict], int]:
    """过滤结果中包含隐藏标签的画廊，返回 (过滤后列表, 隐藏数量)。"""
    hidden = _load_ex_hidden_tags()
    if not hidden:
        return items, 0
    kept = []
    for item in items:
        tags = item.get("tags") or []
        if any(_ex_hidden_tag_matched(t, hidden) for t in tags):
            continue
        kept.append(item)
    return kept, len(items) - len(kept)


def exhentai_get_hidden_tags() -> None:
    """获取隐藏标签列表。"""
    emit({"event": "ex_hidden_tags", "tags": _load_ex_hidden_tags()})


def exhentai_add_hidden_tag(tag: str) -> None:
    """新增隐藏标签。"""
    tag = (tag or "").strip()
    if not tag:
        emit({"event": "account_error", "message": "标签名不能为空"})
        return
    tags = _load_ex_hidden_tags()
    low = tag.lower()
    if any(t.lower() == low for t in tags):
        emit({"event": "ex_hidden_tags", "tags": tags})
        return
    tags.append(tag)
    _save_ex_hidden_tags(tags)
    emit({"event": "ex_hidden_tags", "tags": tags})
    logging.info("ExHentai 新增隐藏标签: %s", tag)


def exhentai_delete_hidden_tag(tag: str) -> None:
    """删除隐藏标签（× 按钮）。"""
    tag = (tag or "").strip()
    tags = _load_ex_hidden_tags()
    new_tags = [t for t in tags if t.lower() != tag.lower()]
    _save_ex_hidden_tags(new_tags)
    emit({"event": "ex_hidden_tags", "tags": new_tags})
    logging.info("ExHentai 删除隐藏标签: %s", tag)


# ExHentai 搜索分类（f_cats 位掩码：勾选位掩码之和，f_cats = 1023 - 勾选和）
EXHENTAI_CATEGORIES = [
    ("misc", "杂项", 1),
    ("doujinshi", "同人志", 2),
    ("manga", "漫画", 4),
    ("artistcg", "艺术家CG", 8),
    ("gamecg", "游戏CG", 16),
    ("imageset", "图集", 32),
    ("cosplay", "Cosplay", 64),
    ("asianporn", "亚洲色情", 128),
    ("nonh", "非H", 256),
    ("western", "西方", 512),
]


def _exhentai_search_params(query: str, options: dict) -> dict:
    """根据搜索选项构造 EX 搜索 URL 参数（对应原版搜索页的过滤按钮）。"""
    params: dict = {"f_search": query}
    if options is None:
        return params
    # 分类复选（原版 10 个分类；f_cats = 1023 - 勾选位掩码和）
    cats = options.get("exhentai_cats")
    if isinstance(cats, list) and cats:
        bits = sum(bit for key, _, bit in EXHENTAI_CATEGORIES if key in cats)
        if 0 < bits < 1023:
            params["f_cats"] = 1023 - bits
    # 最低评分（2-5 星）
    try:
        mr = int(options.get("exhentai_min_rating") or 0)
    except (TypeError, ValueError):
        mr = 0
    if 2 <= mr <= 5:
        params["f_sr"] = "on"
        params["f_srdd"] = mr
    # 仅显示有种子的画廊
    if options.get("exhentai_torrents_only"):
        params["f_sto"] = "on"
    # 页数范围
    try:
        pmin = int(options.get("exhentai_page_min") or 0)
        pmax = int(options.get("exhentai_page_max") or 0)
    except (TypeError, ValueError):
        pmin = pmax = 0
    if pmin > 0 or pmax > 0:
        params["f_sp"] = "on"
        if pmin > 0:
            params["f_spf"] = pmin
        if pmax > 0:
            params["f_spt"] = pmax
    return params


async def exhentai_search(query: str, page: int = 1, options: dict | None = None) -> None:
    """ExHentai 画廊关键词搜索（f_search + 过滤选项 + next 游标分页）。

    游标规则：进入第 N 页用 next=<第 N-1 页最后一个画廊的 ID>。
    跳页时从已缓存的最高已知页顺序推进到目标页（每页受节流限制）。
    过滤选项（分类/评分/种子/页数范围）来自 settings，与原版搜索页按钮等效。
    """
    if not query.strip():
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    page = max(1, int(page))
    base_params = _exhentai_search_params(query, options or {})
    try:
        emit({"event": "search_start", "query": query, "page": page})
        cursors = _load_ex_cursors()
        # 游标缓存 key 需包含过滤条件（不同过滤 = 不同结果集）
        filter_key = "&".join(
            f"{k}={v}" for k, v in base_params.items() if k != "f_search"
        )
        key = query.strip().lower() + ("|" + filter_key if filter_key else "")
        entry = cursors.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        # 已知入口游标：{"2": gid, "3": gid, ...}（进入该页所需 next 值）
        pages_map = {int(k): v for k, v in entry.items() if str(k).isdigit()}

        # 起始页：已知游标的最高页（不超过目标页），从它开始顺序抓
        cur = 1
        for p in sorted(pages_map):
            if p <= page:
                cur = max(cur, p)

        html = ""
        items: list[dict] = []
        while cur <= page:
            params: dict = dict(base_params)
            if cur > 1:
                cursor = pages_map.get(cur)
                if cursor is None:
                    break
                params["next"] = cursor
            response = await asyncio.to_thread(_exhentai_fetch, EXHENTAI_HOST + "/", params)
            html = response.text
            gids = _parse_ex_gallery_ids(html)
            if cur == page:
                items = _parse_ex_search_page(html)
                # 记录下一页游标（本页最后一个画廊 ID）
                if gids:
                    pages_map[page + 1] = gids[-1]
                break
            # 中间页：仅记录下一页游标后继续推进
            if not gids:
                break
            pages_map[cur + 1] = gids[-1]
            cur += 1

        if page > 1 and not items and not pages_map.get(page):
            # 目标页不可达（超出结果范围）
            emit({"event": "search_error", "message": f"第 {page} 页不存在或超出结果范围"})
            return

        # 总页数："Found about 225,000 results" / 过滤后 "Found 37 results" → 按每页条数折算
        total_results = entry.get("total_results") or 0
        m = re.search(r"Found (?:about )?([\d,]+) results", html)
        if m:
            try:
                total_results = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        per_page = len(items) or 25
        if total_results > 0:
            total_pages = max(1, -(-total_results // per_page))
        else:
            # 无总数信息：有结果就保守认为还有下一页
            total_pages = page + 1 if items else page

        # 是否有下一页：页面存在 next= 链接即有
        has_next = bool(re.search(r"[?&]next=\d+", html)) and bool(items)

        # 保存游标缓存
        entry = {"total_results": total_results}
        for p, gid in sorted(pages_map.items()):
            entry[str(p)] = gid
        cursors[key] = entry
        _save_ex_cursors(cursors)

        # 隐藏标签过滤（用户手动标记的 tags 不显示）
        items, hidden_count = _exhentai_filter_hidden_tags(items)

        _apply_cached_thumbnails(items)
        emit({
            "event": "search_result",
            "query": query,
            "page": page,
            "total_pages": total_pages,
            "total_results": total_results,
            "has_more": has_next,
            "hidden_count": hidden_count,
            "items": items,
        })
        asyncio.create_task(_cache_thumbnails(items))
        logging.info("ExHentai 搜索完成: '%s' 第 %d/%d 页，%d 个结果（隐藏 %d）",
                     query, page, total_pages, len(items), hidden_count)

    except PermissionError as exc:
        emit({"event": "search_error", "message": str(exc)})
    except requests.RequestException as exc:
        emit({"event": "search_error", "message": f"ExHentai 搜索失败: {exc}（请检查代理设置）"})
        logging.exception("ExHentai 搜索出错")


# ============================
# Download 命令：下载选中文件
# ============================
async def gui_download(url: str, selected_items: list[dict], options: dict) -> None:
    """下载用户选中的文件。"""
    if not selected_items:
        emit({"event": "download_error", "message": "没有选中的文件"})
        return

    logging.info("开始下载: %s, 选中 %d 个文件", url, len(selected_items))
    args = create_args(options)

    try:
        validated_url = normalize_url(url)

        if is_pawchive_url(validated_url):
            # Pawchive：直链永久有效，无需抓取页面；目录按画师名组织
            soup = None
            album_name = await asyncio.to_thread(
                _pawchive_album_name, validated_url, selected_items,
            )
            album_id = None
        elif is_coomer_url(validated_url):
            soup = await fetch_page(validated_url)
            if soup is None:
                emit({"event": "download_error", "message": f"无法获取页面: {validated_url}"})
                return
            # Coomer：相册名取作者名，下载目录按作者组织
            info = _coomer_parse_url(validated_url)
            album_name = (info or {}).get("username") or "Coomer 下载"
            album_id = None
        else:
            soup = await fetch_page(validated_url)
            if soup is None:
                emit({"event": "download_error", "message": f"无法获取页面: {validated_url}"})
                return
            is_album = check_url_type(validated_url)
            album_name = get_album_name(soup)
            album_id = get_album_id(validated_url) if is_album else None

        # 构建相册目录
        # EX 批量下载母文件夹：用搜索词作母文件夹名，每个画廊按其标题分子文件夹
        batch_parent = (options.get("batch_parent_folder") or "").strip()
        if batch_parent:
            # 用母文件夹名作为顶层目录名（album_id 留空避免拼接后缀）
            album_path = build_album_directory(batch_parent, None, options)
        else:
            album_path = build_album_directory(album_name, album_id, options)
        logging.info("下载目录: %s", album_path)

        # 创建速率限制器
        rate_limit = args.rate_limit
        rate_limiter = RateLimiter(rate_limit * KB if rate_limit else None)

        # 创建 session_info
        session_info = SessionInfo(
            args=args,
            bunkr_status={},
            download_path=album_path,
            rate_limiter=rate_limiter,
        )

        live_manager = GuiLiveManager()
        live_manager.add_overall_task(
            album_name or album_id or "下载",
            len(selected_items),
        )

        semaphore = asyncio.Semaphore(MAX_WORKERS)
        max_retries = args.max_retries or MAX_RETRIES

        async def download_one(index: int, item: dict) -> None:
            async with semaphore:
                item_page = item["item_page"]
                filename_hint = item.get("filename", "")

                # 创建任务
                task_id = live_manager.add_task(current_task=index)

                if item.get("site") == "pawchive":
                    # Pawchive：直链永久有效，直接下载（站点对下载有限速，先节流）
                    await _pawchive_throttle_download()
                    download_link = item.get("media_url") or ""
                    filename = item.get("filename") or "pawchive_file"
                    if not download_link.startswith("http"):
                        live_manager.update_log(
                            event="解析失败",
                            details=f"缺少下载直链: {filename_hint}",
                        )
                        emit({
                            "event": "file_complete",
                            "filename": filename_hint,
                            "success": False,
                            "size": item.get("size"),
                        })
                        return
                elif item.get("site") == "coomer":
                    # Coomer：重新抓取帖子页获取新的媒体直链（视频链接带签名会过期）
                    download_link, filename = await get_coomer_download_info(item)
                    if not download_link:
                        live_manager.update_log(
                            event="解析失败",
                            details=f"无法获取下载链接: {filename_hint}",
                        )
                        emit({
                            "event": "file_complete",
                            "filename": filename_hint,
                            "success": False,
                            "size": item.get("size"),
                        })
                        return
                else:
                    # 重新解析下载信息（下载链接可能已过期）
                    item_soup = await fetch_page(item_page)
                    if item_soup is None:
                        live_manager.update_log(
                            event="获取失败",
                            details=f"无法获取文件页面: {filename_hint}",
                        )
                        emit({
                            "event": "file_complete",
                            "filename": filename_hint,
                            "success": False,
                            "size": item.get("size"),
                        })
                        return

                    download_link, filename = await get_download_info(
                        item_page, item_soup, clean_name=args.clean_name,
                    )
                if not download_link:
                    live_manager.update_log(
                        event="解析失败",
                        details=f"无法获取下载链接: {filename_hint}",
                    )
                    emit({
                        "event": "file_complete",
                        "filename": filename_hint,
                        "success": False,
                        "size": item.get("size"),
                    })
                    return

                size = item.get("size")
                live_manager.set_task_info(task_id, filename, size)

                # 构建文件下载路径（Pawchive 专属子文件夹规则 + 按类型分类）
                if item.get("site") == "pawchive":
                    base_dir = _pawchive_build_file_dir(album_path, item, options)
                    file_download_path = build_file_download_path(
                        base_dir, filename, options,
                    )
                else:
                    # EX 批量下载：按画廊标题分子文件夹（母文件夹已作顶层目录）
                    base_dir = album_path
                    g_title = (item.get("gallery_title") or "").strip()
                    if g_title and batch_parent:
                        sub = str(Path(album_path) / sanitize_directory_name(g_title))
                        Path(sub).mkdir(parents=True, exist_ok=True)
                        base_dir = sub
                    file_download_path = build_file_download_path(
                        base_dir, filename, options,
                    )

                # 创建该文件的 session_info 副本（避免并发修改）
                file_args = args
                if item.get("site") == "pawchive":
                    # Pawchive：站点限流严格，强制单连接下载，避免并行分块触发封锁
                    file_args = Namespace(**vars(args))
                    file_args.connections = 1
                file_session_info = replace(
                    session_info, download_path=file_download_path, args=file_args,
                )

                emit({
                    "event": "file_start",
                    "filename": filename,
                    "index": index,
                    "size": size,
                })

                media_downloader = MediaDownloader(
                    session_info=file_session_info,
                    download_info=DownloadInfo(
                        item_url=item_page,
                        download_link=download_link,
                        filename=filename,
                        task=task_id,
                    ),
                    live_manager=live_manager,
                    retry_config=RetryConfig(
                        retries=max_retries,
                        has_external_retry=False,
                    ),
                )

                failed = await asyncio.to_thread(media_downloader.download)

                emit({
                    "event": "file_complete",
                    "filename": filename,
                    "success": not failed,
                    "size": size,
                })
                if failed:
                    logging.warning("文件下载失败: %s", filename)
                else:
                    logging.info("文件下载完成: %s", filename)
                    # 记录到历史任务
                    final_path = str(Path(file_download_path) / truncate_filename(filename))
                    _add_history_entry({
                        "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                        "filename": filename,
                        "path": final_path,
                        "size": size,
                        "album": album_name or album_id or "下载",
                        "time": datetime.now().isoformat(timespec="seconds"),
                    })

        tasks = [
            download_one(i, item) for i, item in enumerate(selected_items)
        ]
        await asyncio.gather(*tasks)

        live_manager.stop()
        logging.info("下载完成")

    except Exception as exc:
        emit({"event": "download_error", "message": f"下载过程出错: {exc}"})
        logging.exception("下载过程出错")


# ============================
# Search 命令：搜索 Bunkr 相册
# ============================
SEARCH_ENDPOINT = "https://balbums.st/"

# 完整浏览器请求头，模拟真实浏览器访问，降低被识别为爬虫的概率
SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Referer": "https://balbums.st/",
}

# 复用 session：保持 cookie 和连接池，避免每次请求都重新握手
_search_session = requests.Session()
_search_session.headers.update(SEARCH_HEADERS)

# Coomer 搜索专用 session：Referer 指向站点自身（复用 balbums.st 的 Referer 会被拦截）
_coomer_session = requests.Session()
_coomer_session.headers.update({
    "User-Agent": SEARCH_HEADERS["User-Agent"],
    "Accept": SEARCH_HEADERS["Accept"],
    "Accept-Language": SEARCH_HEADERS["Accept-Language"],
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Referer": COOMER_HOST + "/",
})

# 请求节流参数
_SEARCH_MIN_INTERVAL = 0.8   # 两次请求之间的最小间隔（秒）
_SEARCH_MAX_RETRIES = 3      # 最大重试次数
_SEARCH_TIMEOUT = 15         # 单次请求超时（秒）

_search_lock = threading.Lock()
_last_search_time = 0.0


def _throttle_search() -> None:
    """限制搜索请求频率，避免因请求过快触发反爬虫。"""
    global _last_search_time
    with _search_lock:
        elapsed = time.time() - _last_search_time
        wait = _SEARCH_MIN_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)
        _last_search_time = time.time()


def _fetch_search_page(query: str, page: int, per_page: int) -> BeautifulSoup | None:
    """同步抓取 balbums.st 搜索页，带限流、重试和指数退避。

    反爬虫应对：
    - 完整浏览器请求头 + 复用 session（保持 cookie）
    - 请求节流（最小间隔）
    - 429 限流时等待更久再重试
    - 网络异常时指数退避 + 随机抖动
    """
    _throttle_search()

    params = {
        "search": query,
        "mode": "broad",
        "per": str(per_page),
        "sort": "latest",
        "page": str(page),
    }

    for attempt in range(_SEARCH_MAX_RETRIES):
        try:
            response = _search_session.get(
                SEARCH_ENDPOINT,
                params=params,
                timeout=_SEARCH_TIMEOUT,
            )

            # 429 Too Many Requests：被限流，等待更长时间后重试
            if response.status_code == 429:
                backoff = 2 ** (attempt + 1) + random.uniform(0, 1)
                logging.warning("搜索被限流(429)，%.1f 秒后重试", backoff)
                time.sleep(backoff)
                continue

            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")

        except requests.RequestException as exc:
            logging.warning("搜索请求失败(第 %d/%d 次): %s", attempt + 1, _SEARCH_MAX_RETRIES, exc)
            if attempt < _SEARCH_MAX_RETRIES - 1:
                backoff = 2 ** attempt + random.uniform(0.5, 1.5)
                time.sleep(backoff)

    return None


def _parse_search_results(soup: BeautifulSoup) -> tuple[list[dict], int]:
    """解析搜索结果页，返回 (相册列表, 总页数)。"""
    items: list[dict] = []

    for card in soup.find_all("a", class_="card"):
        album_url = card.get("href", "")
        if not album_url:
            continue

        # 缩略图：优先取真实缩略图（static.scdn.st），否则用占位图标
        thumbnail = "/img/bunkr.svg"
        for img in card.find_all("img"):
            src = img.get("src", "")
            if "static.scdn.st" in src or src.startswith("http"):
                thumbnail = src
                break
        if thumbnail.startswith("/"):
            thumbnail = "https://balbums.st" + thumbnail

        # 相册名
        h3 = card.find("h3")
        album_name = h3.get_text(strip=True) if h3 else ""

        # 文件数
        files = 0
        for span in card.find_all("span"):
            match = re.search(r"(\d+)\s*files?", span.get_text(strip=True), re.IGNORECASE)
            if match:
                files = int(match.group(1))
                break

        items.append({
            "album_name": album_name,
            "album_url": album_url,
            "thumbnail": thumbnail,
            "files": files,
        })

    # 分页：从 "page X of Y" 文本中提取总页数
    text = soup.get_text(" ", strip=True)
    match = re.search(r"page\s+(\d+)\s+of\s+(\d+)", text, re.IGNORECASE)
    total_pages = int(match.group(2)) if match else 1

    return items, total_pages


# 缩略图本地缓存目录
THUMBNAIL_CACHE_DIR = "cache/thumbnails"
# 缩略图索引：记录「本地文件名 -> 原始缩略图 URL」的对应关系
THUMBNAIL_INDEX_FILE = "cache/thumbnails_index.json"
# 缓存体积上限：超过后按最旧文件清理（防止长期使用后缓存过大导致卡顿/不显示）
THUMBNAIL_CACHE_MAX_BYTES = 500 * 1024 * 1024
THUMBNAIL_CACHE_KEEP_BYTES = 400 * 1024 * 1024
_thumb_cleanup_last = 0.0


def _cleanup_thumbnail_cache() -> None:
    """缩略图缓存超过上限时按最旧优先删除（LRU），并同步修剪索引。"""
    global _thumb_cleanup_last
    # 每小时最多执行一次，避免频繁扫描目录
    if time.time() - _thumb_cleanup_last < 3600:
        return
    _thumb_cleanup_last = time.time()

    cache_dir = Path(THUMBNAIL_CACHE_DIR)
    if not cache_dir.exists():
        return
    try:
        entries = []
        total = 0
        for p in cache_dir.iterdir():
            if not p.is_file():
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, p, stat.st_size))
            total += stat.st_size
        if total <= THUMBNAIL_CACHE_MAX_BYTES:
            return

        # 按修改时间从旧到新删除，直到降到保留水位以下
        entries.sort()
        removed: set[str] = set()
        for _, path, size in entries:
            if total <= THUMBNAIL_CACHE_KEEP_BYTES:
                break
            try:
                path.unlink(missing_ok=True)
                removed.add(path.name)
                total -= size
            except OSError:
                continue

        if removed:
            index = _load_thumbnail_index()
            index = {k: v for k, v in index.items() if k not in removed}
            _save_thumbnail_index(index)
            logging.info("缩略图缓存清理: 删除 %d 个最旧文件", len(removed))
    except OSError as exc:
        logging.warning("缩略图缓存清理失败: %s", exc)


# ============================
# 本地媒体代理（在线播放：带站点 cookie/代理的流式 HTTP 服务，支持 Range 拖动进度条）
# ============================
# 允许代理的域名关键字（防止本服务被滥用为开放代理）
_MEDIA_ALLOWED_KEYWORDS = (
    "bunkr", "coomer", "pawchive", "e-hentai", "exhentai", "ehgt",
    "hath.network", "twimg", "iwara", "hanime", "hembed", "oreno3d",
    "erommdtube", "asmr", "kiko-play",
)
_media_proxy_port: int = 0  # 启动后填充（127.0.0.1 随机端口）


def _media_host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(k in host for k in _MEDIA_ALLOWED_KEYWORDS)


def media_proxy_url(media_url: str) -> str:
    """把远端媒体直链转换为本地代理 URL（前端 <img>/<video> 直接使用）。"""
    if not media_url or not _media_proxy_port:
        return media_url or ""
    if media_url.startswith(("http://127.0.0.1", "thumb://")):
        return media_url
    from urllib.parse import quote
    return f"http://127.0.0.1:{_media_proxy_port}/media?url={quote(media_url, safe='')}"


def _media_route(url: str) -> tuple[dict, str | None, str | None]:
    """按域名选择 headers / cookie / 代理（与缩略图缓存同套路）。"""
    headers = {"User-Agent": DOWNLOAD_HEADERS.get("User-Agent", "Mozilla/5.0")}
    netloc = urlparse(url).netloc.lower()
    if netloc:
        headers["Referer"] = f"https://{netloc}/"
    cookie = None
    proxy = None
    # Twitter 媒体（pbs.twimg.com / video.twimg.com）：国内必须走代理
    if "twimg" in netloc:
        proxy = _twitter_proxy
    # Iwara 文件（files.iwara.tv）：按设置走代理；带上登录 token（私密视频需要）
    elif "iwara" in netloc:
        proxy = _iwara_proxy or None
        token = _iwara_load_token().get("user_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    # ExHentai 图片（exhentai.org / e-hentai.org / *.hath.network）：必须带账号 cookie + 代理
    elif any(k in netloc for k in ("exhentai", "e-hentai", "ehgt", "hath.network")):
        cookie = _exhentai_cookie_str() or None
        proxy = _exhentai_proxy
    # Pawchive 数据域名（file.pawchive.pw / img.pawchive.pw）：带会话 cookie（部分内容需登录）
    elif "pawchive" in netloc:
        cookie = "; ".join(f"{c.name}={c.value}" for c in _pawchive_session.cookies) or None
    # Hanime1 媒体（vdownload.hembed.com / hanime1.me）：带代理 + Referer
    elif "hanime" in netloc or "hembed" in netloc:
        proxy = _hanime_proxy or None
        headers["Referer"] = f"{HANIME_BASE}/"
    # Oreno3D（oreno3d.com / *.oreno3d.com）：按设置走代理
    elif "oreno3d" in netloc:
        proxy = _oreno_proxy or None
    # EroMMDTube（erommdtube.com）：按设置走代理
    elif "erommdtube" in netloc:
        proxy = _erommd_proxy or None
    # ASMR 音声（api.asmr-200.com / *.kiko-play-niptan.one 等）：按设置走代理
    elif "asmr" in netloc or "kiko-play" in netloc:
        proxy = _asmr_proxy or None
    if cookie:
        headers["Cookie"] = cookie
    return headers, cookie, proxy


async def _media_proxy_handler(request: "aiohttp.web.Request") -> "aiohttp.web.StreamResponse":
    """GET /media?url=<远端媒体直链>：流式转发（支持 Range，视频可拖动进度条）。"""
    web = aiohttp_web
    url = request.query.get("url") or ""
    if not url.startswith(("http://", "https://")) or not _media_host_allowed(urlparse(url).netloc):
        return web.Response(status=403, text="不允许的媒体地址")
    headers, _, proxy = _media_route(url)
    # 透传 Range（视频拖动进度条必需）
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header
    try:
        # auto_decompress=False：按原始字节流转发，Content-Length 才能对得上
        session = aiohttp.ClientSession(auto_decompress=False)
        try:
            upstream = await session.get(
                url, headers=headers, proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=None, sock_read=60),
                allow_redirects=True,
            )
            if upstream.status >= 400:
                await upstream.release()
                return web.Response(status=upstream.status, text="远端返回错误")
            stream = web.StreamResponse(
                status=upstream.status,
                reason=upstream.reason if upstream.status != 200 else "OK",
            )
            for h in ("Content-Type", "Content-Length", "Content-Range",
                      "Accept-Ranges", "ETag", "Last-Modified"):
                v = upstream.headers.get(h)
                if v:
                    stream.headers[h] = v
            await stream.prepare(request)
            try:
                async for chunk in upstream.content.iter_chunked(256 * 1024):
                    await stream.write(chunk)
            finally:
                await stream.write_eof()
            return stream
        finally:
            await session.close()
    except Exception as exc:
        logging.debug("媒体代理转发失败 %s: %s", url, exc)
        return web.Response(status=502, text=f"转发失败: {exc}")


async def start_media_proxy() -> int:
    """启动本地媒体代理（127.0.0.1 随机端口），并通知前端端口。"""
    global _media_proxy_port
    if _media_proxy_port:
        return _media_proxy_port
    app = aiohttp_web.Application()
    app.router.add_get("/media", _media_proxy_handler)
    runner = aiohttp_web.AppRunner(app, access_log=None)
    await runner.setup()
    site = aiohttp_web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    addresses = runner.addresses or [("127.0.0.1", 0)]
    _media_proxy_port = int(addresses[0][1])
    logging.info("媒体代理已启动: http://127.0.0.1:%d/media", _media_proxy_port)
    emit({"event": "media_proxy_ready", "port": _media_proxy_port})
    return _media_proxy_port


async def resolve_media_url(item: dict) -> None:
    """解析条目的媒体直链（在线播放用）。

    - Coomer/Pawchive/Twitter/Iwara：条目已带 media_url，直接返回
    - Bunkr：item_page 是文件页，走签名 API 懒解析直链
    - ExHentai：item_page 是图片页，解析 #img 直链
    成功后发 media_url_resolved 事件，前端把直链换成本地代理地址播放。
    """
    item_page = str(item.get("item_page") or "")
    media_url = str(item.get("media_url") or "")
    site = str(item.get("site") or "")
    event = {"event": "media_url_resolved", "item_page": item_page,
             "media_url": "", "success": False, "message": ""}
    try:
        if media_url:
            event.update({"media_url": media_url, "success": True})
            emit(event)
            return
        netloc = urlparse(item_page).netloc.lower()
        if "bunkr" in netloc:
            # Bunkr 文件页：签名 API 返回直链（与下载流程同一套解析）
            async with aiohttp.ClientSession() as session:
                link = await get_item_download_link(session, item_page)
            if link:
                event.update({"media_url": link, "success": True})
            else:
                event["message"] = "未能解析 Bunkr 直链（页面可能需要重新解析）"
        elif any(k in netloc for k in ("exhentai", "e-hentai")):
            def _ex_resolve() -> str:
                resp = _exhentai_fetch(item_page)
                soup = BeautifulSoup(resp.text, "html.parser")
                img = soup.select_one("#img")
                src = (img.get("src") or "") if img else ""
                return src if src.startswith("http") else ""
            link = await asyncio.to_thread(_ex_resolve)
            if link:
                event.update({"media_url": link, "success": True})
            else:
                event["message"] = "未能解析图片直链（登录可能已失效）"
        else:
            event["message"] = "该条目没有可播放的直链"
    except Exception as exc:
        event["message"] = f"解析失败: {exc}"
    emit(event)



def _load_thumbnail_index() -> dict:
    """读取缩略图索引，返回 {文件名: 原始URL}。"""
    try:
        with Path(THUMBNAIL_INDEX_FILE).open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_thumbnail_index(index: dict) -> None:
    """保存缩略图索引。"""
    try:
        Path(THUMBNAIL_INDEX_FILE).parent.mkdir(parents=True, exist_ok=True)
        with Path(THUMBNAIL_INDEX_FILE).open("w", encoding="utf-8") as file:
            json.dump(index, file, ensure_ascii=False)
    except OSError as exc:
        logging.warning("保存缩略图索引失败: %s", exc)


def _thumbnail_cache_path(url: str) -> Path:
    """根据缩略图 URL 生成本地缓存文件路径。"""
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
        ext = ".jpg"
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return Path(THUMBNAIL_CACHE_DIR) / f"{digest}{ext}"


# 缩略图下载请求头：带上浏览器 UA 和 Referer，避免被 CDN 判为爬虫拒绝
THUMB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://bunkr.cr/",
}


def _is_valid_image(data: bytes) -> bool:
    """通过文件头（魔数）判断下载内容是否为有效图片，避免写入破损文件。"""
    if not data:
        return False
    if data[:3] == b"\xff\xd8\xff":                    # JPEG
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":               # PNG
        return True
    if data[:4] == b"GIF8":                            # GIF
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WebP
        return True
    head = data[:512].lstrip()
    if b"<svg" in head or b"<?xml" in head:  # SVG
        return True
    return False


def _is_valid_cache_file(path: Path) -> bool:
    """检查已缓存缩略图文件头是否为有效图片。"""
    try:
        with path.open("rb") as file:
            return _is_valid_image(file.read(512))
    except OSError:
        return False


def _extract_item_thumbnail(item_soup: BeautifulSoup) -> str | None:
    """从单个文件页面提取缩略图 URL（og:image，视频和图片都适用）。"""
    if item_soup is None:
        return None
    meta = item_soup.find("meta", property="og:image")
    if meta is None:
        return None
    url = (meta.get("content") or "").strip()
    if not url:
        return None
    # 协议相对 URL（//cdn...）补全为 https
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith("http") else None


def _apply_cached_thumbnails(items: list[dict]) -> None:
    """把已缓存到本地的缩略图替换为 thumb://local/ 路径，加快重复查看速度。"""
    for item in items:
        url = item.get("thumbnail", "")
        if not url:
            continue
        # 兼容旧格式 thumb://<name>，迁移为 thumb://local/<name>
        if url.startswith("thumb://") and not url.startswith("thumb://local/"):
            item["thumbnail"] = "thumb://local/" + url[len("thumb://"):]
            continue
        if not url.startswith("http"):
            continue
        cache_path = _thumbnail_cache_path(url)
        if cache_path.exists() and _is_valid_cache_file(cache_path):
            item["thumbnail"] = f"thumb://local/{cache_path.name}"


async def _cache_thumbnails(items: list[dict]) -> None:
    """后台下载尚未缓存的缩略图到本地。

    只负责落盘，不修改 items（结果已经返回给前端），失败不影响搜索主流程。
    """
    Path(THUMBNAIL_CACHE_DIR).mkdir(parents=True, exist_ok=True)

    pending: list[tuple[str, Path]] = []
    for item in items:
        url = item.get("thumbnail", "")
        if not url.startswith("http"):
            continue
        cache_path = _thumbnail_cache_path(url)
        # 未缓存，或已缓存的破损文件，都重新下载
        if not cache_path.exists() or not _is_valid_cache_file(cache_path):
            pending.append((url, cache_path))

    if not pending:
        return

    async def cache_one(session: aiohttp.ClientSession, url: str, cache_path: Path) -> bool:
        # Referer 跟随缩略图所在站点，避免跨站 Referer 被 CDN 拒绝（Pawchive/Coomer 等）
        headers = dict(THUMB_HEADERS)
        netloc = urlparse(url).netloc
        proxy = None
        if netloc:
            headers["Referer"] = f"https://{netloc}/"
        # ExHentai 系缩略图（exhentai.org/e-hentai.org/ehgt.org，302 跨域到 CDN）：
        # 用带账号 cookie + 代理的 requests 会话直接下载（aiohttp 跨域重试/cookie 处理不稳，导致缩略图损坏）
        if netloc.endswith("exhentai.org") or netloc.endswith("e-hentai.org") or netloc.endswith("ehgt.org"):
            def _download_ex_thumb() -> bool:
                try:
                    ex_headers = dict(THUMB_HEADERS)
                    ex_headers["Referer"] = f"{EXHENTAI_HOST}/"
                    cookie = _exhentai_cookie_str()
                    if cookie:
                        ex_headers["Cookie"] = cookie
                    resp = _exhentai_session.get(url, timeout=15, headers=ex_headers)
                    if resp.ok and _is_valid_image(resp.content):
                        cache_path.write_bytes(resp.content)
                        return True
                    return False
                except requests.RequestException:
                    return False

            return await asyncio.to_thread(_download_ex_thumb)
        # Twitter/X 缩略图（pbs.twimg.com / video.twimg.com）国内需代理
        if netloc.endswith("twimg.com"):
            proxy = _twitter_proxy
        # Iwara 缩略图（files.iwara.tv）按设置走代理
        if netloc.endswith("iwara.tv"):
            proxy = _iwara_proxy or None
        # Hanime1 缩略图（vdownload.hembed.com）国内需代理
        if "hembed" in netloc or "hanime" in netloc:
            proxy = _hanime_proxy or None
            headers["Referer"] = f"{HANIME_BASE}/"
        # Oreno3D 缩略图（oreno3d.com/storage/...）/ EroMMDTube 缩略图 按设置走代理
        if "oreno3d" in netloc:
            proxy = _oreno_proxy or None
        if "erommdtube" in netloc:
            proxy = _erommd_proxy or None
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=20), headers=headers, proxy=proxy,
            ) as resp:
                if resp.status != 200:
                    logging.debug("缩略图缓存失败 %s: HTTP %s", url, resp.status)
                    return False
                data = await resp.read()
                # 校验文件头，避免把错误页/破损内容写入缓存
                if not _is_valid_image(data):
                    logging.debug("缩略图缓存失败 %s: 内容非有效图片", url)
                    return False
                cache_path.write_bytes(data)
                return True
        except Exception as exc:
            logging.debug("缩略图缓存失败 %s: %s", url, exc)
        return False

    # 共享同一个 session，减少握手开销
    # 并发限制 6：全量并发会触发站点限流/超时，反而批量失败
    sem = asyncio.Semaphore(6)

    async def fetch_one(session: aiohttp.ClientSession, url: str, cache_path: Path) -> bool:
        # 失败自动重试 1 次（弱网/偶发 503 场景，提高缓存成功率）
        for attempt in range(2):
            ok = await cache_one(session, url, cache_path)
            if ok:
                return True
            if attempt == 0:
                await asyncio.sleep(0.8)
        return False

    async with aiohttp.ClientSession() as session:
        async def bounded(url: str, cp: Path) -> bool:
            async with sem:
                return await fetch_one(session, url, cp)

        results = await asyncio.gather(
            *(bounded(url, cp) for url, cp in pending),
        )

    # 更新索引：本地文件名 -> 原始缩略图 URL
    index = _load_thumbnail_index()
    changed = False
    cached_items: list[dict] = []
    for (url, cache_path), ok in zip(pending, results):
        if ok:
            index[cache_path.name] = url
            changed = True
            cached_items.append({
                "url": url,
                "thumbnail": f"thumb://local/{cache_path.name}",
            })
    if changed:
        _save_thumbnail_index(index)

    # 通知前端：哪些缩略图已缓存到本地，前端把还在直连原图的 <img> 换成本地路径
    # （修复：首次查看时原图 URL 直连国内不通 → 一直加载失败；后台缓存完成也无人刷新）
    if cached_items:
        emit({"event": "thumbnails_cached", "items": cached_items})

    # 缓存体积超限时清理最旧的缩略图（节流：每小时最多一次）
    try:
        _cleanup_thumbnail_cache()
    except Exception:
        logging.exception("缩略图缓存清理出错")


async def gui_search(query: str, page: int, per_page: int, options: dict) -> None:
    """搜索 Bunkr / Coomer / Pawchive / ExHentai 并返回结果（按设置中的站点切换）。"""
    if not query.strip():
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return

    # 记录搜索历史（日常 tags 快速搜索用）
    add_search_history(query.strip(), options.get("site") or "bunkr", options.get("pawchive_search_mode") or "")

    # 站点切换：Coomer 模式下搜索 xxxcoomer.com 的作者
    if options.get("site") == "coomer":
        await coomer_search(query)
        return

    # 站点切换：Pawchive 模式下区分画师搜索 / 标签搜索
    if options.get("site") == "pawchive":
        if options.get("pawchive_search_mode") == "tag":
            await pawchive_search_tag(query, page)
        else:
            await pawchive_search_artist(query, page)
        return

    # 站点切换：ExHentai 模式下搜索画廊
    if options.get("site") == "exhentai":
        await exhentai_search(query, page, options)
        return

    # 站点切换：Twitter/X 模式下按用户名搜索用户
    if options.get("site") == "twitter":
        await twitter_search(query)
        return

    # 站点切换：Iwara 模式下搜索视频（关键词 / @用户名）
    if options.get("site") == "iwara":
        await iwara_search(query, page)
        return

    # 站点切换：Hanime1 模式下搜索视频（关键词 + 可选分类）
    if options.get("site") == "hanime":
        await hanime_search(
            query, page,
            options.get("hanime_genre") or "",
            options.get("hanime_sort") or "",
        )
        return

    # 站点切换：Oreno3D / EroMMDTube 模式下搜索视频（关键词）
    if options.get("site") in ("oreno3d", "erommdtube"):
        await oreno_search(query, page, options.get("oreno_sort") or "", options.get("site"))
        return

    # 站点切换：ASMR 音声站模式搜索作品（RJ 号 / 标题 / 社团 / 标签）
    if options.get("site") == "asmr":
        await asmr_search(query, page, bool(options.get("asmr_subtitle")))
        return

    # 站点切换：JavDB 模式搜索（番号 / 标题 / 演员）
    if options.get("site") == "javdb":
        await javdb_search(query, page)
        return

    emit({"event": "search_start", "query": query, "page": page})
    logging.info("开始搜索: '%s' (第 %d 页)", query, page)

    try:
        soup = await asyncio.to_thread(_fetch_search_page, query, page, per_page)
        if soup is None:
            emit({"event": "search_error", "message": "搜索失败，无法访问搜索服务"})
            return

        items, total_pages = _parse_search_results(soup)

        # 已缓存的缩略图直接使用本地 thumb://，加快重复查看速度
        _apply_cached_thumbnails(items)

        emit({
            "event": "search_result",
            "query": query,
            "page": page,
            "total_pages": total_pages,
            "has_more": page < total_pages,
            "items": items,
        })
        logging.info("搜索完成: '%s' 第 %d/%d 页，%d 个结果", query, page, total_pages, len(items))

        # 后台缓存尚未下载的缩略图，不阻塞结果返回；下次重复查看时命中本地缓存
        asyncio.create_task(_cache_thumbnails(items))

    except Exception as exc:
        emit({"event": "search_error", "message": f"搜索出错: {exc}"})
        logging.exception("搜索出错")


# ============================
# Coomer 站点搜索 (xxxcoomer.com)
# ============================
def _fetch_coomer_search_page(query: str) -> BeautifulSoup | None:
    """同步抓取 xxxcoomer.com 作者搜索页，带限流、重试和指数退避。"""
    _throttle_search()

    for attempt in range(_SEARCH_MAX_RETRIES):
        try:
            response = _coomer_session.get(
                COOMER_HOST,
                params={"q": query},
                timeout=_SEARCH_TIMEOUT,
            )

            if response.status_code == 429:
                backoff = 2 ** (attempt + 1) + random.uniform(0, 1)
                logging.warning("Coomer 搜索被限流(429)，%.1f 秒后重试", backoff)
                time.sleep(backoff)
                continue

            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")

        except requests.RequestException as exc:
            logging.warning(
                "Coomer 搜索请求失败(第 %d/%d 次): %s",
                attempt + 1, _SEARCH_MAX_RETRIES, exc,
            )
            if attempt < _SEARCH_MAX_RETRIES - 1:
                backoff = 2 ** attempt + random.uniform(0.5, 1.5)
                time.sleep(backoff)

    return None


def _parse_coomer_search_results(soup: BeautifulSoup) -> list[dict]:
    """解析 Coomer 作者搜索结果页，返回作者卡片列表。"""
    items: list[dict] = []

    for card in soup.find_all("div", class_="thumb"):
        link = card.find("a", href=True)
        if link is None:
            continue

        album_url = (link.get("href") or "").strip()
        if not album_url:
            continue
        if album_url.startswith("/"):
            album_url = COOMER_HOST + album_url

        # 头像缩略图
        thumbnail = ""
        img = card.find("img")
        if img:
            thumbnail = (img.get("src") or "").strip()
        if thumbnail.startswith("/"):
            thumbnail = COOMER_HOST + thumbnail

        # 作者名
        name_tag = card.find("p")
        album_name = name_tag.get_text(strip=True) if name_tag else ""
        if not album_name:
            album_name = album_url.rstrip("/").rsplit("/", 1)[-1]

        items.append({
            "album_name": album_name,
            "album_url": album_url,
            "thumbnail": thumbnail,
            "files": None,  # 搜索结果页不含文件数
            "site": "coomer",
        })

    return items


async def coomer_search(query: str) -> None:
    """搜索 xxxcoomer.com 作者并返回结果。"""
    emit({"event": "search_start", "query": query, "page": 1})
    logging.info("开始搜索 Coomer 作者: '%s'", query)

    try:
        soup = await asyncio.to_thread(_fetch_coomer_search_page, query)
        if soup is None:
            emit({"event": "search_error", "message": "搜索失败，无法访问 xxxcoomer.com"})
            return

        items = _parse_coomer_search_results(soup)

        # 已缓存的头像直接使用本地 thumb://，加快重复查看速度
        _apply_cached_thumbnails(items)

        emit({
            "event": "search_result",
            "query": query,
            "page": 1,
            "total_pages": 1,
            "has_more": False,
            "items": items,
        })
        logging.info("Coomer 搜索完成: '%s'，%d 个结果", query, len(items))

        # 后台缓存尚未下载的头像缩略图
        asyncio.create_task(_cache_thumbnails(items))

    except Exception as exc:
        emit({"event": "search_error", "message": f"搜索出错: {exc}"})
        logging.exception("Coomer 搜索出错")


# ============================
# 下载任务管理器
# ============================
DOWNLOAD_TASKS_FILE = "downloads_tasks.json"


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
                for item in task.get("files", []):
                    if item.get("status") == "downloading":
                        item["status"] = "pending"
                self.tasks[task["id"]] = task
        except (OSError, json.JSONDecodeError):
            pass

    def _write_tasks_file(self) -> None:
        """把任务表写入磁盘（调用方持有 _dirty 语义，本函数只做 IO）。"""
        try:
            payload = {"tasks": [self._json_safe_task(t) for t in self.tasks.values()]}
            with Path(DOWNLOAD_TASKS_FILE).open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
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
        """任务快照（深拷贝，避免序列化时并发修改导致崩溃/脏数据）。"""
        with self._lock:
            return [self._json_safe_task(t) for t in self.tasks.values()]

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
    def submit(
        self,
        url: str,
        items: list[dict],
        options: dict,
        album_name: str,
        album_id: str | None,
    ) -> str:
        """创建一个下载任务并持久化，返回任务 ID。"""
        task_id = f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        files = []
        for item in items:
            files.append({
                "item_page": item.get("item_page", ""),
                "filename": item.get("filename", ""),
                "size": item.get("size"),
                "status": "pending",
                "completed": 0,
                # Coomer 站点：保存媒体直链信息，下载时据此解析新链接
                "site": item.get("site", ""),
                "media_url": item.get("media_url", ""),
                "media_path": item.get("media_path", ""),
                # ExHentai / Pawchive：命名规则需要的字段（画师/帖子标题/日期）
                "artist": item.get("artist", ""),
                "post_title": item.get("post_title", ""),
                "post_date": item.get("post_date", ""),
            })
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

    def resume(self, task_id: str) -> None:
        self.start(task_id)

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

    def remove(self, task_id: str) -> None:
        """移除任务（运行中的会先标记取消，待其自然结束）。"""
        task = self.tasks.get(task_id)
        if not task:
            return
        task["status"] = "cancelled"
        self.tasks.pop(task_id, None)
        self._save(immediate=True)
        self.emit_snapshot(immediate=True)

    def set_shutdown_after_done(self, enabled: bool) -> None:
        self._shutdown_after_done = enabled
        emit({
            "event": "log",
            "type": "关机",
            "message": "已开启：全部下载完成后关机" if enabled else "已取消下载后关机",
        })

    # ---------- 下载执行 ----------
    async def _run(self, task_id: str) -> None:
        task = self.tasks[task_id]
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
                if item.get("status") == "completed":
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
        except Exception as exc:
            logging.exception("下载任务出错: %s", task_id)
            task["status"] = "failed"
            self._save(immediate=True)
            self.emit_snapshot(immediate=True)
        finally:
            self._runners.pop(task_id, None)

    def _write_failure_report(
        self, task: dict, files: list, album_path: str, task_id: str,
    ) -> None:
        """任务收尾：汇总失败文件生成 txt 清单（文件名 + 网页链接），供用户手动下载。"""
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
        elif item.get("site") == "coomer":
            # Coomer：重新抓取帖子页获取新的媒体直链（视频链接带签名会过期）
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
        file_session_info = replace(session_info, download_path=file_download_path)

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
        )

        failed = await asyncio.to_thread(media_downloader.download)

        if failed:
            item["status"] = "failed"
            task["failed"] = task.get("failed", 0) + 1
        else:
            item["status"] = "completed"
            item["completed"] = 100
            task["done"] = task.get("done", 0) + 1
            final_path = str(Path(file_download_path) / truncate_filename(filename))
            _add_history_entry({
                "id": f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
                "filename": filename,
                "path": final_path,
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

        def _resolve_and_download() -> tuple[bool, str]:
            """同步执行：解析直链 + 下载（带节流和重试）。"""
            import io

            for attempt in range(max(1, max_retries)):
                try:
                    # 1. 重新解析图片页（keystamp 时效签名，缓存的直链会过期）
                    #    首次失败后的重试走原站"刷新失效图片"链接（?nl=token 强制换 H@H 节点）
                    page_url_eff = item_page
                    if attempt > 0:
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

                    # 2. 目录：画师名/画廊标题（自定义模板 exhentai_folder_template 优先）
                    post_title = item.get("post_title") or ""
                    template = (options.get("exhentai_folder_template") or "").strip()
                    if template:
                        sub = _render_folder_template(
                            template, item.get("post_date") or "", post_title, item.get("post_id") or "",
                        )
                    elif post_title:
                        sub = sanitize_directory_name(post_title)
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
                        return True, str(Path(gallery_dir) / truncate_filename(final_name))
                    if dup_action == "prompt":
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
                        return True, ""

                    # 3. 唯一文件名 + 流式下载
                    final_name = final_name if dup_action == "renamed" else _unique_download_filename(gallery_dir, filename)
                    final_path = Path(gallery_dir) / truncate_filename(final_name)

                    _exhentai_throttle()
                    headers = dict(_exhentai_session.headers)
                    cookie = _exhentai_cookie_str()
                    if cookie:
                        headers["Cookie"] = cookie
                    headers["Referer"] = item_page  # hath 服务器校验 Referer

                    with _exhentai_session.get(
                        download_link, stream=True, timeout=60, headers=headers,
                    ) as resp:
                        resp.raise_for_status()
                        size = int(resp.headers.get("Content-Length") or 0)
                        live_manager.set_task_info(internal_task, final_name, size or None)
                        emit({
                            "event": "file_start",
                            "filename": final_name,
                            "index": 0,
                            "size": size or None,
                            "task_id": task_id,
                        })

                        downloaded = 0
                        last_pct = -1
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if task.get("status") in ("paused", "cancelled"):
                                    raise InterruptedError("任务已暂停/取消")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if size:
                                        pct = round(downloaded / size * 100, 1)
                                        if pct != last_pct:
                                            live_manager.update_task(internal_task, pct)
                                            last_pct = pct

                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    # 校验文件头：H@H 节点故障时会返回错误页/截断内容，视为失败走 nl 重试
                    if not _is_valid_cache_file(final_path):
                        final_path.unlink(missing_ok=True)
                        raise IOError("下载内容不是有效图片（H@H 节点故障，将换节点重试）")
                    return True, str(final_path)

                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning(
                        "ExHentai 图片下载失败(第 %d 次) %s: %s",
                        attempt + 1, filename, exc,
                    )
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        try:
            success, final_path = await asyncio.to_thread(_resolve_and_download)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return
        except Exception as exc:
            logging.exception("ExHentai 下载出错: %s", exc)
            success, final_path = False, ""

        final_name = item.pop("_final_name", filename)
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

    async def _twitter_download_one(
        self,
        task: dict,
        item: dict,
        album_path: str,
        task_id: str,
        max_retries: int,
    ) -> None:
        """下载单个 Twitter 媒体文件：直链（pbs/video.twimg.com）+ 代理流式下载。

        目录组织：下载根目录/用户名/YYYY-MM/推文内容（twitter_subfolder 设置）。
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

            for attempt in range(max(1, max_retries)):
                try:
                    # 1. 目录：按 twitter_subfolder 规则建子文件夹
                    options = task.get("options", {})
                    sub = _twitter_subfolder(item, options)
                    file_dir = album_path if not sub else str(Path(album_path) / sub)
                    if sub:
                        Path(file_dir).mkdir(parents=True, exist_ok=True)

                    # 2. 唯一文件名 + 流式下载（直链永久有效，走代理）
                    final_name = _unique_download_filename(file_dir, filename)
                    final_path = Path(file_dir) / truncate_filename(final_name)

                    _twitter_throttle_download()
                    with _twitter_session.get(
                        media_url, stream=True, timeout=60,
                        headers={"Referer": TWITTER_HOST + "/"},
                    ) as resp:
                        resp.raise_for_status()
                        size = int(resp.headers.get("Content-Length") or 0)
                        live_manager.set_task_info(internal_task, final_name, size or None)
                        emit({
                            "event": "file_start",
                            "filename": final_name,
                            "index": 0,
                            "size": size or None,
                            "task_id": task_id,
                        })

                        downloaded = 0
                        last_pct = -1
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if task.get("status") in ("paused", "cancelled"):
                                    raise InterruptedError("任务已暂停/取消")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if size:
                                        pct = round(downloaded / size * 100, 1)
                                        if pct != last_pct:
                                            live_manager.update_task(internal_task, pct)
                                            last_pct = pct

                    item["_final_path"] = str(final_path)
                    item["_final_name"] = final_name
                    item["size"] = size or None
                    return True, str(final_path)

                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning(
                        "Twitter 媒体下载失败(第 %d 次) %s: %s",
                        attempt + 1, filename, exc,
                    )
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        try:
            success, final_path = await asyncio.to_thread(_download)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return
        except Exception as exc:
            logging.exception("Twitter 下载出错: %s", exc)
            success, final_path = False, ""

        final_name = item.pop("_final_name", filename)
        if success:
            item["status"] = "completed"
            item["completed"] = 100
            task["done"] = task.get("done", 0) + 1
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
            "size": item.get("size"),
            "task_id": task_id,
        })
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

        # 目录：下载根目录/作者名/YYYY-MM（可自定义模板 iwara_folder_template）
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
                if date:
                    parts.append(date)
                sub = str(Path(*parts)) if parts else ""
            return str(Path(album_path) / sub) if sub else album_path

        def _resolve_and_download() -> tuple[bool, str]:
            """同步执行：重新解析最高画质源 + 流式下载（带重试）。"""
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

                    _iwara_throttle()
                    with _iwara_session.get(
                        download_link, stream=True, timeout=120,
                        headers={"Referer": "https://www.iwara.tv/"},
                    ) as resp:
                        resp.raise_for_status()
                        size = int(resp.headers.get("Content-Length") or 0)
                        live_manager.set_task_info(internal_task, final_name, size or None)
                        emit({
                            "event": "file_start",
                            "filename": final_name,
                            "index": 0,
                            "size": size or None,
                            "task_id": task_id,
                        })

                        downloaded = 0
                        last_pct = -1
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if task.get("status") in ("paused", "cancelled"):
                                    raise InterruptedError("任务已暂停/取消")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if size:
                                        pct = round(downloaded / size * 100, 1)
                                        if pct != last_pct:
                                            live_manager.update_task(internal_task, pct)
                                            last_pct = pct

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

        try:
            success, final_path = await asyncio.to_thread(_resolve_and_download)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return
        except Exception as exc:
            logging.exception("Iwara 下载出错: %s", exc)
            success, final_path = False, ""

        final_name = item.pop("_final_name", filename)
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

        # 目录：下载根目录/上传者名/YYYY-MM（与其他站点逻辑一致）
        def _hanime_file_dir() -> str:
            parts = []
            artist = sanitize_directory_name((item.get("artist") or "").strip())
            if artist:
                parts.append(artist)
            date = (item.get("post_date") or "")[:7]  # YYYY-MM
            if date:
                parts.append(date)
            sub = str(Path(*parts)) if parts else ""
            return str(Path(album_path) / sub) if sub else album_path

        def _resolve_and_download() -> tuple[bool, str]:
            """同步执行：重新解析最高画质直链 + 流式下载（带重试）。"""
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

                    _hanime_throttle()
                    with _hanime_session.get(
                        download_link, stream=True, timeout=120,
                        headers={"Referer": f"{HANIME_BASE}/"},
                    ) as resp:
                        resp.raise_for_status()
                        size = int(resp.headers.get("Content-Length") or 0)
                        live_manager.set_task_info(internal_task, final_name, size or None)
                        emit({
                            "event": "file_start",
                            "filename": final_name,
                            "index": 0,
                            "size": size or None,
                            "task_id": task_id,
                        })

                        downloaded = 0
                        last_pct = -1
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if task.get("status") in ("paused", "cancelled"):
                                    raise InterruptedError("任务已暂停/取消")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if size:
                                        pct = round(downloaded / size * 100, 1)
                                        if pct != last_pct:
                                            live_manager.update_task(internal_task, pct)
                                            last_pct = pct

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

        try:
            success, final_path = await asyncio.to_thread(_resolve_and_download)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return
        except Exception as exc:
            logging.exception("Hanime1 下载出错: %s", exc)
            success, final_path = False, ""

        final_name = item.pop("_final_name", filename)
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
            for attempt in range(max(1, max_retries)):
                try:
                    _asmr_throttle()
                    with _asmr_session.get(download_link, stream=True, timeout=120) as resp:
                        resp.raise_for_status()
                        size = int(resp.headers.get("Content-Length") or 0) or item.get("size")
                        live_manager.set_task_info(internal_task, final_name, size)
                        emit({"event": "file_start", "filename": final_name, "index": 0,
                              "size": size, "task_id": task_id})
                        downloaded = 0
                        last_pct = -1
                        final_path = Path(file_dir) / truncate_filename(final_name)
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if task.get("status") in ("paused", "cancelled"):
                                    raise InterruptedError("任务已暂停/取消")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if size:
                                        pct = round(downloaded / size * 100, 1)
                                        if pct != last_pct:
                                            live_manager.update_task(internal_task, pct)
                                            last_pct = pct
                        item["_final_path"] = str(final_path)
                        item["_final_name"] = final_name
                        item["size"] = size
                        return True, str(final_path)
                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning("ASMR 文件下载失败(第 %d 次) %s: %s", attempt + 1, final_name, exc)
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        try:
            success, final_path = await asyncio.to_thread(_resolve_and_download)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return
        except Exception as exc:
            logging.exception("ASMR 下载出错: %s", exc)
            success, final_path = False, ""

        skip_history = item.pop("_skip_history", False)
        final_name = item.pop("_final_name", final_name)
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
            for attempt in range(max(1, max_retries)):
                try:
                    _javdb_throttle()
                    with _javdb_session.get(
                        download_link, stream=True, timeout=60,
                        headers={"Referer": JAVDB_BASE + "/"},
                    ) as resp:
                        resp.raise_for_status()
                        size = int(resp.headers.get("Content-Length") or 0) or item.get("size")
                        live_manager.set_task_info(internal_task, final_name, size)
                        emit({"event": "file_start", "filename": final_name, "index": 0,
                              "size": size, "task_id": task_id})
                        downloaded = 0
                        last_pct = -1
                        final_path = Path(file_dir) / truncate_filename(final_name)
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=64 * 1024):
                                if task.get("status") in ("paused", "cancelled"):
                                    raise InterruptedError("任务已暂停/取消")
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if size:
                                        pct = round(downloaded / size * 100, 1)
                                        if pct != last_pct:
                                            live_manager.update_task(internal_task, pct)
                                            last_pct = pct
                        item["_final_path"] = str(final_path)
                        item["_final_name"] = final_name
                        item["size"] = size
                        return True, str(final_path)
                except InterruptedError:
                    raise
                except (requests.RequestException, PermissionError, OSError) as exc:
                    logging.warning("JavDB 图片下载失败(第 %d 次) %s: %s", attempt + 1, final_name, exc)
                    if attempt < max(1, max_retries) - 1:
                        time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            return False, ""

        try:
            success, final_path = await asyncio.to_thread(_resolve_and_download)
        except InterruptedError:
            item["status"] = "pending"
            self._save()
            self.emit_snapshot()
            return
        except Exception as exc:
            logging.exception("JavDB 图片下载出错: %s", exc)
            success, final_path = False, ""

        skip_history = item.pop("_skip_history", False)
        final_name = item.pop("_final_name", final_name)
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


# 全局下载管理器单例
download_manager = DownloadManager()


# ============================
# 历史任务记录
# ============================
HISTORY_FILE = "history.json"
HISTORY_MAX_ENTRIES = 500


def _load_history() -> list[dict]:
    """读取历史记录文件。"""
    try:
        with Path(HISTORY_FILE).open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_history(history: list[dict]) -> None:
    """保存历史记录文件。"""
    try:
        with Path(HISTORY_FILE).open("w", encoding="utf-8") as file:
            json.dump(history, file, ensure_ascii=False, indent=2)

    except OSError as exc:
        logging.warning("保存历史记录失败: %s", exc)


def _add_history_entry(entry: dict) -> None:
    """在历史记录头部插入一条新记录，并限制最大条数。"""
    history = _load_history()
    history.insert(0, entry)
    _save_history(history[:HISTORY_MAX_ENTRIES])


# ============================
# 用户设置持久化
# ============================
SETTINGS_FILE = "settings.json"

# ============================
# 识图（反向图片搜索，多站点并发；失效网站自动移除）
# ============================
_reverse_proxy = ""
# 模块级 settings 引用（main() 加载后 update 进来，供 lenso token 等读取）
_reverse_settings: dict = {}

# 内置识图网站（展示时显示网站来源；解析失败/无免费接口的站点自动从结果移除）
REVERSE_SITES = [
    {"key": "tracemoe", "name": "trace.moe"},
    {"key": "saucenao", "name": "SauceNAO"},
    {"key": "iqdb", "name": "IQDB"},
    {"key": "ascii2d", "name": "ascii2d"},
    {"key": "soutubot", "name": "搜图bot酱"},
    {"key": "google", "name": "Google"},
    {"key": "yandex", "name": "Yandex"},
    {"key": "lenso", "name": "Lenso.ai"},
    {"key": "whos", "name": "Whos.tv"},
]

_REVERSE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def reverse_set_proxy(proxy: str) -> None:
    global _reverse_proxy
    p = (proxy or "").strip()
    if p and not p.startswith("http"):
        p = "http://" + p
    _reverse_proxy = p
    emit({"event": "reverse_proxy_set", "proxy": p})


def _reverse_proxies() -> dict | None:
    return {"http": _reverse_proxy, "https": _reverse_proxy} if _reverse_proxy else None


def _reverse_post_file(url: str, field: str, path: str, extra_data: dict | None = None,
                       timeout: int = 40) -> requests.Response:
    """以 multipart 上传本地图片到识图网站。"""
    with open(path, "rb") as f:
        files = {field: (os.path.basename(path), f, "image/jpeg")}
        return requests.post(url, files=files, data=extra_data or {},
                             headers={"User-Agent": _REVERSE_UA},
                             proxies=_reverse_proxies(), timeout=timeout)


def _reverse_clean(text: str, limit: int = 80) -> str:
    return " ".join((text or "").split())[:limit]


def _reverse_tracemoe(path: str) -> dict:
    """trace.moe：番剧截图识别（免费 JSON API，返回动画/集数/时间点）。"""
    with open(path, "rb") as f:
        r = requests.post("https://api.trace.moe/search", files={"image": f}, timeout=40)
    r.raise_for_status()
    data = r.json() or {}
    items = []
    for it in (data.get("result") or [])[:8]:
        ani = it.get("anilist") or {}
        title = ani.get("title") or {}
        name = title.get("native") or title.get("romaji") or title.get("english") \
            or it.get("filename") or "未知作品"
        try:
            sub = f"第 {it.get('episode') or '?'} 集 · {int(it.get('from') or 0)}s ~ {int(it.get('to') or 0)}s"
        except Exception:
            sub = f"第 {it.get('episode') or '?'} 集"
        items.append({
            "title": _reverse_clean(name, 120),
            "subtitle": sub,
            "similarity": f"{(it.get('similarity') or 0) * 100:.1f}%",
            "url": f"https://anilist.co/anime/{ani['id']}" if ani.get("id") else "https://trace.moe/",
            "thumbnail": it.get("image") or "",
        })
    return {"results": items, "url": "https://trace.moe/"}


def _reverse_saucenao(path: str) -> dict:
    """SauceNAO：二次元插画/漫画来源（P站/推特等，无 key 走免费配额）。"""
    r = _reverse_post_file("https://saucenao.com/search.php", "file", path, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for block in soup.select(".result")[:8]:
        link, title = "", ""
        for a in block.select(".resulttitle a") or block.select("a"):
            href = a.get("href") or ""
            if href.startswith("http"):
                link = href
                title = _reverse_clean(a.get_text(), 120)
                break
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
        raise RuntimeError("未解析到结果（可能无匹配或被限流）")
    return {"results": items, "url": "https://saucenao.com/"}


def _reverse_iqdb(path: str) -> dict:
    """IQDB：二次元图库聚合搜索（danbooru/gelbooru 等，soutubot 同核心引擎）。"""
    r = _reverse_post_file("https://iqdb.org/", "file", path, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for tbl in soup.select("table.result")[:8]:
        a = tbl.select_one("a[href]")
        if not a:
            continue
        href = a.get("href") or ""
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = "https://iqdb.org" + href
        text = _reverse_clean(tbl.get_text(), 120)
        m = re.search(r"(\d+%) ?similar", text)
        img = tbl.select_one("img")
        thumb = (img.get("src") or "") if img else ""
        if thumb.startswith("/"):
            thumb = "https://iqdb.org" + thumb
        if href.startswith("http"):
            items.append({"title": _reverse_clean(a.get_text(), 100) or "匹配结果",
                          "subtitle": text, "similarity": m.group(1) if m else "",
                          "url": href, "thumbnail": thumb})
    if not items:
        raise RuntimeError("未解析到结果（可能无匹配）")
    return {"results": items, "url": "https://iqdb.org/"}


def _reverse_ascii2d(path: str) -> dict:
    """ascii2d：日系以图搜图（色合/特征检索，返回 P站/推特来源）。"""
    r = _reverse_post_file("https://ascii2d.net/search/by-image", "file", path, timeout=50)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for block in soup.select(".item")[:8]:
        links = [a for a in block.select(".detail a[href], a[href]")
                 if (a.get("href") or "").startswith("http")]
        if not links:
            continue
        a = links[0]
        img = block.select_one("img")
        thumb = (img.get("src") or "") if img else ""
        if thumb.startswith("/"):
            thumb = "https://ascii2d.net" + thumb
        author = _reverse_clean(links[1].get_text(), 60) if len(links) > 1 else ""
        items.append({"title": _reverse_clean(a.get_text(), 120) or "匹配结果",
                      "subtitle": author, "similarity": "",
                      "url": a.get("href"), "thumbnail": thumb})
    if not items:
        raise RuntimeError("未解析到结果")
    return {"results": items, "url": "https://ascii2d.net/"}


def _reverse_soutubot(path: str) -> dict:
    """搜图bot酱：本子/漫画出处（与 IQDB 同核心引擎，泛化解析卡片链接）。"""
    r = _reverse_post_file("https://soutubot.moe/query", "file", path, timeout=50)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items, seen = [], set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        text = _reverse_clean(a.get_text(), 80)
        if (not href.startswith("http") or href in seen or len(text) < 4
                or "soutubot.moe/static" in href):
            continue
        seen.add(href)
        items.append({"title": text, "subtitle": "", "similarity": "",
                      "url": href, "thumbnail": ""})
    if not items:
        raise RuntimeError("未解析到结果（站点改版或需等待）")
    return {"results": items[:8], "url": "https://soutubot.moe/"}


def _reverse_google(path: str) -> dict:
    """Google 以图搜图（上传端点 + 解析结果页；国内需代理）。"""
    with open(path, "rb") as f:
        r = requests.post("https://www.google.com/searchbyimage/upload",
                          files={"encoded_image": (os.path.basename(path), f, "image/jpeg")},
                          headers={"User-Agent": _REVERSE_UA},
                          proxies=_reverse_proxies(), timeout=40)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    # 最佳猜测（"Best guess for this image"）
    m = re.search(r"Best guess for this image[^<]*(?:<[^>]+>)*<a[^>]*>([^<]+)</a>", r.text)
    if m:
        items.append({"title": f"最佳猜测: {_reverse_clean(m.group(1), 100)}",
                      "subtitle": "", "similarity": "",
                      "url": r.url, "thumbnail": ""})
    for h3 in soup.select("h3")[:10]:
        a = h3.find_parent("a")
        if not a:
            continue
        href = a.get("href") or ""
        if href.startswith("/url"):
            q = re.search(r"[?&]q=([^&]+)", href)
            if q:
                from urllib.parse import unquote as _unquote
                href = _unquote(q.group(1))
        elif href.startswith("/"):
            href = "https://www.google.com" + href
        title = _reverse_clean(h3.get_text(), 120)
        if title and href.startswith("http"):
            items.append({"title": title, "subtitle": "", "similarity": "",
                          "url": href, "thumbnail": ""})
    if not items:
        raise RuntimeError("未解析到结果（可能被验证码拦截或需代理）")
    return {"results": items[:8], "url": r.url}


def _reverse_yandex(path: str) -> dict:
    """Yandex 以图搜图（上传后解析相似图片/包含该图的页面；国内需代理）。"""
    r = _reverse_post_file("https://yandex.com/images/search?rpt=imageview", "upfile", path,
                           extra_data={"original_image": ""}, timeout=50)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items, seen = [], set()
    for a in soup.select("a[href]"):
        cls = " ".join(a.get("class") or [])
        if ("CbirSites-ItemTitleLink" in cls or "SerpItem-Title" in cls
                or "Link ViewLink" in cls):
            href = a.get("href") or ""
            text = _reverse_clean(a.get_text(), 100)
            if href and text and href not in seen:
                seen.add(href)
                items.append({"title": text, "subtitle": "", "similarity": "",
                              "url": href, "thumbnail": ""})
    if not items:
        raise RuntimeError("未解析到结果（可能需代理或站点改版）")
    return {"results": items[:8], "url": r.url}


def _reverse_lenso(path: str) -> dict:
    """Lenso.ai：AI 反向图片搜索（官方 API 需付费订阅 token；留空则跳过该站）。"""
    import base64
    token = (_reverse_settings.get("reverse_lenso_token") or "").strip()
    if not token:
        raise RuntimeError("Lenso.ai 官方 API 需付费订阅；在设置中填写 Token 后启用")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    r = requests.post("https://api.lenso.ai/search",
                      json={"image": b64, "category": "similar", "page": 1},
                      headers={"Authorization": f"Bearer {token}",
                               "User-Agent": _REVERSE_UA},
                      proxies=_reverse_proxies(), timeout=40)
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


def _reverse_whos(path: str) -> dict:
    """Whos.tv：动漫角色识别（无公开免费 API，尝试上传端点；失败自动移除）。"""
    r = _reverse_post_file("https://whos.tv/api/search", "image", path, timeout=40)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError("接口不可用（站点改版或需登录）")
    rows = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
    items = []
    for it in rows[:8]:
        if not isinstance(it, dict):
            continue
        items.append({"title": _reverse_clean(str(it.get("name") or it.get("title") or ""), 100) or "角色",
                      "subtitle": _reverse_clean(str(it.get("anime") or it.get("source") or ""), 80),
                      "similarity": _reverse_clean(str(it.get("similarity") or ""), 20),
                      "url": it.get("url") or "", "thumbnail": it.get("image") or it.get("thumbnail") or ""})
    if not items:
        raise RuntimeError("未返回结果")
    return {"results": items, "url": "https://whos.tv/"}


_REVERSE_PARSERS = {
    "tracemoe": _reverse_tracemoe,
    "saucenao": _reverse_saucenao,
    "iqdb": _reverse_iqdb,
    "ascii2d": _reverse_ascii2d,
    "soutubot": _reverse_soutubot,
    "google": _reverse_google,
    "yandex": _reverse_yandex,
    "lenso": _reverse_lenso,
    "whos": _reverse_whos,
}


async def reverse_search(path: str) -> None:
    """识图入口：并发请求全部识图网站，逐站推送进度，全部返回后推送完成事件。"""
    path = (path or "").strip()
    if not path or not os.path.isfile(path):
        emit({"event": "reverse_error", "message": f"图片文件不存在: {path}"})
        return
    emit({"event": "reverse_start", "sites": REVERSE_SITES})
    ok_names: list[str] = []
    fail_names: list[str] = []

    async def _run(site: dict) -> None:
        key, name = site["key"], site["name"]
        try:
            data = await asyncio.to_thread(_REVERSE_PARSERS[key], path)
            ok_names.append(name)
            emit({"event": "reverse_site_update", "site": key, "name": name,
                  "status": "done", "results": data.get("results") or [],
                  "url": data.get("url") or ""})
        except Exception as exc:
            fail_names.append(name)
            emit({"event": "reverse_site_update", "site": key, "name": name,
                  "status": "failed", "error": str(exc)[:200], "results": []})

    await asyncio.gather(*[_run(s) for s in REVERSE_SITES])
    emit({"event": "reverse_all_done", "ok_sites": ok_names, "failed_sites": fail_names})


def _reverse_paste_path() -> str:
    return os.path.join("cache", "reverse_paste.txt")


def reverse_paste_get() -> None:
    """读取左侧识图粘贴板内容（cache/reverse_paste.txt）。"""
    text = ""
    try:
        with open(_reverse_paste_path(), "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        text = ""
    emit({"event": "reverse_paste", "text": text})


def reverse_paste_save(text: str) -> None:
    """保存识图粘贴板内容。"""
    try:
        with open(_reverse_paste_path(), "w", encoding="utf-8") as f:
            f.write(text or "")
        emit({"event": "reverse_paste_saved", "ok": True})
    except Exception as exc:
        emit({"event": "reverse_paste_saved", "ok": False, "error": str(exc)})


DEFAULT_SETTINGS = {
    "custom_path": "",
    "site": "bunkr",
    # 识图（反向图片搜索）设置：代理（Google/Yandex 国内必须）；Lenso.ai 需付费 API token
    "reverse_proxy": "",
    "reverse_lenso_token": "",
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
    "twitter_subfolder": "date_post",
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
    "connections": 4,
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
    "float_visible": True,
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
    # P3 设置功能：不息屏 / 快捷键 / 拟态模式
    "prevent_display_sleep": False,       # 不息屏开关（True=阻止系统休眠）
    "shortcut_toggle_prevent_sleep": "",  # 切换不息屏（Electron accelerator 格式，如 "Ctrl+Shift+S"）
    "shortcut_quick_minimize": "",        # 快速缩小到托盘（如 "Ctrl+Shift+M"）
    "shortcut_toggle_mimic": "",          # 切换拟态模式（如 "Ctrl+Shift+P"）
    "shortcut_toggle_float": "",         # 切换悬浮窗显示（如 "Ctrl+Shift+F"）
    "mimic_file_path": "",               # 拟态面板上传的文件路径（txt/word/pdf/图片等）
    "mimic_enabled": False,              # 拟态模式开关
    # GitHub 仓库更新检查代理（国内默认 http://127.0.0.1:10809）
    "github_proxy": "http://127.0.0.1:10809",
}


def _load_settings() -> dict:
    """读取用户设置，并与默认值合并。"""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with Path(SETTINGS_FILE).open("r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                settings.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return settings


def _save_settings(settings: dict) -> None:
    """保存用户设置到 settings.json。"""
    try:
        with Path(SETTINGS_FILE).open("w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("保存设置失败: %s", exc)


# ============================
# 翻译 API（免费方案优先：Google 翻译无 key 端点；可选 LibreTranslate 自建实例）
# ============================
YOUDAO_API = "https://openapi.youdao.com/api"
GOOGLE_TRANSLATE_URL = "https://translate.google.com/translate_a/single"


def _translate_proxy_attempts() -> list:
    """翻译请求的代理尝试列表：先走设置的代理，再尝试直连。

    国内网络访问 Google 翻译必须走代理；海外用户代理不通时自动回退直连。
    返回 [{http,https} 代理配置 or None, ...]，requests.get(proxies=...) 依次尝试。
    """
    s = _load_settings()
    proxy = (s.get("translate_proxy") or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    if proxy:
        return [{"http": proxy, "https": proxy}, None]
    return [None]


def _map_lang_code(lang: str) -> str:
    """统一语言代码：zh-CHS / zh-CHT → zh；其他原样返回。Google 用 zh 即可。"""
    if not lang or lang == "auto":
        return "auto"
    if lang.lower().startswith("zh"):
        return "zh-CN"
    return lang


def translate_free(text: str, from_lang: str = "auto", to_lang: str = "zh-CN") -> None:
    """免费翻译：默认走 Google 翻译无 key 端点（client=at 公开接口，自动检测源语言）。

    成功 emit 'translate_result' 事件，带 translation / detected_source / engine。
    失败时尝试 LibreTranslate 公开实例（如设置里填了 libretranslate_url）。
    所有路径失败 emit ok=False。
    """
    text = text or ""
    if not text.strip():
        emit({"event": "translate_result", "ok": False, "error": "请输入要翻译的文本"})
        return
    s = _load_settings()
    sl = _map_lang_code(from_lang)
    tl = _map_lang_code(to_lang)
    # 源=目标时改成英文，避免无意义请求
    if sl != "auto" and sl == tl:
        tl = "en" if sl == "zh-CN" else "zh-CN"

    # ---------- 1. Google 翻译免费端点（先代理后直连，自动回退） ----------
    last_err = ""
    for proxies in _translate_proxy_attempts():
        try:
            params = {
                "client": "at",
                "dt": "t",       # 返回翻译片段
                "dt": "bd",      # 返回备选词
                "sl": sl,
                "tl": tl,
                "q": text,
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }
            resp = requests.get(GOOGLE_TRANSLATE_URL, params=params, headers=headers,
                                proxies=proxies, timeout=15)
            data = resp.json()
            # 响应结构：[[["译文","原文",None,None,1],...], null, "检测到的源语言", ...]
            if isinstance(data, list) and data and isinstance(data[0], list):
                segments = data[0]
                translation = "".join(seg[0] for seg in segments if seg and seg[0])
                detected = data[2] if len(data) > 2 and data[2] else sl
                if translation:
                    emit({
                        "event": "translate_result",
                        "ok": True,
                        "translation": translation,
                        "query": text,
                        "detected_source": detected,
                        "engine": "google_free",
                    })
                    return
                last_err = "Google 翻译返回空结果"
                continue
            last_err = "Google 翻译返回格式异常，请稍后重试"
            continue
        except Exception as exc:
            last_err = f"Google 翻译失败：{exc}"
            # 该代理不通 → 尝试下一个（直连）
            continue

    # ---------- 2. LibreTranslate（用户自建/公开实例，可选）----------
    libre_url = (s.get("libretranslate_url") or "").strip()
    if libre_url:
        try:
            api_key = (s.get("libretranslate_api_key") or "").strip()
            payload = {
                "q": text,
                "source": "auto" if sl == "auto" else sl,
                "target": tl,
                "format": "text",
            }
            if api_key:
                payload["api_key"] = api_key
            resp = requests.post(
                libre_url.rstrip("/") + "/translate",
                json=payload,
                timeout=20,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
            translation = data.get("translatedText") or ""
            if translation:
                emit({
                    "event": "translate_result",
                    "ok": True,
                    "translation": translation,
                    "query": text,
                    "detected_source": data.get("detectedLanguage", {}).get("language", sl) if isinstance(data.get("detectedLanguage"), dict) else sl,
                    "engine": "libretranslate",
                })
                return
            emit({"event": "translate_result", "ok": False, "error": f"LibreTranslate 未返回结果：{data}"})
            return
        except Exception as exc2:
            last_err = f"{last_err}；LibreTranslate 也失败：{exc2}"

    emit({"event": "translate_result", "ok": False, "error": last_err})


def translate_batch(texts: list, from_lang: str = "auto", to_lang: str = "zh-CN", batch_id: str = "") -> None:
    """批量翻译（一次请求多个文本，复用 Google 免费端点 q 多值）。

    texts: 字符串列表（最多 50 条/批，超过自动分批）
    成功 emit 'translate_batch_result' 事件，带 translations 数组（与输入顺序一致）。
    """
    if not texts or not isinstance(texts, list):
        emit({"event": "translate_batch_result", "ok": False, "error": "未提供要翻译的文本",
              "batch_id": batch_id, "translations": []})
        return
    # 过滤空字符串（保留索引位置，空字符串原样返回）
    non_empty_idx = [i for i, t in enumerate(texts) if t and str(t).strip()]
    if not non_empty_idx:
        emit({"event": "translate_batch_result", "ok": True, "translations": list(texts),
              "batch_id": batch_id})
        return
    s = _load_settings()
    sl = _map_lang_code(from_lang)
    tl = _map_lang_code(to_lang)
    if sl != "auto" and sl == tl:
        tl = "en" if sl == "zh-CN" else "zh-CN"

    translations = list(texts)  # 原样回填，后续只覆盖非空位置
    # 分批处理（每批 30 条，避免 URL 过长）
    BATCH = 30
    batch_total = 0   # 总批数
    batch_failed = 0  # 失败批数
    last_err = ""
    for start in range(0, len(non_empty_idx), BATCH):
        chunk_idx = non_empty_idx[start:start + BATCH]
        chunk_texts = [str(texts[i]) for i in chunk_idx]
        batch_total += 1
        chunk_ok = False
        # 先代理后直连，自动回退（国内 Google 必须代理）
        for proxies in _translate_proxy_attempts():
            try:
                # Google 端点支持多个 q 参数（返回 data[0] 多段拼接）
                params = {"client": "at", "dt": "t", "sl": sl, "tl": tl}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                }
                # 用 GET 多 q 参数（requests 会自动重复 q）
                q_params = [("q", t) for t in chunk_texts]
                # 手动拼 URL（requests params dict 不支持重复 key）
                from urllib.parse import urlencode
                url = GOOGLE_TRANSLATE_URL + "?" + urlencode(params) + "&" + urlencode(q_params)
                resp = requests.get(url, headers=headers, proxies=proxies, timeout=20)
                data = resp.json()
                if isinstance(data, list) and data and isinstance(data[0], list):
                    # data[0] 是 [[译文, 原文, ...], ...] 列表，按顺序对应每个 q
                    got = 0
                    for i, seg in enumerate(data[0]):
                        if i < len(chunk_idx) and seg and seg[0]:
                            translations[chunk_idx[i]] = seg[0]
                            got += 1
                    if got > 0:
                        chunk_ok = True
                        break
                last_err = "Google 翻译返回格式异常"
            except Exception as exc:
                last_err = str(exc)
                continue
        if not chunk_ok:
            batch_failed += 1
            logging.warning("translate_batch 第 %d 批失败: %s", start, last_err)

    if batch_failed == batch_total and batch_total > 0:
        # 全部批次失败 → 明确报错（前端会弹提示，不再静默无效果）
        emit({"event": "translate_batch_result", "ok": False,
              "error": f"翻译失败：Google 端点不可达（{last_err}）。请在左侧翻译面板配置可用代理，或更换翻译引擎",
              "translations": [], "batch_id": batch_id})
        return

    emit({"event": "translate_batch_result", "ok": True,
          "translations": translations, "batch_id": batch_id,
          "detected_source": sl, "engine": "google_free"})


def translate_youdao(text: str, from_lang: str = "auto", to_lang: str = "zh") -> None:
    """调用有道智云翻译 API（需用户在设置里填 app_id/app_secret）。

    成功 emit 'translate_result' 事件。未配置 key / 网络失败 / 错误码 均回 ok=False。
    """
    text = text or ""
    if not text.strip():
        emit({"event": "translate_result", "ok": False, "error": "请输入要翻译的文本"})
        return
    s = _load_settings()
    app_id = (s.get("youdao_app_id") or "").strip()
    app_secret = (s.get("youdao_app_secret") or "").strip()
    if not app_id or not app_secret:
        emit({
            "event": "translate_result",
            "ok": False,
            "error": "未配置有道 API，请在下方填写应用 ID 和密钥后保存设置",
        })
        return
    import uuid
    salt = uuid.uuid4().hex
    curtime = str(int(time.time()))
    # 签名输入：文本 ≤10 全量；>10 取首3+长度+末3
    input_str = text if len(text) <= 10 else text[:3] + str(len(text)) + text[-3:]
    sign_str = app_id + input_str + salt + curtime + app_secret
    sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest()
    params = {
        "q": text,
        "from": from_lang,
        "to": to_lang,
        "appKey": app_id,
        "salt": salt,
        "sign": sign,
        "signType": "v3",
        "curtime": curtime,
    }
    try:
        resp = requests.post(YOUDAO_API, data=params, timeout=20)
        data = resp.json()
    except Exception as exc:
        emit({"event": "translate_result", "ok": False, "error": f"网络请求失败：{exc}"})
        return
    err = str(data.get("errorCode") or "")
    translation = data.get("translation") or []
    if err not in ("", "0") and not translation:
        emit({"event": "translate_result", "ok": False, "error": f"有道返回错误码 {err}"})
        return
    if not translation:
        emit({"event": "translate_result", "ok": False, "error": "未获得翻译结果"})
        return
    emit({
        "event": "translate_result",
        "ok": True,
        "translation": translation[0] if len(translation) == 1 else "；".join(translation),
        "query": data.get("query") or text,
        "raw": data,
    })


# ============================
# GitHub 仓库更新检查（secondashes/xiaoxiaodownloader）
# ============================
GITHUB_REPO = "secondashes/xiaoxiaodownloader"
GITHUB_LAST_SHA_FILE = "cache/github_last_sha.json"


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


def check_github_update() -> None:
    """检查 GitHub 仓库 secondashes/xiaoxiaodownloader 的 main 分支最新 commit。

    国内访问 api.github.com 需走代理（github_proxy 设置）。成功 emit 'github_update_info'。
    """
    s = _load_settings()
    proxy = (s.get("github_proxy") or "").strip()
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

    emit({
        "event": "github_update_info",
        "ok": True,
        "latest_sha": sha,
        "latest_message": message,
        "latest_date": date,
        "latest_author": author,
        "latest_url": html_url,
        "local_sha": local_sha,
        "has_update": has_update,
        "is_first_check": not local_sha,
        "release": {
            "tag": latest_release.get("tag_name") or "",
            "name": latest_release.get("name") or "",
            "url": latest_release.get("html_url") or "",
            "published_at": latest_release.get("published_at") or "",
            "body": (latest_release.get("body") or "")[:800],
        } if latest_release else None,
        "repo_url": f"https://github.com/{GITHUB_REPO}",
        "commits_url": f"https://github.com/{GITHUB_REPO}/commits/main",
    })


def github_mark_update_done(sha: str) -> None:
    """用户确认已更新（或拉取代码后），把当前 sha 记为本地 last_sha。"""
    _github_save_last_sha((sha or "").strip())
    emit({"event": "github_update_marked", "ok": True, "sha": sha})


# ============================
# 账号档案（多账号记录与切换）+ 登录状态指纹（失效原因判断）
# ============================
LOGIN_STATE_FILE = "cache/login_state.json"


def _load_accounts() -> dict:
    """读取账号档案：{站点: {"active": 档案名, "profiles": {档案名: {label, username, cookie_str, saved_at}}}}。

    存于加密账号存储（根目录伪装文件），长期保存。
    """
    return _secure_store_read_section("accounts")


def _save_accounts(accounts: dict) -> None:
    _secure_store_write_section("accounts", accounts)


def _site_cookie_str(site: str) -> str:
    """站点当前登录 cookie 字符串（展示/复制/档案共用）。"""
    if site == "twitter":
        return _twitter_cookie_str()
    if site == "exhentai":
        return _exhentai_cookie_str()
    if site == "pawchive":
        cookies = {c.name: c.value for c in _pawchive_session.cookies}
        return "; ".join(f"{k}={v}" for k, v in cookies.items())
    if site == "iwara":
        return _iwara_load_token().get("user_token") or ""
    if site == "hanime":
        cookies = _hanime_load_cred().get("cookies") or {}
        return "; ".join(f"{k}={v}" for k, v in cookies.items())
    if site == "asmr":
        return _asmr_load_cred().get("token") or ""
    if site in _GENERIC_OAUTH_SITES:
        return _generic_cookie_str(site)
    if site == "javdb":
        return _javdb_load_cred().get("cookie_str") or ""
    return ""


def _site_username(site: str) -> str:
    """站点当前登录的用户名（不联网，从缓存文件读）。"""
    if site == "twitter":
        return _twitter_load_cookies().get("screen_name") or ""
    if site == "exhentai":
        return _exhentai_load_cookies().get("ipb_member_id") or ""
    if site == "pawchive":
        return _pawchive_username or ""
    if site == "iwara":
        return _iwara_load_token().get("username") or ""
    if site == "hanime":
        return _hanime_username or (_hanime_load_cred().get("username") or "")
    if site == "asmr":
        return _asmr_username or (_asmr_load_cred().get("username") or "")
    if site in _GENERIC_OAUTH_SITES:
        return _generic_load_cookies(site).get("username") or ""
    if site == "javdb":
        return _javdb_username or (_javdb_load_cred().get("username") or "")
    return ""


# ============================
# JavDB（javdb.com，X 站类型：webview 登录抓 cookie + HTML 解析）
# ============================
# 登录：Electron webview（partition persist:javdb）打开 javdb 登录页，
#       用户输入邮箱密码（Cloudflare 人机验证在 webview 内完成），登录成功后抓 cookie；
#       "记住此装置"勾选后 cookie 约 7 天有效（机器七天登录），失效提示重新登录。
# 搜索：GET /search?q={关键词}&f=all（番号 / 标题 / 演员均可）
# 详情：GET /v/{id} → 标题 / 封面 / 标签 / 预览图 / 磁力链接
# 下载：封面 + 预览图直链下载；磁力链接一键复制（交给外部种子客户端）
JAVDB_BASE = "https://javdb.com"
JAVDB_LOGIN_URL = "https://javdb.com/zh/login"

_javdb_proxy = "http://127.0.0.1:10809"
_javdb_username = ""
_javdb_last_req = 0.0
_javdb_session = requests.Session()
_javdb_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})


def _javdb_load_cred() -> dict:
    """读取 JavDB 登录凭据（cookie + UA 加密存 theme_cache.dat）。"""
    return _secure_store_read_cred("javdb")


def _javdb_save_cred(data: dict) -> None:
    _secure_store_write_cred("javdb", dict(data))


def javdb_set_proxy(proxy: str) -> None:
    """设置 JavDB 代理（国内必须；空 = 直连）。"""
    global _javdb_proxy
    proxy = (proxy or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    _javdb_proxy = proxy
    _javdb_session.proxies = {"http": proxy, "https": proxy} if proxy else {}
    emit({"event": "javdb_proxy_set", "proxy": proxy})
    logging.info("JavDB 代理已设置: %s", proxy or "（直连）")


def _javdb_restore_session() -> None:
    """启动时从加密凭据恢复 cookie + UA（cf_clearance 绑定 UA，必须与登录时一致）。"""
    global _javdb_username
    cred = _javdb_load_cred()
    ua = cred.get("user_agent") or ""
    if ua:
        _javdb_session.headers["User-Agent"] = ua
    for name, value in (cred.get("cookies") or {}).items():
        try:
            _javdb_session.cookies.set(name, value, domain=".javdb.com")
        except Exception:
            pass
    # 年龄确认 + 界面语言 cookie（未登录也能用）
    _javdb_session.cookies.set("over18", "1", domain=".javdb.com")
    _javdb_session.cookies.set("locale", "zh", domain=".javdb.com")
    _javdb_username = cred.get("username") or ""


def javdb_set_cookies(cookie_str: str, user_agent: str = "", username: str = "") -> dict:
    """保存 webview 抓取的 cookie（+ 登录时的 UA，cf_clearance 校验用）。"""
    cookies = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        idx = pair.find("=")
        if idx <= 0:
            continue
        cookies[pair[:idx].strip()] = pair[idx + 1:].strip()
    cred = {"cookies": cookies, "cookie_str": cookie_str or "",
            "user_agent": user_agent or "", "username": username or "",
            "saved_at": time.time()}
    _javdb_save_cred(cred)
    _javdb_restore_session()
    # 立即验证登录态（推送 site_login_result）
    javdb_check_login()
    return {"ok": True, "count": len(cookies)}


def javdb_check_login(silent: bool = False) -> dict:
    """检查登录态：访问主页，页面有登出链接 = 已登录（cookie 有效期内免验证码）。

    cookie 过期（约 7 天"记住装置"期限）→ logged_in=False，提示重新在 webview 登录。
    """
    logged_in = False
    username = ""
    network_issue = False
    cred = _javdb_load_cred()
    if cred.get("cookies"):
        try:
            _javdb_throttle()
            resp = _javdb_session.get(f"{JAVDB_BASE}/zh/users/home", timeout=25,
                                      allow_redirects=False)
            if resp.status_code == 200:
                logged_in = "/logout" in resp.text or "current-user" in resp.text
            elif resp.status_code in (301, 302):
                # 重定向到登录页 = cookie 失效
                logged_in = False
            else:
                network_issue = resp.status_code in (403, 503, 530)
            if logged_in:
                username = cred.get("username") or ""
                global _javdb_username
                _javdb_username = username
        except Exception as exc:
            logging.warning("JavDB 登录态检查失败: %s", exc)
            network_issue = True
    result = {"logged_in": logged_in, "username": username,
              "network_issue": network_issue}
    if not silent:
        emit({"event": "site_login_result", "site": "javdb", **result})
    return result


def javdb_logout() -> None:
    """退出登录（清除本地凭据）。"""
    global _javdb_username
    _secure_store_clear_cred("javdb")
    _javdb_username = ""
    _javdb_session.cookies.clear()
    emit({"event": "site_login_result", "site": "javdb", "logged_in": False,
          "username": "", "logout": True})


def _javdb_throttle(min_interval: float = 1.0) -> None:
    """请求节流（javdb 有 Cloudflare，过快会触发验证）。"""
    global _javdb_last_req
    wait = _javdb_last_req + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _javdb_last_req = time.time()


def _javdb_soup(path: str, params: dict | None = None) -> "BeautifulSoup":
    """GET 页面并返回 BeautifulSoup；Cloudflare 拦截时给出中文提示。"""
    _javdb_throttle()
    resp = _javdb_session.get(f"{JAVDB_BASE}{path}", params=params, timeout=25)
    if resp.status_code == 404:
        raise FileNotFoundError("页面不存在（链接可能已失效）")
    if resp.status_code in (403, 503, 530):
        raise PermissionError(
            "触发 Cloudflare 拦截：请在左侧重新登录 JavDB（webview 内完成人机验证后自动抓取新 cookie）")
    if resp.status_code != 200:
        raise PermissionError(f"JavDB 返回 HTTP {resp.status_code}")
    return BeautifulSoup(resp.text, "html.parser")


def _javdb_img_src(img) -> str:
    """图片地址（懒加载 data-src 优先，其次 src）。"""
    if img is None:
        return ""
    return img.get("data-src") or img.get("src") or ""


def _javdb_abs(u: str) -> str:
    """相对 URL 转绝对。"""
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return JAVDB_BASE + u
    return u


def _javdb_parse_cards(soup: "BeautifulSoup") -> list[dict]:
    """解析搜索结果卡片（.movie-list .item）→ 统一卡片字段。"""
    items: list[dict] = []
    for it in soup.select(".movie-list .item"):
        a = it.find("a", href=True)
        if not a:
            continue
        href = _javdb_abs(a.get("href") or "")
        if "/v/" not in href:
            continue
        title_el = it.select_one(".video-title strong") or it.select_one(".video-title")
        title = title_el.get_text(strip=True) if title_el else ""
        # 番号（.meta 第一个 span 或 title 前缀）
        code = ""
        meta_spans = it.select(".meta span")
        if meta_spans:
            code = meta_spans[0].get_text(strip=True)
        if not code and title:
            m = re.match(r"^([A-Za-z]{2,6}-\d{2,5})", title)
            if m:
                code = m.group(1)
        # 评分 / 日期 / 标签
        score = (it.select_one(".score") or {}).get_text(strip=True) if it.select_one(".score") else ""
        date = ""
        for sp in meta_spans[1:]:
            if re.search(r"\d{4}-\d{2}-\d{2}", sp.get_text(strip=True)):
                date = sp.get_text(strip=True)
                break
        tags = [t.get_text(strip=True) for t in it.select(".tag")]
        cover = _javdb_img_src(it.select_one(".cover img") or it.find("img"))
        thumb = _javdb_abs(cover)
        # 标题去掉番号前缀展示
        display = title
        album_name = f"[{code}] {title}" if code and not title.startswith(code) else (title or code)
        items.append({
            "album_name": album_name or href.rsplit("/", 1)[-1],
            "album_url": href,
            "cover_url": thumb,
            "thumbnail": thumb,
            "code": code,
            "title": display,
            "score": score,
            "date": date,
            "tags": tags,
            "duration": (it.select_one(".duration") or {}).get_text(strip=True) if it.select_one(".duration") else "",
        })
    return items


async def javdb_search(query: str, page: int = 1) -> None:
    """JavDB 搜索（番号 / 标题 / 演员）。GET /search?q=...&f=all"""
    query = (query or "").strip()
    if not query:
        emit({"event": "search_error", "message": "搜索关键词为空"})
        return
    emit({"event": "search_start", "query": query, "page": page})
    try:
        page = max(1, page or 1)
        soup = await asyncio.to_thread(
            _javdb_soup, "/search", {"q": query, "f": "all", "page": page})
        items = _javdb_parse_cards(soup)
        _apply_cached_thumbnails(items)
        asyncio.create_task(_cache_thumbnails(items))
        # 分页（javdb 用 <a class="pagination-next"> / 最后一页链接判断）
        has_more = bool(soup.select_one("a.pagination-next:not(.is-disabled)"))
        emit({"event": "search_result", "query": query, "site": "javdb",
              "items": items, "page": page, "has_more": has_more,
              "total_pages": 0, "total_results": len(items)})
        logging.info("JavDB 搜索 '%s' 第 %d 页: %d 个结果", query, page, len(items))
    except Exception as exc:
        msg = str(exc)
        hint = ""
        if "Cloudflare" in msg:
            hint = "（请在左侧重新登录 JavDB 刷新 cookie）"
        elif "ProxyError" in msg or "timed out" in msg or "Connection" in msg:
            hint = "（请检查 JavDB 代理设置，国内必须代理）"
        emit({"event": "search_error", "message": f"JavDB 搜索失败: {msg}{hint}"})


def _javdb_parse_detail(soup: "BeautifulSoup", vid: str) -> dict:
    """解析视频详情页 /v/{id}：标题/封面/信息/标签/预览图/磁力。"""
    title_el = soup.select_one("h2.title.current-item") or soup.select_one("h2.title") or soup.select_one(".video-title")
    title = title_el.get_text(strip=True) if title_el else vid
    cover = _javdb_img_src(soup.select_one(".column-video-cover img") or soup.select_one(".cover img"))
    code = ""
    info: dict[str, str] = {}
    # 信息面板（识别码/日期/时长/导演/片商/系列…）
    for block in soup.select(".movie-panel-info .panel-block"):
        strong = block.find("strong")
        if not strong:
            continue
        key = strong.get_text(strip=True).rstrip("：:")
        value = block.get_text(" ", strip=True).replace(strong.get_text(strip=True), "", 1).strip()
        if key in ("識別碼", "识别码", "ID"):
            code = value
        elif key and value and key not in ("演員", "演员", "類別", "类别", "標籤", "标签"):
            info[key] = value
    # 标签 / 演员
    tags = [a.get_text(strip=True) for a in soup.select(".movie-panel-info a[href*='/tags/']")]
    actors = [a.get_text(strip=True) for a in soup.select(".movie-panel-info a[href*='/actors/']")]
    # 预览图（需登录才可见）
    previews = []
    for a in soup.select(".preview-images a.tile-item"):
        img = a.find("img")
        if img:
            previews.append(_javdb_abs(_javdb_img_src(img)))
    # 磁力链接（含名称/大小/日期/字幕标签）
    magnets = []
    for it in soup.select("#magnets .item"):
        a = it.select_one("a[href^='magnet:']")
        if not a:
            continue
        name_el = it.select_one(".magnet-name .name")
        meta_texts = [t.get_text(strip=True) for t in it.select(".magnet-name .meta")]
        size = ""
        date = ""
        for t in meta_texts:
            if re.search(r"^\d+(\.\d+)?\s*(GB|MB|KB|TB)$", t, re.I):
                size = t
            elif re.search(r"\d{4}-\d{2}-\d{2}", t):
                date = t
        magnet_tags = [t.get_text(strip=True) for t in it.select(".magnet-name .tags .tag")]
        magnets.append({
            "name": name_el.get_text(strip=True) if name_el else (a.get("href") or "")[:60],
            "link": a.get("href") or "",
            "size": size,
            "date": date,
            "tags": magnet_tags,
        })
    return {
        "video_id": vid,
        "title": title,
        "code": code,
        "cover": _javdb_abs(cover),
        "info": info,
        "tags": tags,
        "actors": actors,
        "previews": previews,
        "magnets": magnets,
        "url": f"{JAVDB_BASE}/v/{vid}",
    }


async def javdb_video_info(url: str) -> None:
    """视频详情页解析（标题/封面/标签/预览图/磁力列表）。"""
    m = re.search(r"javdb\.com/(?:zh/)?v/([0-9a-zA-Z]+)", url or "")
    if not m:
        emit({"event": "javdb_video_detail", "error": "无法识别的 JavDB 链接（支持 /v/{id}）"})
        return
    vid = m.group(1)
    emit({"event": "javdb_detail_loading", "loading": True})
    try:
        soup = await asyncio.to_thread(_javdb_soup, f"/v/{vid}", None)
        detail = _javdb_parse_detail(soup, vid)
        if not detail["magnets"] and not detail["previews"] and not detail["cover"]:
            emit({"event": "javdb_video_detail",
                  "error": "解析结果为空（可能未登录：预览图与部分磁力需登录后可见，请在左侧登录 JavDB）"})
            return
        emit({"event": "javdb_video_detail", "video": detail})
        logging.info("JavDB 详情解析完成: %s (%d 磁力 / %d 预览图)", vid, len(detail["magnets"]), len(detail["previews"]))
    except Exception as exc:
        msg = str(exc)
        hint = "（请重新登录 JavDB 刷新 cookie）" if "Cloudflare" in msg else "（请检查网络或代理设置）"
        emit({"event": "javdb_video_detail", "error": f"JavDB 解析失败: {msg}{hint}"})
    finally:
        emit({"event": "javdb_detail_loading", "loading": False})


async def javdb_download_images(url: str, options: dict) -> None:
    """下载封面 + 全部预览图（直链下载，磁力链接需外部种子客户端）。"""
    m = re.search(r"javdb\.com/(?:zh/)?v/([0-9a-zA-Z]+)", url or "")
    if not m:
        emit({"event": "inspect_error", "message": "无法识别的 JavDB 链接"})
        return
    vid = m.group(1)
    try:
        soup = await asyncio.to_thread(_javdb_soup, f"/v/{vid}", None)
        detail = _javdb_parse_detail(soup, vid)
        code = detail.get("code") or vid
        items: list[dict] = []
        if detail.get("cover"):
            items.append({
                "filename": "cover.jpg",
                "size": None,
                "item_page": detail["url"],
                "status": "ok",
                "thumbnail": "",
                "media_url": detail["cover"],
                "site": "javdb",
            })
        for i, pv in enumerate(detail.get("previews") or [], 1):
            items.append({
                "filename": f"preview_{i:02d}.jpg",
                "size": None,
                "item_page": detail["url"],
                "status": "ok",
                "thumbnail": "",
                "media_url": pv,
                "site": "javdb",
            })
        if not items:
            emit({"event": "inspect_error",
                  "message": "没有可下载的图片（预览图需登录后可见）"})
            return
        # 逐个直链下载（走通用下载管理器，带进度）
        task_id = download_manager.submit(
            detail["url"], items, options,
            f"JavDB {code}", f"javdb_{vid}",
        )
        download_manager.start(task_id)
        emit({"event": "inspect_complete",
              "album_name": f"JavDB {code}（{len(items)} 张图片，任务已提交）",
              "album_id": f"javdb_{vid}",
              "is_album": True,
              "items": items})
        logging.info("JavDB 图片下载已提交: %s (%d 张)", vid, len(items))
    except Exception as exc:
        emit({"event": "inspect_error", "message": f"JavDB 解析失败: {exc}"})


async def javdb_batch_download(urls: list, options: dict) -> None:
    """批量下载多个视频的封面+预览图（逐个解析，每个视频单独一个下载任务）。

    options["batch_parent_folder"] 非空时：任务文件夹 = 母文件夹名，
    每个视频按 <番号>/ 子文件夹归档（与 EX 批量下载归档规则一致）。
    """
    urls = [str(u).strip() for u in (urls or []) if str(u).strip()]
    total = len(urls)
    done = 0
    failed: list[str] = []
    parent = (options.get("batch_parent_folder") or "").strip()

    def _progress(done_: int, msg: str) -> None:
        emit({"event": "javdb_batch_progress", "done": done_, "total": total, "message": msg})

    if not total:
        _progress(0, "请先勾选要下载的视频")
        emit({"event": "javdb_batch_done", "done": 0, "total": 0, "failed": []})
        return

    try:
        for u in urls:
            m = re.search(r"javdb\.com/(?:zh/)?v/([0-9a-zA-Z]+)", u)
            if not m:
                failed.append(f"{u}（无法识别链接）")
                done += 1
                continue
            vid = m.group(1)
            _progress(done, f"正在解析 {vid} ...")
            try:
                soup = await asyncio.to_thread(_javdb_soup, f"/v/{vid}", None)
                detail = _javdb_parse_detail(soup, vid)
                code = detail.get("code") or vid
                items: list[dict] = []
                if detail.get("cover"):
                    items.append({
                        "filename": f"{code}/cover.jpg",
                        "size": None, "item_page": detail["url"], "status": "ok",
                        "thumbnail": "", "media_url": detail["cover"], "site": "javdb",
                    })
                for i, pv in enumerate(detail.get("previews") or [], 1):
                    items.append({
                        "filename": f"{code}/preview_{i:02d}.jpg",
                        "size": None, "item_page": detail["url"], "status": "ok",
                        "thumbnail": "", "media_url": pv, "site": "javdb",
                    })
                if not items:
                    failed.append(f"{code}（无图片，预览图需登录后可见）")
                else:
                    task_id = download_manager.submit(
                        detail["url"], items, options,
                        parent or f"JavDB {code}", f"javdb_{vid}",
                    )
                    download_manager.start(task_id)
                    logging.info("JavDB 批量下载：已提交 %s（%d 张图）", code, len(items))
            except Exception as exc:
                failed.append(f"{vid}（{exc}）")
                logging.exception("JavDB 批量下载解析失败: %s", vid)
            done += 1
            _progress(done, f"{done}/{total} 完成")

        summary = f"JavDB 批量下载已提交：{done}/{total}"
        if failed:
            summary += f"；失败：{'、'.join(failed)}"
        emit({"event": "javdb_batch_done", "done": done, "total": total,
              "failed": failed, "message": summary})
    except Exception as exc:
        emit({"event": "javdb_batch_done", "done": done, "total": total, "failed": failed,
              "message": f"批量下载中断: {exc}"})
        logging.exception("JavDB 批量下载出错")


def is_javdb_url(url: str) -> bool:
    """判断是否为 JavDB 链接（/v/{id} 详情页）。"""
    return bool(re.search(r"javdb\.com/(?:zh/)?v/[0-9a-zA-Z]+", url or "", re.I))


# 通用 webview OAuth 站点（xhamster/pornhub/xvideos）凭据存取（AP1 阶段）
# cookie 字符串存 theme_cache.dat 的 creds[site]，具体 check_login/搜索/解析待 AP2/AP3/AP4 填充
_GENERIC_OAUTH_SITES = ("xhamster", "pornhub", "xvideos")


def _generic_save_cookies(site: str, cookie_str: str) -> dict:
    """保存 webview 抓取的 cookie 字符串到加密凭据库。"""
    if site not in _GENERIC_OAUTH_SITES:
        return {"ok": False, "error": f"未知站点: {site}"}
    # 解析 cookie 字符串为 dict
    cookies = {}
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        idx = pair.find("=")
        if idx <= 0:
            continue
        cookies[pair[:idx].strip()] = pair[idx + 1:].strip()
    cred = {"cookies": cookies, "cookie_str": cookie_str, "saved_at": time.time()}
    _secure_store_write_cred(site, cred)
    return {"ok": True, "count": len(cookies)}


def _generic_load_cookies(site: str) -> dict:
    """读取站点 cookie 凭据。"""
    if site not in _GENERIC_OAUTH_SITES:
        return {}
    return _secure_store_read_cred(site)


def _generic_cookie_str(site: str) -> str:
    """读取站点 cookie 字符串。"""
    return _generic_load_cookies(site).get("cookie_str") or ""


def _generic_check_login(site: str, silent: bool = False) -> dict:
    """通用登录态检查（AP1 阶段占位：仅检查 cookie 是否存在；具体验证待 AP2/AP4 填充）。"""
    cred = _generic_load_cookies(site)
    cookies = cred.get("cookies") or {}
    has_auth = bool(cookies)
    username = cred.get("username") or ""  # AP2/AP4 时填充实际用户名提取
    if not silent:
        emit({
            "event": "site_login_result",
            "site": site,
            "logged_in": has_auth,
            "username": username,
            "cookie_count": len(cookies),
        })
    return {"logged_in": has_auth, "username": username, "cookie_count": len(cookies)}


def _generic_logout(site: str) -> None:
    """通用退出登录（清缓存凭据）。"""
    _secure_store_clear_cred(site)
    emit({
        "event": "site_login_result",
        "site": site,
        "logged_in": False,
        "username": "",
        "cookie_count": 0,
        "logout": True,
    })


def _emit_login_info() -> None:
    accounts = _load_accounts()
    pa_cookies = {c.name: c.value for c in _pawchive_session.cookies}
    tw = _twitter_load_cookies()
    ex = _exhentai_load_cookies()
    sites: dict = {}
    for site, logged_in, cookie_str in (
        ("twitter", bool(tw.get("auth_token")), _twitter_cookie_str()),
        ("exhentai", bool(ex.get("ipb_member_id")), _exhentai_cookie_str()),
        ("pawchive", bool(pa_cookies.get("session")), "; ".join(f"{k}={v}" for k, v in pa_cookies.items())),
        ("iwara", bool(_iwara_load_token().get("user_token")), _iwara_load_token().get("user_token") or ""),
        ("hanime", bool(_hanime_load_cred().get("cookies")), _site_cookie_str("hanime")),
        ("asmr", bool(_asmr_load_cred().get("token")), _site_cookie_str("asmr")),
        ("xhamster", bool(_generic_load_cookies("xhamster").get("cookies")), _generic_cookie_str("xhamster")),
        ("pornhub", bool(_generic_load_cookies("pornhub").get("cookies")), _generic_cookie_str("pornhub")),
        ("xvideos", bool(_generic_load_cookies("xvideos").get("cookies")), _generic_cookie_str("xvideos")),
        ("javdb", bool(_javdb_load_cred().get("cookies")), _javdb_load_cred().get("cookie_str") or ""),
    ):
        entry = accounts.get(site) or {}
        sites[site] = {
            "logged_in": logged_in,
            "username": _site_username(site),
            "cookie_str": cookie_str,
            "accounts": entry.get("profiles") or {},
            "active": entry.get("active") or "",
        }
    emit({"event": "login_info", "sites": sites})


def save_account(site: str, label: str = "") -> None:
    """把当前登录信息保存为账号档案（多账号记录，长期持久化）。"""
    cookie_str = _site_cookie_str(site)
    if not cookie_str:
        emit({"event": "account_error", "message": "当前站点没有可保存的登录信息"})
        return
    accounts = _load_accounts()
    entry = accounts.setdefault(site, {"active": "", "profiles": {}})
    profiles = entry.setdefault("profiles", {})
    name = (label or _site_username(site) or "").strip() or f"账号{len(profiles) + 1}"
    profile = {
        "label": name,
        "username": _site_username(site),
        "cookie_str": cookie_str,
        "saved_at": time.time(),
    }
    # Iwara：连密码一起存进档案（加密存储），切换账号后 token 过期也能自动续期
    if site == "iwara":
        iw_cred = _iwara_load_token()
        profile["password"] = iw_cred.get("password") or ""
        profile["email"] = iw_cred.get("email") or profile["username"]
    # Hanime1：连邮箱密码一起存进档案（加密存储），切换账号后会话失效也能自动重登
    if site == "hanime":
        ha_cred = _hanime_load_cred()
        profile["password"] = ha_cred.get("password") or ""
        profile["email"] = ha_cred.get("email") or profile["username"]
        profile["hanime_cred"] = {
            "email": ha_cred.get("email") or "",
            "password": ha_cred.get("password") or "",
            "username": ha_cred.get("username") or "",
            "user_id": ha_cred.get("user_id") or "",
            "cookies": ha_cred.get("cookies") or {},
        }
    # ASMR：token + 用户名密码一起存进档案（加密存储），切换后失效也能自动重登
    if site == "asmr":
        as_cred = _asmr_load_cred()
        profile["password"] = as_cred.get("password") or ""
        profile["username"] = as_cred.get("username") or profile["username"]
        profile["asmr_cred"] = dict(as_cred)
    profiles[name] = profile
    entry["active"] = name
    _save_accounts(accounts)
    emit({"event": "account_saved", "message": f"已保存账号档案: {name}"})
    logging.info("已保存 %s 账号档案: %s", site, name)
    _emit_login_info()


def _writeback_iwara_profile(site: str, label: str) -> None:
    """把当前 Iwara 凭据（密码/用户名/邮箱）回写进账号档案（旧档案自动补全密码）。"""
    if site != "iwara" or not label:
        return
    try:
        accounts = _load_accounts()
        profile = (accounts.get("iwara") or {}).get("profiles", {}).get(label)
        cred = _iwara_load_token()
        if profile and cred.get("password"):
            profile.setdefault("password", "")
            if not profile.get("password"):
                profile["password"] = cred.get("password")
            if not profile.get("email") and cred.get("email"):
                profile["email"] = cred.get("email")
            if not profile.get("username") and cred.get("username"):
                profile["username"] = cred.get("username")
            _save_accounts(accounts)
    except Exception:
        pass


def switch_account(site: str, label: str) -> None:
    """切换到已保存的账号档案（写入站点登录文件并重新验证登录）。"""
    accounts = _load_accounts()
    profiles = (accounts.get(site) or {}).get("profiles") or {}
    profile = profiles.get(label)
    if not profile:
        emit({"event": "account_error", "message": f"账号档案不存在: {label}"})
        return
    cookie_str = profile.get("cookie_str") or ""
    accounts.setdefault(site, {})["active"] = label
    _save_accounts(accounts)
    if site == "twitter":
        twitter_set_cookies(cookie_str)
    elif site == "exhentai":
        exhentai_set_cookies(cookie_str)
    elif site == "pawchive":
        pawchive_set_cookies(cookie_str, profile.get("username") or label)
    elif site == "iwara":
        # 旧档案可能没存密码/邮箱：保留现存的密码，避免覆盖成空导致自动续期失效
        old_cred = _iwara_load_token()
        _iwara_save_token({
            "user_token": cookie_str,
            "email": profile.get("email") or old_cred.get("email") or profile.get("username") or label,
            "username": profile.get("username") or label,
            "password": profile.get("password") or old_cred.get("password") or "",
        })
        _emit_login_info()
        emit({"event": "iwara_login_result", "success": True, "silent": True,
              "username": profile.get("username") or label, "message": "账号档案已恢复"})
        # 档案恢复后验证登录（token 过期时用档案里的密码自动续期），
        # 验证成功后把密码/用户名回写进档案，旧档案从此也自带密码
        iwara_check_login(silent=True)
        _writeback_iwara_profile(site, label)
    elif site == "hanime":
        # 恢复完整凭据（cookies + 邮箱密码），会话失效时自动重登
        global _hanime_username
        cred = dict(profile.get("hanime_cred") or {})
        cred.setdefault("cookies", {})
        if not cred.get("cookies") and cookie_str:
            # 旧档案只有 cookie 字符串：解析回字典
            cred["cookies"] = {
                p.split("=", 1)[0]: p.split("=", 1)[1]
                for p in cookie_str.split("; ") if "=" in p
            }
        if not cred.get("password") and profile.get("password"):
            cred["password"] = profile.get("password")
        if not cred.get("email") and profile.get("email"):
            cred["email"] = profile.get("email")
        cred["username"] = profile.get("username") or cred.get("username") or label
        _hanime_save_cred(cred)
        _hanime_session.cookies.clear()
        _hanime_restore_session()
        _hanime_username = cred.get("username") or ""
        _emit_login_info()
        emit({"event": "hanime_login_result", "success": True, "silent": True,
              "username": cred.get("username") or label, "message": "账号档案已恢复"})
        hanime_check_login(silent=True)
    elif site == "asmr":
        # 恢复完整凭据（token + 用户名密码），token 过期时自动重登
        global _asmr_token, _asmr_username
        cred = dict(profile.get("asmr_cred") or {})
        if not cred.get("token") and cookie_str:
            cred["token"] = cookie_str
        if not cred.get("password") and profile.get("password"):
            cred["password"] = profile.get("password")
        if not cred.get("username"):
            cred["username"] = profile.get("username") or label
        _asmr_save_cred(cred)
        _asmr_token = cred.get("token") or ""
        _asmr_username = cred.get("username") or ""
        _emit_login_info()
        emit({"event": "asmr_login_result", "success": True, "silent": True,
              "username": _asmr_username, "message": "账号档案已恢复"})
        asmr_check_login(silent=True)
    else:
        _emit_login_info()
        return
    logging.info("已切换 %s 账号: %s", site, label)


def delete_account(site: str, label: str) -> None:
    """删除账号档案（不影响当前登录状态）。"""
    accounts = _load_accounts()
    entry = accounts.get(site)
    if entry and (entry.get("profiles") or {}).pop(label, None) is not None:
        if entry.get("active") == label:
            entry["active"] = ""
        _save_accounts(accounts)
        emit({"event": "account_saved", "message": f"已删除账号档案: {label}"})
        logging.info("已删除 %s 账号档案: %s", site, label)
    _emit_login_info()


def _load_login_state() -> dict:
    try:
        data = json.loads(Path(LOGIN_STATE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_login_state(state: dict) -> None:
    try:
        Path("cache").mkdir(parents=True, exist_ok=True)
        Path(LOGIN_STATE_FILE).write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError:
        pass


def _cookie_fingerprint(site: str) -> str:
    cookie_str = _site_cookie_str(site)
    return hashlib.md5(cookie_str.encode("utf-8")).hexdigest() if cookie_str else ""


def _record_login_ok(site: str) -> None:
    """登录验证成功时记录当前 cookie 指纹（用于失效原因判断）。"""
    state = _load_login_state()
    state[site] = {"ok_hash": _cookie_fingerprint(site), "ok_at": time.time()}
    _save_login_state(state)


def _login_network_issue(site: str) -> bool:
    """登录检查失败时判断是否为网络问题：

    当前 cookie 与上次成功登录时一致 → 网络问题（登录信息没变，只是连不上）；
    不一致 → 登录信息已被更换/失效，提示用户重新检查 Cookie。
    """
    state = _load_login_state()
    ok_hash = (state.get(site) or {}).get("ok_hash") or ""
    if not ok_hash:
        return False
    return _cookie_fingerprint(site) == ok_hash


# ============================
# 主循环：读取命令并执行
# ============================
async def command_loop() -> None:
    """从 stdin 读取 NDJSON 命令并执行。"""
    # 恢复已保存的 Pawchive 登录会话，并通知前端当前登录状态
    _pawchive_load_session()
    emit({"event": "ready"})
    # 启动本地媒体代理（在线播放：图片/视频经本地流式转发，带站点 cookie/代理/Range）
    try:
        await start_media_proxy()
    except Exception as exc:
        logging.warning("媒体代理启动失败（在线播放不可用）: %s", exc)
    if _pawchive_username:
        emit({
            "event": "pawchive_login_result",
            "success": True,
            "silent": True,
            "username": _pawchive_username,
            "message": "已恢复登录",
        })
    # 恢复 ExHentai 代理设置（有已保存 cookie 时同时检查登录状态）
    _settings = _load_settings()
    if _settings.get("exhentai_proxy"):
        exhentai_set_proxy(_settings["exhentai_proxy"])
    if _exhentai_load_cookies().get("ipb_member_id"):
        ok, username, msg = await asyncio.to_thread(_exhentai_check_login)
        if ok:
            _record_login_ok("exhentai")
        emit({
            "event": "exhentai_login_result",
            "success": ok,
            "silent": True,
            "username": username or "",
            "message": msg,
            "network_issue": (not ok) and _login_network_issue("exhentai"),
        })
    # 恢复 Twitter 代理设置（有已保存 cookie 时同时检查登录状态）
    if _settings.get("twitter_proxy"):
        twitter_set_proxy(_settings["twitter_proxy"])
    if _twitter_load_cookies().get("auth_token"):
        ok, username, msg = await asyncio.to_thread(_twitter_check_login)
        if ok:
            _record_login_ok("twitter")
            # 持久化账号名（账号卡片展示用）
            if username:
                saved = _twitter_load_cookies()
                if saved.get("screen_name") != username:
                    saved["screen_name"] = username
                    _twitter_save_cookies(saved)
        emit({
            "event": "twitter_login_result",
            "success": ok,
            "silent": True,
            "username": username or "",
            "message": msg,
            "network_issue": (not ok) and _login_network_issue("twitter"),
        })
    # 恢复 Iwara 代理设置并静默检查登录状态
    if _settings.get("iwara_proxy"):
        iwara_set_proxy(_settings["iwara_proxy"])
    if _iwara_load_token().get("user_token"):
        await asyncio.to_thread(iwara_check_login, True)
    # 恢复 Hanime1 / Oreno3D / EroMMDTube 代理设置（Hanime1 有已保存会话时同时静默检查登录）
    hanime_set_proxy(_settings.get("hanime_proxy") or HANIME_DEFAULT_PROXY)
    oreno_set_proxy(_settings.get("oreno_proxy") or "")
    oreno_set_proxy(_settings.get("erommd_proxy") or "", "erommdtube")
    # 恢复 ASMR 代理设置并静默检查登录（token 失效自动用保存的密码重登）
    asmr_set_proxy(_settings.get("asmr_proxy") or "")
    if _asmr_load_cred().get("token"):
        await asyncio.to_thread(asmr_check_login, True)
    # 恢复识图（反向图片搜索）代理设置 + 粘贴板内容推送
    _reverse_settings.update(_settings)
    reverse_set_proxy(_settings.get("reverse_proxy") or "")
    reverse_paste_get()
    _hanime_restore_session()
    if _hanime_load_cred().get("cookies"):
        await asyncio.to_thread(hanime_check_login, True)
    # 恢复 JavDB 代理设置 + 会话（cookie 约 7 天有效，过期提示重新 webview 登录）
    javdb_set_proxy(_settings.get("javdb_proxy") or "http://127.0.0.1:10809")
    _javdb_restore_session()
    if _javdb_load_cred().get("cookies"):
        await asyncio.to_thread(javdb_check_login, True)
    # 推送全部站点登录信息（账号卡片数据源，切换站点不丢失）
    _emit_login_info()
    logging.info("GUI 桥接模块就绪，等待命令...")

    loop = asyncio.get_event_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                # stdin 关闭
                logging.info("stdin 已关闭，退出")
                break

            line = line.strip()
            if not line:
                continue

            try:
                command = json.loads(line)
            except json.JSONDecodeError as exc:
                logging.warning("无效的 JSON 命令: %s (%s)", line, exc)
                continue

            cmd = command.get("cmd")
            logging.info("收到命令: %s", cmd)

            if cmd == "inspect":
                url = command.get("url", "")
                options = command.get("options", {})
                await gui_inspect(url, options)

            elif cmd == "search":
                query = command.get("query", "")
                page = command.get("page", 1)
                per_page = command.get("per_page", 20)
                options = command.get("options", {})
                await gui_search(query, page, per_page, options)

            elif cmd == "download":
                url = command.get("url", "")
                items = command.get("items", [])
                options = command.get("options", {})
                album_name = command.get("album_name", "")
                album_id = command.get("album_id")
                task_id = download_manager.submit(url, items, options, album_name, album_id)
                download_manager.start(task_id)
                logging.info("已创建下载任务: %s (%d 个文件)", task_id, len(items))

            elif cmd == "resolve_media_url":
                # 在线播放：解析条目直链（Bunkr/EX 懒解析；其他站点条目已带 media_url）
                await resolve_media_url(command.get("item") or {})
            elif cmd == "get_tasks":
                download_manager.emit_snapshot(immediate=True)

            elif cmd == "pause_task":
                download_manager.pause(command.get("task_id", ""))

            elif cmd == "resume_task":
                download_manager.resume(command.get("task_id", ""))

            elif cmd == "cancel_task":
                download_manager.cancel(command.get("task_id", ""))

            elif cmd == "remove_task":
                download_manager.remove(command.get("task_id", ""))

            elif cmd == "shutdown_after_done":
                download_manager.set_shutdown_after_done(bool(command.get("enabled", True)))

            elif cmd == "get_settings":
                emit({"event": "settings", "settings": _load_settings()})

            elif cmd == "save_settings":
                _save_settings(command.get("settings", {}))
                _reverse_settings.update(command.get("settings", {}))

            elif cmd == "get_history":
                emit({"event": "history", "items": _load_history()})

            elif cmd == "delete_history":
                record_id = command.get("id", "")
                delete_file = command.get("delete_file", False)
                history = _load_history()

                for entry in history:
                    if entry.get("id") == record_id:
                        # 可选：同时删除磁盘上的文件
                        if delete_file and entry.get("path"):
                            try:
                                Path(entry["path"]).unlink(missing_ok=True)
                                logging.info("已删除文件: %s", entry["path"])
                            except OSError as exc:
                                logging.warning("删除文件失败: %s", exc)
                        history.remove(entry)
                        break

                _save_history(history)
                emit({"event": "history", "items": history})

            elif cmd == "clear_cache":
                result = clear_all_cache()
                emit({
                    "event": "cache_cleared",
                    "cleared": result["cleared"],
                    "cache_dir": result["cache_dir"],
                })
                logging.info("缓存已清除: %s", result["cache_dir"])

            elif cmd == "pawchive_login":
                await pawchive_login(
                    command.get("username", ""),
                    command.get("password", ""),
                )

            elif cmd == "pawchive_logout":
                pawchive_logout()

            elif cmd == "pawchive_set_cookies":
                pawchive_set_cookies(command.get("cookies", ""), command.get("username", ""))

            elif cmd == "pawchive_check_login":
                ok, username, msg = await asyncio.to_thread(_pawchive_check_login)
                if ok:
                    _record_login_ok("pawchive")
                emit({
                    "event": "pawchive_login_result",
                    "success": ok,
                    "username": username or "",
                    "message": msg,
                    "silent": not command.get("notify", False),
                    "network_issue": (not ok) and _login_network_issue("pawchive"),
                })
                _emit_login_info()

            elif cmd == "pawchive_favorites":
                await pawchive_get_favorites()

            elif cmd == "pawchive_post_info":
                await pawchive_post_info(command.get("url", ""))

            elif cmd == "pawchive_artist_posts":
                await pawchive_artist_posts(command.get("url", ""))

            elif cmd == "exhentai_get_hidden_tags":
                exhentai_get_hidden_tags()

            elif cmd == "exhentai_add_hidden_tag":
                exhentai_add_hidden_tag(command.get("tag", ""))

            elif cmd == "exhentai_delete_hidden_tag":
                exhentai_delete_hidden_tag(command.get("tag", ""))

            elif cmd == "get_login_info":
                _emit_login_info()

            elif cmd == "save_account":
                save_account(command.get("site", ""), command.get("label", ""))

            elif cmd == "switch_account":
                switch_account(command.get("site", ""), command.get("label", ""))

            elif cmd == "delete_account":
                delete_account(command.get("site", ""), command.get("label", ""))

            elif cmd == "exhentai_set_cookies":
                exhentai_set_cookies(command.get("cookies", ""))

            elif cmd == "exhentai_clear_cookies":
                exhentai_clear_cookies()

            elif cmd == "exhentai_check_login":
                ok, username, msg = await asyncio.to_thread(_exhentai_check_login)
                if ok:
                    _record_login_ok("exhentai")
                emit({
                    "event": "exhentai_login_result",
                    "success": ok,
                    "username": username or "",
                    "silent": not command.get("notify", False),
                    "message": msg,
                    "network_issue": (not ok) and _login_network_issue("exhentai"),
                })
                _emit_login_info()

            elif cmd == "exhentai_set_proxy":
                exhentai_set_proxy(command.get("proxy", ""))

            elif cmd == "twitter_set_cookies":
                twitter_set_cookies(command.get("cookies", ""))

            elif cmd == "twitter_clear_cookies":
                twitter_clear_cookies()

            elif cmd == "twitter_check_login":
                ok, username, msg = await asyncio.to_thread(_twitter_check_login)
                if ok:
                    _record_login_ok("twitter")
                    # 更新缓存的账号名（首次恢复时 screen_name 可能还没记录）
                    if username:
                        saved = _twitter_load_cookies()
                        if saved.get("screen_name") != username:
                            saved["screen_name"] = username
                            _twitter_save_cookies(saved)
                emit({
                    "event": "twitter_login_result",
                    "success": ok,
                    "username": username or "",
                    "message": msg,
                    "silent": not command.get("notify", False),
                    "network_issue": (not ok) and _login_network_issue("twitter"),
                })
                _emit_login_info()

            elif cmd == "twitter_set_proxy":
                twitter_set_proxy(command.get("proxy", ""))

            # ---------- X 关注列表 / 关注管理 / 关注分类 ----------
            elif cmd == "twitter_following":
                await twitter_follow_list(
                    "following", command.get("cursor", ""),
                    command.get("screen_name", ""),
                )

            elif cmd == "twitter_followers":
                await twitter_follow_list(
                    "followers", command.get("cursor", ""),
                    command.get("screen_name", ""),
                )

            elif cmd == "twitter_browse":
                await twitter_browse(int(command.get("offset") or 0))

            elif cmd == "twitter_clear_cache":
                twitter_clear_cache()

            elif cmd == "twitter_follow":
                await twitter_follow(
                    str(command.get("user_id", "")), command.get("screen_name", ""),
                )

            elif cmd == "twitter_unfollow":
                await twitter_unfollow(
                    str(command.get("user_id", "")), command.get("screen_name", ""),
                )

            elif cmd == "twitter_get_follow_tags":
                _emit_twitter_follow_tags()

            elif cmd == "twitter_add_follow_tag":
                _twitter_add_follow_tag(
                    command.get("parent", ""), command.get("child", ""),
                )

            elif cmd == "twitter_delete_follow_tag":
                _twitter_delete_follow_tag(
                    command.get("parent", ""), command.get("child", ""),
                )

            elif cmd == "twitter_get_follows":
                _emit_twitter_follows()

            elif cmd == "twitter_set_follow_tag":
                _twitter_set_follow_tag(
                    command.get("user", {}) or {},
                    command.get("parent", ""),
                    command.get("child", ""),
                )

            elif cmd == "exhentai_get_torrents":
                await exhentai_get_torrents(command.get("url", ""))

            elif cmd == "exhentai_get_magnet":
                await exhentai_get_magnet(command.get("torrent_url", ""))

            elif cmd == "exhentai_favorites":
                await exhentai_favorites(int(command.get("page", 1) or 1))

            elif cmd == "exhentai_gallery_info":
                await exhentai_gallery_info(command.get("url", ""))

            elif cmd == "exhentai_save_torrent":
                await exhentai_save_torrent(command.get("torrent_url", ""), command.get("name", ""))

            elif cmd == "exhentai_gallery_page":
                await exhentai_gallery_page(
                    command.get("url", ""), int(command.get("page", 0) or 0),
                )

            elif cmd == "exhentai_reload_image":
                await exhentai_reload_image(command.get("item_page", ""))

            # ---------- Iwara 站点 ----------
            elif cmd == "iwara_login":
                await asyncio.to_thread(
                    iwara_login, command.get("email", ""), command.get("password", ""),
                )

            elif cmd == "iwara_logout":
                iwara_logout()

            elif cmd == "iwara_check_login":
                await asyncio.to_thread(iwara_check_login)

            elif cmd == "iwara_set_proxy":
                iwara_set_proxy(command.get("proxy", ""))

            elif cmd == "iwara_set_site":
                iwara_set_site(command.get("site", "iwara"))

            elif cmd == "iwara_home":
                await iwara_home(int(command.get("page", 1)), command.get("mode", ""))

            elif cmd == "iwara_following":
                await iwara_following_list(int(command.get("page", 1)))

            elif cmd == "iwara_friends":
                await iwara_friend_list(int(command.get("page", 1)))

            elif cmd == "iwara_follow":
                await asyncio.to_thread(
                    iwara_follow, command.get("user_id", ""),
                    bool(command.get("follow", True)),
                )

            elif cmd == "iwara_video_detail":
                await iwara_video_detail(command.get("video_id", ""))

            elif cmd == "iwara_video_comments":
                await iwara_video_comments(
                    command.get("video_id", ""), int(command.get("page", 1)))

            elif cmd == "iwara_batch_download":
                await iwara_batch_download(
                    command.get("usernames") or [],
                    command.get("video_ids") or [],
                    command.get("options") or {},
                )

            # ---------- Hanime1 站点 ----------
            elif cmd == "hanime_login":
                await asyncio.to_thread(
                    hanime_login, command.get("email", ""), command.get("password", ""),
                )

            elif cmd == "hanime_logout":
                await asyncio.to_thread(hanime_logout)

            elif cmd == "hanime_check_login":
                await asyncio.to_thread(hanime_check_login)

            elif cmd == "hanime_set_proxy":
                hanime_set_proxy(command.get("proxy", ""))

            elif cmd == "hanime_home":
                await hanime_home()

            elif cmd == "hanime_search":
                await hanime_search(
                    command.get("query", ""),
                    int(command.get("page", 1) or 1),
                    command.get("genre", ""),
                    command.get("sort", ""),
                    command.get("tags") or [],
                )

            elif cmd == "hanime_video_detail":
                await hanime_video_detail(command.get("video_id", ""))

            elif cmd == "hanime_comments":
                await hanime_comments(command.get("video_id", ""))

            elif cmd == "hanime_add_comment":
                await asyncio.to_thread(
                    hanime_add_comment,
                    command.get("video_id", ""), command.get("text", ""),
                )

            elif cmd == "hanime_save_video":
                await asyncio.to_thread(
                    hanime_save_video,
                    command.get("video_id", ""), bool(command.get("saved", True)),
                )

            elif cmd == "hanime_user_videos":
                await hanime_user_videos(
                    command.get("tab", "saves"), int(command.get("page", 1) or 1))

            elif cmd == "hanime_batch_download":
                await hanime_batch_download(
                    command.get("video_ids") or [], command.get("options") or {})

            # ---------- Oreno3D / EroMMDTube 站点 ----------
            elif cmd == "oreno_set_proxy":
                oreno_set_proxy(command.get("proxy", ""), command.get("site_key", "oreno3d"))

            elif cmd == "oreno_home":
                await oreno_home(
                    int(command.get("page", 1) or 1), command.get("sort", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_search":
                await oreno_search(
                    command.get("query", ""),
                    int(command.get("page", 1) or 1), command.get("sort", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_tag":
                await oreno_tag(
                    command.get("tag_id", ""),
                    int(command.get("page", 1) or 1), command.get("sort", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_author":
                await oreno_author(
                    command.get("author_id", ""),
                    int(command.get("page", 1) or 1), command.get("sort", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_character":
                await oreno_character(
                    command.get("character_id", ""),
                    int(command.get("page", 1) or 1), command.get("sort", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_origin":
                await oreno_origin(
                    command.get("origin_id", ""),
                    int(command.get("page", 1) or 1), command.get("sort", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_tags_index":
                await oreno_tags_index(command.get("site_key", "oreno3d"))

            elif cmd == "oreno_tag_group":
                await oreno_tag_group(
                    command.get("group_id", ""), command.get("site_key", "oreno3d"))

            elif cmd == "oreno_characters":
                await oreno_characters(command.get("site_key", "oreno3d"))

            elif cmd == "oreno_authors_index":
                await oreno_authors_index(
                    int(command.get("page", 1) or 1),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_favorites":
                await oreno_favorites(command.get("site_key", "oreno3d"))

            elif cmd == "oreno_toggle_favorite":
                await oreno_toggle_favorite(
                    command.get("movie_id", ""), command.get("card") or {},
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_detail":
                await oreno_detail(
                    command.get("movie_id", ""),
                    command.get("site_key", "oreno3d"))

            elif cmd == "oreno_batch_download":
                await oreno_batch_download(
                    command.get("video_ids") or [], command.get("options") or {},
                    command.get("site_key", "oreno3d"))

            # ---------- ASMR 音声站（asmr-100.com） ----------
            elif cmd == "asmr_set_proxy":
                asmr_set_proxy(command.get("proxy", ""))

            elif cmd == "reverse_set_proxy":
                reverse_set_proxy(command.get("proxy", ""))
            elif cmd == "reverse_search":
                await reverse_search(command.get("path", ""))
            elif cmd == "reverse_paste_get":
                reverse_paste_get()
            elif cmd == "reverse_paste_save":
                reverse_paste_save(command.get("text", ""))

            elif cmd == "asmr_login":
                await asyncio.to_thread(
                    asmr_login, command.get("username", ""), command.get("password", ""))

            elif cmd == "asmr_logout":
                asmr_logout()

            elif cmd == "asmr_check_login":
                await asyncio.to_thread(asmr_check_login, bool(command.get("silent")))

            elif cmd == "asmr_popular":
                await asmr_popular(int(command.get("page", 1) or 1), bool(command.get("subtitle")))

            elif cmd == "asmr_works":
                await asmr_works(
                    int(command.get("page", 1) or 1),
                    command.get("order", "create_date"), command.get("sort", "desc"),
                    bool(command.get("subtitle")),
                    command.get("circle_id", ""), command.get("tag_id", ""),
                    command.get("va_id", ""),
                    command.get("view", "works"), command.get("label", ""))

            elif cmd == "asmr_work_detail":
                await asmr_work_detail(command.get("work_id", ""))

            elif cmd == "asmr_browse_index":
                await asmr_browse_index(command.get("kind", "circles"))

            elif cmd == "asmr_toggle_favorite":
                await asmr_toggle_favorite(
                    command.get("work_id", ""), command.get("card") or {})

            elif cmd == "asmr_favorites":
                await asmr_favorites(int(command.get("page", 1) or 1))

            elif cmd == "asmr_batch_download":
                await asmr_batch_download(
                    command.get("work_ids") or [], command.get("options") or {})

            elif cmd == "translate_youdao":
                await asyncio.to_thread(
                    translate_youdao,
                    command.get("text", ""),
                    command.get("from", "auto"),
                    command.get("to", "zh"),
                )

            elif cmd == "translate_free":
                # 免费翻译（默认 Google 翻译无 key 端点，失败回退 LibreTranslate）
                await asyncio.to_thread(
                    translate_free,
                    command.get("text", ""),
                    command.get("from", "auto"),
                    command.get("to", "zh-CN"),
                )

            elif cmd == "translate_batch":
                # 批量翻译（一次多文本，用于"自动翻译搜索结果"按钮）
                await asyncio.to_thread(
                    translate_batch,
                    command.get("texts", []),
                    command.get("from", "auto"),
                    command.get("to", "zh-CN"),
                    command.get("batch_id", ""),
                )

            elif cmd == "check_github_update":
                await asyncio.to_thread(check_github_update)

            elif cmd == "github_mark_update_done":
                await asyncio.to_thread(github_mark_update_done, command.get("sha", ""))

            elif cmd == "get_search_history":
                emit({"event": "search_history", "items": _load_search_history()})

            elif cmd == "add_search_history":
                add_search_history(
                    command.get("query", ""),
                    command.get("site", "bunkr"),
                    command.get("search_mode", ""),
                )

            elif cmd == "delete_search_history":
                delete_search_history(command.get("query", ""), command.get("site", ""))
                emit({"event": "search_history", "items": _load_search_history()})

            elif cmd == "clear_search_history":
                clear_search_history()
                emit({"event": "search_history", "items": []})

            elif cmd == "get_favorites":
                emit({"event": "local_favorites", "items": _load_local_favorites()})

            elif cmd == "add_favorite":
                add_local_favorite(command.get("item", {}))

            elif cmd == "delete_favorite":
                delete_local_favorite(command.get("id", ""))

            # ---------- 通用 webview OAuth 站点（xhamster/pornhub/xvideos）----------
            # AP1 阶段：通用 set_cookies/check_login/logout/set_proxy，具体搜索/解析待 AP2/AP3/AP4
            elif cmd.endswith("_set_cookies") and cmd.rsplit("_set_cookies", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_set_cookies", 1)[0]
                cookie_str = command.get("cookie_str", "")
                result = _generic_save_cookies(site, cookie_str)
                if result.get("ok"):
                    _generic_check_login(site)  # 立即推送登录态

            elif cmd.endswith("_check_login") and cmd.rsplit("_check_login", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_check_login", 1)[0]
                _generic_check_login(site)

            elif cmd.endswith("_logout") and cmd.rsplit("_logout", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_logout", 1)[0]
                _generic_logout(site)

            elif cmd.endswith("_set_proxy") and cmd.rsplit("_set_proxy", 1)[0] in _GENERIC_OAUTH_SITES:
                # AP1 阶段：代理设置存到 settings，实际应用待 AP2/AP3/AP4 站点模块实现
                site = cmd.rsplit("_set_proxy", 1)[0]
                proxy = command.get("proxy", "")
                settings[f"{site}_proxy"] = proxy
                _save_settings(settings)
                emit({"event": "log", "type": "设置", "message": f"{site} 代理已设置: {proxy or '直连'}"})

            # ---------- JavDB（javdb.com）----------
            elif cmd == "javdb_set_cookies":
                # webview 登录成功后抓取的 cookie（+ UA，cf_clearance 校验绑定 UA）
                javdb_set_cookies(
                    command.get("cookie_str", ""),
                    command.get("user_agent", ""),
                    command.get("username", ""),
                )

            elif cmd == "javdb_check_login":
                await asyncio.to_thread(javdb_check_login, bool(command.get("silent", False)))

            elif cmd == "javdb_logout":
                javdb_logout()

            elif cmd == "javdb_set_proxy":
                proxy = command.get("proxy", "")
                settings["javdb_proxy"] = proxy
                _save_settings(settings)
                javdb_set_proxy(proxy)
                emit({"event": "log", "type": "设置", "message": f"JavDB 代理已设置: {proxy or '直连'}"})

            elif cmd == "javdb_video_info":
                await javdb_video_info(command.get("url", ""))

            elif cmd == "javdb_download_images":
                await javdb_download_images(command.get("url", ""), command.get("options", {}))

            elif cmd == "javdb_batch_download":
                await javdb_batch_download(command.get("urls", []), command.get("options", {}))

            elif cmd == "cancel":
                logging.info("收到取消命令")
                emit({"event": "log", "type": "取消", "message": "收到取消请求"})

            else:
                logging.warning("未知命令: %s", cmd)

        except Exception as exc:
            logging.exception("命令处理出错: %s", exc)
            emit({"event": "log", "type": "错误", "message": f"命令处理出错: {exc}"})


def _force_utf8_stdio() -> None:
    """强制 stdin/stdout 使用 UTF-8。

    Windows 下管道默认跟随系统代码页（GBK），而 Electron 前端发送的是 UTF-8，
    不重配置会导致中文搜索词/用户名/收藏标题乱码甚至保存失败。
    """
    try:
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError, AttributeError) as exc:
        logging.warning("stdio UTF-8 重配置失败: %s", exc)


def main() -> None:
    """入口函数。"""
    setup_logging()
    _force_utf8_stdio()

    try:
        asyncio.run(command_loop())
    except KeyboardInterrupt:
        logging.info("用户中断，退出")
    except Exception as exc:
        logging.exception("致命错误: %s", exc)


if __name__ == "__main__":
    main()
