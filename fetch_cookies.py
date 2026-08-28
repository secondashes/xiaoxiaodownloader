# -*- coding: utf-8 -*-
"""Cookie 一键抓取工具（双击"抓取Cookie.bat"运行）

自动扫描本机所有浏览器的已登录网站 Cookie，按网站分类输出到本目录 cookies.txt。
支持来源：本工具内嵌浏览器（EX 视图）、Chrome、Edge、Brave、X-Spider（WebView2）、Firefox。

【维护准则】以后工具新增支持网站时，只需在下方 SITES 列表加一行即可，
格式：{"name": 显示名, "domains": [匹配域名], "important": [关键 Cookie 名]}。
"""
import base64
import ctypes
import ctypes.wintypes as wt
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone

# ============================ 站点配置（新增网站在这里加） ============================
SITES = [
    {
        "name": "ExHentai",
        "domains": ["exhentai.org", "e-hentai.org"],
        "important": ["ipb_member_id", "ipb_pass_hash", "igneous"],  # 关键 Cookie（判断登录用）
        "usage": "粘贴到 工具左侧 EX 站点设置的 Cookie 输入框（或网页版 document.cookie）",
    },
    {
        "name": "Pawchive",
        "domains": ["pawchive.pw"],
        "important": ["session"],
        "usage": "用于 工具左侧 Pawchive 登录（用户名+密码登录更方便，Cookie 可作备用）",
    },
    {
        "name": "X (Twitter)",
        "domains": ["x.com", "twitter.com"],
        "important": ["auth_token", "ct0"],
        "usage": "粘贴到 工具左侧 X 站点的 Cookie 输入框（必须含 auth_token 和 ct0）",
    },
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "cookies.txt")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
APPDATA = os.environ.get("APPDATA", "")


# ============================ DPAPI 解密（Windows 用户级密钥） ============================
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi_decrypt(data: bytes) -> bytes | None:
    """调用 Windows DPAPI 解密（CryptUnprotectData），失败返回 None。"""
    if not data:
        return None
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out),
    )
    if not ok:
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


# ============================ Chromium 系浏览器（Chrome/Edge/WebView2/Electron） ============================
# Chrome 127+ 的 v20 cookie 用 App-Bound 加密，密钥需通过浏览器自带的
# "提权服务"（elevation_service.exe，SYSTEM 权限 COM 服务）解密，
# 调用方在用户态即可完成（IElevator::DecryptData），无需管理员权限。
_ole32 = ctypes.WinDLL("ole32")
_oleaut32 = ctypes.WinDLL("oleaut32")
_oleaut32.SysAllocStringByteLen.restype = ctypes.c_void_p
_oleaut32.SysAllocStringByteLen.argtypes = [ctypes.c_char_p, ctypes.c_uint]
_oleaut32.SysStringByteLen.restype = ctypes.c_uint
_oleaut32.SysStringByteLen.argtypes = [ctypes.c_void_p]
_oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]

# 已知 Elevator COM 类（Chrome 各版本），配合注册表扫描兜底
_KNOWN_ELEVATOR_CLSIDS = [
    "{708860E0-F641-4611-8895-7D867DD3675B}",  # Chrome v136+
    "{708860E0-F641-4E4B-9633-E4D62A79E0BB}",  # Chrome 旧版
]
# IElevator 系接口（依次尝试）
_ELEVATOR_IIDS = [
    "{463ABECF-410D-407F-8AF5-0DF35A005CC8}",  # IElevatorChrome（新）
    "{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}",  # IElevator（新）
    "{C9C2B807-7731-4F34-81B7-44FF7779522B}",  # IElevator（旧）
]
# DecryptData 固定在 vtable 槽 5（IUnknown×3 + RunRecoveryCRXElevated + EncryptData 之后）
_ELEVATOR_DECRYPT_SLOT = 5


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_str(s: str) -> _GUID:
    s = s.strip("{}")
    d1, d2, d3, rest = s.split("-", 3)
    g = _GUID()
    g.Data1 = int(d1, 16)
    g.Data2 = int(d2, 16)
    g.Data3 = int(d3, 16)
    for i, b in enumerate(bytes.fromhex(rest.replace("-", ""))):
        g.Data4[i] = b
    return g


