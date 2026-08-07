#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shufe_ics_gen.py — 上财课表 → iCalendar (.ics) 订阅源生成器
============================================================
把课程表/考试/作业截止 生成标准 .ics 文件，托管到 GitHub Pages / Cloudflare
Pages 后即可在 iPhone/Mac 日历「添加订阅日历」订阅。

特性：
  * 周次处理：支持 '1-16' / '1,3,5,7'（单周）/ '2-16' 等，用 RRULE + EXDATE 实现
  * 时区：TZID=Asia/Shanghai（带 VTIMEZONE 块，跨时区不错位）
  * 多日历：course.ics（课表）/ exams.ics（考试，单次事件）
  * 节次→时间映射可配置（config JSON），开学后以 EAMS 数据为准

用法：
  python shufe_ics_gen.py --demo                       # 内置示例课表（测试订阅用）
  python shufe_ics_gen.py --courses courses.json       # 从 JSON 读课程
  python shufe_ics_gen.py --eams                       # 接 fetch_eams.py 课表（开学后）
  python shufe_ics_gen.py --semester-start 2026-09-07  # 指定开学第一周周一
输出到 ./dist/*.ics
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Timezone, TimezoneStandard, vText

TZ = ZoneInfo("Asia/Shanghai")

# 上财节次 → 时间映射（默认值，开学后以 EAMS 课表数据为准；可通过 config 覆盖）
DEFAULT_PERIODS = {
    "1": ("08:00", "08:45"), "2": ("08:55", "09:40"),
    "3": ("10:00", "10:45"), "4": ("10:55", "11:40"),
    "5": ("13:30", "14:15"), "6": ("14:25", "15:10"),
    "7": ("15:30", "16:15"), "8": ("16:25", "17:10"),
    "9": ("17:20", "18:05"), "10": ("18:30", "19:15"),
    "11": ("19:25", "20:10"), "12": ("20:20", "21:05"),
}

# 内置示例课表（2025级投资学-信息与计算科学 第3学期 培养计划建议课，仅供链路测试！）
DEMO_COURSES = [
    {"name": "马克思主义基本原理", "teacher": "示例教师", "location": "示例教室-1",
     "day": 1, "start": 1, "end": 2, "weeks": "1-16"},
    {"name": "人工智能导论B", "teacher": "示例教师", "location": "示例教室-2",
     "day": 3, "start": 3, "end": 4, "weeks": "1-16"},
    {"name": "社会保障", "teacher": "示例教师", "location": "示例教室-3",
     "day": 2, "start": 5, "end": 6, "weeks": "1-16"},
    {"name": "经济法导论", "teacher": "示例教师", "location": "示例教室-4",
     "day": 4, "start": 7, "end": 8, "weeks": "1-16"},
    {"name": "市场营销", "teacher": "示例教师", "location": "示例教室-5",
     "day": 5, "start": 1, "end": 2, "weeks": "1-16"},
    {"name": "管理学", "teacher": "示例教师", "location": "示例教室-6",
     "day": 2, "start": 3, "end": 4, "weeks": "1-16"},
]


def parse_weeks(weeks_str: str):
    """'1-16' -> {1..16}; '1,3,5' -> {1,3,5}; 支持混合 '1-8,10-16'"""
    weeks = set()
    for part in str(weeks_str).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            weeks.update(range(int(a), int(b) + 1))
        elif part:
            weeks.add(int(part))
    return sorted(weeks)


def make_tz_component():
    tz = Timezone()
    tz.add("tzid", "Asia/Shanghai")
    std = TimezoneStandard()
    std.add("dtstart", datetime(1970, 1, 1, 0, 0))
    std.add("tzoffsetfrom", timedelta(hours=8))
    std.add("tzoffsetto", timedelta(hours=8))
    std.add("tzname", "CST")
    tz.add_component(std)
    return tz


def new_calendar(name: str, desc: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//SHUFE Calendar//shufe_ics_gen//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-caldesc", desc)
    cal.add_component(make_tz_component())
    return cal


def course_event(cal: Calendar, course: dict, semester_start: date, periods: dict, tag: str = ""):
    weeks = parse_weeks(course["weeks"])
    if not weeks:
        return
    first_week_date = semester_start + timedelta(days=course["day"] - 1)  # day: 1=周一
    start_h, start_m = map(int, periods[str(course["start"])][0].split(":"))
    end_h, end_m = map(int, periods[str(course["end"])][1].split(":"))
    dtstart = datetime(first_week_date.year, first_week_date.month, first_week_date.day,
                       start_h, start_m, tzinfo=TZ)
    dtend = datetime(first_week_date.year, first_week_date.month, first_week_date.day,
                     end_h, end_m, tzinfo=TZ)

    ev = Event()
    title = f"{course['name']}{' ' + tag if tag else ''}"
    ev.add("summary", title)
    # 稳定 UID：课名+星期+节次+周次 → 订阅刷新时苹果据此去重/更新
    import hashlib
    uid_src = f"{course['name']}|{course['day']}|{course['start']}-{course['end']}|{weeks}"
    ev.add("uid", hashlib.sha1(uid_src.encode()).hexdigest() + "@shufe-calendar")
    if course.get("location"):
        ev.add("location", course["location"])
    desc_lines = [f"第 {weeks[0]}-{weeks[-1]} 周" if len(weeks) > 1 else f"第 {weeks[0]} 周"]
    if course.get("teacher"):
        desc_lines.append(f"教师：{course['teacher']}")
    if course.get("note"):
        desc_lines.append(course["note"])
    ev.add("description", "\n".join(desc_lines))
    ev.add("dtstart", dtstart)
    ev.add("dtend", dtend)
    ev.add("rrule", {"freq": "weekly", "count": len(weeks)})
    # EXDATE：排除非上课周（单双周/假期）
    exdates = []
    for i in range(1, weeks[-1] + 1):
        if i not in weeks:
            d = semester_start + timedelta(days=course["day"] - 1 + 7 * (i - 1))
            exdates.append(datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ))
    if exdates:
        ev.add("exdate", exdates)
    cal.add_component(ev)


def add_single_event(cal: Calendar, title: str, when: datetime, end: datetime,
                     location: str = "", desc: str = ""):
    ev = Event()
    ev.add("summary", title)
    if location:
        ev.add("location", location)
    if desc:
        ev.add("description", desc)
    ev.add("dtstart", when)
    ev.add("dtend", end)
    ev.add("uid", f"{title}-{when:%Y%m%d%H%M}@shufe-calendar")
    cal.add_component(ev)


def render(cal: Calendar) -> bytes:
    return cal.to_ical().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def build_course_ics(courses, semester_start: date, periods=None) -> bytes:
    cal = new_calendar("上财课表", "SHUFE 课程表订阅源")
    periods = periods or DEFAULT_PERIODS
    for c in courses:
        course_event(cal, c, semester_start, periods)
    return render(cal)


def build_exams_ics(exams: list) -> bytes:
    """exams: [{title, start:'2026-11-09T09:00', end:'2026-11-09T11:00', location, note}]"""
    cal = new_calendar("上财考试", "SHUFE 考试安排订阅源")
    for e in exams:
        add_single_event(cal, e["title"], datetime.fromisoformat(e["start"]).replace(tzinfo=TZ),
                         datetime.fromisoformat(e["end"]).replace(tzinfo=TZ),
                         e.get("location", ""), e.get("note", ""))
    return render(cal)


def main():
    ap = argparse.ArgumentParser(description="SHUFE 课表 → ICS 生成器")
    ap.add_argument("--demo", action="store_true", help="使用内置示例课表")
    ap.add_argument("--courses", help="课程 JSON 文件路径")
    ap.add_argument("--eams", action="store_true", help="从 EAMS 拉取课表（开学后可用）")
    ap.add_argument("--semester-start", default="2026-09-07", help="开学第一周周一日期")
    ap.add_argument("--periods", help="节次时间映射 JSON（可选）")
    ap.add_argument("--outdir", default="dist", help="输出目录（默认 ./dist）")
    args = ap.parse_args()

    semester_start = date.fromisoformat(args.semester_start)
    periods = DEFAULT_PERIODS
    if args.periods:
        with open(args.periods, encoding="utf-8") as f:
            periods = {str(k): tuple(v) for k, v in json.load(f).items()}

    if args.demo:
        courses = DEMO_COURSES
    elif args.courses:
        with open(args.courses, encoding="utf-8") as f:
            courses = json.load(f)
    elif args.eams:
        sys.path.insert(0, ".")
        try:
            from fetch_eams import fetch_course_table  # 开学后由 fetch_eams.py 提供
            courses = fetch_course_table()
        except ImportError:
            print("[EAMS] fetch_eams.py 未提供 fetch_course_table()，请开学后更新", file=sys.stderr)
            sys.exit(1)
    else:
        ap.error("需要 --demo / --courses / --eams 之一")

    import os
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "course.ics"), "wb") as f:
        f.write(build_course_ics(courses, semester_start, periods))
    print(f"[OK] 生成 {args.outdir}/course.ics（{len(courses)} 门课，学期起始 {semester_start}）")


if __name__ == "__main__":
    main()
