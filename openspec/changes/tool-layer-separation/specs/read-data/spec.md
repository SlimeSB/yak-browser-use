## ADDED Requirements

### Requirement: read_data 工具注册
系统 MUST 在 `tools/registry.py` 中注册名为 `read_data` 的工具，作为 LLM 唯一可获取文件全文的数据入口。

#### Scenario: read_data 出现在工具列表中
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中 MUST 包含 `read_data`

#### Scenario: read_data 参数定义
- **WHEN** 系统注册 `read_data` tool
- **THEN** tool name MUST 为 `"read_data"`
- **AND** parameters MUST 包含 `path`（string, required）：文件路径
- **AND** parameters MUST 包含 `limit`（integer, optional, default=20）：返回行数上限
- **AND** parameters MUST 包含 `offset`（integer, optional, default=0）：跳过的起始行数
- **AND** parameters MUST 包含 `encoding`（string, optional）：文件编码，为空时自动检测
- **AND** parameters MUST 包含 `convert_to`（string, optional）：二进制文件的目标转换格式（csv、json）
- **AND** parameters MUST 包含 `source_key`（string, optional）：结果存入 shared_store 的 key，供其他工具通过 `{key}` 引用

### Requirement: read_data workspace 子目录限制
`read_data` MUST 与 `file_write` 一致，仅允许读取 workspace 子目录内的文件。workspace 根目录（如 `pipeline.yaml` 所在位置）SHALL 被拒绝。

#### Scenario: 读取 workspace 子目录文件
- **WHEN** 调用 `read_data(path="downloads/data.csv")`
- **THEN** 系统 MUST 解析到 `WORKSPACES_ROOT/<pipeline>/downloads/data.csv`
- **AND** 读取 MUST 成功

#### Scenario: 读取 workspace 根目录被拒绝
- **WHEN** 调用 `read_data(path="pipeline.yaml")` 或路径解析后无子目录层级
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "请使用 pipeline_view 查看 pipeline 内容"}`
- **AND** 文件内容 SHALL NOT 被返回

### Requirement: read_data 强制渐进式披露
`read_data` MUST 默认截断返回内容。`limit` SHALL NOT 接受 0 或负值（禁止"无限"），`offset` SHALL NOT 超出文件总行数。

#### Scenario: 默认截断
- **WHEN** 调用 `read_data(path="data.csv")` 不传 limit 和 offset
- **THEN** 系统 MUST 返回前 20 行（limit=20, offset=0）

#### Scenario: LLM 主动展开
- **WHEN** 调用 `read_data(path="data.csv", limit=50)`
- **THEN** 系统 MUST 返回前 50 行

#### Scenario: LLM 翻页
- **WHEN** 调用 `read_data(path="data.csv", offset=20, limit=20)`
- **THEN** 系统 MUST 返回第 21-40 行

#### Scenario: 禁止无限
- **WHEN** 调用 `read_data(path="data.csv", limit=0)`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "limit 必须大于 0"}`

#### Scenario: offset 越界
- **WHEN** 调用 `read_data(path="data.csv", offset=99999)` 但文件仅有 100 行
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "offset 超出文件行数"}`

### Requirement: read_data 内部串联
`read_data` 执行时 MUST 内部调用 `file_read` 读取文件，对二进制文件自动调用 `format_convert` 转换后返回文本。

#### Scenario: 读取文本文件
- **WHEN** 调用 `read_data(path="data.txt", limit=20, offset=0)`
- **THEN** 系统 MUST 内部调用 `file_read` 获取内容
- **AND** 系统 MUST 应用 limit 和 offset 截断
- **AND** 系统 MUST 返回截断后的文本

#### Scenario: 读取二进制文件并转换
- **WHEN** 调用 `read_data(path="data.xlsx", convert_to="csv")`
- **THEN** 内部 `file_read` 检测到二进制扩展名后，`read_data` MUST 调用 `format_convert(source="data.xlsx", target_fmt="csv")` 获取转换后文本
- **AND** 系统 MUST 应用 limit 和 offset 截断
- **AND** LLM SHALL NOT 感知到 `format_convert` 的调用

#### Scenario: 无转换目标时二进制文件报错
- **WHEN** 调用 `read_data(path="data.xlsx")` 不传 `convert_to`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "二进制文件，请指定 convert_to 参数（如 convert_to='csv'）"}`

#### Scenario: 文件不存在
- **WHEN** 调用 `read_data(path="nonexistent.txt")`
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "..."}`

### Requirement: read_data source_key 写入 shared_store
`read_data` 的结果 MUST 可通过 `source_key` 写入 `shared_store`，供其他工具通过 `{key}` 或 `_source_key` 引用。

#### Scenario: source_key 写入
- **WHEN** 调用 `read_data(path="data.csv", source_key="table_data")`
- **THEN** `shared_store["table_data"]` MUST 被设为截断后的文本内容
- **AND** 后续 tool 可通过 `{table_data}` 或 `{"_source_key": "table_data"}` 引用

### Requirement: read_data 通过 registry 调度
`read_data` MUST 在 `_execute_single_tool_call()` 中有专用 handler，handler MUST 将 `ctx.pipeline_name` 传递给内部调用。
