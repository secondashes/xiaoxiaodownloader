# -*- coding: utf-8 -*-
"""临时探测 11：验证 o 参数分页 + 标签页分页 href。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. API 用 o 参数
r1 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?o=0&limit=5", headers=HEADERS, timeout=20)
r2 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?o=5&limit=5", headers=HEADERS, timeout=20)
p1 = r1.json()
p2 = r2.json()
print("o=0 前3:", [p["id"] for p in p1[:3]], "总数:", len(p1))
print("o=5 前3:", [p["id"] for p in p2[:3]], "总数:", len(p2))
print("分页生效:", p1[0]["id"] != p2[0]["id"] if p2 else "空")

print()

# 2. 标签搜索页的分页 href
r3 = requests.get(BASE + "/posts?tags=furry", headers=HEADERS, timeout=20)
html = r3.text
# 找 pagination 区域的所有链接
m = re.search(r'<ul[^>]*pagination[^>]*>(.*?)</ul>', html, re.S | re.I)
if m:
    links = re.findall(r'href="([^"]*)"', m.group(1))
    print("标签页分页链接:", links[:15])
else:
    # 找所有含 offset 或 o= 的链接
    links = re.findall(r'href="([^"]*(?:\bo=|offset)[^"]*)"', html)
    print("offset 链接:", links[:15])
    nxt = re.findall(r'<a[^>]*rel="next"[^>]*href="([^"]*)"', html)
    print("rel=next:", nxt)

# 3. 标签搜索页用 o 参数试试
r4 = requests.get(BASE + "/posts?tags=furry&o=50", headers=HEADERS, timeout=20)
ids_a = re.findall(r'data-id="(\d+)"', r3.text)
ids_b = re.findall(r'data-id="(\d+)"', r4.text)
print()
print("tags 页 o=0 vs o=50:", ids_a[:2], "vs", ids_b[:2], "| 生效:", ids_a[:2] != ids_b[:2])