def _find_elevator_clsids(install_hint: str) -> list[str]:
    """扫描注册表 CLSID，找指向 elevation_service.exe 且路径匹配浏览器安装目录的 COM 类。"""
    found: list[str] = []
    try:
        import winreg
    except ImportError:
        return found
    hint = (install_hint or "").lower()
    for sub_path in (r"SOFTWARE\Classes\CLSID", r"SOFTWARE\Classes\WOW6432Node\CLSID"):
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
                i += 1
            except OSError:
                break
            try:
                with winreg.OpenKey(root, sub + r"\LocalServer32") as k:
                    path, _ = winreg.QueryValueEx(k, None)
                    low = str(path).lower()
                    if "elevation_service" in low and (not hint or hint in low):
                        found.append(sub)
            except OSError:
                continue
    return found


def _com_decrypt_app_bound_key(clsid_str: str, iid_str: str, ciphertext: bytes) -> bytes | None:
    """通过 Elevator COM 接口解密 app_bound_encrypted_key（用户态，无需管理员）。"""
    _ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED（重复初始化返回 S_FALSE，无害）
    clsid = _guid_from_str(clsid_str)
    iid = _guid_from_str(iid_str)
    obj = ctypes.c_void_p()
    # CLSCTX_LOCAL_SERVER = 4：启动/连接提权服务进程
    hr = _ole32.CoCreateInstance(
        ctypes.byref(clsid), None, 4, ctypes.byref(iid), ctypes.byref(obj),
    )
    if hr != 0 or not obj.value:
        return None
    try:
        bstr_ct = _oleaut32.SysAllocStringByteLen(ciphertext, len(ciphertext))
        if not bstr_ct:
            return None
        try:
            # vtable 槽 5 = DecryptData；注意参数个数随版本不同（新版 3 个，旧版 4 个带 protection_level）
            vtable = ctypes.cast(
                ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value,
                ctypes.POINTER(ctypes.c_void_p),
            )
            fn_addr = vtable[_ELEVATOR_DECRYPT_SLOT]
            plain = ctypes.c_void_p()
            err = wt.DWORD()
            # 变体 B（新版 3 参数）: DecryptData(BSTR ciphertext, BSTR* plaintext, DWORD* last_error)
            try:
                fn_b = ctypes.WINFUNCTYPE(
                    ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD),
                )(fn_addr)
                hr = fn_b(obj, bstr_ct, ctypes.byref(plain), ctypes.byref(err))
                if hr == 0 and plain.value:
                    n = _oleaut32.SysStringByteLen(plain)
                    data = ctypes.string_at(plain.value, n)
                    _oleaut32.SysFreeString(plain)
                    if data:
                        return data
            except Exception:
                pass
            # 变体 A（旧版 4 参数）: DecryptData(ProtectionLevel, BSTR, BSTR*, DWORD*)
            plain = ctypes.c_void_p()
            err = wt.DWORD()
            fn_a = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD),
            )(fn_addr)
            hr = fn_a(obj, 0, bstr_ct, ctypes.byref(plain), ctypes.byref(err))
            if hr == 0 and plain.value:
                n = _oleaut32.SysStringByteLen(plain)
                data = ctypes.string_at(plain.value, n)
                _oleaut32.SysFreeString(plain)
                if data:
                    return data
            return None
        finally:
            _oleaut32.SysFreeString(bstr_ct)
    finally:
        _ole32.CoDisconnectObject  # noqa: B018（占位注释：无显式断开接口，进程退出自动清理）


