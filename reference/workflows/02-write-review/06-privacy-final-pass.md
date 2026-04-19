## 第 2.6 步：全文隐私复审

对完整日报重新执行第 2.1 步隐私审查(reference/workflows/02-write-review/01-privacy-first-pass.md) prompt，调用 `general-purpose` 子 agent，模型指定 Haiku。

范围包括：

- 主体正文
- 思考 / 建议
- Token 统计
- Session 指标
- 审议过程附录

发现问题就修改并复审，直到通过。通过后才能进入第 3.0 步发布。
