#!/usr/bin/env python3
"""上财 EAMS 数据采集: 成绩/课表/考试 → SQLite + Markdown 报告
用法: python fetch_eams.py [--grades] [--course-table] [--exams] [--report]
默认全部采集
"""
import argparse
import datetime
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shufe_auth import AuthSession, login

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sufe.db")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
EAMS = "https://eams.sufe.edu.cn/eams"

# 凭据实际位于 hermes 根目录 secrets/（C:\Users\<user>\AppData\Local\hermes\secrets\）；
# GitHub Actions 等无该路径的环境可用环境变量 SHUFE_CRED_FILE 覆盖
CRED_FILE = os.environ.get("SHUFE_CRED_FILE",
                           os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "secrets", "shufe_portal.txt"))


def ensure_session():
    """确保登录态, cookie 过期则自动重登"""
    s = AuthSession()
    st, b = s.req(f"{EAMS}/home.action")
    if st == 200 and "杨皓博" in b.decode("utf-8", "ignore"):
        return s
    # 重新登录
    if not os.path.exists(CRED_FILE):
        raise RuntimeError("缺少凭据文件 secrets/shufe_portal.txt")
    with open(CRED_FILE) as f:
        user, pw = f.read().strip().split(":", 1)
    ok, res = login(user, pw, session=s)
    if not ok:
        raise RuntimeError(f"自动登录失败: {res}")
    return s


def parse_table(html):
    """解析 HTML 表格为二维列表"""
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if any(cells):
            rows.append(cells)
    return rows


