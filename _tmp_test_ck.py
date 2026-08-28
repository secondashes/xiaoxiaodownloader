# -*- coding: utf-8 -*-
"""临时测试：验证 Chrome/Edge 的 cookie 解密能力（不限目标站点）。用完即删。"""
import fetch_cookies as fc

for label, root in [
    ("Chrome", fc.os.path.join(fc.LOCALAPPDATA, r"Google\Chrome\User Data")),
    ("Edge", fc.os.path.join(fc.LOCALAPPDATA, r"Microsoft\Edge\User Data")),
    ("X-Spider", fc.os.path.join(fc.BASE_DIR, "X-Spider", "EBWebView")),
]:
    key = fc.get_chromium_key(root)
    print(f"\n{label}: key={'OK' if key else 'FAIL'}")
    if not key:
        continue
    # 读全部 cookie 前缀统计
    import sqlite3, shutil, tempfile, os, glob
    total, v10, v20, plain_ok = 0, 0, 0, 0
    hosts = set()
    for profile in fc.find_chromium_profiles(root):
        db = os.path.join(profile, "Network", "Cookies")
        if not os.path.exists(db):
            db = os.path.join(profile, "Cookies")
        if not os.path.exists(db):
            continue
        tmp = tempfile.mkdtemp()
        tdb = os.path.join(tmp, "C")
        try:
            shutil.copy2(db, tdb)
            conn = sqlite3.connect(tdb)
            rows = conn.execute("SELECT host_key, encrypted_value FROM cookies").fetchall()
            conn.close()
        except Exception as e:
            print("  read err:", e)
            continue
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        for host, ev in rows:
            total += 1
            hosts.add(host)
            if ev[:3] in (b"v10", b"v11"):
                v10 += 1
                if fc.decrypt_chromium_value(key, ev) is not None:
                    plain_ok += 1
            elif ev[:3] == b"v20":
                v20 += 1
    print(f"  cookie 总数={total}, v10/v11={v10}, v20={v20}, 解密成功={plain_ok}")
    tw = [h for h in hosts if any(d in h for d in ("x.com", "twitter", "exhentai", "e-hentai", "pawchive"))]
    print(f"  含目标域名的 host: {tw if tw else '无'}")
