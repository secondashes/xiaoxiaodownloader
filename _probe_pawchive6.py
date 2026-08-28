# -*- coding: utf-8 -*-
"""临时探测 6：媒体 URL 格式 + 收藏 API 结构 + 标签分页。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 取一个帖子的 API 数据，验证附件 URL 格式
r = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?offset=0&limit=2", headers=HEADERS, timeout=20)
posts = r.json()
p = posts[0]
print("=== 帖子数据结构 ===")
print("keys:", list(p.keys()))
print("file:", p.get("file"))
print("attachments[0]:", (p.get("attachments") or [{}])[0])
print("published:", p.get("published"))

# 2. 测试媒体 URL 可访问性（HEAD）
file_path = p["file"]["path"]
for url in [f"https://img.pawchive.pw/data{file_path}", f"{BASE}/data{file_path}"]:
    try:
        h = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        print(f"HEAD {url[:60]}... -> {h.status_code} {h.headers.get('content-type')} {h.headers.get('content-length')}")
    except Exception as e:
        print(f"HEAD {url[:60]}... -> {type(e).__name__} {str(e)[:80]}")

print()

# 3. 帖子页 HTML 里的媒体链接（确认网页用的 URL）
r2 = requests.get(BASE + f"/patreon/user/{p['user']}/post/{p['id']}", headers=HEADERS, timeout=20)
if r2.status_code == 200:
    urls = re.findall(r'https://[a-z.]*pawchive[a-z.]*/data[^"\']*', r2.text)
    print("=== 帖子页媒体 URL 示例 ===")
    for u in urls[:3]:
        print("  ", u[:100])
else:
    print("帖子页状态:", r2.status_code)

print()

# 4. 标签搜索分页（找下一页链接）
r3 = requests.get(BASE + "/posts?tags=furry&offset=50", headers=HEADERS, timeout=20)
print("=== /posts?tags=furry&offset=50 status=", r3.status_code, "len=", len(r3.text))
cards = re.findall(r'data-id="(\d+)"', r3.text)
print("卡片数:", len(cards), "前3个 id:", cards[:3])

# 5. 未登录访问收藏页
r4 = requests.get(BASE + "/favorites", headers=HEADERS, timeout=20, allow_redirects=False)
print()
print("=== /favorites（未登录）status=", r4.status_code, "redirect=", r4.headers.get("location"))

# 6. follows API 尝试
for ep in ["/api/v1/account/favorites-artists", "/api/v1/account/favorites/posts", "/api/v1/favorites", "/api/v1/account/subscriptions"]:
    try:
        rr = requests.get(BASE + ep, headers=HEADERS, timeout=15)
        print(f"GET {ep} -> {rr.status_code} {rr.text[:100]}")
    except Exception as e:
        print(f"GET {ep} -> {type(e).__name__}")
