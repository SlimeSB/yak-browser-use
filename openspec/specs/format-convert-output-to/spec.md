# format-convert-output-to Specification

## Purpose
TBD - created by archiving change chat-agent-extract-tools. Update Purpose after archive.
## Requirements
### Requirement: format_convert SHALL 支持 output_to 参数将转换后的绝对路径存入 shared_store

当 Agent 调用 `format_convert` 并提供 `output_to` 参数时，转换成功后将目标文件路径存入 `ctx.shared_store[output_to]`。存入的值为 `validate_path()` 解析后的**绝对路径**字符串，确保 Agent 在后续步骤中能准确定位文件。

#### Scenario: 文件转换后存入 shared_store（绝对路径）

- **WHEN** Agent 调用 `format_convert(source="data.json", target="output.csv", output_to="csv_path")`
- **THEN** 转换成功后 `ctx.shared_store["csv_path"]` MUST 等于 `validate_path("output.csv")` 返回的绝对路径字符串
- **AND** 返回中 MUST 含 `"_output_to": "csv_path"`

#### Scenario: source_json 转换后存入 shared_store

- **WHEN** Agent 调用 `format_convert(source_json=[{"a":1}], target="output.xlsx", output_to="xlsx_path")`
- **THEN** 转换成功后 `ctx.shared_store["xlsx_path"]` MUST 是 `output.xlsx` 的绝对路径字符串

#### Scenario: 转换失败时不存入 shared_store

- **WHEN** Agent 调用 `format_convert(source="nonexistent.json", target="output.csv", output_to="result")` 且源文件不存在
- **THEN** MUST 不修改 `ctx.shared_store`
- **AND** 返回 `{"ok": false, "error": "..."}`

#### Scenario: 不提供 output_to 时行为不变

- **WHEN** Agent 调用 `format_convert(source="data.json", target="output.csv")` 且不提供 `output_to`
- **THEN** MUST 不修改 `ctx.shared_store`，行为与变更前完全一致

