# -*- coding: utf-8 -*-
"""临时探测 12：确认 API 分页参数。"""
import json
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# o=5 的实际返回
r2 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?o=5", headers=HEADERS, timeout=20)
print("o=5 status:", r2.status_code, "type:", type(r2.json()).__name__)
print("内容:", r2.text[:300].encode("gbk", "replace").decode("gbk"))

print()
# o=50
r3 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?o=50", headers=HEADERS, timeout=20)
try:
    data = r3.json()
    if isinstance(data, list):
        print("o=50 status:", r3.status_code, "是列表，数量:", len(data), "首 id:", data[0]["id"] if data else None)
    else:
        print("o=50 status:", r3.status_code, "dict:", r3.text[:200])
except Exception as e:
    print("o=50 error:", e, r3.text[:100])

print()
# 标签页分页链接（完整 pagination HTML）
import re
r4 = requests.get(BASE + "/posts?tags=furry", headers=HEADERS, timeout=20)
html = r4.text
m = re.search(r'<ul[^>]*pagination[^>]*>(.*?)</ul>', html, re.S | re.I)
if m:
    block = m.group(1)
    print("pagination HTML:")
    print(block[:800].encode("gbk", "replace").decode("gbk"))
else:
    print("无 pagination ul，找 rel=next:")
    nxt = re.findall(r'<a[^>]*rel="next"[^>]*>', html)
    print(nxt[:3])
    # 找所有含 tags= 的链接
    links = [l for l in re.findall(r'href="([^"]*)"', html) if "tags=" in l]
    print("tags 链接:", links[:15])
