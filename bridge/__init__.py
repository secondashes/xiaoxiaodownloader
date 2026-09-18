# -*- coding: utf-8 -*-
"""gui_bridge 拆分包。

加载语义（与原单文件完全等价）：
1. 子模块按原物理顺序 import —— 模块级语句（Session 创建、常量、默认设置等）
   的执行顺序与原单文件一致；
2. 每个子模块开头经 `_state.apply_prev` 注入此前已加载模块的全部名字
   （模块级语句的跨段引用与原单文件自上而下的可见性一致）；
3. 全部加载后 `_state.finalize` 做全量交叉注入 —— 函数体在调用时按各自模块
   命名空间解析名字，注入后每个模块都能看到全部名字，等价于原单文件的扁平
   全局作用域（oreno→iwara、DownloadManager→各站、command_loop→全部 等
   跨段引用无需任何改动）。

注意：新增跨段引用时不要在本文件加 import；按原物理顺序排在对应子模块里即可。
"""
from __future__ import annotations

from . import _state as _state

from . import _core as _m_core
_state.register(_m_core.__dict__)

from . import site_coomer as _m_site_coomer
_state.register(_m_site_coomer.__dict__)

from . import site_coomerst as _m_site_coomerst
_state.register(_m_site_coomerst.__dict__)

from . import site_fapello as _m_site_fapello
_state.register(_m_site_fapello.__dict__)

from . import site_coomerfans as _m_site_coomerfans
_state.register(_m_site_coomerfans.__dict__)

from . import site_leakedzone as _m_site_leakedzone
_state.register(_m_site_leakedzone.__dict__)

from . import site_pawchive as _m_site_pawchive
_state.register(_m_site_pawchive.__dict__)

from . import site_exhentai as _m_site_exhentai
_state.register(_m_site_exhentai.__dict__)

from . import site_twitter as _m_site_twitter
_state.register(_m_site_twitter.__dict__)

from . import site_iwara as _m_site_iwara
_state.register(_m_site_iwara.__dict__)

from . import site_hanime as _m_site_hanime
_state.register(_m_site_hanime.__dict__)

from . import site_xhamster as _m_site_xhamster
_state.register(_m_site_xhamster.__dict__)

from . import site_pixiv as _m_site_pixiv
_state.register(_m_site_pixiv.__dict__)

from . import site_oreno as _m_site_oreno
_state.register(_m_site_oreno.__dict__)

from . import site_asmr as _m_site_asmr
_state.register(_m_site_asmr.__dict__)

from . import site_fc2 as _m_site_fc2
_state.register(_m_site_fc2.__dict__)

from . import features_search as _m_features_search
_state.register(_m_features_search.__dict__)

from . import commands as _m_commands
_state.register(_m_commands.__dict__)

from . import media_proxy as _m_media_proxy
_state.register(_m_media_proxy.__dict__)

from . import download_manager as _m_download_manager
_state.register(_m_download_manager.__dict__)

from . import history as _m_history
_state.register(_m_history.__dict__)

from . import reverse_image as _m_reverse_image
_state.register(_m_reverse_image.__dict__)

from . import translate as _m_translate
_state.register(_m_translate.__dict__)

from . import github_update as _m_github_update
_state.register(_m_github_update.__dict__)

from . import accounts as _m_accounts
_state.register(_m_accounts.__dict__)

from . import site_javdb as _m_site_javdb
_state.register(_m_site_javdb.__dict__)

from . import google_oauth as _m_google_oauth
_state.register(_m_google_oauth.__dict__)

from . import sniffer as _m_sniffer
_state.register(_m_sniffer.__dict__)

from . import site_bilibili as _m_site_bilibili
_state.register(_m_site_bilibili.__dict__)

from . import webcapture as _m_webcapture
_state.register(_m_webcapture.__dict__)

from . import sniffer_proxy as _m_sniffer_proxy
_state.register(_m_sniffer_proxy.__dict__)

from . import bt_downloader as _m_bt_downloader
_state.register(_m_bt_downloader.__dict__)

from . import sniffer_tap as _m_sniffer_tap
_state.register(_m_sniffer_tap.__dict__)

