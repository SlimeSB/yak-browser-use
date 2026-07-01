## ADDED Requirements

### Requirement: file_write SHALL 支持 {*变量名} 模板引用

当 `content` 参数中包含 `{*变量名}` 语法时，系统 MUST 在执行写入前从 `ctx.shared_store` 中取值替换。

#### Scenario: content 直接引用 shared_store 变量

- **WHEN** Agent 调用 `file_write(path="result.csv", content="{*csv_data}")` 且 `ctx.shared_store["csv_data"]` 存在
- **THEN** 写入文件的内容 MUST 是 `ctx.shared_store["csv_data"]` 的 JSON 序列化字符串

#### Scenario: content 中混合静态文本和变量引用

- **WHEN** Agent 调用 `file_write(path="report.md", content="数据摘要:\n{*summary}\n\n---原始数据---")` 且 `ctx.shared_store["summary"]` 存在
- **THEN** 写入文件的内容 MUST 将 `{*summary}` 替换为 shared_store 值，其余文本保持不变

#### Scenario: content 中无模板语法

- **WHEN** Agent 调用 `file_write(path="note.txt", content="hello world")`
- **THEN** 写入文件的内容 MUST 是 `"hello world"`，与变更前行为完全一致

#### Scenario: 引用不存在的变量

- **WHEN** Agent 调用 `file_write(path="result.csv", content="{*nonexistent}")` 且 `ctx.shared_store` 中无 `nonexistent` 键
- **THEN** MUST 写入原始文本 `"{*nonexistent}"`（保留原文，不报错），并在返回结果中添加 `_warnings: ["变量 nonexistent 未找到"]`
