# -*- coding: utf-8 -*-
"""手动抓取 · 透明重定向（WinDivert）——强制抓取 QQ/微信等不走系统代理的聊天工具流量。

原理：QQ/微信等应用的网络栈不走系统代理（mitm 模式抓不到），且大量使用 QUIC(UDP 443)。
本模块在网络层做两件事（WinDivert 驱动，需管理员）：
1. 出站 TCP 443 全部改道到本地 mitm（127.0.0.1:18081），映射表记录原目标 IP；
   回程包把源地址伪装回原目标 IP:443（对应用透明）
2. 出站 UDP 443（QUIC）直接丢弃 → 应用被迫回落 TCP 443 → 落进 mitm
域名识别不靠 IP 反查：TLS ClientHello 的 SNI（mitm 的 sni_callback 已动态签证书），
HTTP 层用 Host 头。

安全：仅重定向 443 端口；映射表容量上限；关闭 tap 时全部恢复。
命名：SNIFT_ 前缀唯一（bridge finalize 同名互踩坑）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（emit/logging/…）

import threading

# ============================
# 0. 状态
# ============================
_snift_threads = []          # [Thread, Thread]
_snift_stop = threading.Event()
_snift_lock = threading.RLock()  # RLock：_snift_cmd_on 锁内调用 _snift_emit 会再次抢锁，Lock（非重入）会自死锁
_snift_map = {}              # "srcIp:srcPort" -> "origDstIp"（回程伪装源地址用）
_SNIFT_MAP_MAX = 4096


def _snift_emit(payload: dict) -> None:
    with _snift_lock:
        try:
            emit(payload)  # noqa: F821
        except Exception as exc:
            logging.warning("sniffer_tap emit 失败: %s", exc)


def _snift_running() -> bool:
    return any(t.is_alive() for t in _snift_threads)


# ============================
# 1. 重定向工作线程
# ============================
def _snift_redirect_loop(port: int):
    """出站 443 → 本地 mitm；回程 18081 → 伪装回原目标。"""
    import pydivert
    # 回程包（mitm 发给客户端的响应）源端口=18081 → 源地址伪装回原目标；映射表无记录的放行原样
    flt = (
        "outbound and tcp and tcp.DstPort == 443 and ip.DstAddr != 127.0.0.1 "
        "or inbound and tcp and tcp.SrcPort == 443 "
        "or outbound and tcp and tcp.SrcPort == {port}"
    ).format(port=port)
    with pydivert.WinDivert(flt) as w:
        while not _snift_stop.is_set():
            try:
                packet = w.recv()
            except Exception:
                break
            try:
                if packet.is_outbound:
                    if packet.dst_port == 443:
                        # 出站新连接：记录映射 → 改道本地 mitm
                        key = f"{packet.src_addr}:{packet.src_port}"
                        with _snift_lock:
                            if len(_snift_map) < _SNIFT_MAP_MAX:
                                _snift_map[key] = packet.dst_addr
                        packet.dst_addr = "127.0.0.1"
                        packet.dst_port = port
                    elif packet.src_port == port:
                        # mitm → 客户端的回程：把源伪装回原目标 IP（端口本来就是 443 的对端）
                        key = f"{packet.dst_addr}:{packet.dst_port}"
                        with _snift_lock:
                            orig = _snift_map.get(key)
                        if orig:
                            packet.src_addr = orig
                else:
                    # 入站包：原目标 IP 发来的响应——真实会话里不可能出现在 443 伪连接上，
                    # 放行兜底（不干扰其它连接）
                    pass
                w.send(packet)
            except Exception:
                continue


def _snift_quic_drop_loop():
    """出站 UDP 443（QUIC）直接丢弃 → 应用回落 TCP 443 → 进 mitm。"""
    import pydivert
    with pydivert.WinDivert("outbound and udp and udp.DstPort == 443") as w:
        while not _snift_stop.is_set():
            try:
                w.recv()
            except Exception:
                break
            # 不 send = 丢弃


def _snift_cleanup_map_loop():
    """映射表定期清防膨胀（半开连接残留；活跃条目重连会重填）。"""
    while not _snift_stop.is_set():
        _snift_stop.wait(120)
        if _snift_stop.is_set():
            return
        with _snift_lock:
            if len(_snift_map) > 512:
                _snift_map.clear()


# ============================
# 2. GS 命令
# ============================
async def _snift_cmd_on(command: dict) -> None:
    def _do():
        with _snift_lock:
            if _snift_running():
                _snift_emit({"event": "sniff_tap_state", "on": True})
                return
            _snift_stop.clear()
        port = int(command.get("port") or 18081)
        t1 = threading.Thread(target=_snift_redirect_loop, args=(port,), daemon=True)
        t2 = threading.Thread(target=_snift_quic_drop_loop, daemon=True)
        t3 = threading.Thread(target=_snift_cleanup_map_loop, daemon=True)
        t1.start(); t2.start(); t3.start()
        with _snift_lock:
            globals()["_snift_threads"] = [t1, t2, t3]
        time.sleep(1.0)
        alive = all(t.is_alive() for t in (t1, t2))
        _snift_emit({"event": "sniff_tap_state", "on": alive,
                     "message": "透明重定向已开启（443→mitm，QUIC 已阻断）" if alive else "透明重定向启动失败（需管理员权限）"})
    await asyncio.to_thread(_do)


async def _snift_cmd_off(command: dict) -> None:
    def _do():
        _snift_stop.set()
        with _snift_lock:
            globals()["_snift_threads"] = []
            _snift_map.clear()
        time.sleep(0.6)
        _snift_emit({"event": "sniff_tap_state", "on": False,
                     "message": "透明重定向已关闭"})
    await asyncio.to_thread(_do)


async def _snift_cmd_status(command: dict) -> None:
    with _snift_lock:
        on = _snift_running()
    _snift_emit({"event": "sniff_tap_state", "on": on})


# 命令表：唯一名，由 bridge/__init__.py 显式并入总表
SNIFT_COMMANDS = {
    "sniff_tap_on": _snift_cmd_on,
    "sniff_tap_off": _snift_cmd_off,
    "sniff_tap_status": _snift_cmd_status,
}