def get_app_bound_key(user_data_root: str) -> bytes | None:
    """获取 v20 App-Bound 密钥。

    Chrome 127~135：Elevator COM 接口（用户态即可，无需管理员）。
    Chrome 136+（COM 注册已移除）：需管理员 —— SYSTEM DPAPI + 用户 DPAPI +
    提权服务硬编码密钥解密（Chrome 137+ 为 CNG KSP + XOR）。
    """
    local_state = os.path.join(user_data_root, "Local State")
    try:
        with open(local_state, "r", encoding="utf-8") as f:
            encrypted_key = json.load(f)["os_crypt"]["app_bound_encrypted_key"]
    except (OSError, KeyError, ValueError):
        return None
    blob = base64.b64decode(encrypted_key)
    if blob[:4] != b"APPB":
        return None
    ciphertext = blob[4:]
    if not ciphertext:
        return None

    # 方式一：Elevator COM（老版本 Chrome，无需管理员）
    root_low = user_data_root.lower()
    hint = ""
    if "google\\chrome" in root_low or "google/chrome" in root_low:
        hint = "google\\chrome"
    elif "microsoft\\edge" in root_low:
        hint = "microsoft\\edge"
    elif "brave" in root_low:
        hint = "brave"
    clsids = list(_KNOWN_ELEVATOR_CLSIDS) + _find_elevator_clsids(hint)
    for clsid in clsids:
        for iid in _ELEVATOR_IIDS:
            key = _com_decrypt_app_bound_key(clsid, iid, ciphertext)
            if key and len(key) >= 32:
                return key[-32:]
    # 方式二：管理员路径（Chrome 136+）
    return _get_app_bound_key_admin(ciphertext)


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _enable_debug_privilege() -> bool:
    """提权当前进程令牌的 SeDebugPrivilege（打开 lsass 需要）。"""
    try:
        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("PrivilegeCount", wt.DWORD),
                        ("Luid", LUID), ("Attributes", wt.DWORD)]

        h_token = wt.HANDLE()
        if not ctypes.windll.advapi32.OpenProcessToken(
                ctypes.windll.kernel32.GetCurrentProcess(),
                0x00000020 | 0x0002,  # TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY
                ctypes.byref(h_token)):
            return False
        luid = LUID()
        if not ctypes.windll.advapi32.LookupPrivilegeValueW(
                None, "SeDebugPrivilege", ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES(1, luid, 0x2)  # SE_PRIVILEGE_ENABLED
        return bool(ctypes.windll.advapi32.AdjustTokenPrivileges(
            h_token, False, ctypes.byref(tp), 0, None, None))
    except Exception:
        return False


class _SystemImpersonation:
    """临时模拟 SYSTEM（借 lsass 令牌），用于 SYSTEM DPAPI 和 CNG KSP 密钥访问。"""

    def __enter__(self):
        import re
        import subprocess
        self._token = None
        if not _enable_debug_privilege():
            return self
        try:
            out = subprocess.run(
                ["tasklist", "/fi", "IMAGENAME eq lsass.exe", "/fo", "csv", "/nh"],
                capture_output=True,
            ).stdout.decode("utf-8", errors="replace")
            m = re.search(r'"(\d+)"', out)
            if not m:
                return self
            lsass_pid = int(m.group(1))
            h_process = ctypes.windll.kernel32.OpenProcess(0x0400, False, lsass_pid)
            if not h_process:
                return self
            try:
                h_token = wt.HANDLE()
                if not ctypes.windll.advapi32.OpenProcessToken(
                        h_process, 0x0002 | 0x0001 | 0x0008,  # DUP|QUERY|IMPERSONATE
                        ctypes.byref(h_token)):
                    return self
                dup = wt.HANDLE()
                # DuplicateTokenEx：SecurityImpersonation=2, TokenImpersonation=4
                if ctypes.windll.advapi32.DuplicateTokenEx(
                        h_token, 0x02000000, None, 2, 4, ctypes.byref(dup)):
                    self._token = dup
            finally:
                ctypes.windll.kernel32.CloseHandle(h_process)
            if self._token:
                ctypes.windll.advapi32.SetThreadToken(None, self._token)
        except Exception:
            pass
        return self

    def __exit__(self, *exc):
        if self._token:
            ctypes.windll.advapi32.SetThreadToken(None, None)
            ctypes.windll.kernel32.CloseHandle(self._token)
            self._token = None
        return False


def _dpapi_unprotect_as_system(data: bytes) -> bytes | None:
    """以 SYSTEM 身份执行 DPAPI 解密（App-Bound 密钥第一层）。

    优先借 lsass 令牌模拟；lsass 被 PPL 保护时回退到计划任务（schtasks SYSTEM）。
    """
    # 方式一：lsass 令牌模拟（无 PPL 的系统）
    with _SystemImpersonation():
        result = dpapi_decrypt(data)
    if result:
        return result
    # 方式二：计划任务以 SYSTEM 身份运行解密助手
    return _run_system_helper("dpapi", data)


# SYSTEM 助手脚本（以 SYSTEM 身份运行，完成 SYSTEM 级解密）
_SYSTEM_HELPER_SRC = r'''
# -*- coding: utf-8 -*-
import ctypes
import sys

mode, in_file, out_file = sys.argv[1], sys.argv[2], sys.argv[3]
data = open(in_file, "rb").read()

if mode == "dpapi":
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if ok:
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        open(out_file, "wb").write(out)
elif mode == "cng":
    # NCryptDecrypt via KSP key "Google Chromekey1"（Chrome 137+ flag 3）
    import ctypes.wintypes as wt

    # 注意：NCrypt API 为纯 Unicode 接口，导出函数名不带 W 后缀
    ncrypt = ctypes.WinDLL("ncrypt")
    ncrypt.NCryptOpenStorageProvider.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, wt.DWORD]
    ncrypt.NCryptOpenKey.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, wt.DWORD, wt.DWORD]
    ncrypt.NCryptDecrypt.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p,
        ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
    ]
    h_provider = ctypes.c_void_p()
    if ncrypt.NCryptOpenStorageProvider(
            ctypes.byref(h_provider), "Microsoft Software Key Storage Provider", 0) != 0:
        sys.exit(1)
    h_key = ctypes.c_void_p()
    if ncrypt.NCryptOpenKey(h_provider, ctypes.byref(h_key),
                            "Google Chromekey1", 0, 0) != 0:
        sys.exit(1)
    in_buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    cb = wt.DWORD(0)
    if ncrypt.NCryptDecrypt(h_key, in_buf, len(data), None, None, 0,
                            ctypes.byref(cb), 0x40) != 0:
        sys.exit(1)
    out_buf = (ctypes.c_ubyte * cb.value)()
    if ncrypt.NCryptDecrypt(h_key, in_buf, len(data), None, out_buf, cb.value,
                            ctypes.byref(cb), 0x40) != 0:
        sys.exit(1)
    open(out_file, "wb").write(bytes(out_buf[:cb.value]))
'''


def _run_system_helper(mode: str, data: bytes) -> bytes | None:
    """通过计划任务以 SYSTEM 身份运行解密助手（PPL 系统上借不到 lsass 令牌）。

    mode: "dpapi"（第一层解密）或 "cng"（Chrome 137+ flag 3 的 CNG KSP 密钥解密）。
    """
    import subprocess

    if not is_admin():
        return None
    task_name = "BunkrCookieSysHelper"
    try:
        base = tempfile.mkdtemp(prefix="ck_sys_")
        helper = os.path.join(base, "helper.py")
        in_file = os.path.join(base, "in.bin")
        out_file = os.path.join(base, "out.bin")
        run_cmd = os.path.join(base, "run.cmd")
        with open(helper, "w", encoding="utf-8") as f:
            f.write(_SYSTEM_HELPER_SRC)
        with open(in_file, "wb") as f:
            f.write(data)
        # 目录授权（SYSTEM 任务进程需要读写）
        with open(run_cmd, "w", encoding="utf-8") as f:
            f.write(f'@echo off\r\n"{sys.executable}" -X utf8 "{helper}" {mode} "{in_file}" "{out_file}"\r\n')
        subprocess.run(["icacls", base, "/grant", "Everyone:(OI)(CI)F"],
                       capture_output=True)
        # 创建并立即运行 SYSTEM 任务
        tr = run_cmd.replace('"', '\\"')
        for cmd in (
            f'schtasks /Create /F /TN {task_name} /SC ONCE /ST 00:00 /RU SYSTEM /TR "{tr}"',
            f"schtasks /Run /TN {task_name}",
        ):
            subprocess.run(cmd, shell=True, capture_output=True)
        # 等待结果（最多 20 秒）
        for _ in range(40):
            if os.path.exists(out_file):
                break
            time.sleep(0.5)
        subprocess.run(f"schtasks /Delete /F /TN {task_name}",
                       shell=True, capture_output=True)
        if os.path.exists(out_file):
            with open(out_file, "rb") as f:
                result = f.read()
            if result:
                return result
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            subprocess.run(f"schtasks /Delete /F /TN {task_name}",
                           shell=True, capture_output=True)
            shutil.rmtree(base, ignore_errors=True)
        except Exception:
            pass


def _cng_decrypt_chrome_key(encrypted: bytes) -> bytes | None:
    """用 CNG 密钥存储提供程序解密（'Google Chromekey1'，Chrome 137+ flag 3）。

    该密钥由提权服务以 SYSTEM 身份创建，需 SYSTEM 上下文访问。
    """
    # 优先 lsass 模拟
    with _SystemImpersonation():
        result = _cng_decrypt_chrome_key_direct(encrypted)
    if result:
        return result
    # 回退计划任务
    return _run_system_helper("cng", encrypted)


def _cng_decrypt_chrome_key_direct(encrypted: bytes) -> bytes | None:
    """直接调用 CNG 解密（需当前线程已是 SYSTEM）。"""
    # 注意：NCrypt API 为纯 Unicode 接口，导出函数名不带 W 后缀
    ncrypt = ctypes.WinDLL("ncrypt")
    ncrypt.NCryptOpenStorageProvider.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, wt.DWORD]
    ncrypt.NCryptOpenKey.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, wt.DWORD, wt.DWORD]
    ncrypt.NCryptDecrypt.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p,
        ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
    ]
    h_provider = ctypes.c_void_p()
    if ncrypt.NCryptOpenStorageProvider(
            ctypes.byref(h_provider), "Microsoft Software Key Storage Provider", 0) != 0:
        return None
    h_key = ctypes.c_void_p()
    if ncrypt.NCryptOpenKey(h_provider, ctypes.byref(h_key),
                            "Google Chromekey1", 0, 0) != 0:
        return None
    in_buf = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
    cb = wt.DWORD(0)
    # 第一次调用查询输出长度（NCRYPT_SILENT_FLAG = 0x40）
    if ncrypt.NCryptDecrypt(h_key, in_buf, len(encrypted), None, None, 0,
                            ctypes.byref(cb), 0x40) != 0:
        return None
    out_buf = (ctypes.c_ubyte * cb.value)()
    if ncrypt.NCryptDecrypt(h_key, in_buf, len(encrypted), None, out_buf, cb.value,
                            ctypes.byref(cb), 0x40) != 0:
        return None
    return bytes(out_buf[:cb.value])


