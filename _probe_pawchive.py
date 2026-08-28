# -*- coding: utf-8 -*-
"""临时探测：pawchive.pw 的 API 端点和页面结构。"""
import json
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

BASE = "https://pawchive.pw"

endpoints = [
    "/api/v1/artists",
    "/api/v1/creators",
    "/api/v1/posts",
    "/api/v1/artists?search=test",
]

for ep in endpoints:
    try:
        r = requests.get(BASE + ep, headers=HEADERS, timeout=20)
        text = r.text[:500] if r.text else "(empty)"
        print(f"GET {ep}")
        print(f"  status={r.status_code} content-type={r.headers.get('content-type')} len={len(r.text)}")
        print("  body:", text.encode("gbk", "replace").decode("gbk")[:400])
    except Exception as e:
        print(f"GET {ep} -> error: {type(e).__name__} {str(e)[:150]}")
    print()
