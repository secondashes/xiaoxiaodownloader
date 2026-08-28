# -*- coding: utf-8 -*-
"""临时测试2：调试 COM。用完即删。"""
import ctypes
import json, base64, winreg
import fetch_cookies as fc
import ctypes.wintypes as wt

# 1. 查 {0EDEAF3C...} 的 LocalServer32 路径
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\CLSID\{0EDEAF3C-D36E-4E7E-9467-900B977DC4FF}\LocalServer32") as k:
    print("LocalServer32:", winreg.QueryValueEx(k, None)[0])

root = fc.os.path.join(fc.LOCALAPPDATA, r"Google\Chrome\User Data")
with open(fc.os.path.join(root, "Local State"), "r", encoding="utf-8") as f:
    ls = json.load(f)
blob = base64.b64decode(ls["os_crypt"]["app_bound_encrypted_key"])
ct = blob[4:]

fc._ole32.CoInitializeEx(None, 0x2)
clsid = fc._guid_from_str("{0EDEAF3C-D36E-4E7E-9467-900B977DC4FF}")
obj = ctypes.c_void_p()
for iid_str in fc._ELEVATOR_IIDS + ["{B88C45B9-8825-4629-B83E-77CC67D9CEED}"]:
    iid = fc._guid_from_str(iid_str)
    hr = fc._ole32.CoCreateInstance(ctypes.byref(clsid), None, 4, ctypes.byref(iid), ctypes.byref(obj))
    print(f"CoCreateInstance {iid_str}: hr=0x{hr & 0xFFFFFFFF:08X}, obj={'yes' if obj.value else 'no'}")
    if hr != 0 or not obj.value:
        continue
    # 成功创建 → 尝试槽 5 两种签名（打印 hr）
    bstr_ct = fc._oleaut32.SysAllocStringByteLen(ct, len(ct))
    vtable = ctypes.cast(
        ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value,
        ctypes.POINTER(ctypes.c_void_p),
    )
    fn_addr = vtable[5]
    plain = ctypes.c_void_p()
    err = wt.DWORD()
    fn_b = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD))(fn_addr)
    hr = fn_b(obj, bstr_ct, ctypes.byref(plain), ctypes.byref(err))
    print(f"  变体B hr=0x{hr & 0xFFFFFFFF:08X} err={err.value} plain={'yes' if plain.value else 'no'}")
    if plain.value:
        n = fc._oleaut32.SysStringByteLen(plain)
        data = ctypes.string_at(plain.value, n)
        print(f"  明文 {n} 字节: {data[:16].hex()}...")