# 提权服务（elevation_service.exe）内置密钥（版本间稳定，来自公开研究）
_ELEVATOR_AES_KEY = bytes.fromhex(
    "B31C6E241AC846728DA9C1FAC4936651CFFB944D143AB816276BCC6DA0284787")
_ELEVATOR_CHACHA_KEY = bytes.fromhex(
    "E98F37D7F4E1FA433D19304DC2258042090E2D1D7EEA7670D41F738D08729660")
_ELEVATOR_FLAG3_XOR_KEY = bytes.fromhex(
    "CCF8A1CEC56605B8517552BA1A2D061C03A29E90274FB2FCF59BA4B75C392390")


def _get_app_bound_key_admin(ciphertext: bytes) -> bytes | None:
    """管理员路径解密 App-Bound 密钥（Chrome 136+）。

    双层 DPAPI（SYSTEM → 用户）→ 按 flag 分支：
      flag 1: AES-GCM + 提权服务内置 AES 密钥
      flag 2: ChaCha20-Poly1305 + 内置密钥
      flag 3: CNG KSP 密钥解密 + XOR → AES 主密钥（Chrome 137+）
    """
    import io
    import struct

    if not is_admin():
        print("  [提示] Chrome 新版加密需要管理员权限（右键 bat 以管理员运行）")
        return None
    # 第一层：SYSTEM DPAPI
    blob = _dpapi_unprotect_as_system(ciphertext)
    if not blob:
        print("  [提示] SYSTEM DPAPI 解密失败")
        return None
    # 第二层：用户 DPAPI
    blob = dpapi_decrypt(blob)
    if not blob:
        print("  [提示] 用户 DPAPI 解密失败")
        return None
    # 解析结构：[header_len(4) | header | content_len(4) | flag(1) | ...]
    try:
        buffer = io.BytesIO(blob)
        header_len = struct.unpack("<I", buffer.read(4))[0]
        buffer.read(header_len)
        content_len = struct.unpack("<I", buffer.read(4))[0]
        content = buffer.read(content_len)
        flag = content[0]
    except (struct.error, IndexError):
        print("  [提示] 密钥结构解析失败")
        return None

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    try:
        if flag == 1:
            cipher = AESGCM(_ELEVATOR_AES_KEY)
            iv, ct, tag = content[1:13], content[13:45], content[45:61]
        elif flag == 2:
            cipher = ChaCha20Poly1305(_ELEVATOR_CHACHA_KEY)
            iv, ct, tag = content[1:13], content[13:45], content[45:61]
        elif flag == 3:
            # [flag(1) | encrypted_aes_key(32) | iv(12) | ciphertext(32) | tag(16)]
            enc_key = content[1:33]
            iv, ct, tag = content[33:45], content[45:77], content[77:93]
            dec_key = _cng_decrypt_chrome_key(enc_key)
            if not dec_key:
                print("  [提示] CNG KSP 密钥解密失败")
                return None
            master = bytes(a ^ b for a, b in zip(dec_key, _ELEVATOR_FLAG3_XOR_KEY))
            cipher = AESGCM(master)
        else:
            print(f"  [提示] 未知密钥格式 flag={flag}（浏览器版本过新）")
            return None
        return cipher.decrypt(iv, ct + tag, None)
    except Exception as exc:
        print(f"  [提示] App-Bound 密钥解密失败: {exc}")
        return None


