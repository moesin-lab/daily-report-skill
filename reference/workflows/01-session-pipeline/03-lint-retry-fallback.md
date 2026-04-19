### 步骤 c：lint

顺序固定：

```bash
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/lint-phase1.py
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/lint-facet.py
```

读取 `$RUN_DIR/lint-report.json`：

- 空数组：进入步骤 d。
- 非空：进入步骤 c.5。

### 步骤 c.5：重派一次

对失败 sid 并行重派 `session-reader`。同一 sid 的 md / facet 失败合并为一次调用。

追加变量：

```text
RETRY_OF_LINT=1
PREVIOUS_OUTPUT=<失败文件路径；多个则逐行给出>
LINT_ERRORS=
<原始错误逐行给出>
```

不做第三次重派。

### 步骤 c.6：复跑 lint

```bash
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/lint-phase1.py
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/lint-facet.py
```

### 步骤 c.7：二次失败降级

再次读取 `lint-report.json`：

- 空数组：进入步骤 d。
- 非空：执行机械降级脚本，再复跑 lint。

```bash
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/fallback-session-artifacts.py --from-lint-report
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/lint-phase1.py
RUN_DIR="$RUN_DIR" python3 ~/.claude/skills/daily-report/scripts/session/lint-facet.py
```

脚本按 `target` 字段覆盖失败文件，并记录 `$RUN_DIR/runtime-issues.txt`。
