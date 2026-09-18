# -*- coding: utf-8 -*-
"""综合资源站点 · 通用批量下载（GSV 批量勾选 → gs_batch_download）。

对每个选中的列表卡片调用该站的 open_detail 收集媒体文件（临时交换 emit 捕获
detail 完成事件，不干扰前端），合并为一个下载任务提交 download_manager。
新站只要实现 open_detail（detail.files 契约）即自动获得批量能力。

命名：GSB_ 前缀唯一（bridge finalize 同名互踩坑）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字

import asyncio

from . import site_coomerst as _m_cst
from . import site_coomerfans as _m_cfs
from . import site_fapello as _m_fpl
from . import site_leakedzone as _m_lz

_GSB_SITES = ("coomerst", "coomerfans", "fapello", "leakedzone")


async def _gsb_cmd_download(command: dict, site: str) -> None:
    site = str(command.get("site") or "")
    items = [i for i in (command.get("items") or []) if isinstance(i, dict)]
    if site not in _GSB_SITES or not items:
        emit({"event": "gs_state", "site": site or "gs", "view": "list",  # noqa: F821
              "error": "批量下载：站点无效或未选中项目"})
        return
    detail_handler = _SITE_COMMANDS.get(f"{site}_open_detail")  # noqa: F821
    if detail_handler is None:
        emit({"event": "gs_state", "site": site, "view": "list",  # noqa: F821
              "error": f"批量下载：{site} 未实现 open_detail"})
        return

    files: list[dict] = []
    seen: set = set()
    # 各站 open_detail 经本站模块的 emit（_xx_gs_emit 包装）发 detail 事件——
    # 拦截须替换【该站模块】的 emit 名（finalize 后各模块 globals 独立）
    site_modules = {"coomerst": _m_cst, "coomerfans": _m_cfs, "fapello": _m_fpl, "leakedzone": _m_lz}
    mod = site_modules[site]
    real_emit = mod.emit

    def _collect(payload: dict) -> None:
        try:
            if (payload or {}).get("view") == "detail":
                for f in payload.get("files") or []:
                    u = f.get("media_url") or ""
                    if u and u not in seen:
                        seen.add(u)
                        files.append(f)
        except Exception:
            pass

    mod.emit = _collect
    try:
        for it in items:
            try:
                await detail_handler({"item": it})
            except Exception as exc:
                logging.warning("gs_batch %s 条目处理失败: %s", site, exc)
    finally:
        mod.emit = real_emit

    if not files:
        emit({"event": "gs_state", "site": site, "view": "list",  # noqa: F821
              "error": f"批量下载：{len(items)} 个选中项没有解析到可下载文件"})
        return
    task_id = download_manager.submit(  # noqa: F821
        f"gsbatch:{site}", files, {}, f"{site} 批量下载", f"gsbatch:{site}",
    )
    download_manager.start(task_id)  # noqa: F821
    emit({"event": "gs_state", "site": site, "view": "list",  # noqa: F821
          "message": f"批量下载已提交：{len(items)} 项 → {len(files)} 个文件"})


# 各站批量命令：handleGsCommand 拼 `${site}_batch_download`（GSV 批量勾选统一入口）
def _gsb_site_batch(site: str):
    async def _handler(command: dict) -> None:
        await _gsb_cmd_download({**command, "site": site}, site)
    return _handler


# 命令表：唯一名，由 bridge/__init__.py 显式并入总表
GSB_COMMANDS = {
    "coomerst_batch_download": _gsb_site_batch("coomerst"),
    "coomerfans_batch_download": _gsb_site_batch("coomerfans"),
    "fapello_batch_download": _gsb_site_batch("fapello"),
    "leakedzone_batch_download": _gsb_site_batch("leakedzone"),
}
