# -*- coding: utf-8 -*-
"""手动抓取（资源嗅探）模块 —— 复刻 res-downloader 核心能力。

链路：嗅探窗口内置浏览器（Electron webview，persist:sniffer 会话）浏览任意网页 →
主进程 webRequest.onCompleted 捕获媒体响应（URL/类型/大小）→ 嗅探窗口实时列表 →
勾选后发 sniff_download 命令到本模块 → 走 download_manager 通用下载管线
（site="sniffer" 分支直下 media_url，无重解析）。

命名：全模块 SNIF_ 前缀唯一（bridge finalize 同名互踩坑）。
"""
from __future__ import annotations

import os

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（emit/download_manager/ipaddress/…）

import ipaddress
import logging
import time
from urllib.parse import urlparse

# ============================
# 0. 站点标识 / 命令表名
# ============================
SNIF_SITE_KEY = "sniffer"
SNIF_ALBUM_NAME = "手动抓取"

# ============================
# 1. URL 安全校验（仅公网 http/https：拒绝非 http(s)、localhost/环回/私有/保留地址）
# ============================
def _snif_check_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False, "URL 解析失败"
    if parsed.scheme not in ("http", "https"):
        return False, f"仅支持 http/https（收到 {parsed.scheme or '空'}）"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "URL 缺少主机名"
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        return False, f"拒绝内网/本机地址: {host}"
    try:
        ip = ipaddress.ip_address(host)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, f"拒绝私有/保留 IP: {host}"
    except ValueError:
        pass  # 域名（非 IP 字面量）放行
    return True, ""


# ============================
# 2. GS 命令：嗅探下载提交
# ============================
async def _snif_cmd_download(command: dict) -> None:
    raw_items = command.get("items") or []
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or it.get("media_url") or "").strip()
        ok, reason = _snif_check_url(url)
        if not ok:
            logging.warning("嗅探下载拒绝非法 URL: %s（%s）", url[:120], reason)
            continue
        media_type = str(it.get("media_type") or "other")
        items.append({
            "media_url": url,
            "filename": str(it.get("filename") or "").strip() or f"sniffer_{int(time.time() * 1000)}",
            "media_type": media_type,
            "site": SNIF_SITE_KEY,
            "size": it.get("size"),
            "post_title": str(it.get("page_title") or ""),
            # 来源页随条目下发：下载器据此推断 Referer（B站等 CDN 防盗链必需）
            "page_url": str(it.get("page_url") or "").strip(),
        })
    if not items:
        emit({"event": "sniff_download_result", "ok": False, "message": "没有可下载的有效资源"})  # noqa: F821
        return
    referer = ""
    for it in raw_items:
        rp = str((it or {}).get("page_url") or "")
        if rp.startswith("http"):
            referer = rp
            break
    # world=surface（表世界发起）：真实落盘用户下载夹（防露馅，路径即事实）
    # 保存位置跟随设置区「表世界保存位置」（web_surface_root，留空=用户下载夹）；
    # 同时 no_download_folder=True —— create_download_directory 默认还会再拼一层
    # "Downloads"，不关掉会落成 <自定义路径>/Downloads/<相册>/（双重目录）。
    submit_options = {}
    if str(command.get("world") or "") == "surface":
        submit_options["custom_path"] = web_surface_root()   # noqa: F821
        submit_options["no_download_folder"] = True
        submit_options["world"] = "surface"
    task_id = download_manager.submit(  # noqa: F821
        referer or f"https://sniffer.local/{SNIF_SITE_KEY}", items, submit_options,
        command.get("album") or SNIF_ALBUM_NAME,
        f"{SNIF_SITE_KEY}:{command.get('album') or 'default'}",
    )
    download_manager.start(task_id)  # noqa: F821
    emit({  # noqa: F821
        "event": "sniff_download_result", "ok": True, "task_id": task_id,
        "urls": [it["media_url"] for it in items],
        "message": f"已提交下载：{len(items)} 个资源（可在下载管理查看进度）",
    })


# 命令表：唯一名，由 bridge/__init__.py 显式并入总表
SNIF_COMMANDS = {
    "sniff_download": _snif_cmd_download,
}
