import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36", "X-Site": "www.iwara.ai"}

r = requests.get("https://api.iwara.tv/videos", params={"limit": 1, "sort": "date"}, headers=UA, timeout=30)
v = r.json()["results"][0]
av = v["user"]["avatar"]
print("avatar:", json.dumps({k: av.get(k) for k in ("id", "path", "name")}, ensure_ascii=False))
print("thumbnail type:", type(v.get("thumbnail")), str(v.get("thumbnail"))[:120])
print("customThumbnail:", str(v.get("customThumbnail"))[:120])
print("file id:", (v.get("file") or {}).get("id"))

path, fid, name = av["path"], av["id"], av["name"]
stem = name.rsplit(".", 1)[0]
candidates = [
    f"https://www.iwara.tv/image/avatar/{path}/{fid}.jpg",
    f"https://www.iwara.tv/image/avatar/{path}/{stem}",
    f"https://www.iwara.tv/image/original/{path}/{stem}",
    f"https://files.iwara.tv/image/original/{path}/{stem}",
    f"https://www.iwara.tv/image/avatar/{path}/{name}",
    f"https://www.iwara.tv/image/x/avatar/{path}/{stem}.jpg",
    f"https://www.iwara.tv/image/l/avatar/{path}/{stem}.jpg",
    f"https://www.iwara.tv/image/m/avatar/{path}/{stem}.jpg",
]
for u in candidates:
    try:
        rr = requests.get(u, headers=UA, timeout=20, stream=True)
        rr.close()
        print(rr.status_code, u)
    except Exception as e:
        print("ERR", type(e).__name__, u)
