# -*- coding: utf-8 -*-
"""临时探测 13：标签分页验证 + 帖子 tags 结构。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 标签搜索 o 分页验证
r1 = requests.get(BASE + "/posts?tags=furry&o=0", headers=HEADERS, timeout=20)
r2 = requests.get(BASE + "/posts?tags=furry&o=50", headers=HEADERS, timeout=20)
ids1 = re.findall(r'data-id="(\d+)"', r1.text)
ids2 = re.findall(r'data-id="(\d+)"', r2.text)
print("tags o=0:", ids1[:3])
print("tags o=50:", ids2[:3])
print("分页生效:", ids1[:2] != ids2[:2])

# 2. 从标签页取一个帖子的详情，看 tags 结构
m = re.search(r'data-id="(\d+)"\s+data-service="(\w+)"\s+data-user="(\d+)"', r1.text)
if m:
    pid, service, user = m.groups()
    r3 = requests.get(BASE + f"/api/v1/{service}/user/{user}/post/{pid}", headers=HEADERS, timeout=20)
    post = r3.json()
    print()
    print(f"=== 帖子 {pid} ({service}/{user}) ===")
    print("tags:", post.get("tags"))
    print("title:", str(post.get("title"))[:50])
    print("file:", post.get("file"))
    atts = post.get("attachments") or []
    print("附件数:", len(atts), "| 第一个:", atts[0] if atts else None)

# 3. 画师内 tag 搜索：API 是否支持 tags 过滤参数
r4 = requests.get(BASE + "/api/v1/patreon/user/30500811/posts?o=0&tags=whatever", headers=HEADERS, timeout=20)
print()
print("画师 posts + tags 参数:", r4.status_code, r4.text[:150].encode("gbk", "replace").decode("gbk"))

# 4. 画师页 SSR 是否支持 tags 过滤（网页上画师页有 tag 过滤 UI 吗）
r5 = requests.get(BASE + "/patreon/user/30500811?tags=test", headers=HEADERS, timeout=20)
html5 = r5.text
# 找搜索框
search_inputs = re.findall(r'<input[^>]*(?:search|tag|query)[^>]*>', html5, re.I)
print()
print("画师页搜索框:", search_inputs[:3])
tags_links = [l for l in re.findall(r'href="([^"]*)"', html5) if "tags=" in l]
print("画师页 tags 链接:", tags_links[:10])
