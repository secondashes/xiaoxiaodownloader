# -*- coding: utf-8 -*-
"""临时探测 7：帖子详情 API + 真实媒体 URL + 分页验证。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 找一个有附件的帖子（fanbox 13774247 的帖子 12487176 有 3 attachments）
r = requests.get(BASE + "/api/v1/fanbox/user/13774247/post/12487176", headers=HEADERS, timeout=20)
print("=== 帖子详情 API status=", r.status_code)
if r.status_code == 200:
    post = r.json()
    print("keys:", list(post.keys()))
    print("title:", post.get("title"))
    print("tags:", post.get("tags"))
    print("file:", post.get("file"))
    atts = post.get("attachments") or []
    print("attachments 数量:", len(atts))
    for a in atts[:3]:
        print("  att:", a)
    print("published:", post.get("published"))
    print("user:", post.get("user"), "service:", post.get("service"))

    # 2. 验证附件 URL 格式
    for a in atts[:2]:
        path = a.get("path", "")
        name = a.get("name", "")
        for host in ["https://img.pawchive.pw/data", "https://pawchive.pw/data"]:
            url = host + path
            try:
                h = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
                print(f"HEAD {host}{path[:30]}... -> {h.status_code} {h.headers.get('content-type')} {h.headers.get('content-length')}")
            except Exception as e:
                print(f"HEAD {host}{path[:30]}... -> {type(e).__name__} {str(e)[:60]}")

# 3. 分页验证：对比不同 offset 的第一批 id
print()
print("=== 分页验证 ===")
for offset in [0, 50]:
    r2 = requests.get(BASE + f"/posts?tags=furry&offset={offset}", headers=HEADERS, timeout=20)
    ids = re.findall(r'data-id="(\d+)"', r2.text)
    print(f"offset={offset}: 前3 id = {ids[:3]}")

# 4. creator 列表 API 分页参数验证
r3 = requests.get(BASE + "/api/v1/creators?offset=0&limit=3", headers=HEADERS, timeout=20)
print()
print("=== /api/v1/creators?offset=0&limit=3 ===")
try:
    creators = r3.json()
    print("返回数量:", len(creators))
    for c in creators[:3]:
        print("  ", c)
except Exception as e:
    print("解析失败:", e, r3.text[:100])
