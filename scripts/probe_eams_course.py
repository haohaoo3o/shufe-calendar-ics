#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dump courseTableForm 全部字段, 然后带全参数 POST 课表"""
import os, re, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shufe_auth import AuthSession

EAMS = "https://eams.sufe.edu.cn/eams"
s = AuthSession()
H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": f"{EAMS}/courseTableForStd!index.action",
}


def form_post(url, params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers=H)
    try:
        resp = s.opener.open(req, timeout=20)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get(url):
    req = urllib.request.Request(url, headers={k: v for k, v in H.items() if k != "Content-Type"})
    try:
        resp = s.opener.open(req, timeout=20)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# 1) GET index, dump form 结构
st, b = get(f"{EAMS}/courseTableForStd!index.action")
html = b.decode("utf-8", "ignore")
print(f"[index] http={st} len={len(html)}")
fm = re.search(r'<form[^>]*name="courseTableForm"[^>]*>(.*?)</form>', html, re.S)
if fm:
    seg = fm.group(1)
    print("[form 内 input/select]")
    for m in re.finditer(r'<(?:input|select|textarea)[^>]*>', seg):
        tag = m.group(0)
        nm = re.search(r'name="([^"]*)"', tag)
        vl = re.search(r'value="([^"]*)"', tag)
        print(f"  {nm.group(1) if nm else '?'} = {vl.group(1) if vl else ''}  [{tag[:80]}]")
else:
    print("[未找到 courseTableForm, 找所有 form]")
    for m in re.finditer(r'<form[^>]*>', html):
        print("  ", m.group(0)[:120])

# 2) 带全参数 POST courseTable (semesterId=3928)
print("\n[POST courseTable 全参数]")
st, b = form_post(f"{EAMS}/courseTableForStd!courseTable.action",
                  {"semesterId": "3928", "ids": "410965",
                   "project.id": "1", "setting.kind": "std", "startWeek": "1"})
t = b.decode("utf-8", "ignore")
print(f"http={st} len={len(t)} 未开放={'未开放' in t} 周一={'周一' in t}")
with open("course_raw.html", "w", encoding="utf-8") as f:
    f.write(t)
print("文本:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:300])
