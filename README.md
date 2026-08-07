# SHUFE Calendar ICS

上财课表 → iCalendar (.ics) 订阅源，托管于 GitHub Pages，
在 iPhone / Mac / iPad 日历中直接订阅。

## 订阅地址

| 日历 | 地址 |
| --- | --- |
| 课表 | `https://haohaoo3o.github.io/shufe-calendar-ics/dist/course.ics` |
| 校历/节假日 | `https://haohaoo3o.github.io/shufe-calendar-ics/dist/holidays.ics` |
| webcal 版 | `webcal://haohaoo3o.github.io/shufe-calendar-ics/dist/course.ics` |

✅ **课表 = 2026-2027 学年第 1 学期真实课表**（EAMS 数据，中文课名 + [线下]/[线上] 标注，14 门课次，第 2-17 周）；
✅ **校历 = 官方校历解析**（开学 8/31、中秋 9/25、国庆 10/1、考试周 12/21-1/1、寒假 1/18 起，每周日自动监控校历图片 hash，更新时自动识别并刷新）。

## iPhone / Mac 订阅步骤

**iOS 26**：日历 App → 点「日历」按钮 → 「添加日历」→「添加订阅日历」
→ 粘贴上面地址 →「查找」→ 命名/选色 → 账户选「iCloud」→「完成」。
**iOS 18 及更早**：日历 App → 底部「日历」→「添加日历」→「添加订阅日历」→ 粘贴地址 →「订阅」。
**macOS**：日历 App → 文件 → 新建日历订阅 → 粘贴地址 →「订阅」。

订阅后自动刷新；iOS 26 可在 日历列表 → 日历 ⓘ → 打开「日程提醒」。

## 数据与更新

- 数据源：EAMS `courseTableForStd!courseTable.action`（2026-2027-1 学期 id=3928）
- GitHub Actions 每天 14:00（北京时间）自动拉取最新课表并重新发布；EAMS 不可用时回退到仓库内快照
- 学期起始周：**2026-08-31**（第 1 周，校历确认在读生 8/31 正式上课）；个人课表第 1 周无课，实际从第 2 周（9/7）开始（RRULE + EXDATE 精确对齐）
- 节次时间：上财真实作息（08:00–21:30，14 时段，来自 EAMS 表头实测）
- 课程名中文（自动映射），[线下]/[线上] 前缀区分授课模式；隔周轮换课程（如马原）拆分为两条独立事件
- 时区：`TZID=Asia/Shanghai` + VTIMEZONE，跨时区不错位

## 本地生成

```bash
pip install icalendar
python scripts/shufe_ics_gen.py --eams                        # 从 EAMS 实时拉取（需凭据）
python scripts/shufe_ics_gen.py --courses scripts/courses_real.json --semester-start 2026-09-07  # 用快照
python scripts/shufe_ics_gen.py --demo                        # 示例课表
```

输出到 `dist/course.ics`。课程 JSON 字段：`name / teacher / location / day(1=周一) / start(0-based节次) / end / weeks("1-16" 或 "1,3,5")`。

## 路线图

- [x] EAMS 真实课表接入（2026-2027-1）
- [ ] 考试安排日历（exams.ics）
- [ ] Canvas 作业截止日历
- [ ] 校历/节假日订阅源
- [ ] 微信推送提醒层（复用通知管线）
