#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 course_raw.html → 结构化课表 JSON (v2: 顺序切片, 课程名映射, 全节次)"""
import json
import re

html = open("course_raw.html", encoding="utf-8").read()

act_pat = re.compile(r'new\s+TaskActivity\("([^"]*)","([^"]*)","([^"]*)",\s*("[^"]*"|\w+),\s*"([^"]*)","([^"]*)","([^"]*)"\)')
name_pat = re.compile(r'var\s+courseNameLessonNo\s*=\s*"([^"]*)"')
idx_pat = re.compile(r'index\s*=\s*(\d+)\*unitCount\+(\d+);')

out = []
for m in act_pat.finditer(html):
    tid, tname, cno, cname_expr, rid, room, weeks = m.groups()
    before = html[:m.start()]
    names = name_pat.findall(before)
    cur_name = names[-1] if names else cname_expr.strip('"')
    seg_after = html[m.end():]
    nxt = act_pat.search(seg_after)
    seg_until = seg_after[:nxt.start()] if nxt else seg_after
    for wd, per in idx_pat.findall(seg_until):
        out.append({
            "teacher": tname, "course_no": cno, "course_name": cur_name,
            "room": room, "weekday": int(wd), "period": int(per), "weeks": weeks,
        })

for r in out:
    r["week_list"] = [i + 1 for i, ch in enumerate(r["weeks"]) if ch == "1"]
    r.pop("weeks", None)

# 按 课名+教师+教室+周次 合并连续节次
merged = {}
for r in out:
    key = (r["course_name"], r["teacher"], r["room"], tuple(r["week_list"]), r["weekday"])
    if key not in merged:
        merged[key] = {"start": r["period"], "end": r["period"],
                       "course_name": r["course_name"], "teacher": r["teacher"],
                       "room": r["room"], "weekday": r["weekday"], "week_list": r["week_list"]}
    else:
        merged[key]["end"] = max(merged[key]["end"], r["period"])

records = sorted(merged.values(), key=lambda x: (x["weekday"], x["start"]))
print(f"[活动 {len(out)} 条 → 合并 {len(records)} 个时间段]")
for r in records:
    wl = r["week_list"]
    wtext = f"{wl[0]}-{wl[-1]}周" if len(wl) > 1 and wl == list(range(wl[0], wl[-1] + 1)) else f"{wl}"
    print(f"  周{r['weekday']+1} 第{r['start']}-{r['end']}节 {r['course_name']} | {r['teacher']} | {r['room']} | {wtext}")

with open("course_parsed.json", "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
print(f"\n已存 course_parsed.json（{len(records)} 条）")