def get_chromium_key(user_data_root: str) -> bytes | None:
    """从 Chromium 的 Local State 提取 Cookie 加密密钥（DPAPI 解密 encrypted_key）。"""
    local_state = os.path.join(user_data_root, "Local State")
    try:
        with open(local_state, "r", encoding="utf-8") as f:
            encrypted_key = json.load(f)["os_crypt"]["encrypted_key"]
        key = dpapi_decrypt(base64.b64decode(encrypted_key)[5:])  # 前 5 字节是 "DPAPI" 前缀
        if key and len(key) == 32:
            return key
    except (OSError, KeyError, ValueError):
        pass
    return None


def decrypt_chromium_value(v10_key: bytes | None, v20_key: bytes | None,
                           encrypted_value: bytes) -> str | None:
    """解密单条 Chromium Cookie（v10/v11 = DPAPI key + AES-GCM；v20 = App-Bound 加密）。"""
    if not encrypted_value:
        return ""
    prefix = encrypted_value[:3]
    if prefix == b"v20":
        # Chrome 127+ App-Bound：密钥来自提权服务
        if not v20_key:
            return None
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            plain = AESGCM(v20_key).decrypt(encrypted_value[3:15], encrypted_value[15:], None)
        except Exception:
            return None
        # Chrome 明文前 32 字节是域名哈希，需剥离；其他内核浏览器无前缀
        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError:
            if len(plain) > 32:
                return plain[32:].decode("utf-8", errors="replace")
            return plain.decode("utf-8", errors="replace")
    if prefix in (b"v10", b"v11"):
        if not v10_key:
            return None
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:]
            plain = AESGCM(v10_key).decrypt(nonce, ciphertext, None)
            return plain.decode("utf-8", errors="replace")
        except Exception:
            return None  # 解密失败（密钥不符或新版加密）
    # 老 Chromium 直接 DPAPI
    plain = dpapi_decrypt(encrypted_value)
    return plain.decode("utf-8", errors="replace") if plain else None


