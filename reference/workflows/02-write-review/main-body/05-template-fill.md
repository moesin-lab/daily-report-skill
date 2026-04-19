## 模板填充

读取 `reference/templates/main-body.md`，填充后得到 `$MAIN_BODY`。

占位符：

- `{{TARGET_DATE}}`：`$TARGET_DATE`
- `{{TOPIC_TAGS}}`：0-N 个项目 tag；无可靠 tag 时删除该行。
- `{{OVERVIEW}}`：2-3 句，≤ 250 字。
- `{{MAIN_AXIS_LINE}}`：有 session cards 时写主轴行；空 session 删除。
- `{{TODAY_WORK_SECTION}}`：有 session cards 时写 `## 今日工作`；空 session 删除。
- `{{GITHUB_ACTIVITY}}`：≤ 3 行，列 PR / Issue / Commit 编号，不铺叙述。
- `{{OUTSIDE_ACTIVITY_SECTION}}`：按 `06-outside-activity.md` 写入完整 `## 沙盒外活动` 节；`$OUTSIDE_NOTES_FILE` 空或只含 `<!-- empty -->` 时删除该占位符。
- `{{SUMMARY}}`：2-3 句，≤ 150 字，只写客观总结。
- `{{RUNTIME_ISSUES_SECTION}}`：有运行时问题时写完整章节；无则删除。
