#!/usr/bin/env python3
"""课表追踪 v4: 从 EAMS 实时抓取课表 + 数据库快照比对, 有变动才输出 (供 cron agent 模式消费)
- 学期自动发现 (dataQuery semesterCalendar → 最新学年第1学期)
- 与 sufe.db course_snapshot 表比对 (fingerprint = 课程 JSON)
- 首次开放 / 有变动 → 输出 [COURSE_OPEN]/[COURSE_CHANGE] + 详情
- 无变动 → 输出空 (agent 应回复 [SILENT])
- 复用 shufe_ics_gen.fetch_eams_courses() (表单编码 + 双键 + TaskActivity 解析)
"""
import datetime
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shufe_ics_gen import fetch_eams_courses

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sufe.db")


def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS course_snapshot (
        semester_id INTEGER PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        courses_json TEXT,
        fetched_at TEXT NOT NULL,
        last_change TEXT
    )""")
    conn.commit()
    return conn


def main():
    conn = init_db()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outputs = []

    try:
        res = fetch_eams_courses()
    except Exception as e:
        print(f"[ERROR] 课表抓取失败: {e}", flush=True)
        sys.exit(1)

    sid = res["semester_id"]
    courses = res["courses"]
    fp = hashlib.sha256(json.dumps(courses, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    courses_json = json.dumps(courses, ensure_ascii=False)

    cur = conn.execute("SELECT fingerprint, courses_json FROM course_snapshot WHERE semester_id=?", (sid,))
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO course_snapshot VALUES (?,?,?,?,?)",
                     (sid, fp, courses_json, now, "首次开放"))
        lines = [f"[COURSE_OPEN] 学期 {sid} 课表开放!", "课表:"]
        for c in courses:
            lines.append(f"· 周{c['day']} 第{c['start']}-{c['end']}节 {c['name']} | {c['teacher']} | {c['location']} | 周{c['weeks']}")
        outputs.append("\n".join(lines))
        print(f"[学期发现] {sid} 课表开放(首次), {len(courses)} 门课", flush=True)
    elif row[0] != fp:
        old = json.loads(row[1]) if row[1] else []
        old_names = {(c["name"], c["day"], c["start"], c["end"]) for c in old}
        new_names = {(c["name"], c["day"], c["start"], c["end"]) for c in courses}
        added = new_names - old_names
        removed = old_names - new_names
        conn.execute("UPDATE course_snapshot SET fingerprint=?, courses_json=?, fetched_at=?, last_change=? WHERE semester_id=?",
                     (fp, courses_json, now, "有变动", sid))
        lines = [f"[COURSE_CHANGE] 学期 {sid} 课表有变动!"]
        if added:
            lines.append("新增:")
            for c in courses:
                if (c["name"], c["day"], c["start"], c["end"]) in added:
                    lines.append(f"· 周{c['day']} 第{c['start']}-{c['end']}节 {c['name']} | {c['teacher']} | {c['location']} | 周{c['weeks']}")
        if removed:
            lines.append("移除:")
            for c in old:
                if (c["name"], c["day"], c["start"], c["end"]) in removed:
                    lines.append(f"· 周{c['day']} 第{c['start']}-{c['end']}节 {c['name']}")
        outputs.append("\n".join(lines))
        print(f"[变动] {sid}: +{len(added)} -{len(removed)}", flush=True)
    else:
        print("[无变动]", flush=True)

    conn.commit()
    conn.close()
    if outputs:
        print("\n\n".join(outputs), flush=True)


if __name__ == "__main__":
    main()
