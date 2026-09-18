# -*- coding: utf-8 -*-
"""综合资源站点 · 通用账号系统（登录框 / 保存密码 / 多账号选择）。

四站（coomerst/coomerfans/fapello/leakedzone）均无传统账号体系，本模块提供统一的
"会话凭据档案"：用户可为每站保存多份命名凭据（账号名 + Cookie + 可选密码），
选择激活即生效——leakedzone 激活 = leakedzone_set_cookies(cookie, 现存 UA)；
其余三站免登录，激活仅作档案标记（cookie 留档备用）。

存储：cache/gs_accounts.json  {site: {"accounts": [{name, cookie, password, save_password}], "active": name}}
命名：GSAC_ 前缀唯一（bridge finalize 同名互踩坑）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字

import asyncio
import json
import logging
from pathlib import Path

GSAC_STORE = Path("cache/gs_accounts.json")
GSAC_SITES = ("coomerst", "coomerfans", "fapello", "leakedzone")
_gsac_lock = asyncio.Lock()


def _gsac_load() -> dict:
    try:
        return json.loads(GSAC_STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gsac_save(data: dict) -> None:
    GSAC_STORE.parent.mkdir(parents=True, exist_ok=True)
    GSAC_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _gsac_site(data: dict, site: str) -> dict:
    return data.setdefault(site, {"accounts": [], "active": ""})


def _gsac_public(acc: dict) -> dict:
    return {
        "name": acc.get("name", ""),
        "has_cookie": bool(acc.get("cookie")),
        "cookie_preview": (acc.get("cookie") or "")[:24],
        "has_password": bool(acc.get("password")),
        "active": False,  # 由调用方按 site.active 回填
    }


def _gsac_emit_state(site: str, data: dict) -> None:
    site_data = _gsac_site(data, site)
    accounts = []
    for acc in site_data["accounts"]:
        pub = _gsac_public(acc)
        pub["active"] = acc.get("name") == site_data.get("active")
        accounts.append(pub)
    emit({"event": "gs_account_list", "site": site, "accounts": accounts})  # noqa: F821


async def _gsac_cmd_save(command: dict) -> None:
    async def _do():
        site = str(command.get("site") or "")
        name = str(command.get("name") or "").strip()
        if site not in GSAC_SITES or not name:
            emit({"event": "gs_account_result", "ok": False,  # noqa: F821
                  "message": "站点无效或账号名为空"})
            return
        async with _gsac_lock:
            data = _gsac_load()
            site_data = _gsac_site(data, site)
            cookie = str(command.get("cookie") or "").strip()
            save_pwd = bool(command.get("save_password"))
            password = str(command.get("password") or "") if save_pwd else ""
            for acc in site_data["accounts"]:
                if acc.get("name") == name:
                    if cookie:
                        acc["cookie"] = cookie
                    if save_pwd or password:
                        acc["password"] = password
                    acc["save_password"] = save_pwd
                    break
            else:
                site_data["accounts"].append({
                    "name": name, "cookie": cookie, "password": password,
                    "save_password": save_pwd,
                })
            # 首个账号自动激活
            if not site_data.get("active"):
                site_data["active"] = name
            _gsac_save(data)
        # leakedzone：保存即问是否激活（激活走 switch；这里仅提示）
        logging.info("gs_account_save %s/%s", site, name)
        async with _gsac_lock:
            data = _gsac_load()
        _gsac_emit_state(site, data)
        emit({"event": "gs_account_result", "ok": True,  # noqa: F821
              "message": f"账号「{name}」已保存（{site}）"})
    await asyncio.to_thread(_do)


async def _gsac_cmd_list(command: dict) -> None:
    async def _do():
        site = str(command.get("site") or "")
        if site not in GSAC_SITES:
            return
        async with _gsac_lock:
            data = _gsac_load()
        _gsac_emit_state(site, data)
    await asyncio.to_thread(_do)


async def _gsac_cmd_switch(command: dict) -> None:
    async def _do():
        site = str(command.get("site") or "")
        name = str(command.get("name") or "").strip()
        if site not in GSAC_SITES:
            return
        async with _gsac_lock:
            data = _gsac_load()
            site_data = _gsac_site(data, site)
            acc = next((a for a in site_data["accounts"] if a.get("name") == name), None)
            if not acc:
                emit({"event": "gs_account_result", "ok": False,  # noqa: F821
                      "message": f"账号「{name}」不存在"})
                return
            site_data["active"] = name
            _gsac_save(data)
            cookie = acc.get("cookie") or ""
        # leakedzone：激活即把该账号 cookie 灌入后端过盾会话（UA 沿用已存档值）
        if site == "leakedzone" and cookie:
            await leakedzone_set_cookies(cookie)  # noqa: F821
            leakedzone_check_login(True)  # noqa: F821
            emit({"event": "gs_account_result", "ok": True,  # noqa: F821
                  "message": f"已切换到账号「{name}」并重灌过盾会话"})
        else:
            emit({"event": "gs_account_result", "ok": True,  # noqa: F821
                  "message": f"已选择账号「{name}」"})
        async with _gsac_lock:
            data = _gsac_load()
        _gsac_emit_state(site, data)
    await asyncio.to_thread(_do)


async def _gsac_cmd_delete(command: dict) -> None:
    async def _do():
        site = str(command.get("site") or "")
        name = str(command.get("name") or "").strip()
        async with _gsac_lock:
            data = _gsac_load()
            site_data = _gsac_site(data, site)
            site_data["accounts"] = [a for a in site_data["accounts"] if a.get("name") != name]
            if site_data.get("active") == name:
                site_data["active"] = ""
            _gsac_save(data)
        _gsac_emit_state(site, data)
        emit({"event": "gs_account_result", "ok": True,  # noqa: F821
              "message": f"账号「{name}」已删除"})
    await asyncio.to_thread(_do)


# 命令表：唯一名，由 bridge/__init__.py 显式并入总表
GSAC_COMMANDS = {
    "gs_account_save": _gsac_cmd_save,
    "gs_account_list": _gsac_cmd_list,
    "gs_account_switch": _gsac_cmd_switch,
    "gs_account_delete": _gsac_cmd_delete,
}
