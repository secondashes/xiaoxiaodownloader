# -*- coding: utf-8 -*-
"""临时测试3：找 Chrome 的 elevation service COM 注册。用完即删。"""
import os
import winreg

# 1. Chrome 安装位置 + elevation_service.exe 是否存在
for p in [
    r"C:\Program Files\Google\Chrome\Application",
    r"C:\Program Files (x86)\Google\Chrome\Application",
    os.path.join(os.environ["LOCALAPPDATA"], r"Google\Chrome\Application"),
]:
    if os.path.isdir(p):
        subs = [d for d in os.listdir(p) if d[0].isdigit()]
        for v in subs:
            exe = os.path.join(p, v, "elevation_service.exe")
            print(f"Chrome {v}: elevation_service.exe {'存在' if os.path.exists(exe) else '不存在'}")

# 2. 已知 CLSID 在 HKLM / HKCU 的注册情况
known = [
    "{708860E0-F641-4611-8895-7D867DD3675B}",
    "{708860E0-F641-4E4B-9633-E4D62A79E0BB}",
]
for hive, hname in [(winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")]:
    for clsid in known:
        for view in [0, winreg.KEY_WOW64_32KEY]:
            try:
                with winreg.OpenKey(hive, rf"SOFTWARE\Classes\CLSID\{clsid}\LocalServer32", 0, winreg.KEY_READ | view) as k:
                    print(f"{hname} {clsid}: {winreg.QueryValueEx(k, None)[0]}")
            except OSError:
                pass

# 3. Chrome elevation 服务名（Windows 服务）
import subprocess
r = subprocess.run(["sc", "query", "type=", "service=", "state=", "all"], capture_output=True, text=True)
for line in r.stdout.splitlines():
    if "elevation" in line.lower():
        print("服务:", line.strip())

# 4. 全注册表搜 Google Chrome 的 elevation（HKCU\Software\Classes）
def scan(hive, hname):
    found = []
    try:
        root = winreg.OpenKey(hive, r"SOFTWARE\Classes\CLSID")
    except OSError:
        return found
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i); i += 1
        except OSError:
            break
        try:
            with winreg.OpenKey(root, sub + r"\LocalServer32") as k:
                path = str(winreg.QueryValueEx(k, None)[0]).lower()
                if "google\\chrome" in path and "elevation" in path:
                    found.append((sub, path))
        except OSError:
            continue
    return found

print("HKCU Chrome elevator:", scan(winreg.HKEY_CURRENT_USER, "HKCU"))