def find_chromium_profiles(user_data_root: str) -> list[str]:
    """枚举 Chromium 用户数据根目录下的全部 profile（Default/Profile N/Partitions/*）。"""
    profiles = []
    patterns = [
        os.path.join(user_data_root, "Default"),
        os.path.join(user_data_root, "Profile *"),
        os.path.join(user_data_root, "Partitions", "*"),
    ]
    for pat in patterns:
        for p in glob.glob(pat):
            if os.path.isdir(p):
                # 有 Cookies 文件的才算（Network\Cookies 新版 / Cookies 老版）
                if os.path.exists(os.path.join(p, "Network", "Cookies")) or \
                        os.path.exists(os.path.join(p, "Cookies")):
                    profiles.append(p)
    return profiles


def read_chromium_cookies(user_data_root: str) -> dict[str, dict[str, str]]:
    """读取一个 Chromium 数据根目录下全部 profile 的 cookie。

    返回 {域名匹配键: {cookie名: 值}}，解密失败的跳过。
    """
    domain_cookies: dict[str, dict[str, str]] = {}
    # 先收集全部加密行（v20 cookie 需要先确认存在才去拿 App-Bound 密钥）
    all_rows: list[tuple[str, str, bytes]] = []
    for profile in find_chromium_profiles(user_data_root):
        db = os.path.join(profile, "Network", "Cookies")
        if not os.path.exists(db):
            db = os.path.join(profile, "Cookies")
        if not os.path.exists(db):
            continue
        # 复制到临时目录再读（浏览器运行时会锁库）
        tmp_dir = tempfile.mkdtemp(prefix="ck_")
        tmp_db = os.path.join(tmp_dir, "Cookies")
        try:
            shutil.copy2(db, tmp_db)
            wal = db + "-wal"
            if os.path.exists(wal):
                shutil.copy2(wal, tmp_db + "-wal")
            conn = sqlite3.connect(tmp_db)
            try:
                rows = conn.execute(
                    "SELECT host_key, name, encrypted_value FROM cookies "
                    "WHERE expires_utc > ? OR expires_utc = 0",
                    (int((time.time() + 11644473600) * 1_000_000),),
                ).fetchall()
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            continue
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        all_rows.extend(rows)

    if not all_rows:
        return {}
    v10_key = get_chromium_key(user_data_root)
    # 有 v20 cookie 才通过提权服务获取 App-Bound 密钥（COM 调用较慢）
    has_v20 = any((ev[:3] == b"v20" if ev else False) for _, _, ev in all_rows)
    v20_key = get_app_bound_key(user_data_root) if has_v20 else None
    if has_v20 and not v20_key:
        print("  [提示] 检测到 Chrome v20 加密 Cookie，但提权服务解密失败（浏览器可能刚更新）")

    for host_key, name, encrypted_value in all_rows:
        value = decrypt_chromium_value(v10_key, v20_key, encrypted_value)
        if value is None:
            continue  # 解密失败
        domain_cookies.setdefault(host_key.lower(), {})[name] = value
    return domain_cookies


