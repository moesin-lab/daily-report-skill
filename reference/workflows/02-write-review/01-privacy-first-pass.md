## 第 2.1 步：隐私审查

`$MAIN_BODY` 写完后，调用 `general-purpose` 子 agent 做隐私审查，模型指定 Haiku。

读取 `reference/prompts/privacy-review.md`，把 `{{REPORT_CONTENT}}` 替换为 `$MAIN_BODY`。

发现问题就修改并复审，直到通过。
