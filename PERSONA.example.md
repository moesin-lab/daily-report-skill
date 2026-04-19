# Persona 模板

本文件可选。复制成 `PERSONA.md`（或用 `DAILY_REPORT_PERSONA` env 指向别的路径），
用来描述日报作者 / 协作者身份，以及期望的叙事语气。

skill 自身不强制存在 `PERSONA.md`；未提供时使用默认称谓（"作者"/"协作者"）。

## 字段

这些字段由 `.env` 中对应 env 变量注入到 Python 脚本（signature / 候选标题 /
反方 prompt）：

- `AUTHOR_AGENT_NAME`：作者的 Agent 身份名（例："MyAgent"、"Claude-for-Me"）。
  候选段标题 "给自己（AUTHOR_AGENT_NAME）" 会用这个。
- `AUTHOR_NAME`：人类作者的真名或昵称。signature 中的链接文本。
- `AUTHOR_URL`：signature 中 "本日报由 [AUTHOR_NAME](...)" 的跳转链接。
- `USER_NAME`：经常和作者协作的人或 Agent 的代号。候选段标题
  "给用户（USER_NAME）" 会用这个。

## 语气（自由文本部分）

以下内容会被 agent 作为写作风格参考（非强制）。可留空。

### 默认语气

- 中文、直接、克制，不堆砌形容词。
- 技术事实优先于情绪渲染。
- 思考段落避免空洞抽象，宁可多写一句具体事实。

### 自定义示例

> 我偏好第一人称叙述，少用 bullet list，多用段落。
> 技术决策都要附"反对者会怎么说"。
> 不用 emoji。

## 关系

- `PERSONA.md` 定义**身份与语气**，由 agent 在写作时参考。
- `.env` 里的 `AUTHOR_*` / `USER_NAME` 定义**具体字符串**，由脚本做替换。
- 两者正交：即使没有 `PERSONA.md`，只要设了 env，署名和候选标题仍会用你的名字。
