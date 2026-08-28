# -*- coding: utf-8 -*-
"""临时调试：验证 Iwara 登录持久化各环节（测完即删）。"""
import sys, json, time, base64
sys.path.insert(0, ".")
import gui_bridge as gb

data = gb._iwara_load_token()
print("存储的凭据字段:", sorted(data.keys()))
print("email:", repr(data.get("email")))
print("password 长度:", len(data.get("password") or ""))
print("username:", repr(data.get("username")))
token = data.get("user_token") or ""
print("user_token 存在:", bool(token))

def jwt_exp(t):
    try:
        p = t.split(".")[1]
        p += "=" * (-len(p) % 4)
        return float(json.loads(base64.urlsafe_b64decode(p)).get("exp") or 0)
    except Exception:
        return 0.0

exp = jwt_exp(token)
print("token exp:", exp, "now:", time.time(), "已过期:", exp < time.time())

# 直接调 /user 看返回
try:
    r = gb._iwara_session.get(
        f"{gb.IWARA_API}/user", timeout=20,
        headers={"Authorization": f"Bearer {token}"},
    )
    print("/user 状态码:", r.status_code)
    print("/user 返回:", r.text[:300])
except Exception as e:
    print("/user 请求异常:", e)
