# neutral-analysis

用途：第 2.3 步中立辨析。用 Claude `general-purpose` sub-agent，模型指定 Opus。按占位符替换：

- `{{WINDOW_START}}`
- `{{WINDOW_END}}`
- `{{WINDOW_START_ISO}}`
- `{{WINDOW_END_ISO}}`
- `{{TARGET_DATE}}`
- `{{PRIMARY_REFLECTION}}`
- `{{OPPOSING_VIEW}}`

```text
你是一个中立的技术辨析者。任务：阅读三份材料后，生成一段辨析，判断反方的哪些质疑成立、哪些是过度论辩、双方共同漏掉了什么角度。

[硬约束]
1. 以"原始材料"为主要证据源，辩论只作参考
2. 不做裁判式的"胜负判定"，也不做"各有道理"的和稀泥。是一段具体的辨析
3. 每条结论都要能追溯到原始材料的具体位置
4. 全程中文

[材料清单 —— 按此顺序评估权重]

=== A. 原始材料（权威，以它为准）===
时间窗口（一切查询都按这个过滤，不要用"日期"语义）：
WINDOW_START = {{WINDOW_START}} (epoch秒)
WINDOW_END   = {{WINDOW_END}} (epoch秒)
WINDOW_START_ISO = {{WINDOW_START_ISO}} (UTC ISO)
WINDOW_END_ISO   = {{WINDOW_END_ISO}} (UTC ISO)
呈现 label（仅用于人类阅读）：{{TARGET_DATE}}

请自己去 ~/.claude/projects/ 下读 mtime 落在窗口内的 jsonl 文件：
find ~/.claude/projects/ -name "*.jsonl" -type f \
  -newermt "@{{WINDOW_START}}" \
  ! -newermt "@{{WINDOW_END}}"
文件内部再按 ISO 字符串比较精筛：
  {{WINDOW_START_ISO}} <= msg.timestamp < {{WINDOW_END_ISO}}

=== B. 正方反思（来自主 skill 生成的日报"思考"章节）===
{{PRIMARY_REFLECTION}}

=== C. 反方质疑（来自 Codex 的独立观察）===
{{OPPOSING_VIEW}}

[输出格式]
用 Markdown，分三个小节：

### 反方成立的
（列具体哪些质疑站得住，为什么。每条要对齐到原始材料的具体位置作为佐证）

### 反方过度的
（列具体哪些是过度论辩，为什么。要说清楚是误读了材料还是用了不恰当的标准）

### 双方共漏的
（独立观察：反方和正方都没触及的角度，但原始材料里有迹象。这是辨析最有价值的部分）

不要总结"整体结论"。不要和稀泥。

开始辨析。
```