# ============================ Firefox ============================
def read_firefox_cookies() -> dict[str, dict[str, str]]:
    """读取 Firefox 全部 profile 的 cookie（明文存储，直接读）。"""
    domain_cookies: dict[str, dict[str, str]] = {}
    profiles_dir = os.path.join(APPDATA, r"Mozilla\Firefox\Profiles")
    for profile in glob.glob(os.path.join(profiles_dir, "*")):
        db = os.path.join(profile, "cookies.sqlite")
        if not os.path.exists(db):
            continue
        tmp_dir = tempfile.mkdtemp(prefix="ff_")
        tmp_db = os.path.join(tmp_dir, "cookies.sqlite")
        try:
            shutil.copy2(db, tmp_db)
            conn = sqlite3.connect(tmp_db)
            try:
                rows = conn.execute(
                    "SELECT host, name, value FROM moz_cookies "
                    "WHERE expiry > ? OR expiry = 0",
                    (int(time.time()),),
                ).fetchall()
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            continue
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        for host, name, value in rows:
            if value:
                domain_cookies.setdefault(host.lower(), {})[name] = value
    return domain_cookies


# ============================ 主流程 ============================
def domain_matches(host: str, domains: list[str]) -> bool:
    """host（如 .exhentai.org）是否属于目标站点域名组。"""
    host = host.lower().lstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def collect_site_cookies(domain_cookies: dict[str, dict[str, str]], site: dict) -> dict[str, str]:
    """从来源的全部 cookie 中挑出属于目标站点的。"""
    merged: dict[str, str] = {}
    for host, cookies in domain_cookies.items():
        if domain_matches(host, site["domains"]):
            merged.update(cookies)
    return merged


def score_cookies(cookies: dict[str, str], site: dict) -> int:
    """给一组 cookie 打分：关键 Cookie 每个记 10 分，普通每个 1 分（用于选最佳来源）。"""
    score = sum(10 for k in site["important"] if k in cookies)
    return score + len(cookies)


