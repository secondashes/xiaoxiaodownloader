# -*- coding: utf-8 -*-
"""临时测试4：全注册表找 Chrome elevator。用完即删。"""
import os
import winreg

def scan(hive, hname, keyword):
    found = []
    for sub_path in (r"SOFTWARE\Classes\CLSID", r"SOFTWARE\Classes\WOW6432Node\CLSID"):
        try:
            root = winreg.OpenKey(hive, sub_path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i); i += 1
            except OSError:
                break
            try:
                with winreg.OpenKey(root, sub + r"\LocalServer32") as k:
                    path = str(winreg.QueryValueEx(k, None)[0])
                    if keyword in path.lower():
                        found.append((sub, path))
            except OSError:
                continue
    return found

print("HKCU:", scan(winreg.HKEY_CURRENT_USER, "HKCU", "google\\chrome"))
print("HKLM:", scan(winreg.HKEY_LOCAL_MACHINE, "HKLM", "google\\chrome"))

# Chrome 151 elevation service 的注册方式：查服务
os.system("sc qc GoogleChromeElevationService 2>&1 | findstr /i \"BINARY_PATH DISPLAY\"")

# Chrome 151 elevation_service.exe 的版本目录
app = r"C:\Program Files\Google\Chrome\Application"
for d in os.listdir(app):
    if d[0].isdigit():
        print("版本目录:", d)
