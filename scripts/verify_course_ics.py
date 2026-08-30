#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_course_ics.py — 校验 dist/course.ics 与课程数据源完全一致（防回归）
============================================================================
对 course.ics 里每个 VEVENT：展开 RRULE（FREQ=WEEKLY;COUNT=N）再减去 EXDATE，
得到该事件实际发生的全部日期 → 换算成「第几周」→ 与 courses_real.json 的
weeks 期望逐门核对（周次、星期、时间、地点）。

用法：
  python scripts/verify_course_ics.py [--ics dist/course.ics] [--courses scripts/courses_real.json]

退出码 0 = 全部通过；1 = 有不一致（打印详细差异）。
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar

TZ = ZoneInfo("Asia/Shanghai")


def expand_event(ev, semester_start: date):
    """展开单个 VEVENT → (summary, weekday, start_time, end_time, location, set(week_numbers))"""
    dtstart = ev.get("dtstart").dt
    if isinstance(dtstart, datetime):
        start_dt = dtstart.astimezone(TZ)
    else:  # DATE 值
        start_dt = datetime(dtstart.year, dtstart.month, dtstart.day, 0, 0, tzinfo=TZ)
    dtend = ev.get("dtend").dt
    if isinstance(dtend, datetime):
        end_dt = dtend.astimezone(TZ)
    else:
        end_dt = start_dt
    rrule = ev.get("rrule")
    cnt = rrule.get("count") if rrule else 1
    count = int(cnt[0]) if isinstance(cnt, (list, tuple)) else int(cnt)
    exdates = set()
    exdate = ev.get("exdate")
    if exdate is not None:
        dt_list = getattr(exdate, "dts", None)
        if dt_list is None and hasattr(exdate, "to_list"):
            dt_list = [type("x", (), {"dt": v})() for v in exdate.to_list()]
        for ed in dt_list or []:
            v = ed.dt
            if isinstance(v, datetime):
                exdates.add(v.astimezone(TZ))
            else:
                exdates.add(datetime(v.year, v.month, v.day, 0, 0, tzinfo=TZ))
    # 展开候选周
    weekdays = set()
    for i in range(count):
        d = start_dt + timedelta(weeks=i)
        if d not in exdates:
            weekdays.add((d.date(), d.hour, d.minute))
    # 换算周数
    week_nums = set()
    for d, h, m in weekdays:
        week_nums.add((d - semester_start).days // 7 + 1)
    return {
        "summary": str(ev.get("summary")),
        "weekday": start_dt.weekday(),  # 0=周一
        "start": f"{start_dt.hour:02d}:{start_dt.minute:02d}",
        "end": f"{end_dt.hour:02d}:{end_dt.minute:02d}",
        "location": str(ev.get("location") or ""),
        "weeks": sorted(week_nums),
        "occurrences": sorted(d for d, h, m in weekdays),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ics", default="dist/course.ics")
    ap.add_argument("--courses", default="scripts/courses_real.json")
    ap.add_argument("--semester-start", default="2026-08-31")
    args = ap.parse_args()

    semester_start = date.fromisoformat(args.semester_start)
    with open(args.ics, "rb") as f:
        cal = Calendar.from_ical(f.read())
    with open(args.courses, encoding="utf-8") as f:
        courses = json.load(f)["courses"]

    # 按 (weekday, start) 索引期望课程
    expect = defaultdict(list)
    for c in courses:
        expect[(c["day"] - 1, c["start"])].append(c)

    failures = []
    checked = 0
    for ev in cal.walk("VEVENT"):
        info = expand_event(ev, semester_start)
        key = (info["weekday"], int(info["start"][:2]) * 60 + int(info["start"][3:]))
        # 节次 start → 用 period 映射回查（简化：用时间戳找期望）
        cands = []
        for (wd, st), clist in expect.items():
            if wd == info["weekday"]:
                for c in clist:
                    cands.append(c)
        # 精确匹配课程名（区分 [线上]/线下，剥前缀会导致两条马原互相误匹配）
        name = info["summary"]
        is_online = name.startswith("[线上]")
        expect_course = None
        for c in cands:
            c_online = c["name"].startswith("[线上]")
            if c_online == is_online and c["name"].lstrip("[线上]") == name.lstrip("[线上]"):
                expect_course = c
                break
        if expect_course is None:
            failures.append(f"[FAIL] {name}: ICS 中找不到对应课程定义")
            continue
        checked += 1
        # 期望周次
        exp_weeks = {int(w) for w in str(expect_course["weeks"]).split(",")}
        got_weeks = set(info["weeks"])
        status = "PASS" if got_weeks == exp_weeks else "FAIL"
        if status == "FAIL":
            failures.append(
                f"[FAIL] {name} 周次不符: 期望 {sorted(exp_weeks)} 实际 {sorted(got_weeks)}")
        # 时间核对
        exp_start = None
        exp_end = None
        # 用 DEFAULT_PERIODS 逆映射（从生成脚本导入）
        sys.path.insert(0, "scripts")
        from shufe_ics_gen import DEFAULT_PERIODS
        es = DEFAULT_PERIODS[str(expect_course["start"])][0]
        ee = DEFAULT_PERIODS[str(expect_course["end"])][1]
        if info["start"] != es or info["end"] != ee:
            failures.append(
                f"[FAIL] {name} 时间不符: 期望 {es}-{ee} 实际 {info['start']}-{info['end']}")
        # 地点核对
        if expect_course.get("location") and info["location"] != expect_course["location"]:
            failures.append(
                f"[FAIL] {name} 地点不符: 期望 {expect_course['location']} 实际 {info['location']}")
        print(f"[{status}] {name:　<24} 周{'、'.join(map(str, sorted(got_weeks))):　<40} "
              f"{info['start']}-{info['end']} {info['location']}")
        # 打印每周明细（方便人工目检）
        by_week = defaultdict(list)
        for occ in info["occurrences"]:
            wk = (occ - semester_start).days // 7 + 1
            by_week[wk].append(f"{occ.month:02d}-{occ.day:02d}")
        detail = " | ".join(f"第{w}周:{','.join(v)}" for w, v in sorted(by_week.items()))
        print(f"          ↳ {detail}")

    # 反向检查：数据源里的课程是否全部出现在 ICS
    ics_names = {str(ev.get("summary")).lstrip("[线上]") for ev in cal.walk("VEVENT")}
    src_names = {c["name"].lstrip("[线上]") for c in courses}
    missing = src_names - ics_names
    if missing:
        failures.append(f"[FAIL] 数据源中存在但 ICS 缺失: {sorted(missing)}")

    print(f"\n共核对 {checked}/{len(courses)} 门课次")
    if failures:
        print("\n".join(failures))
        sys.exit(1)
    print("✅ 全部一致：周次/时间/地点与课程数据源完全对应")


if __name__ == "__main__":
    main()
