#!/usr/bin/env python3
"""上财校历监控 (fetch_calendar.py)
下载校历页面正文图片 + hash 比对, 供 cron agent 消费:
- 有变化 → 输出 [CALENDAR_CHANGE] + 新图片路径 (agent 用 vision 识别解读)
- 无变化 → 输出空 (agent 应回复 [SILENT])
- 状态存 calendar/state.json; 图片存 calendar/

用法: python fetch_calendar.py
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAL_DIR = os.path.join(BASE_DIR, "calendar")
STATE_FILE = os.path.join(CAL_DIR, "state.json")
PAGE_URL = "https://www.sufe.edu.cn/13651/list.htm"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def main():
    os.makedirs(CAL_DIR, exist_ok=True)
    try:
        page = fetch(PAGE_URL).decode("utf-8", "ignore")
    except Exception as e:
        print(f"[ERROR] 校历页面抓取失败: {e}", flush=True)
        sys.exit(1)

    # 正文图片: 只取 wp_articlecontent 容器内 (排除右侧新闻栏缩略图/模板图)
    m = re.search(r'<div[^>]*class="wp_articlecontent"[^>]*>(.*?)</div>\s*</div>', page, re.S)
    if not m:
        m = re.search(r'<div[^>]*class="wp_articlecontent"[^>]*>(.*?)</div>', page, re.S)
    if not m:
        print("[ERROR] 未找到校历正文容器", flush=True)
        sys.exit(1)
    imgs = re.findall(r'<img[^>]*src="(/_upload/article/images/[^"]+)"', m.group(1))
    if not imgs:
        print("[ERROR] 校历正文无图片", flush=True)
        sys.exit(1)

    page_hash = hashlib.sha256(page.encode()).hexdigest()
    new_hashes = []
    changed = []
    for i, path in enumerate(imgs):
        data = fetch("https://www.sufe.edu.cn" + path)
        h = hashlib.sha256(data).hexdigest()
        new_hashes.append(h)
        fn = os.path.join(CAL_DIR, f"xiaoli_{i+1}.jpg")
        with open(fn, "wb") as f:
            f.write(data)
        changed.append((fn, h))

    old = {}
    if os.path.exists(STATE_FILE):
        try:
            old = json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception:
            old = {}

    if old.get("page_hash") == page_hash and old.get("hashes") == new_hashes:
        print("", flush=True)  # 无变化 → 空输出
    else:
        json.dump({"page_hash": page_hash, "hashes": new_hashes, "fetched_at": __import__("datetime").datetime.now().isoformat()},
                  open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[CALENDAR_CHANGE] 校历有更新!", flush=True)
        for fn, h in changed:
            print(f"图片: {fn} (sha256:{h[:16]})", flush=True)
        if old.get("page_hash"):
            print("提示: 用 vision 识别新图片, 对比旧校历找出变化日期", flush=True)
        else:
            print("提示: 首次抓取, 用 vision 识别图片建立校历基线", flush=True)


if __name__ == "__main__":
    main()