from . import gs_accounts as _m_gs_accounts
_state.register(_m_gs_accounts.__dict__)
from . import gs_batch as _m_gs_batch
_state.register(_m_gs_batch.__dict__)

from . import command_loop as _m_command_loop
_state.register(_m_command_loop.__dict__)

# 全量交叉注入（后定义的名字对先定义模块的函数在调用期可见，与原单文件一致）
_MODS = [
    _m_core, _m_site_coomer, _m_site_coomerst, _m_site_coomerfans, _m_site_leakedzone, _m_site_fapello, _m_site_pawchive, _m_site_exhentai, _m_site_twitter,
    _m_site_iwara, _m_site_hanime, _m_site_xhamster, _m_site_pixiv, _m_site_oreno,
    _m_site_asmr, _m_features_search, _m_commands, _m_media_proxy, _m_download_manager,
    _m_history, _m_reverse_image, _m_translate, _m_github_update, _m_accounts,
    _m_site_javdb, _m_site_fc2, _m_google_oauth, _m_sniffer, _m_site_bilibili, _m_webcapture, _m_sniffer_proxy, _m_bt_downloader, _m_sniffer_tap, _m_gs_accounts, _m_gs_batch, _m_command_loop,
]

# 先清掉导入系统自动设置的子模块包属性，避免遮蔽扁平命名空间里的同名全局
# （如 command_loop 主循环函数 / download_manager 管理器实例）
for _m in _MODS:
    globals().pop(_m.__name__.rsplit(".", 1)[-1], None)

_state.finalize(_MODS, globals())

# 通用站点命令总表（模块化架构 m3）：注册了 SITE_COMMANDS 的站点模块（如 site_template
# 复制出的新站）自动进入分发；command_loop 在旧 if/elif 之前查此表。键必须带站点前缀。
_SITE_COMMANDS: dict = {}
for _m in _MODS:
    _sc = _m.__dict__.get("SITE_COMMANDS")
    if isinstance(_sc, dict):
        for _k, _fn in _sc.items():
            _SITE_COMMANDS[_k] = _fn
# 唯一名命令表（同模块多表场景：SITE_COMMANDS 名会被 finalize 互踩，见 site_coomerst）
for _m in _MODS:
    for _extra in ("COOMERST_SITE_COMMANDS", "FAPELLO_SITE_COMMANDS", "COOMERFANS_SITE_COMMANDS", "LZ_SITE_COMMANDS", "SNIF_COMMANDS", "SNIFP_COMMANDS", "SNIFT_COMMANDS", "GSAC_COMMANDS", "GSB_COMMANDS", "BILI_COMMANDS", "WEB_COMMANDS", "WEB_HLS_COMMANDS", "BT_COMMANDS"):
        _sc2 = _m.__dict__.get(_extra)
        if isinstance(_sc2, dict):
            for _k, _fn in _sc2.items():
                _SITE_COMMANDS[_k] = _fn
# finalize 已跑完，须显式注入各模块命名空间（command_loop 函数体按本模块 globals 解析）
for _m in _MODS:
    _m.__dict__["_SITE_COMMANDS"] = _SITE_COMMANDS
globals()["_SITE_COMMANDS"] = _SITE_COMMANDS

# 清理加载器别名（避免 _m_* 泄漏进导出名字集合）
del _m_core, _m_site_coomer, _m_site_coomerst, _m_site_coomerfans, _m_site_leakedzone, _m_site_fapello, _m_site_pawchive, _m_site_exhentai, _m_site_twitter
del _m_site_iwara, _m_site_hanime, _m_site_xhamster, _m_site_pixiv, _m_site_oreno
del _m_site_asmr, _m_features_search, _m_commands, _m_media_proxy, _m_download_manager
del _m_history, _m_reverse_image, _m_translate, _m_github_update, _m_accounts
del _m_site_javdb, _m_google_oauth, _m_sniffer, _m_sniffer_proxy, _m_bt_downloader, _m_sniffer_tap, _m_gs_accounts, _m_gs_batch, _m_command_loop
del _MODS, _m
globals().pop("_state", None)  # 状态器仅加载期使用，不进导出名字集合
