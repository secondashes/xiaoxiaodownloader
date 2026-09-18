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

"""
----------------------------------------------------------------------------------------------------
拆分说明（2026-09-05，重构第二批）：实现已按原物理顺序拆入 `bridge/` 包（每站/每子系统一文件，
见 bridge/__init__.py 的加载说明与 重构第二批-任务清单.md）。本文件保留为：
  1. 启动入口（启动.bat / PyInstaller spec 的 gui_bridge.spec 以本文件为 entry）；
  2. 兼容出口——外部引用（探针脚本/测试）仍可 `import gui_bridge` 使用全部名字
     （含下划线私有名，由 bridge 包扁平命名空间整体导出）。
----------------------------------------------------------------------------------------------------
"""

import bridge as _bridge

# 全量名字出口（含下划线私有名；bridge 包内已清理子模块对象，不会覆盖真实全局名）
globals().update({k: v for k, v in vars(_bridge).items() if not k.startswith("__")})
del _bridge

if __name__ == "__main__":
    main()
