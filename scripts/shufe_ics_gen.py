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

# 英文课名 → 中文（EAMS 课表为英文 locale；新课程需补充）
EN_ZH_MAP = {
    "Probability Theory and Mathematical Statistics": "概率论与数理统计",
    "Mathematical Analysis III": "数学分析（三）",
    "Discoverying Data": "数据发现",
    "Physical Education III": "体育（三）",
    "Intermediate Macroeconomics": "中级宏观经济学",
    "Basic principles of Marxism": "马克思主义基本原理",
    "Introduction to Economic Law": "经济法导论",
    "Investment Economics": "投资经济学",
    "Ordinary Differential Equations": "常微分方程",
    "Marketing": "市场营销",
}

# 上财真实节次 → 时间映射（0-based，来自 EAMS 课表页表头 2026-08 实测）
DEFAULT_PERIODS = {
    "0": ("08:00", "08:45"), "1": ("08:55", "09:40"),
    "2": ("10:05", "10:50"), "3": ("11:00", "11:45"), "4": ("11:55", "12:40"),
    "5": ("13:20", "14:05"), "6": ("14:15", "15:00"),
    "7": ("15:25", "16:10"), "8": ("16:20", "17:05"), "9": ("17:15", "18:00"),
    "10": ("18:00", "18:45"), "11": ("18:55", "19:40"),
    "12": ("19:50", "20:35"), "13": ("20:45", "21:30"),
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


def parse_weeks(weeks_str):
    """'1-16' -> {1..16}; '1,3,5' -> {1,3,5}; 支持混合 '1-8,10-16'; 也接受 list"""
    if isinstance(weeks_str, (list, tuple, set)):
        return sorted(int(w) for w in weeks_str)
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


def fetch_eams_courses():
    """从 EAMS 抓取当前学年课表 → 标准课程 dict 列表
    流程: 表单编码 + 双键(semesterId&semester.id) + dataQuery 学期发现 + TaskActivity 解析
    """
    import os
    import re
    import urllib.parse
    import urllib.request
    import urllib.error
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fetch_eams import ensure_session

    EAMS = "https://eams.sufe.edu.cn/eams"
    s = ensure_session()
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

    # 1) 会话热身: projectId 查询设置上下文 (必须, 否则学期列表为空)
    form_post(f"{EAMS}/dataQuery.action", {"dataType": "projectId", "entityId": ""})
    raw = ""
    for attempt in range(4):
        st, b = form_post(f"{EAMS}/dataQuery.action",
                          {"dataType": "semesterCalendar", "tagId": "x",
                           "empty": "false", "value": "", "entityId": ""})
        raw = b.decode("utf-8", "ignore")
        if re.search(r"y0:\[\{id:\d+,", raw):
            break
        import time
        time.sleep(2)
    m0 = re.search(r"y0:\[\{id:(\d+),", raw)
    if not m0:
        raise RuntimeError(f"学期列表解析失败: {raw[:200]}")
    sid = m0.group(1)  # 最新学年 (y0) 第1学期
    print(f"[EAMS] 当前学期 semesterId={sid}")

    # 2) 课表 (semesterId + semester.id 双键都必须; EAMS 模板间歇性出错, 重试)
    html = ""
    for attempt in range(4):
        st, b = form_post(f"{EAMS}/courseTableForStd!courseTable.action",
                          {"semesterId": sid, "semester.id": sid, "ids": "410965",
                           "project.id": "1", "setting.kind": "std", "startWeek": "1"})
        html = b.decode("utf-8", "ignore")
        if ("未开放" not in html and "FreeMarker" not in html
                and html.count('new TaskActivity("') > 5):
            break
        import time
        time.sleep(2)
    if "未开放" in html or "FreeMarker" in html or html.count('new TaskActivity("') <= 5:
        raise RuntimeError(f"课表抓取失败(重试后仍异常, len={len(html)})")

    # 3) 解析 TaskActivity + index
    act_pat = re.compile(r'new\s+TaskActivity\("([^"]*)","([^"]*)","([^"]*)",\s*("[^"]*"|\w+),\s*"([^"]*)","([^"]*)","([^"]*)"\)')
    name_pat = re.compile(r'var\s+courseNameLessonNo\s*=\s*"([^"]*)"')
    idx_pat = re.compile(r'index\s*=\s*(\d+)\*unitCount\+(\d+);')
    out = []
    for m in act_pat.finditer(html):
        tid, tname, cno, cname_expr, rid, room, weeks = m.groups()
        names = name_pat.findall(html[:m.start()])
        cname = names[-1] if names else cname_expr.strip('"')
        seg_after = html[m.end():]
        nxt = act_pat.search(seg_after)
        seg_until = seg_after[:nxt.start()] if nxt else seg_after
        for wd, per in idx_pat.findall(seg_until):
            week_list = [i + 1 for i, ch in enumerate(weeks) if ch == "1"]
            out.append({"teacher": tname, "course_no": cno, "course_name": cname,
                        "room": room, "weekday": int(wd), "period": int(per),
                        "week_list": week_list})

    # 4) 合并: 线下/线上课分开; 同课名+周几+节次+模式 → 周次并集, 教师/教室轮换进描述
    def is_online(room):
        return any(k in room for k in ("在线", "直播", "慕课"))

    merged = {}
    for r in out:
        online = is_online(r["room"])
        key = (r["course_name"], r["weekday"], r["period"], online)
        if key not in merged:
            merged[key] = {"course_name": r["course_name"], "teacher": r["teacher"],
                           "rooms": [r["room"]], "weekday": r["weekday"],
                           "start": r["period"], "end": r["period"],
                           "weeks": set(r["week_list"]), "course_no": r["course_no"],
                           "online": online, "teachers": [r["teacher"]]}
        else:
            mrec = merged[key]
            mrec["start"] = min(mrec["start"], r["period"])
            mrec["end"] = max(mrec["end"], r["period"])
            mrec["weeks"] |= set(r["week_list"])
            if r["room"] not in mrec["rooms"]:
                mrec["rooms"].append(r["room"])
            if r["teacher"] not in mrec["teachers"]:
                mrec["teachers"].append(r["teacher"])

    courses = []
    for key, r in sorted(merged.items()):
        base_name = re.sub(r"\(\d+\)$", "", r["course_name"]).strip()
        title = EN_ZH_MAP.get(base_name, base_name)  # 中文课名, 未知保留英文
        prefix = "[线上]" if r["online"] else "[线下]"
        weeks_sorted = sorted(r["weeks"])
        room = " / ".join(r["rooms"])
        note = f"课程号: {r['course_no']}；英文: {base_name}"
        if len(r["teachers"]) > 1:
            note += f"；教师轮换: {' / '.join(r['teachers'])}"
        if len(r["rooms"]) > 1:
            note += f"；教室轮换: {' / '.join(r['rooms'])}"
        courses.append({
            "name": f"{prefix}{title}", "teacher": r["teachers"][0], "location": room,
            "day": r["weekday"] + 1, "start": r["start"], "end": r["end"],
            "weeks": ",".join(str(w) for w in weeks_sorted), "note": note,
        })
    print(f"[EAMS] 解析 {len(out)} 条活动 → 合并 {len(courses)} 门课次")
    return {"semester_id": int(sid), "courses": courses}


def build_holidays_ics(events_file: str) -> bytes:
    """校历日历: calendar_events.json → holidays.ics（全天事件）"""
    import hashlib
    with open(events_file, encoding="utf-8") as f:
        data = json.load(f)
    cal = new_calendar("上财校历", "SHUFE 校历/节假日订阅源")
    for sem, events in data.items():
        for e in events:
            d0 = date.fromisoformat(e["date"])
            d1 = date.fromisoformat(e["end"]) if e.get("end") else d0
            ev = Event()
            ev.add("summary", e["title"])
            ev.add("uid", hashlib.sha1(f"{sem}|{e['date']}|{e['title']}".encode()).hexdigest() + "@shufe-calendar")
            ev.add("dtstart", d0)
            ev.add("dtend", d1 + timedelta(days=1))
            cal.add_component(ev)
    return render(cal)


def main():
    ap = argparse.ArgumentParser(description="SHUFE 课表 → ICS 生成器")
    ap.add_argument("--demo", action="store_true", help="使用内置示例课表")
    ap.add_argument("--courses", help="课程 JSON 文件路径")
    ap.add_argument("--eams", action="store_true", help="从 EAMS 拉取课表（开学后可用）")
    ap.add_argument("--holidays", metavar="JSON", help="从校历 JSON 生成 holidays.ics")
    ap.add_argument("--semester-start", default="2026-08-31", help="开学第一周周一日期（2026-2027-1 = 2026-08-31，校历确认）")
    ap.add_argument("--periods", help="节次时间映射 JSON（可选）")
    ap.add_argument("--outdir", default="dist", help="输出目录（默认 ./dist）")
    args = ap.parse_args()

    semester_start = date.fromisoformat(args.semester_start)
    periods = DEFAULT_PERIODS
    if args.periods:
        with open(args.periods, encoding="utf-8") as f:
            periods = {str(k): tuple(v) for k, v in json.load(f).items()}

    if args.holidays:
        import os
        os.makedirs(args.outdir, exist_ok=True)
        with open(os.path.join(args.outdir, "holidays.ics"), "wb") as f:
            f.write(build_holidays_ics(args.holidays))
        print(f"[OK] 生成 {args.outdir}/holidays.ics")
        return

    if args.demo:
        courses = DEMO_COURSES
    elif args.courses:
        with open(args.courses, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            # 支持 {"semester_start": "...", "courses": [...]} 包装格式
            if raw.get("semester_start") and not args.semester_start:
                ap.error("--courses 带 semester_start 时需配合 --semester-start 显式指定")
            semester_start = date.fromisoformat(args.semester_start)
            courses = raw["courses"]
        else:
            courses = raw
    elif args.eams:
        try:
            res = fetch_eams_courses()
            courses = res["courses"]
        except Exception as e:
            print(f"[EAMS] 抓取失败: {e}", file=sys.stderr)
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
