# -*- coding: utf-8 -*-
"""临时探测 10：tag 搜索分页 + 画师页分页 + 帖子 tags 字段。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. tag 搜索页找分页线索（找 hx-* 属性、data 属性、next 按钮）
r = requests.get(BASE + "/posts?tags=furry", headers=HEADERS, timeout=20)
html = r.text
print("=== /posts?tags=furry 分页线索 ===")
# htmx 属性（该站用 hx-boost）
hx = re.findall(r'hx-[a-z-]+="[^"]*"', html)
print("hx 属性:", sorted(set(hx))[:15])
# pagination 区块
m = re.search(r'<[^>]*pagination[^>]*>(.*?)</\w+>', html, re.S | re.I)
if m:
    print("pagination 区块:", m.group(0)[:500].encode("gbk", "replace").decode("gbk"))
# 下一页按钮
nxt = re.findall(r'(rel="next"|下一页|Next|load.?more|Load more)', html, re.I)
print("下一页线索:", nxt[:5])

# 2. 画师页分页（BOKABA 250 卡片，检查是否有更多）
r2 = requests.get(BASE + "/patreon/user/30500811", headers=HEADERS, timeout=20)
html2 = r2.text
print()
print("=== 画师页分页线索 ===")
nxt2 = re.findall(r'(rel="next"|load.?more|Load more|hx-get="[^"]*offset[^"]*")', html2, re.I)
print("线索:", nxt2[:5])
hxget = re.findall(r'hx-get="([^"]*)"', html2)
print("hx-get:", hxget[:10])
hxvals = re.findall(r'hx-vals="([^"]*)"', html2)
print("hx-vals:", hxvals[:5])

# 3. 画师页直接加 offset 参数
r3 = requests.get(BASE + "/patreon/user/30500811?offset=250", headers=HEADERS, timeout=20)
ids1 = re.findall(r'data-id="(\d+)"', html2)
ids3 = re.findall(r'data-id="(\d+)"', r3.text)
print("画师页 offset=0 vs offset=250 首卡片:", ids1[:2], "vs", ids3[:2], "| 总数:", len(ids1), len(ids3))

# 4. API 分页验证（offset/limit）
r4 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?offset=0&limit=2", headers=HEADERS, timeout=20)
posts1 = r4.json()
r5 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?offset=2&limit=2", headers=HEADERS, timeout=20)
posts2 = r5.json()
print()
print("=== API 分页 ===")
print("offset=0 ids:", [p["id"] for p in posts1])
print("offset=2 ids:", [p["id"] for p in posts2])

# 5. 帖子的 tags 字段（画师内 tag 搜索用）
for p in posts1:
    print("帖子 tags:", repr(p.get("tags")), "| title:", repr(p.get("title", ""))[:40])
