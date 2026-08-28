"""小小下载器 - 补丁更新程序（PyInstaller onefile）

工作原理：
1. PyInstaller 把 update/ 文件夹整体打包进 onefile exe（spec: datas=[('update', 'update')]）
2. 用户把"补丁.exe"放到本体目录（与 小小下载器.exe / 小小下载器/ 文件夹同目录）双击
3. 程序解压到 _MEIPASS 临时目录，遍历 update/ 下所有文件，逐个复制到本体目录的同名相对路径
4. 复制完成 → 提示用户重启 → 延迟自删（cmd ping 延时 + del）

注意：
- 本程序只覆盖程序文件，不动 data/（用户数据完整保留）
- 若本体 小小下载器.exe 正在运行，无法覆盖其本身；本补丁默认不打包本体 exe
  （本体 exe 的更新走单文件 EXE 重新下载流程）
- 用 Tkinter 显示进度（无控制台黑框），符合"傻瓜式操作"约束
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

# ------------------------------------------------------------------
# 路径解析
# ------------------------------------------------------------------
# PyInstaller onefile 运行时：sys._MEIPASS = 解压临时目录（只读资源）
# 开发模式（python patch_runtime.py）：用脚本所在目录
PATCH_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
UPDATE_DIR = PATCH_DIR / "update"

# 本体目录：补丁.exe 放在本体同目录运行，sys.executable 指向补丁.exe 自身
# 开发模式 fallback 到脚本所在目录
if getattr(sys, "frozen", False):
    TARGET_DIR = Path(sys.executable).resolve().parent
else:
    TARGET_DIR = Path(__file__).resolve().parent

# Tkinter 可用性（PyInstaller 默认打包 tcl/tk）
try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk
    HAS_TK = True
except Exception:
    HAS_TK = False


# ------------------------------------------------------------------
# 补丁应用逻辑
# ------------------------------------------------------------------
def collect_files() -> list[Path]:
    """收集 update/ 下所有待复制文件（含子目录）。"""
    if not UPDATE_DIR.exists():
        return []
    return [p for p in UPDATE_DIR.rglob("*") if p.is_file()]


def apply_patch(log_fn, progress_fn) -> tuple[int, int, list[tuple[str, str]]]:
    """遍历 update/ → 复制到本体目录同名相对路径。

    返回 (成功数, 失败数, 失败列表 [(相对路径, 错误信息)])。
    """
    files = collect_files()
    total = len(files)
    log_fn(f"发现 {total} 个待更新文件")
    log_fn(f"补丁源目录: {UPDATE_DIR}")
    log_fn(f"目标目录: {TARGET_DIR}")
    log_fn("-" * 60)

    success = 0
    failed: list[tuple[str, str]] = []
    for i, src in enumerate(files, 1):
        try:
            rel = src.relative_to(UPDATE_DIR)
        except ValueError:
            rel = Path(*src.parts[len(UPDATE_DIR.parts):])
        dst = TARGET_DIR / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 跳过本体 exe 自身（正在运行被锁，无法覆盖）
            if dst.name.lower() == "小小下载器.exe":
                log_fn(f"[{i}/{total}] 跳过 {rel}（本体 exe，请通过重新下载新版单文件 EXE 更新）")
                continue
            # 强制覆盖（同路径文件被覆盖）
            if dst.exists():
                # 试图覆盖运行中的 .exe 会失败 → 跳过并记录
                try:
                    shutil.copy2(src, dst)
                except PermissionError:
                    failed.append((str(rel), "文件被占用（可能正在运行）"))
                    log_fn(f"[{i}/{total}] ✗ {rel}（文件被占用）")
                    progress_fn(i, total)
                    continue
            else:
                shutil.copy2(src, dst)
            success += 1
            # 只在文件较多时打印，避免日志过长
            if total <= 30 or i % 10 == 0 or i == total:
                log_fn(f"[{i}/{total}] {rel} ✓")
        except Exception as exc:
            failed.append((str(rel), str(exc)))
            log_fn(f"[{i}/{total}] ✗ {rel}（{exc}）")
        progress_fn(i, total)

    log_fn("-" * 60)
    log_fn(f"完成：成功 {success}，失败 {len(failed)}")
    if failed:
        log_fn("失败明细：")
        for rel, err in failed:
            log_fn(f"  · {rel} → {err}")
    return success, len(failed), failed


def self_delete() -> None:
    """延迟自删：补丁.exe 自身正在运行被锁，spawn 外部 cmd 延时 3 秒后删除。"""
    if not getattr(sys, "frozen", False):
        return  # 开发模式不自删
    exe = sys.executable
    # ping 127.0.0.1 -n 4 ≈ 3 秒延时，然后 del /f 强制删除
    cmd = f'ping 127.0.0.1 -n 4 >nul & del /f "{exe}"'
    try:
        subprocess.Popen(
            ["cmd", "/c", cmd],
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except Exception:
        # 自删失败不影响补丁已应用
        pass


# ------------------------------------------------------------------
# Tkinter GUI
# ------------------------------------------------------------------
def run_gui() -> None:
    root = tk.Tk()
    root.title("小小下载器 - 补丁更新")
    root.geometry("680x460")
    root.minsize(560, 360)

    # 主题色
    bg = "#1e1e22"
    fg = "#e0e0e6"
    accent = "#63e2b7"
    root.configure(bg=bg)

    # 标题
    title = tk.Label(
        root, text="小小下载器 补丁更新",
        font=("Microsoft YaHei UI", 16, "bold"),
        bg=bg, fg=accent,
    )
    title.pack(pady=(20, 4))

    # 提示
    hint = tk.Label(
        root,
        text="本程序会把内置的更新文件覆盖到当前目录。\n建议先关闭 小小下载器.exe 再继续。",
        font=("Microsoft YaHei UI", 10),
        bg=bg, fg=fg, justify="center",
    )
    hint.pack(pady=(0, 10))

    # 进度条
    progress = ttk.Progressbar(root, length=560, mode="determinate")
    progress.pack(pady=4)

    # 进度文本
    progress_text = tk.StringVar(value="尚未开始")
    pt_label = tk.Label(
        root, textvariable=progress_text,
        font=("Microsoft YaHei UI", 10),
        bg=bg, fg=fg,
    )
    pt_label.pack(pady=(0, 8))

    # 日志
    log_widget = scrolledtext.ScrolledText(
        root, width=82, height=14,
        font=("Consolas", 9), bg="#15151a", fg=fg,
        wrap="word", relief="flat",
    )
    log_widget.pack(padx=10, pady=4, fill="both", expand=True)
    log_widget.configure(state="disabled")

    def log(msg: str) -> None:
        log_widget.configure(state="normal")
        log_widget.insert("end", str(msg) + "\n")
        log_widget.see("end")
        log_widget.configure(state="disabled")

    def set_progress(i: int, total: int) -> None:
        if total <= 0:
            return
        progress["maximum"] = total
        progress["value"] = i
        progress_text.set(f"{i} / {total}")

    # 操作按钮
    btn_frame = tk.Frame(root, bg=bg)
    btn_frame.pack(pady=10)

    start_btn = tk.Button(
        btn_frame, text="开始应用补丁",
        font=("Microsoft YaHei UI", 11, "bold"),
        bg=accent, fg="#15151a", activebackground="#4fd1a5",
        relief="flat", padx=24, pady=6, cursor="hand2",
    )
    close_btn = tk.Button(
        btn_frame, text="关闭",
        font=("Microsoft YaHei UI", 10),
        bg="#3a3a42", fg=fg, activebackground="#4a4a52",
        relief="flat", padx=20, pady=6, cursor="hand2",
        command=root.destroy,
    )
    start_btn.pack(side="left", padx=6)
    close_btn.pack(side="left", padx=6)

    state = {"running": False}

    def start_patch() -> None:
        if state["running"]:
            return
        state["running"] = True
        start_btn.configure(state="disabled", text="正在应用...")

        def task() -> None:
            try:
                success, failed, _ = apply_patch(log, set_progress)
                log("")
                if failed:
                    log(f"⚠ 有 {failed} 个文件失败，请关闭 小小下载器.exe 后重试")
                    log("（或手动把补丁.exe 同目录的 update 文件夹内容复制到当前目录）")
                    progress_text.set(f"完成：成功 {success}，失败 {failed}")
                    root.after(0, lambda: start_btn.configure(
                        state="normal", text="重试失败项",
                    ))
                else:
                    log("✓ 全部文件更新成功")
                    log("请重新启动 小小下载器.exe 查看新功能")
                    progress_text.set(f"完成：{success} 个文件已更新")
                    root.after(0, lambda: start_btn.configure(
                        state="disabled", text="完成（3 秒后自动关闭并删除补丁程序）",
                    ))
                    # 3 秒后关闭窗口并自删
                    root.after(1500, lambda: log("3 秒后自动关闭并删除补丁程序..."))
                    root.after(3000, lambda: (root.destroy(), self_delete()))
            except Exception:
                log("✗ 应用补丁时发生异常：")
                log(traceback.format_exc())
                root.after(0, lambda: start_btn.configure(
                    state="normal", text="重试",
                ))
            finally:
                state["running"] = False

        threading.Thread(target=task, daemon=True).start()

    start_btn.configure(command=start_patch)

    # 首次显示文件数预览
    files_preview = collect_files()
    if files_preview:
        log(f"补丁包含 {len(files_preview)} 个更新文件")
        log(f"目标目录：{TARGET_DIR}")
    else:
        log("⚠ 未发现 update 目录（补丁打包异常）")
        start_btn.configure(state="disabled")

    root.mainloop()


def run_cli() -> None:
    """无 Tkinter 时的命令行 fallback（仍可用，但有黑框）。"""
    print("=" * 60)
    print(" 小小下载器 - 补丁更新程序")
    print("=" * 60)
    files = collect_files()
    print(f"发现 {len(files)} 个待更新文件")
    print(f"补丁源目录: {UPDATE_DIR}")
    print(f"目标目录: {TARGET_DIR}")
    if not files:
        print("⚠ 未发现 update 目录，按回车退出...")
        input()
        return

    print("\n按回车开始应用补丁（或 Ctrl+C 取消）...")
    input()

    def log(msg): print(msg)
    def progress(i, total): pass
    success, failed, _ = apply_patch(log, progress)
    print()
    if failed:
        print(f"⚠ {failed} 个文件失败，请关闭 小小下载器.exe 后重试")
    else:
        print(f"✓ 全部 {success} 个文件更新成功")
        print("请重新启动 小小下载器.exe 查看新功能")
        print("3 秒后自动关闭并删除补丁程序...")
        time.sleep(3)
        self_delete()
    print("\n按回车退出...")
    input()


if __name__ == "__main__":
    if HAS_TK:
        try:
            run_gui()
        except Exception:
            # GUI 异常时回退到 CLI
            traceback.print_exc()
            run_cli()
    else:
        run_cli()
