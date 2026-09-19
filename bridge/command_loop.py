# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：主循环（命令分发）+ main()。

由 gui_bridge.py 按物理顺序拆出（原行区间 18851-19951），
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
# 主循环：读取命令并执行
# ============================
# 后台化长命令：命令循环是单队列顺序 await，批量解析/大画廊解析这类长命令
# 会把后续所有命令（切站/搜索/收藏）卡在队列里——其他界面全部"没反应"。
# 名单内命令改为 fire-and-forget（进度事件驱动 UI），同命令进行中则拒绝重入。
_BG_RUNNING: set = set()
BG_COMMANDS = {
    "inspect", "fc2_batch_download", "xhamster_batch_download",
    "hanime_batch_download", "asmr_batch_download", "iwara_batch_download",
    "pixiv_batch_download", "pixiv_bookmarks_download_all",
    "pixiv_following_download_all", "pixiv_user_download_all", "javdb_download_images",
    "exhentai_popular",
    "javdb_batch_download",
}


def _spawn_bg(name: str, coro) -> None:
    if name in _BG_RUNNING:
        emit({"event": "bg_busy", "command": name,
              "message": "上一个同类任务还在处理中，请等它完成再发起"})
        return
    _BG_RUNNING.add(name)

    async def _runner():
        try:
            await coro
        except Exception as exc:
            logging.exception("后台命令 %s 异常", name)
            emit({"event": "bg_busy", "command": name,
                  "message": f"后台任务异常结束: {exc}"})
        finally:
            _BG_RUNNING.discard(name)

    asyncio.create_task(_runner())


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
    if _pawchive_username_now():
        emit({
            "event": "pawchive_login_result",
            "success": True,
            "silent": True,
            "username": _pawchive_username_now(),
            "message": "已恢复登录",
        })
    # 启动期的各站网络登录检查全部后台化（串行 10+ 站实测拖慢就绪 ~11 秒，
    # 期间前端命令全部排队 = "打开很卡"）。结果经 *_login_result 事件照常推送。
    async def _startup_login_checks():
        try:
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
            # O3D / E站：把保存的登录会话 cookie 应用到站点请求会话（浏览/搜索自动带会话，Cloudflare 免重复验证）
            _oreno_apply_saved_cookies("oreno3d")
            _oreno_apply_saved_cookies("erommdtube")
            # 恢复 ASMR 代理设置并静默检查登录（token 失效自动用保存的密码重登）
            asmr_set_proxy(_settings.get("asmr_proxy") or "")
            if _asmr_load_cred().get("token"):
                await asyncio.to_thread(asmr_check_login, True)
            # 恢复识图（反向图片搜索）代理设置 + 粘贴板内容推送
            # （启动恢复阶段不回推 reverse_proxy_set 事件，避免前端收到后重复保存设置）
            _reverse_settings.update(_settings)
            p = (_settings.get("reverse_proxy") or "").strip()
            if p and not p.startswith("http"):
                p = "http://" + p
            _reverse_apply_proxy(p, bool(_settings.get("reverse_proxy_all")))
            reverse_paste_get()
            _hanime_restore_session()
            if _hanime_load_cred().get("cookies"):
                await asyncio.to_thread(hanime_check_login, True)
            # 恢复 Pixiv 代理设置 + Refresh Token 会话（access_token 过期自动续期）
            pixiv_set_proxy(_settings.get("pixiv_proxy") or PIXIV_DEFAULT_PROXY)
            coomerst_set_proxy(_settings.get("coomerst_proxy") or COOMERST_DEFAULT_PROXY)
            fapello_set_proxy(_settings.get("fapello_proxy") or FAPELLO_DEFAULT_PROXY)
            coomerfans_set_proxy(_settings.get("coomerfans_proxy") or CFANS_DEFAULT_PROXY)
            leakedzone_set_proxy(_settings.get("leakedzone_proxy") or LZ_DEFAULT_PROXY)
            _pixiv_restore_session()
            if _pixiv_load_cred().get("refresh_token"):
                await asyncio.to_thread(pixiv_check_login, True)
            # 恢复 JavDB 代理设置 + 会话（cookie 约 7 天有效，过期提示重新 webview 登录）
            javdb_set_proxy(_settings.get("javdb_proxy") or "http://127.0.0.1:10809")
            _javdb_restore_session()
            if _javdb_load_cred().get("cookies"):
                await asyncio.to_thread(javdb_check_login, True)
            # 恢复 xHamster 代理设置 + 会话（cookie 长期有效，启动时静默校验并提取用户名）
            xhamster_set_proxy(_settings.get("xhamster_proxy") or "")
            _xhamster_restore_session()
            if _generic_load_cookies("xhamster").get("cookies"):
                await asyncio.to_thread(xhamster_check_login, True)
            # 恢复 FC2 代理设置 + 会话（cookie 长期有效，启动时静默校验）
            fc2_set_proxy(_settings.get("fc2_proxy") or "http://127.0.0.1:10809")
            _fc2_restore_session()
            if _generic_load_cookies("fc2").get("cookies"):
                await asyncio.to_thread(fc2_check_login, True)

        except Exception:
            logging.exception("启动登录检查后台任务失败（忽略，继续）")
    asyncio.create_task(_startup_login_checks())
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
            if not cmd or not isinstance(cmd, str):
                # 缺 cmd 的消息（前端异常序列化等）无法路由，静默跳过——此前走到
                # cmd.endswith("_set_cookies") 会 AttributeError 打整段 traceback
                logging.warning("忽略无 cmd 命令: %s", line[:200])
                continue
            logging.info("收到命令: %s", cmd)
            # 通用站点命令总表（模块化架构 m3）：站点模块 SITE_COMMANDS 汇总，命中即分发
            gs_handler = _SITE_COMMANDS.get(cmd)
            if gs_handler is not None:
                if cmd in BG_COMMANDS:
                    _spawn_bg(cmd, gs_handler(command))
                else:
                    await gs_handler(command)
                continue


            if cmd == "inspect":
                url = command.get("url", "")
                options = command.get("options", {})
                _spawn_bg("inspect", gui_inspect(url, options))

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

            elif cmd == "retry_task":
                download_manager.retry(command.get("task_id", ""))

            elif cmd == "retry_file":
                download_manager.retry_file(
                    command.get("task_id", ""), command.get("item_page", ""),
                )

            elif cmd == "cancel_task":
                download_manager.cancel(command.get("task_id", ""))

            elif cmd == "remove_task":
                download_manager.remove(
                    command.get("task_id", ""),
                    delete_files=bool(command.get("delete_files", False)))

            elif cmd == "move_task_folder":
                # 里世界：把任务文件夹整体移动到目标目录（迁移/集中资源）
                ok, msg = download_manager.move_task_folder(
                    command.get("task_id", ""), command.get("dest_dir", ""))
                emit({"event": "move_task_folder_result", "ok": ok,
                      "task_id": command.get("task_id", ""), "message": msg})

            elif cmd == "clear_tasks":
                n = download_manager.clear_all(
                    delete_files=bool(command.get("delete_files", False)))
                emit({"event": "log", "type": "下载", "message":
                      f"已清除全部 {n} 个任务"
                      + ("（已同步删除本地文件与文件夹）" if command.get("delete_files") else "")})

            elif cmd == "shutdown_after_done":
                download_manager.set_shutdown_after_done(bool(command.get("enabled", True)))

            elif cmd == "get_settings":
                emit({"event": "settings", "settings": _load_settings()})

            elif cmd == "set_setting":
                # 单键更新（主进程写入 settings.json 后前端转发，刷新后端内存缓存）
                key = str(command.get("key", ""))
                if key:
                    merged = _load_settings()
                    merged[key] = command.get("value")
                    _save_settings(merged)
                    _reverse_settings.update(merged)

            elif cmd == "save_settings":
                # 合并保存：磁盘上可能有主进程写入的键（如 close_action 关闭行为），
                # 直接用前端载荷整表覆盖会把这些键丢掉
                merged = _load_settings()
                merged.update(command.get("settings", {}))
                _save_settings(merged)
                _reverse_settings.update(merged)

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
                await pawchive_get_favorites(str(command.get("fav_type", "creator") or "creator"))
            elif cmd == "pawchive_favorite":
                await pawchive_favorite_creator(
                    str(command.get("service") or ""),
                    str(command.get("user_id") or ""),
                    bool(command.get("unfavorite", False)))

            elif cmd == "pawchive_home":
                await pawchive_home(int(command.get("page", 1) or 1))

            elif cmd == "pawchive_post_info":
                await pawchive_post_info(command.get("url", ""))

            elif cmd == "pawchive_artist_posts":
                await pawchive_artist_posts(command.get("url", ""))

            elif cmd == "pawchive_download_artist":
                await pawchive_download_artist(
                    command.get("url", ""), command.get("options", {}),
                )

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

            # ---------- X 博主内容流（点开博主自动解析展示） ----------
            elif cmd == "twitter_user_feed":
                await twitter_user_feed(
                    command.get("screen_name", ""),
                    str(command.get("user_id") or ""),
                    command.get("cursor", ""),
                    bool(command.get("load_all", False)),
                )

            elif cmd == "twitter_export_html":
                _spawn_bg("twitter_export_html", twitter_export_html(
                    command.get("screen_name", ""),
                    str(command.get("user_id") or ""),
                ))

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

            elif cmd == "exhentai_popular":
                # 首页推荐（与主站 exhentai.org 首页相同的最新画廊列表），后台执行
                _spawn_bg("exhentai_popular", exhentai_popular(int(command.get("page", 1) or 1)))

            elif cmd == "exhentai_gallery_info":
                await exhentai_gallery_info(command.get("url", ""))

            elif cmd == "exhentai_get_torrents":
                # 磁力弹窗数据源（前端 handleExGetTorrents → RightPanel
                # defineExpose.setTorrents 消费 ex_torrents_result）
                await exhentai_torrents(command.get("url", ""))

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
                _spawn_bg("iwara_batch_download", iwara_batch_download(
                    command.get("usernames") or [],
                    command.get("video_ids") or [],
                    command.get("options") or {},
                ))

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

            elif cmd == "pixiv_oauth_start":
                await asyncio.to_thread(pixiv_oauth_start)

            elif cmd == "pixiv_oauth_complete":
                await asyncio.to_thread(
                    pixiv_oauth_complete,
                    command.get("code", ""), command.get("cookie_str", ""),
                )

            elif cmd == "pixiv_logout":
                await asyncio.to_thread(pixiv_logout)

            elif cmd == "pixiv_check_login":
                await asyncio.to_thread(
                    pixiv_check_login, bool(command.get("silent", False)))

            elif cmd == "pixiv_set_proxy":
                pixiv_set_proxy(command.get("proxy", ""))

            elif cmd == "pixiv_set_cookies":
                await asyncio.to_thread(
                    pixiv_set_cookies, command.get("cookie_str", ""),
                    command.get("email", ""), command.get("password", ""),
                )

            elif cmd == "pixiv_feed":
                await pixiv_feed(command.get("kind", "home"),
                                 int(command.get("page", 1) or 1))

            elif cmd == "pixiv_follow_feed":
                # 后台执行：关注更新要顺 next_url 抓多页（~10s+），内联会阻塞
                # 命令循环——期间所有界面点击（切视图/详情）全部排队
                _spawn_bg("pixiv_follow_feed", pixiv_follow_feed(
                    command.get("content", "illust")))

            elif cmd == "pixiv_bookmarks":
                await pixiv_bookmarks(
                    command.get("content", "illust"),
                    command.get("restrict", "public"),
                    bool(command.get("allow_r18", True)),
                    int(command.get("page", 1) or 1),
                    command.get("user_id", ""),
                )

            elif cmd == "pixiv_bookmark_tags":
                await pixiv_bookmark_tags(command.get("content", "illust"))

            elif cmd == "pixiv_bookmarks_download_all":
                _spawn_bg("pixiv_bookmarks_download_all", pixiv_bookmarks_download_all(
                    command.get("content", "illust"),
                    command.get("restrict", "public"),
                    bool(command.get("allow_r18", True)),
                    command.get("options") or {},
                ))

            elif cmd == "pixiv_user_page":
                await pixiv_user_page(command.get("user_id", ""),
                                      int(command.get("page", 1) or 1),
                                      command.get("tab", "all"))

            elif cmd == "pixiv_user_list":
                await pixiv_user_list(
                    command.get("mode", "following"),
                    command.get("user_id", ""),
                    int(command.get("page", 1) or 1),
                )

            elif cmd == "pixiv_detail":
                await pixiv_detail(command.get("kind", "illust"),
                                   command.get("item_id", ""))

            elif cmd == "pixiv_user_download_all":
                _spawn_bg("pixiv_batch_download", pixiv_user_download_all(
                    command.get("user_id") or command.get("uid") or "",
                    command.get("kind") or "illustmanga",
                    command.get("fmt") or "txt",
                ))
            elif cmd == "pixiv_batch_download":
                # 双形态：卡片勾选发 items；用户列表批量发 user_ids+content。
                # （2026-09-13：曾因 site_pixiv 内两个同名定义互相覆盖，
                #   items 调用实际走进 user_ids 版 → 任务永远创建失败）
                if command.get("user_ids"):
                    _spawn_bg("pixiv_batch_download", pixiv_batch_download_users(
                        command.get("user_ids") or [],
                        command.get("content") or "illust",
                        command.get("illust_ids") or [],
                        command.get("novel_ids") or [],
                        command.get("options") or {},
                    ))
                else:
                    _spawn_bg("pixiv_batch_download", pixiv_batch_download(
                        command.get("items") or [],
                        novel_fmt=command.get("novel_fmt") or "txt",
                    ))

            elif cmd == "pixiv_series_download":
                _spawn_bg("pixiv_batch_download", pixiv_series_download(
                    command.get("series_id") or "",
                    command.get("kind") or "novel",
                    command.get("novel_fmt") or "txt",
                    command.get("options") or {},
                ))

            elif cmd == "pixiv_related":
                await pixiv_related(command.get("kind", "illust"),
                                    command.get("item_id", ""))

            elif cmd == "pixiv_action":
                await pixiv_action(
                    command.get("action", ""), command.get("kind", "illust"),
                    command.get("item_id", ""),
                    text=command.get("text", ""),
                    parent_id=command.get("parent_id", ""),
                    comment_id=command.get("comment_id", ""),
                    restrict=command.get("restrict", "public"),
                )

            elif cmd == "pixiv_tags":
                await pixiv_tags()

            elif cmd == "pixiv_tag_click":
                await asyncio.to_thread(
                    _pixiv_record_tag_click, command.get("tag", ""))

            elif cmd == "pixiv_notification":
                await pixiv_notification()

            elif cmd == "pixiv_upload":
                await pixiv_upload(
                    command.get("paths") or [],
                    command.get("title", ""), command.get("caption", ""),
                    command.get("tags") or [],
                    int(command.get("x_restrict", 0) or 0),
                )

            elif cmd == "pixiv_user_novels":
                await pixiv_user_novels(command.get("user_id", ""))

            elif cmd == "pixiv_following_download_all":
                _spawn_bg("pixiv_following_download_all", pixiv_following_download_all(
                    command.get("content", "illust"), command.get("options") or {}))

            elif cmd == "hanime_home":
                await hanime_home()

            elif cmd == "hanime_search":
                await hanime_search(
                    command.get("query", ""),
                    int(command.get("page", 1) or 1),
                    command.get("genre", ""),
                    command.get("sort", ""),
                    command.get("tags") or [],
                    command.get("broad", ""),
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
                _spawn_bg("hanime_batch_download", hanime_batch_download(
                    command.get("video_ids") or [], command.get("options") or {}))

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
                reverse_set_proxy(command.get("proxy", ""), command.get("all_sites"))
            elif cmd == "reverse_search":
                await reverse_search(command.get("path", ""))
            elif cmd == "reverse_cancel":
                reverse_cancel()
            elif cmd == "reverse_download":
                await reverse_download(command.get("url", ""))
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
                _spawn_bg("asmr_batch_download", asmr_batch_download(
                    command.get("work_ids") or [], command.get("options") or {}))

            elif cmd == "asmr_file_download":
                await asmr_file_download(
                    command.get("work_id", ""), command.get("work") or {},
                    command.get("files") or [], command.get("options") or {})

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

            elif cmd == "leakedzone_set_cookies":
                await asyncio.to_thread(
                    leakedzone_set_cookies,
                    command.get("cookie_str") or command.get("cookies") or "")
                emit({"event": "log", "type": "系统", "message": "Leakedzone 过盾 Cookie 已保存"})

            elif cmd == "leakedzone_check_login":
                await asyncio.to_thread(
                    leakedzone_check_login, bool(command.get("silent", False)))

            elif cmd == "common_proxy":
                # 通用代理（Pornhub / GitHub 更新共用）：App 已持久化设置，
                # 此处仅回执确认；github_update 在调用时实时读 settings 生效
                emit({"event": "log", "type": "系统",
                      "message": f"通用代理已更新：{command.get('proxy') or '默认 http://127.0.0.1:10809'}"})

            elif cmd == "check_github_update":
                await asyncio.to_thread(check_github_update, command.get("current_version", ""))

            elif cmd == "fetch_changelog":
                await asyncio.to_thread(fetch_changelog, command.get("current_version", ""))

            elif cmd == "download_update":
                # 下载 GitHub Release 更新安装包（流式 + 进度事件），放线程池避免阻塞命令循环
                await asyncio.to_thread(
                    download_update,
                    command.get("url", ""),
                    command.get("file_name", ""),
                )

            elif cmd == "open_update_installer":
                # 运行已下载的更新安装包（NSIS 覆盖安装即更新）
                await asyncio.to_thread(open_update_installer, command.get("path", ""))

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

            # ---------- 谷歌邮箱（OAuth 授权共用凭据源）----------
            elif cmd == "google_save_cred":
                # 设置区"登录谷歌邮箱"表单：保存账号密码（cookie 登录后自动补充）
                google_save_cred(command.get("email", ""), command.get("password", ""))

            elif cmd == "google_switch_account":
                google_switch_account(command.get("email", ""))

            elif cmd == "google_delete_account":
                google_delete_account(command.get("email", ""))

            elif cmd == "google_check_login":
                google_check_login(bool(command.get("silent", False)))

            # ---------- Oreno3D / EroMMDTube 账号密码保存 ----------
            elif cmd in ("oreno3d_save_cred", "erommdtube_save_cred"):
                # 含首页会话网络验证（cookie 与账号密码互相验证），放线程池避免阻塞
                await asyncio.to_thread(
                    oreno_save_cred,
                    cmd.rsplit("_save_cred", 1)[0],
                    command.get("email", ""),
                    command.get("password", ""),
                )

            # ---------- 通用账号密码保存（全站登录套件：加密入库 + 表单回填） ----------
            elif cmd == "site_save_cred":
                await asyncio.to_thread(
                    site_save_cred,
                    command.get("site", ""),
                    command.get("email", ""),
                    command.get("password", ""),
                )

            # ---------- Hanime1 内置浏览器登录（真人验证完成后保存会话 cookie） ----------
            elif cmd == "hanime_set_cookies":
                await asyncio.to_thread(
                    hanime_set_cookies,
                    command.get("cookie_str", ""),
                    command.get("email", ""),
                    command.get("password", ""),
                )

            # ---------- 通用 webview OAuth 站点（xhamster/pornhub/xvideos/google/oreno3d）----------
            # AP1 阶段：通用 set_cookies/check_login/logout/set_proxy，具体搜索/解析待 AP2/AP3/AP4
            elif cmd.endswith("_set_cookies") and cmd.rsplit("_set_cookies", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_set_cookies", 1)[0]
                cookie_str = command.get("cookie_str", "")
                # google 登录成功后补记邮箱（凭据里保存的账号），便于展示与授权提示
                if site == "google":
                    g_cred = _secure_store_read_cred("google")
                    if not g_cred.get("email"):
                        g_cred["email"] = command.get("email", "") or ""
                        if g_cred["email"]:
                            _secure_store_write_cred("google", g_cred)
                result = _generic_save_cookies(site, cookie_str)
                # O3D / E站：webview 登录时表单预填的账号密码一并保存（下次登录自动回填），
                # 并把新 cookie 应用到站点请求会话（浏览/搜索自动带会话）
                # （必须在 _generic_save_cookies 之后：它会整体重建凭据记录）
                if site in ("oreno3d", "erommdtube") and result.get("ok"):
                    o_cred = _secure_store_read_cred(site)
                    if command.get("email"):
                        o_cred["email"] = command.get("email", "")
                    if command.get("password"):
                        o_cred["password"] = command.get("password", "")
                    _secure_store_write_cred(site, o_cred)
                    _oreno_apply_saved_cookies(site)
                if result.get("ok"):
                    if site in ("oreno3d", "erommdtube"):
                        await asyncio.to_thread(_generic_check_login, site)  # 含首页会话网络验证
                    elif site == "xhamster":
                        # xHamster：应用保存的 cookie 到请求会话，并网络校验提取用户名
                        _xhamster_restore_session()
                        await asyncio.to_thread(xhamster_check_login, False)
                    elif site == "fc2":
                        # FC2：应用保存的 cookie 到请求会话，并网络校验登录态。
                        # 推来的分区 cookie 可能是游客会话（用户在内置浏览器打开过
                        # FC2 页面即被降级游客）——校验失败时回滚内存与档案，避免
                        # 冲掉 _fc2_sync_cred_cookie 轮换保存的登录会话（反复要求
                        # 重新登录的元凶）
                        prev_cred = _generic_load_cookies("fc2")
                        _fc2_restore_session()
                        await asyncio.to_thread(fc2_check_login, False)
                        if not fc2_is_login_ok():  # noqa: F821 —— 跨模块读变量是注册时快照，必须走函数
                            cur = _generic_load_cookies("fc2")
                            if cur.get("cookie_str") and cur.get("cookie_str") != (prev_cred.get("cookie_str") or ""):
                                _secure_store_write_cred("fc2", prev_cred)  # noqa: F821
                                fc2_rollback_session(prev_cred.get("cookie_str") or "")  # noqa: F821
                    else:
                        _generic_check_login(site)  # 立即推送登录态
                    _emit_login_info()          # 刷新左侧账号卡片（google/oreno3d 等）

            elif cmd.endswith("_check_login") and cmd.rsplit("_check_login", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_check_login", 1)[0]
                silent = bool(command.get("silent", False))
                # O3D / E站 的登录验证含网络请求（首页会话校验），放线程池避免阻塞命令循环
                if site in ("oreno3d", "erommdtube"):
                    await asyncio.to_thread(_generic_check_login, site, silent)
                elif site == "xhamster":
                    # xHamster：带网络校验（/users/me 提取用户名），放线程池
                    _xhamster_restore_session()
                    await asyncio.to_thread(xhamster_check_login, silent)
                elif site == "fc2":
                    _fc2_restore_session()
                    await asyncio.to_thread(fc2_check_login, silent)
                else:
                    _generic_check_login(site, silent)

            elif cmd.endswith("_logout") and cmd.rsplit("_logout", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_logout", 1)[0]
                if site == "xhamster":
                    # 清请求会话 cookie 头 + 已提取用户名（凭据由通用逻辑清除）
                    _xhamster_set_username("")
                    _xhamster_session.headers.pop("Cookie", None)
                elif site == "fc2":
                    _fc2_session.headers.pop("Cookie", None)
                _generic_logout(site)

            elif cmd.endswith("_set_proxy") and cmd.rsplit("_set_proxy", 1)[0] in _GENERIC_OAUTH_SITES:
                site = cmd.rsplit("_set_proxy", 1)[0]
                proxy = command.get("proxy", "")
                settings[f"{site}_proxy"] = proxy
                _save_settings(settings)
                if site == "xhamster":
                    # 立即应用到请求会话（浏览/搜索/下载都走此代理）
                    xhamster_set_proxy(proxy)
                elif site == "fc2":
                    fc2_set_proxy(proxy)
                emit({"event": "log", "type": "设置", "message": f"{site} 代理已设置: {proxy or '直连'}"})

            # ---------- JavDB（javdb.com）----------
            elif cmd == "javdb_set_cookies":
                # webview 登录成功后抓取的 cookie（+ UA，cf_clearance 校验绑定 UA）
                # email/password：登录表单预填的账号密码，随 cookie 长期保存供下次回填
                javdb_set_cookies(
                    command.get("cookie_str", ""),
                    command.get("user_agent", ""),
                    command.get("username", ""),
                    command.get("email", ""),
                    command.get("password", ""),
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

            elif cmd == "javdb_home":
                await javdb_home(int(command.get("page", 1) or 1))

            elif cmd == "javdb_actor":
                await javdb_actor(command.get("url", ""), int(command.get("page", 1) or 1))

            elif cmd == "javdb_tags_vocab":
                javdb_tags_vocab()

            elif cmd == "javdb_hot_search":
                javdb_hot_search()

            elif cmd == "javdb_directory":
                await javdb_directory(command.get("kind", ""), int(command.get("page", 1) or 1),
                                      command.get("params", "") or "")

            elif cmd == "javdb_open_url":
                await javdb_open_url(command.get("url", ""), command.get("label", ""),
                                     int(command.get("page", 1) or 1))

            elif cmd == "javdb_download_images":
                # 后台任务执行（批量下载逐视频 throttle+请求，耗时数分钟；
                # 直接 await 会阻塞命令循环，导致期间点解析/搜索"一直转圈"）
                _spawn_bg("javdb_download_images", javdb_download_images(command.get("url", ""), command.get("options", {})))

            elif cmd == "javdb_batch_download":
                _spawn_bg("javdb_batch_download", javdb_batch_download(command.get("urls", []), command.get("options", {})))

            # ---------- xHamster 浏览（首页/分类/短视频/消息/我的 + 搜索/详情） ----------
            elif cmd == "xhamster_home":
                await xhamster_home(int(command.get("page", 1) or 1),
                                    command.get("sort", "newest"))

            elif cmd == "xhamster_categories":
                await xhamster_categories()

            elif cmd == "xhamster_category":
                await xhamster_category(command.get("slug", ""),
                                        int(command.get("page", 1) or 1))

            elif cmd == "xhamster_shorts":
                await xhamster_shorts(int(command.get("page", 1) or 1))

            elif cmd == "xhamster_video_detail":
                await xhamster_video_detail(
                    command.get("page_url") or command.get("url") or "")

            elif cmd == "xhamster_user_videos":
                await xhamster_user_videos(command.get("username", ""),
                                           int(command.get("page", 1) or 1),
                                           command.get("tab", "videos") or "videos")

            elif cmd == "xhamster_subscribe":
                await xhamster_subscribe(command.get("user_id", ""),
                                         command.get("username", ""),
                                         bool(command.get("subscribe", True)))

            elif cmd == "xhamster_add_comment":
                await xhamster_add_comment(command.get("entity_type", "video"),
                                           command.get("entity_id", ""),
                                           command.get("text", ""),
                                           command.get("page_url", ""))

            elif cmd == "xhamster_my":
                await xhamster_my(command.get("tab", "videos"),
                                  int(command.get("page", 1) or 1))

            elif cmd == "xhamster_notifications":
                await xhamster_notifications()

            elif cmd == "xhamster_batch_download":
                # 后台任务执行（批量逐个解析详情取直链，耗时较长；
                # 直接 await 会阻塞命令循环，导致期间点解析/搜索"一直转圈"）
                _spawn_bg("xhamster_batch_download", xhamster_batch_download(
                    command.get("urls", []),
                    command.get("options", {}),
                    command.get("items") or [],
                ))

            elif cmd == "cancel":
                logging.info("收到取消命令")
                emit({"event": "log", "type": "取消", "message": "收到取消请求"})

            else:
                logging.warning("未知命令: %s", cmd)

        except SystemExit as exc:
            # src/ 模块残留的 sys.exit 绝不能杀死后端进程（表现为前端"无法发送命令"）
            logging.exception("命令处理触发 SystemExit(%s)（src 模块调用了 sys.exit）", exc)
            emit({"event": "log", "type": "错误",
                  "message": f"命令处理内部退出({exc})，已拦截，后端继续运行"})
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
    except SystemExit as exc:
        # src/ 模块残留的 sys.exit() 会以 SystemExit 穿透 except Exception，
        # 静默杀死整个后端（前端表现为"无法发送命令"）。记录堆栈便于定位。
        logging.exception("SystemExit 逃逸（src 模块调用了 sys.exit）: %s", exc)
    except BaseException as exc:  # noqa: BLE001 —— GUI 后端绝不允许静默死亡
        logging.exception("致命错误(BaseException): %s", exc)


if __name__ == "__main__":
    main()