# ============================ --json 模式（GUI 一键抓取调用） ============================
def run_json_mode(site_query: str) -> int:
    """抓取指定站点，stdout 只输出一行 JSON（供 Electron GUI 调用，不写 cookies.txt）。"""
    import contextlib
    import io
    import subprocess

    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    site = next((s for s in SITES if site_query.lower() in s["name"].lower()), None)
    if site is None:
        print(json.dumps({"ok": False, "error": f"未知站点: {site_query}"}, ensure_ascii=False))
        return 1

    # 依赖检查（静默安装，不污染 JSON 输出）
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        ret = subprocess.run(
            [sys.executable, "-m", "pip", "install", "cryptography",
             "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "--quiet"],
            capture_output=True,
        )
        if ret.returncode != 0:
            print(json.dumps({"ok": False, "error": "缺少依赖 cryptography，请手动执行: pip install cryptography"},
                             ensure_ascii=False))
            return 1

    quiet = contextlib.redirect_stdout(io.StringIO())
    sources: list[tuple[str, dict[str, dict[str, str]]]] = []
    chromium_roots = [
        ("本工具内嵌浏览器", os.path.join(APPDATA, "bunkr-downloader-gui")),
        ("Chrome", os.path.join(LOCALAPPDATA, r"Google\Chrome\User Data")),
        ("Edge", os.path.join(LOCALAPPDATA, r"Microsoft\Edge\User Data")),
        ("Brave", os.path.join(LOCALAPPDATA, r"BraveSoftware\Brave-Browser\User Data")),
        ("X-Spider", os.path.join(BASE_DIR, "X-Spider", "EBWebView")),
    ]
    with quiet:
        for label, root in chromium_roots:
            if not os.path.isdir(root):
                continue
            try:
                cookies = read_chromium_cookies(root)
            except Exception:
                continue
            if sum(len(v) for v in cookies.values()):
                sources.append((label, cookies))
        try:
            ff_cookies = read_firefox_cookies()
            if sum(len(v) for v in ff_cookies.values()):
                sources.append(("Firefox", ff_cookies))
        except Exception:
            pass

    best: tuple[str, dict[str, str]] | None = None
    for label, domain_cookies in sources:
        cookies = collect_site_cookies(domain_cookies, site)
        if not cookies:
            continue
        if best is None or score_cookies(cookies, site) > score_cookies(best[1], site):
            best = (label, cookies)

    if not best or not any(k in best[1] for k in site["important"]):
        print(json.dumps({
            "ok": False,
            "error": "本机浏览器未找到该站点的登录 Cookie。请先在浏览器登录该网站后重试；"
                     "Chrome 新版加密可能需要管理员权限（右键管理员运行 抓取Cookie.bat）",
        }, ensure_ascii=False))
        return 1

    label, cookies = best
    print(json.dumps({
        "ok": True,
        "site": site["name"],
        "source": label,
        "cookie_str": "; ".join(f"{k}={v}" for k, v in cookies.items()),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    # 控制台中文输出
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("  Cookie 一键抓取工具")
    print("  扫描本机浏览器的已登录网站，输出到 cookies.txt")
    print("=" * 60)

    # 依赖检查
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        print("\n缺少依赖 cryptography，正在自动安装（国内镜像）...")
        ret = os.system(
            f'"{sys.executable}" -m pip install cryptography -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet'
        )
        if ret != 0:
            print("安装失败！请手动执行: pip install cryptography")
            return 1

    # Chromium 系来源（顺序即展示顺序；每个站点自动选"分数最高"的来源）
    sources: list[tuple[str, dict[str, dict[str, str]]]] = []
    chromium_roots = [
        ("本工具内嵌浏览器", os.path.join(APPDATA, "bunkr-downloader-gui")),
        ("Chrome", os.path.join(LOCALAPPDATA, r"Google\Chrome\User Data")),
        ("Edge", os.path.join(LOCALAPPDATA, r"Microsoft\Edge\User Data")),
        ("Brave", os.path.join(LOCALAPPDATA, r"BraveSoftware\Brave-Browser\User Data")),
        ("X-Spider", os.path.join(BASE_DIR, "X-Spider", "EBWebView")),
    ]
    for label, root in chromium_roots:
        if os.path.isdir(root):
            print(f"\n正在扫描 {label} ...")
            try:
                cookies = read_chromium_cookies(root)
            except Exception as exc:
                print(f"  扫描失败: {exc}")
                continue
            total = sum(len(v) for v in cookies.values())
            print(f"  解密 {total} 条 Cookie")
            if total:
                sources.append((label, cookies))

    # Firefox
    print("\n正在扫描 Firefox ...")
    try:
        ff_cookies = read_firefox_cookies()
        total = sum(len(v) for v in ff_cookies.values())
        print(f"  读取 {total} 条 Cookie")
        if total:
            sources.append(("Firefox", ff_cookies))
    except Exception as exc:
        print(f"  扫描失败: {exc}")

    # 每个站点选最佳来源
    lines: list[str] = []
    lines.append("Cookie 抓取结果")
    lines.append(f"抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    found_any = False
    for site in SITES:
        best: tuple[str, dict[str, str]] | None = None
        for label, domain_cookies in sources:
            cookies = collect_site_cookies(domain_cookies, site)
            if not cookies:
                continue
            if best is None or score_cookies(cookies, site) > score_cookies(best[1], site):
                best = (label, cookies)
        lines.append("=" * 70)
        if best:
            found_any = True
            label, cookies = best
            key_hits = [k for k in site["important"] if k in cookies]
            lines.append(f"网站: {site['name']}  (来源: {label})")
            if key_hits:
                lines.append(f"登录状态: 检测到关键 Cookie {', '.join(key_hits)}")
            else:
                lines.append("登录状态: 未见关键 Cookie（可能未登录，抓到的不一定可用）")
            lines.append("-" * 70)
            lines.append("; ".join(f"{k}={v}" for k, v in cookies.items()))
            lines.append(f"用途: {site['usage']}")
        else:
            lines.append(f"网站: {site['name']}")
            lines.append("未找到 Cookie（本机浏览器没有该站点的登录记录）")
        lines.append("")

    if not found_any:
        print("\n没有抓到任何目标网站的 Cookie！")
        print("请先在浏览器登录对应网站，再运行本工具。")
        lines.append("（本次没有抓到任何目标网站的 Cookie）")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print()
    print("=" * 60)
    print(f"完成！结果已保存到: {OUTPUT_FILE}")
    print("用记事本打开 cookies.txt，按网站标题复制对应 Cookie 行即可。")
    print("（如显示乱码请用记事本/VS Code 打开，编码为 UTF-8）")
    return 0


if __name__ == "__main__":
    # --json <站点名>：GUI 一键抓取模式（stdout 输出纯 JSON）
    if len(sys.argv) >= 3 and sys.argv[1] == "--json":
        sys.exit(run_json_mode(sys.argv[2]))
    sys.exit(main())
