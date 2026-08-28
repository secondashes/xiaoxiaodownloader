# -*- coding: utf-8 -*-
"""临时探测 2：pawchive.pw 的帖子/标签/登录 API。"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 用一个真实 creator 测试（BOKABA / patreon / 30500811）
endpoints = [
    "/api/v1/patreon/user/30500811/posts?offset=0&limit=5",
    "/api/v1/patreon/user/30500811/profile",
    "/api/v1/tags/search?query=test",
    "/api/v1/posts/search?query=test",
    "/api/v1/account/favorites",
    "/api/v1/account/follows",
    "/api/v1/account",
    "/api/v1/search?query=test",
]

for ep in endpoints:
    try:
        r = requests.get(BASE + ep, headers=HEADERS, timeout=20)
        text = r.text[:300] if r.text else "(empty)"
        print(f"GET {ep}")
        print(f"  status={r.status_code} len={len(r.text)}")
        print("  body:", text.encode("gbk", "replace").decode("gbk")[:280])
    except Exception as e:
        print(f"GET {ep} -> error: {type(e).__name__} {str(e)[:120]}")
    print()
