"""BunkrDownloader 对接接口（单文件，可直接复制到任意项目使用）。

原理：通过子进程启动 BunkrDownloader 后端（gui_bridge.py），使用 NDJSON 协议通信：
  - 往 stdin 写一行 JSON 命令
  - 从 stdout 读一行 JSON 事件

快速开始：
    from bunkr_api import BunkrAPI, is_bunkr_url

    # project_root 指向 BunkrDownloader 项目根目录（含 gui_bridge.py）
    api = BunkrAPI(project_root=r"D:\\BunkrDownloader")
    api.wait_ready()

    api.on("log", lambda ev: print(f"[{ev.get('type')}] {ev.get('message')}"))
    api.inspect("https://bunkr.cr/a/xxxx")

    # ... 收到 inspect_complete 后，拿到文件列表再调用 download ...

    api.stop()

依赖：仅 Python 标准库；后端还需要 BunkrDownloader 项目已安装依赖。
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path

# 匹配 Bunkr 相册/单文件链接
_BUNKR_URL_RE = re.compile(
    r"https?://(?:www\.)?bunkr\.[a-z]+/(?:a|f|i|v)/[^\s\"'<>]+",
    re.IGNORECASE,
)


def is_bunkr_url(text: str) -> bool:
    """判断文本中是否包含 Bunkr 链接。"""
    return bool(_BUNKR_URL_RE.search(text or ""))


def extract_bunkr_url(text: str):
    """从文本中提取第一个 Bunkr 链接，找不到返回 None。"""
    m = _BUNKR_URL_RE.search(text or "")
    return m.group(0) if m else None


class BunkrAPI:
    """BunkrDownloader 后端适配器：负责启动 / 写命令 / 读事件 / 停止。"""

    def __init__(self, project_root: str | None = None, python: str = "python"):
        """初始化并启动后端。

        参数：
            project_root: BunkrDownloader 项目根目录（含 gui_bridge.py）。
                          默认取当前文件所在目录；复制到别的项目后请显式传入。
            python: 用于启动后端的 Python 解释器（默认 "python"）。
        """
        if project_root is None:
            project_root = Path(__file__).resolve().parent
        project_root = Path(project_root)

        self.script = str(project_root / "gui_bridge.py")
        self.cwd = str(project_root)

        self._listeners: dict[str, list] = {}
        self._any_listeners: list = []
        self._ready = threading.Event()

        self.proc = subprocess.Popen(
            [python, self.script],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ---------- 底层通信 ----------
    def _read_loop(self) -> None:
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue

            if event.get("event") == "ready":
                self._ready.set()

            for cb in list(self._listeners.get(event.get("event"), [])):
                try:
                    cb(event)
                except Exception:
                    pass

            for cb in list(self._any_listeners):
                try:
                    cb(event)
                except Exception:
                    pass

    def on(self, event: str, cb) -> callable:
        """注册某个事件的回调，返回 cb 便于 off。"""
        self._listeners.setdefault(event, []).append(cb)
        return cb

    def on_any(self, cb) -> None:
        """注册全局回调，所有事件都会触发。"""
        self._any_listeners.append(cb)

    def off(self, event: str, cb) -> None:
        if event in self._listeners:
            self._listeners[event] = [f for f in self._listeners[event] if f is not cb]

    def send(self, cmd: dict) -> None:
        """向后端写一条命令。"""
        self.proc.stdin.write(json.dumps(cmd, ensure_ascii=True) + "\n")
        self.proc.stdin.flush()

    def wait_ready(self, timeout: float = 15.0) -> bool:
        """等待后端发出 ready 事件。"""
        return self._ready.wait(timeout)

    def stop(self) -> None:
        """停止后端进程。"""
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    # ---------- 高层命令 ----------
    def inspect(self, url: str, options: dict | None = None) -> None:
        """解析相册/链接，返回文件列表（事件 inspect_complete）。"""
        self.send({"cmd": "inspect", "url": url, "options": options or {}})

    def search(self, query: str, page: int = 1, per_page: int = 20, options: dict | None = None) -> None:
        """搜索相册（事件 search_result）。"""
        self.send({
            "cmd": "search",
            "query": query,
            "page": page,
            "per_page": per_page,
            "options": options or {},
        })

    def download(
        self,
        url: str,
        items: list,
        options: dict | None = None,
        album_name: str = "",
        album_id: str | None = None,
    ) -> None:
        """创建下载任务。items 为 inspect_complete 返回的文件列表（需含 item_page）。"""
        self.send({
            "cmd": "download",
            "url": url,
            "items": items,
            "options": options or {},
            "album_name": album_name,
            "album_id": album_id,
        })

    def get_tasks(self) -> None:
        """获取下载任务列表（事件 tasks_snapshot）。"""
        self.send({"cmd": "get_tasks"})

    def pause_task(self, task_id: str) -> None:
        self.send({"cmd": "pause_task", "task_id": task_id})

    def resume_task(self, task_id: str) -> None:
        self.send({"cmd": "resume_task", "task_id": task_id})

    def cancel_task(self, task_id: str) -> None:
        self.send({"cmd": "cancel_task", "task_id": task_id})

    def remove_task(self, task_id: str) -> None:
        self.send({"cmd": "remove_task", "task_id": task_id})

    def shutdown_after_done(self, enabled: bool = True) -> None:
        """全部下载完成后关机。"""
        self.send({"cmd": "shutdown_after_done", "enabled": enabled})

    def get_history(self) -> None:
        """获取下载历史（事件 history）。"""
        self.send({"cmd": "get_history"})

    def delete_history(self, record_id: str, delete_file: bool = False) -> None:
        self.send({"cmd": "delete_history", "id": record_id, "delete_file": delete_file})

    def clear_cache(self) -> None:
        """清除缩略图与相册缓存（事件 cache_cleared）。"""
        self.send({"cmd": "clear_cache"})
