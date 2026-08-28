# -*- coding: utf-8 -*-
"""临时探测 9：验证下载 URL + 登录流程测试。"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://pawchive.pw/",
}

# 1. 验证下载 URL（GET 带流式读取前几字节）
url = "https://file.pawchive.pw/data/ff/ce/ffcecbd00f30c8fe594eb57791061a457765445f83bffb0c187aa6f6b4e98764.jpeg?f=cover.jpeg"
try:
    r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
    print("GET file URL:", r.status_code, r.headers.get("content-type"), r.headers.get("content-length"))
    chunk = next(r.iter_content(1024))
    print("首块字节:", len(chunk), "JPEG头:", chunk[:3].hex())
    r.close()
except Exception as e:
    print("error:", type(e).__name__, str(e)[:100])

# 2. 无 f 参数
url2 = "https://file.pawchive.pw/data/ff/ce/ffcecbd00f30c8fe594eb57791061a457765445f83bffb0c187aa6f6b4e98764.jpeg"
try:
    r = requests.head(url2, headers=HEADERS, timeout=15, allow_redirects=True)
    print("HEAD 无f参数:", r.status_code, r.headers.get("content-type"), r.headers.get("content-length"))
except Exception as e:
    print("无f参数 error:", type(e).__name__)

# 3. 登录流程测试（错误凭据，验证 cookie 流程）
s = requests.Session()
s.headers.update(HEADERS)
login_page = s.get("https://pawchive.pw/account/login?location=/", timeout=15)
print()
print("登录页 cookies:", dict(s.cookies))

r3 = s.post(
    "https://pawchive.pw/account/login",
    data={"username": "testuser123", "password": "wrongpass", "location": "/"},
    timeout=15,
    allow_redirects=False,
)
print("登录 POST status:", r3.status_code, "cookies:", dict(s.cookies))
print("响应前 300 字符:", r3.text[:300].encode("gbk", "replace").decode("gbk"))