def fetch_grades(s, conn):
    """全部学期成绩"""
    url = f"{EAMS}/teach/grade/course/person!historyCourseGrade.action?projectType=MAJOR"
    st, b = s.req(url, "POST", {})
    html = b.decode("utf-8", "ignore")
    rows = parse_table(html)

    conn.execute("""CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        semester TEXT, course_code TEXT, course_no TEXT, course_name TEXT,
        course_type TEXT, credit REAL, score TEXT, final_score TEXT, grade_point REAL,
        fetched_at TEXT, UNIQUE(semester, course_code)
    )""")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    in_detail = False
    for row in rows:
        joined = " | ".join(row)
        if "Course Name" in joined and "Credit" in joined:
            in_detail = True
            continue
        if not in_detail:
            continue
        if len(row) < 9:
            continue
        sem, code, no, name, ctype, credit, score, final, gp = row[:9]
        try:
            credit = float(credit)
        except ValueError:
            credit = None
        try:
            gp = float(gp) if gp else None
        except ValueError:
            gp = None
        conn.execute("""INSERT OR REPLACE INTO grades
            (semester, course_code, course_no, course_name, course_type, credit, score, final_score, grade_point, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sem, code, no, name, ctype, credit, score, final, gp, now))
        count += 1
    conn.commit()
    # 汇总行 (GPA)
    summary = {}
    for row in rows:
        if "School Summary" in " | ".join(row):
            parts = [c for c in row if c]
            summary["school"] = parts
    # 覆盖的学期
    cur = conn.execute("SELECT DISTINCT semester FROM grades ORDER BY semester DESC")
    sems = [r[0] for r in cur.fetchall()]
    print(f"[成绩] {count} 条课程成绩入库, 覆盖学期: {sems}, 汇总: {summary.get('school')}")
    return count


def fetch_course_table(s, conn):
    """课表 (v2: 表单编码 + semesterId&semester.id 双键 + dataQuery 自动发现学期)
    返回 (semester_id, 课程列表); 未开放/失败抛异常"""
    import re
    import urllib.parse
    import urllib.request
    import urllib.error
    EAMS_BASE = EAMS
    H = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{EAMS_BASE}/courseTableForStd!index.action",
    }

    def form_post(url, params):
        body = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers=H)
        try:
            resp = s.opener.open(req, timeout=20)
            return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    # 会话热身 (必须, 否则学期列表为空)
    form_post(f"{EAMS_BASE}/dataQuery.action", {"dataType": "projectId", "entityId": ""})
    _, b = form_post(f"{EAMS_BASE}/dataQuery.action",
                     {"dataType": "semesterCalendar", "tagId": "x",
                      "empty": "false", "value": "", "entityId": ""})
    raw = b.decode("utf-8", "ignore")
    m0 = re.search(r"y0:\[\{id:(\d+),", raw)
    if not m0:
        raise RuntimeError("学期列表解析失败")
    sid = m0.group(1)
    print(f"[课表] 学期 {sid}")
    st, b = form_post(f"{EAMS_BASE}/courseTableForStd!courseTable.action",
                      {"semesterId": sid, "semester.id": sid, "ids": "410965",
                       "project.id": "1", "setting.kind": "std", "startWeek": "1"})
    html = b.decode("utf-8", "ignore")
    if "未开放" in html or "FreeMarker" in html or html.count('new TaskActivity("') <= 5:
        raise RuntimeError(f"课表未开放或模板异常 (len={len(html)})")
    conn.execute("""CREATE TABLE IF NOT EXISTS course_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT, semester TEXT, row_data TEXT, fetched_at TEXT
    )""")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM course_table WHERE semester=?", (sid,))
    conn.execute("INSERT INTO course_table (semester, row_data, fetched_at) VALUES (?,?,?)",
                 (sid, html[:20000], now))
    conn.commit()
    print(f"[课表] 学期 {sid} 抓取成功 ({len(html)} 字节)")
    return sid, html


def fetch_exams(s, conn, semester_id="3908"):
    """考试安排"""
    url = f"{EAMS}/stdExamTable.action"
    st, b = s.req(url)
    html = b.decode("utf-8", "ignore")
    # 找考试表格 iframe/链接
    links = re.findall(r'<a[^>]*href="([^"]*exam[^"]*)"[^>]*>([^<]{2,40})', html, re.I)
    print(f"[考试] 页面 {st}, 考试链接: {links[:5]}")
    rows = parse_table(html)
    print(f"[考试] 表格行: {len(rows)}")
    for r in rows[:8]:
        print("   ", " | ".join(r)[:150])
    return 0


def generate_report(conn):
    """生成成绩 Markdown 报告"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    cur = conn.execute("""SELECT semester, course_name, course_type, credit, score, grade_point
                          FROM grades ORDER BY semester DESC, course_name""")
    grades = cur.fetchall()
    # 按学期分组
    by_sem = {}
    for sem, name, ctype, credit, score, gp in grades:
        by_sem.setdefault(sem, []).append((name, ctype, credit, score, gp))
    # 学分加权均分/加权GPA
    cur = conn.execute("""SELECT semester, COUNT(*), SUM(credit),
                          SUM(score*credit)/SUM(credit),
                          SUM(grade_point*credit)/SUM(credit)
                          FROM grades
                          WHERE score IS NOT NULL AND score != ''
                          GROUP BY semester""")
    summary = cur.fetchall()

    lines = ["# 上财成绩单", "", f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"> 数据源: EAMS 教务系统 (eams.sufe.edu.cn)", ""]
    for sem, cnt, credit, wavg, wgpa in summary:
        gpa_txt = f"{wgpa:.2f}" if wgpa is not None else "-"
        lines.append(f"## {sem} 学期 — {cnt} 门课 · 加权均分 {wavg:.2f} · {credit:.0f} 学分 · 加权GPA {gpa_txt}")
        lines.append("")
        lines.append("| 课程 | 类型 | 学分 | 成绩 | 绩点 |")
        lines.append("|---|---|---|---|---|")
        for name, ctype, c, score, gp in by_sem.get(sem, []):
            lines.append(f"| {name} | {ctype} | {c} | {score} | {gp or '-'} |")
        lines.append("")
    # 总 GPA
    cur = conn.execute("""SELECT SUM(credit), SUM(score*credit)/SUM(credit),
                          SUM(grade_point*credit)/SUM(credit) FROM grades
                          WHERE score IS NOT NULL AND score != ''""")
    total = cur.fetchone()
    if total and total[0]:
        lines.append(f"## 汇总 — 共 {len(grades)} 门课 · {total[0]:.0f} 学分 · 加权均分 {total[1]:.2f} · 加权GPA {total[2]:.2f}")
    path = os.path.join(REPORT_DIR, "grades.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[报告] 成绩单 -> {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grades", action="store_true")
    ap.add_argument("--course-table", action="store_true")
    ap.add_argument("--exams", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    all_ = not (args.grades or args.course_table or args.exams)

    s = ensure_session()
    conn = sqlite3.connect(DB_PATH)
    if all_ or args.grades:
        fetch_grades(s, conn)
    if all_ or args.course_table:
        fetch_course_table(s, conn)
    if all_ or args.exams:
        fetch_exams(s, conn)
    if all_ or args.report:
        generate_report(conn)
    conn.close()


if __name__ == "__main__":
    main()
