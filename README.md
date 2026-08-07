# SHUFE Calendar ICS

上财课表 / 考试 / 作业截止 → iCalendar (.ics) 订阅源，托管于 GitHub Pages，
在 iPhone / Mac / iPad 日历中直接订阅。

## 订阅地址

| 日历 | 地址 |
| --- | --- |
| 课表（示例数据） | `https://haohaoo3o.github.io/shufe-calendar-ics/dist/course.ics` |
| webcal 版 | `webcal://haohaoo3o.github.io/shufe-calendar-ics/dist/course.ics` |

> ⚠️ 当前为**示例数据**（培养计划建议课，非真实课表）。EAMS 课表接口暑假未开放，
> 开学后自动切换真实数据，订阅地址不变。

## iPhone / Mac 订阅步骤

**iOS 26**：日历 App → 点「日历」按钮 → 「添加日历」→「添加订阅日历」
→ 粘贴上面地址 →「查找」→ 命名/选色 → 账户选「iCloud」→「完成」。
**iOS 18 及更早**：日历 App → 底部「日历」→「添加日历」→「添加订阅日历」→ 粘贴地址 →「订阅」。
**macOS**：日历 App → 文件 → 新建日历订阅 → 粘贴地址 →「订阅」。

订阅后自动刷新；iOS 26 可在 日历列表 → 日历 ⓘ → 打开「日程提醒」。

## 生成与更新

```bash
python scripts/shufe_ics_gen.py --demo        # 示例课表
python scripts/shufe_ics_gen.py --courses scripts/courses.example.json  # 自定义课表
python scripts/shufe_ics_gen.py --eams        # 开学后从 EAMS 拉真实课表
```

- 输出到 `dist/course.ics`，提交后 GitHub Pages 自动部署
- GitHub Actions（`.github/workflows/update-calendar.yml`）每天 06:00 UTC 自动重新生成并提交
- 周次支持：`1-16`（全周）、`1,3,5,...`（单周）、`2,4,6,...`（双周）、`1-8,10-16`（混合）

## 时区 / 兼容性

- 所有事件使用 `TZID=Asia/Shanghai` + VTIMEZONE，跨时区不错位
- RRULE + EXDATE 表达周期与单双周，Apple / Google / Outlook 均兼容
- 稳定 UID：课表变更时苹果日历只更新对应事件，不重建

## 路线图

- [ ] 开学后 EAMS 课表接入（真实数据）
- [ ] 考试安排日历（exams.ics）
- [ ] Canvas 作业截止日历
- [ ] 校历/节假日订阅源
- [ ] 微信推送提醒层（复用通知管线）
