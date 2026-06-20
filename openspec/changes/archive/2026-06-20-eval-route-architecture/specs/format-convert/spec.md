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
