## ADDED Requirements

### Requirement: format_convert SHALL 支持 source_json 参数直接从内存 JSON 转换

当调用 `format_convert` 时提供了 `source_json` 参数，系统 MUST 跳过从 source 文件读取的步骤，直接从 `source_json` 的值转换。

#### Scenario: source_json 为列表数据，target 为 CSV

- **WHEN** Agent 调用 `format_convert(source_json=[{"name":"Alice","age":30},{"name":"Bob","age":25}], target="output.csv", target_fmt="csv")`
- **THEN** 文件 output.csv MUST 包含表头 `name,age` 和对应的两行 CSV 数据
- **AND** MUST 不检查 source 文件是否存在

#### Scenario: source_json 为列表数据，target 为 xlsx

- **WHEN** Agent 调用 `format_convert(source_json=[{"a":1}], target="output.xlsx", target_fmt="xlsx")`
- **THEN** 文件 output.xlsx MUST 能被正常打开并包含 `{a:1}` 对应的行

#### Scenario: source_json 未提供时保持原行为

- **WHEN** Agent 调用 `format_convert(source="data.json", target="output.csv")` 且不提供 `source_json`
- **THEN** 行为 MUST 与变更前完全一致：从 `source` 文件读取并转换

#### Scenario: source_json 和 source 同时提供

- **WHEN** Agent 调用 `format_convert(source="data.json", source_json=[{"x":1}], target="output.csv")`
- **THEN** MUST 优先使用 `source_json`，忽略 `source` 参数
- **AND** MUST 在返回结果中添加 `_note`: `"source_json takes precedence over source"`
