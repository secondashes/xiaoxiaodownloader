# -*- coding: utf-8 -*-
"""临时测试：调试 Chrome Elevator COM 解密。用完即删。"""
import fetch_cookies as fc
import ctypes

root = fc.os.path.join(fc.LOCALAPPDATA, r"Google\Chrome\User Data")
key = fc.get_app_bound_key(root)
print("get_app_bound_key:", "OK len=%d" % len(key) if key else "FAIL")

# 手动逐步调试
import json, base64, winreg
with open(fc.os.path.join(root, "Local State"), "r", encoding="utf-8") as f:
    ls = json.load(f)
blob = base64.b64decode(ls["os_crypt"]["app_bound_encrypted_key"])
print("APPB prefix:", blob[:4])
ct = blob[4:]

# 注册表里 Chrome 的 elevator CLSID
found = fc._find_elevator_clsids("google\\chrome")
print("注册表找到的 CLSID:", found)
# 也看看不带过滤的
all_el = fc._find_elevator_clsids("")
print("全部 elevation_service CLSID:", all_el)

fc._ole32.CoInitializeEx(None, 0x2)
for clsid in set(fc._KNOWN_ELEVATOR_CLSIDS + found):
    for iid in fc._ELEVATOR_IIDS:
        try:
            data = fc._com_decrypt_app_bound_key(clsid, iid, ct)
        except Exception as e:
            print(f"{clsid} x {iid}: EXC {e}")
            continue
        print(f"{clsid} x {iid}: {'OK len=%d %s' % (len(data), data[:8].hex()) if data else 'None'}")
