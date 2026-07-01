## ADDED Requirements

### Requirement: format_convert 调度
`format_convert` MUST 在 `_execute_single_tool_call()` 中有专用 handler，不走 `else → execute_tool()` 分支。

**Reason:** chat 模式下 `tools_dir = Path("tools")` 在项目根不存在，`execute_tool()` 的文件路径查找会永远失败。`format_convert` 通过 `from tools.format_convert import format_convert` 直接导入。

#### Scenario: format_convert 调度
- **WHEN** `_execute_single_tool_call` 收到 `fn_name == "format_convert"`
- **THEN** 系统 MUST 从 `tools.format_convert` 导入 `format_convert` 函数
- **AND** 系统 MUST 调用 `await format_convert(**fn_args)` 并返回结果

### Requirement: format_convert 统一入口
`format_convert` tool MUST 提供 xlsx/csv/json 之间的 any-to-any 格式转换统一入口。

#### Scenario: xlsx 转 csv
- **WHEN** 调用 `format_convert(source="data.xlsx", target="data.csv")`
- **THEN** 系统 MUST 使用 openpyxl 读取 xlsx 文件
- **AND** 系统 MUST 使用 csv.writer 写入 csv 文件
- **AND** 系统 MUST 返回 `{"ok": True, "target": "data.csv"}`

#### Scenario: csv 转 xlsx
- **WHEN** 调用 `format_convert(source="data.csv", target="data.xlsx")`
- **THEN** 系统 MUST 使用 csv 读取源文件
- **AND** 系统 MUST 使用 openpyxl 写入 xlsx 文件
- **AND** 系统 MUST 返回 `{"ok": True, "target": "data.xlsx"}`

#### Scenario: csv 转 json（委托 adapters.py）
- **WHEN** 调用 `format_convert(source="data.csv", target="data.json")`
- **THEN** 系统 MUST 构造适配参数：`input_files={"input": "data.csv"}`、`output_dir` 为 target 的父目录
- **AND** 系统 MUST 调用 `await adapters.csv_to_json(input_files=input_files, output_dir=output_dir)`
- **AND** 系统 MUST 返回 `{"ok": True, "target": "data.json"}`

#### Scenario: json 转 csv（委托 adapters.py）
- **WHEN** 调用 `format_convert(source="data.json", target="data.csv")`
- **THEN** 系统 MUST 构造适配参数：`input_files={"input": "data.json"}`、`output_dir` 为 target 的父目录
- **AND** 系统 MUST 调用 `await adapters.json_to_csv(input_files=input_files, output_dir=output_dir)`
- **AND** 系统 MUST 返回 `{"ok": True, "target": "data.csv"}`

#### Scenario: xlsx 转 json（两步转换）
- **WHEN** 调用 `format_convert(source="data.xlsx", target="data.json")`
- **THEN** 系统 MUST 先将 xlsx 转为临时 csv 文件（写入系统临时目录）
- **AND** 系统 MUST 再将临时 csv 转为 json（委托 adapters.py）
- **AND** 系统 MUST 在转换完成后删除临时 csv 文件
- **AND** 系统 MUST 返回 `{"ok": True, "target": "data.json"}`

#### Scenario: json 转 xlsx（两步转换）
- **WHEN** 调用 `format_convert(source="data.json", target="data.xlsx")`
- **THEN** 系统 MUST 先将 json 转为临时 csv 文件（委托 adapters.py，写入系统临时目录）
- **AND** 系统 MUST 再将临时 csv 转为 xlsx
- **AND** 系统 MUST 在转换完成后删除临时 csv 文件
- **AND** 系统 MUST 返回 `{"ok": True, "target": "data.xlsx"}`

### Requirement: format_convert 格式嗅探
当 source_fmt 或 target_fmt 为空时，系统 MUST 从文件扩展名自动推断格式。

#### Scenario: 从扩展名嗅探源格式
- **WHEN** 调用 `format_convert(source="data.xlsx", target="out.csv", source_fmt="")`
- **THEN** 系统 MUST 从 `.xlsx` 扩展名推断 source_fmt 为 "xlsx"

#### Scenario: 从扩展名推断目标格式
- **WHEN** 调用 `format_convert(source="data.csv", target="out.json", target_fmt="")`
- **THEN** 系统 MUST 从 `.json` 扩展名推断 target_fmt 为 "json"

#### Scenario: 显式指定格式优先
- **WHEN** 调用 `format_convert(source="data.txt", target="out.csv", source_fmt="csv")`
- **THEN** 系统 MUST 使用显式指定的 source_fmt="csv"，忽略扩展名

#### Scenario: 不支持的格式
- **WHEN** 调用 `format_convert(source="data.png", target="out.csv")`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "不支持的源格式: png"}`

### Requirement: format_convert tool schema
format_convert MUST 注册为 OpenAI function calling tool。

#### Scenario: format_convert tool 参数定义
- **WHEN** 系统注册 format_convert tool
- **THEN** tool name MUST 为 `"format_convert"`
- **AND** parameters MUST 包含 `source`（string, required）：源文件路径
- **AND** parameters MUST 包含 `target`（string, required）：目标文件路径
- **AND** parameters MUST 包含 `source_fmt`（string, optional）：源格式（xlsx/csv/json），为空时从扩展名推断
- **AND** parameters MUST 包含 `target_fmt`（string, optional）：目标格式（xlsx/csv/json），为空时从扩展名推断

---

## ADDED Requirements (data-pipeline-bind-variables)

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
