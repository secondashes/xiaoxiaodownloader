# -*- coding: utf-8 -*-
"""通用站点模块模板（模块化架构 m2，见 任务中心/任务清单/模块化架构-通用站点模块-任务清单.md）。

用法：复制本文件为 bridge/site_<key>.py，把 example 替换为站点键，按 TODO 填规则，
然后在 bridge/__init__.py 加两行注册——命令经 SITE_COMMANDS 自动进入总命令表，
前端经 siteConfigs.js 配置驱动渲染（GenericSiteView），无需再改 command_loop / RightPanel。

模块级名字会被 _state.register 注入 bridge 扁平命名空间（跨段引用直接写名字即可，
勿在本文件 import 其他子模块）。未注册时本文件是死代码，仅 py_compile 校验。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（requests/emit/…；注册后本行必需）

import asyncio
import logging

# ============================
# 0. 站点标识（接通点 ⑤ 前端芯片/LeftPanel 依赖）
# ============================
SITE_KEY = "example"          # 前端 site === 'example'；命令前缀 example_*
SITE_NAME = "示例站"

EXAMPLE_HOST = "https://example.com"        # TODO: 主站域名（国内直连性决定代理默认值）
EXAMPLE_API = EXAMPLE_HOST + "/api"         # TODO: API 基址（如有）
EXAMPLE_PAGE_SIZE = 50

# ============================
# 1. 会话 / 代理（照 site_coomer/site_oreno 模式）
# ============================
_example_session = requests.Session()  # noqa: F821 —— requests 由 _core 注入
_example_proxy = ""


def example_set_proxy(proxy: str) -> None:
    """设置站点代理（空 = 直连；LeftPanel 设置区调用）。"""
    global _example_proxy
    _example_proxy = (proxy or "").strip()
    if _example_proxy and not _example_proxy.startswith("http"):
        _example_proxy = "http://" + _example_proxy
    _example_session.proxies.update({"http": _example_proxy, "https": _example_proxy} if _example_proxy else {})
    emit({"event": "example_proxy_set", "proxy": _example_proxy})  # noqa: F821


def _example_fetch_json(path: str, params: dict | None = None):
    """同步 GET JSON（节流/重试按 准则与调研/站点接入调研清单.md 第二节规范补齐）。"""
    # TODO: 接入站点节流（_throttle 工厂，见重构二批 f5）与 UA/Referer
    try:
        response = _example_session.get(f"{EXAMPLE_HOST}{path}", params=params, timeout=30)
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):  # noqa: F821
        return None


# ============================
# 2. 登录套件（仅登录站需要；无登录站整段删除。四处注册见接通点 ②）
# ============================
_example_token = ""
_example_username = ""


def _example_load_cred() -> dict:
    # TODO: 凭据存取（照 _javdb_load_cred：加密账号库/明文 json + 原子写）
    return {}


def _example_save_cred(cred: dict) -> None:
    # TODO
    pass


def _example_username_now() -> str:
    """跨模块读入口（accounts._site_username 会调用；缺失曾致后端退出——必须提供）。"""
    return _example_username or ""


async def example_login(username: str, password: str) -> None:
    # TODO: POST 登录 → 存 cookie/token → emit({"event": "example_login_result", ...})
    raise NotImplementedError


async def example_check_login(silent: bool = False) -> None:
    # TODO: 校验登录态 → emit example_login_result（静默模式不弹窗）
    raise NotImplementedError


def example_logout() -> None:
    _example_session.cookies.clear()
    _example_save_cred({})
    # TODO: emit logout 结果 + 清态


# ============================
# 3. 搜索 / 列表（通用列表流：与前端 GenericSiteView 的 list 视图对应）
# ============================
def _example_map_item(raw: dict) -> dict:
    """API 条目 → 通用卡片字段（GenericSiteView 按 search-card 渲染）。

    通用字段约定：album_name/album_url/thumbnail/files/site/video_id +
    可选 author/posted/duration/tags。站内展示的额外字段放 extra。
    """
    return {
        "album_name": raw.get("title") or "未命名",
        "album_url": f"{EXAMPLE_HOST}/item/{raw.get('id')}",
        "thumbnail": raw.get("thumb") or "",
        "files": None,
        "site": SITE_KEY,
        "video_id": str(raw.get("id") or ""),
        "author": raw.get("author") or "",
        "posted": raw.get("date") or "",
    }


async def example_search(query: str, page: int = 1) -> None:
    """关键词搜索 → gs_state {view: 'list', items, page, hasMore}。"""
    emit({"event": "search_start", "query": query, "page": page})  # noqa: F821
    try:
        data = await asyncio.to_thread(
            _example_fetch_json, "/search",
            {"q": query, "o": (page - 1) * EXAMPLE_PAGE_SIZE},  # TODO: 分页方式 page/offset/cursor 按实测
        )
        items = [_example_map_item(r) for r in (data or {}).get("results", [])]
        _gs_emit({"view": "list", "items": items, "page": page,
                  "hasMore": len(items) >= EXAMPLE_PAGE_SIZE,
                  "total": (data or {}).get("total", 0)})
    except Exception as exc:
        _gs_emit({"view": "list", "items": [], "page": page, "error": f"搜索失败: {exc}"})
        logging.exception("example 搜索失败")


async def example_home(page: int = 1) -> None:
    """主页/列表流（无需关键词）。"""
    # TODO: 按站点首页流实现；形状同 example_search
    raise NotImplementedError


# ============================
# 4. 详情 / 媒体直链（接通点 ③：媒体域名加 media_proxy 白名单）
# ============================
async def example_detail(item_id: str) -> None:
    """详情 → gs_state {view: 'detail', detail, files}。

    files 约定（与全站文件列表/下载兼容）：[{filename, media_url, size, type}]
    需要在线播放的媒体：play_url = media_proxy_url(media_url)  # noqa: F821
    """
    try:
        data = await asyncio.to_thread(_example_fetch_json, f"/item/{item_id}")
        if not data:
            _gs_emit({"view": "detail", "detail": None, "files": [], "error": "未获取到详情"})
            return
        detail = {
            "album_name": data.get("title") or "未命名",
            "album_url": f"{EXAMPLE_HOST}/item/{item_id}",
            "thumbnail": data.get("thumb") or "",
            "author": data.get("author") or "",
            "posted": data.get("date") or "",
            "tags": data.get("tags") or [],
            "description": data.get("desc") or "",
            "video_id": str(item_id),
            "site": SITE_KEY,
        }
        files = [{
            "filename": f.get("name") or "",
            "media_url": f.get("url") or "",       # TODO: 签名直链过期 → 下载时重解析
            "size": f.get("size"),
            "type": f.get("type") or "file",
        } for f in (data.get("files") or [])]
        _gs_emit({"view": "detail", "detail": detail, "files": files})
    except Exception as exc:
        _gs_emit({"view": "detail", "detail": None, "files": [], "error": f"详情失败: {exc}"})
        logging.exception("example 详情失败")


# ============================
# 5. 批量下载（交互规范：独立开关→勾选→可取消→完成"查看收集的文件"）
# ============================
_batch_running = False


async def example_batch_download(urls: list) -> None:
    """批量解析：逐个解析后并入下载流（照 EX 批量语义，可取消）。

    进度契约（m7 通用批量模块）：解析/下载循环中按节流频率 emit——
        _gs_emit({"view": keep_view, "batchRunning": True,
                  "batchProgress": {"done": n, "total": len(urls), "message": "..."}})
    完成时 batchRunning=False；前端 GenericSiteView 工具条自动渲染进度。
    节流间隔按站点实测（准则：搜索与下载分开节流）。
    """
    total = len(urls or [])
    for i, url in enumerate(urls or [], 1):
        # TODO: 单个解析 + 提交下载；每步 _gs_emit 进度；检查取消标记
        _gs_emit({"view": "list", "batchRunning": True,
                  "batchProgress": {"done": i - 1, "total": total, "message": "解析中"}})
    _gs_emit({"view": "list", "batchRunning": False,
              "batchProgress": {"done": total, "total": total, "message": "完成"}})


# ============================
# 6. 下载分发辅助（接通点 ④：gui_inspect URL 路由 + _download_file 分支）
#    标准形状：给定 album_url 返回 (直链, 文件名) 列表，供既有下载器落盘
# ============================
async def example_download_info(item: dict) -> tuple:
    """返回 (media_url, filename)；写法照 get_coomer_download_info。"""
    raise NotImplementedError


# ============================
# 7. 通用状态回流（前端 gs_state → App.gsStates[SITE_KEY] → GenericSiteView）
# ============================
def _gs_emit(state: dict) -> None:
    emit({"event": "gs_state", "site": SITE_KEY, **state})  # noqa: F821


# ============================
# 8. 命令表（m3：__init__ 汇总进 _SITE_COMMANDS；键必须带 SITE_KEY_ 前缀）
# ============================
async def _cmd_search(command: dict) -> None:
    await example_search(str(command.get("query") or ""), int(command.get("page") or 1))


async def _cmd_home(command: dict) -> None:
    await example_home(int(command.get("page") or 1))


async def _cmd_detail(command: dict) -> None:
    await example_detail(str(command.get("item_id") or command.get("url") or ""))


async def _cmd_batch(command: dict) -> None:
    await example_batch_download(command.get("urls") or [])


async def _cmd_favorite(command: dict) -> None:
    """卡片 ♥ 收藏到本地：item 是站点卡片（album_url/album_name 契约字段，同 FC2 做法）。"""
    it = command.get("item") or {}
    add_local_favorite({
        "url": it.get("album_url") or it.get("url") or "",
        "title": it.get("album_name") or it.get("title") or "",
        "site": SITE_KEY,
        "type": it.get("type") or "gallery",
        "thumbnail": it.get("thumbnail") or "",
    })


SITE_COMMANDS = {
    "example_search": _cmd_search,
    "example_home": _cmd_home,
    "example_detail": _cmd_detail,
    "example_batch_download": _cmd_batch,
    "example_favorite": _cmd_favorite,
}
