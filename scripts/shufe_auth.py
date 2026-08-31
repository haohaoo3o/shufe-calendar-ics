#!/usr/bin/env python3
"""上财统一认证登录器 - 可复用模块
用法:
  python shufe_auth.py login <学号> <密码>      # 登录并保存会话
  python shufe_auth.py status                    # 检查会话是否有效
"""
import base64, json, os, sys, time, urllib.request, urllib.error, ssl, re, http.cookiejar

BASE = "https://login.sufe.edu.cn/esc-sso"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sufe_cookies.txt")
ctx = ssl.create_default_context()
# 绕过注册表系统代理(Clash 等未运行时 127.0.0.1:7890 拒连)的直连 opener
direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 强制直连: 本机 Windows 注册表系统代理 (127.0.0.1:7890, Clash) 常处于"已启用但客户端未运行"状态,
# urllib 默认读注册表代理 → 所有请求 WinError 10061 连接被拒 (2026-08-13 cron 故障根因)。
# 上财/国内站点直连可达, 无需代理; 显式禁用避免踩死代理。
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"


class AuthSession:
    def __init__(self):
        self.cj = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
        try:
            self.cj.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),  # 绕过注册表系统代理(如 Clash 未运行时 127.0.0.1:7890 拒连)
            urllib.request.HTTPCookieProcessor(self.cj),
        )

    def req(self, url, method="GET", data=None, headers=None, raw=False):
        h = {"User-Agent": UA, "Referer": "https://login.sufe.edu.cn/login/", "Accept": "application/json"}
        if headers:
            h.update(headers)
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            resp = self.opener.open(r, timeout=20)
            return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def save(self):
        self.cj.save(ignore_discard=True, ignore_expires=True)


def rsa_encrypt(password, modulus_b64):
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import serialization
    der = base64.b64decode(modulus_b64)
    pub = serialization.load_der_public_key(der)
    return base64.b64encode(pub.encrypt(password.encode(), padding.PKCS1v15())).decode()


def login(username, password, max_rounds=12, session=None):
    s = session or AuthSession()
    _, b = s.req(f"{BASE}/api/v3/auth/queryAllValid")
    cfg = json.loads(b)
    param = cfg["data"]["param"]
    ticket = cfg["data"]["config"]["loginTicket"]
    enc_pw = rsa_encrypt(password, param["publicKey"])

    x_candidates = [100, 98, 102]
    for rnd in range(1, max_rounds+1):
        _, b = s.req(f"{BASE}/api/v3/sliderCaptcha/init", "POST", {})
        sd = json.loads(b)["data"]
        y, token = sd["Y"], sd["token"]
        vcode = None
        for x in x_candidates:
            _, b = s.req(f"{BASE}/api/v3/sliderCaptcha/check?X={x}&Y={y}&token={token}")
            r = json.loads(b)
            if r.get("code") == "0":
                vcode = r.get("data")
                break
        if not vcode:
            print(f"[slider r{rnd}] ✗ Y={y}", flush=True)
            # 风控冷却: 连续失败后逐步加长间隔 (2026-08-12 实测 8 连败为瞬时风控, 加长间隔可过)
            if rnd >= 8:
                time.sleep(8)
            elif rnd >= 5:
                time.sleep(4)
            else:
                time.sleep(1.5)
            continue
        print(f"[slider r{rnd}] ✓ X={x} Y={y}", flush=True)
        payload = {
            "authType": "webLocalAuth",
            "dataField": {
                "username": username,
                "password": enc_pw,
                "vcode": vcode,
                "publicKeyId": param["publicKeyId"],
            },
            "loginTicket": ticket,
            "redirectUri": "",
        }
        _, b = s.req(f"{BASE}/api/v3/auth/doLogin", "POST", payload)
        res = json.loads(b)
        print(f"[doLogin] code={res.get('code')} msg={res.get('msg')}", flush=True)
        if res.get("code") == "0":
            s.save()
            return True, res
        if res.get("code") == "SSO10002":
            return False, res  # 密码错误
        time.sleep(1.5)
    return False, {"error": "slider failed"}


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "login":
        ok, res = login(sys.argv[2], sys.argv[3])
        print("LOGIN_OK" if ok else f"LOGIN_FAIL: {res}")
    elif len(sys.argv) == 2 and sys.argv[1] == "status":
        s = AuthSession()
        st, b = s.req(f"{BASE}/api/v3/auth/queryAllValid")
        print(f"queryAllValid: {st} (cookie 数: {len(s.cj)})")
        for c in s.cj:
            print(f"  {c.name}={c.value[:20]}... domain={c.domain}")
