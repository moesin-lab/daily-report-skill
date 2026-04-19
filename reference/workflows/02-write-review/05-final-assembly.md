## 第 2.5 步：拼接完整日报

本步骤涉及最终写作组织，调用 `general-purpose` 子 agent，模型指定 Opus。

输入：

- `$MAIN_BODY`
- `$REFLECTION_SECTION`
- `$SUGGESTIONS_SECTION`
- `$TOKEN_STATS`
- `$OPPOSING_CONTENT`
- `$ANALYSIS_CONTENT`

章节顺序：

```text
概览 → 今日工作 → GitHub 活动 → 总结 → 运行时问题（条件）→ 思考（条件）→ 建议（条件）→ Token 统计 → Session 指标（条件）→ 审议过程附录（条件）→ 署名
```

步骤：

1. 以 `$MAIN_BODY` 开头。
2. `$REFLECTION_SECTION` 非空时追加。
3. `$SUGGESTIONS_SECTION` 非空时追加。
4. 读取 `reference/templates/token-stats.md`，用 `$TOKEN_STATS` 填充。
5. 生成 Session 指标：
   ```bash
   RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/aggregate-facet.py
   ```
   stdout 非空时追加；空则省略整节。
6. 反方或辨析非空时，读取 `reference/templates/deliberation-appendix.md`，填充要点后追加。
7. 追加 signature：不要直接 `cat` 模板，要用 render 脚本把占位符换成 env 值。
   ```bash
   python3 ~/.claude/skills/daily-report/scripts/publish/render-signature.py
   ```
   stdout 直接追加到日报尾部。env 中 `AUTHOR_NAME` / `AUTHOR_URL` / `AUTHOR_AGENT_NAME`
   任一未设置时脚本自动退化为中性措辞，永远不会写出 `{{...}}` 字面量。

附录要点提取：

- `$OPPOSING_CONTENT`：每条质疑压成 1 行，保留证据锚点和盲点结论。
- `$ANALYSIS_CONTENT`：按“成立 / 过度 / 共漏”提炼，每类 1-3 行。
- 反方和辨析都跳过时，附录整块省略。

省略规则：

| 章节 | 省略条件 |
|------|----------|
| 运行时问题 | `$MAIN_BODY` 未包含该节 |
| 思考 | `$REFLECTION_SECTION` 为空 |
| 建议 | `$SUGGESTIONS_SECTION` 为空 |
| Session 指标 | `aggregate-facet.py` stdout 为空 |
| 审议过程附录 | 反方和辨析都跳过 |
| Token 统计 | 不省略 |
