## ADDED Requirements

### Requirement: file_read 调度
`file_read` MUST 在 `_execute_single_tool_call()` 中有专用 handler，不走 `else → execute_tool()` 分支。

**Reason:** chat 模式下 `tools_dir = Path("tools")` 在项目根不存在，`execute_tool()` 的文件路径查找会永远失败。`file_read` 通过 `from tools.file_read import file_read` 直接导入，与 `todo` 工具的模式一致。

#### Scenario: file_read 调度
- **WHEN** `_execute_single_tool_call` 收到 `fn_name == "file_read"`
- **THEN** 系统 MUST 从 `tools.file_read` 导入 `file_read` 函数
- **AND** 系统 MUST 调用 `await file_read(**fn_args)` 并返回结果

### Requirement: file_read 纯文本读取
`file_read` tool MUST 读取文件并返回原始文本内容，不做任何格式解析。

#### Scenario: 读取文本文件
- **WHEN** 调用 `file_read(path="data.txt", head=20, max_chars=3000)`
- **THEN** 系统 MUST 读取文件内容
- **AND** 系统 MUST 截取前 head 行（如果 head > 0）
- **AND** 系统 MUST 截断到 max_chars 字符
- **AND** 系统 MUST 返回原始文本，不做 JSON 解析、不做 tab 分隔

#### Scenario: 读取二进制文件
- **WHEN** 调用 `file_read(path="data.xlsx")`
- **THEN** 系统 MUST 检测到非文本扩展名
- **AND** 系统 MUST 返回提示"二进制文件，请使用 format_convert"

#### Scenario: 文件不存在
- **WHEN** 调用 `file_read(path="nonexistent.txt")`
- **THEN** 系统 MUST 返回错误信息，包含文件路径

#### Scenario: head=0 时不截取行数
- **WHEN** 调用 `file_read(path="data.txt", head=0)`
- **THEN** 系统 MUST 返回完整文件内容（仅受 max_chars 限制）

#### Scenario: 编码处理
- **WHEN** 调用 `file_read(path="data.csv", encoding="")`
- **THEN** 系统 MUST 尝试 UTF-8 编码读取
- **AND** 如果 UTF-8 失败，MUST 尝试 GBK 编码
- **AND** 如果 GBK 也失败，MUST 返回错误信息

#### Scenario: 显式指定编码
- **WHEN** 调用 `file_read(path="data.csv", encoding="gbk")`
- **THEN** 系统 MUST 使用指定的编码读取文件
- **AND** 如果指定编码失败，MUST 返回错误信息（不 fallback）

### Requirement: file_write 调度
`file_write` MUST 在 `_execute_single_tool_call()` 中有专用 handler，不走 `else → execute_tool()` 分支。

**Reason:** 与 `file_read` 相同，`tools_dir` 在 chat 模式不可用。

#### Scenario: file_write 调度
- **WHEN** `_execute_single_tool_call` 收到 `fn_name == "file_write"`
- **THEN** 系统 MUST 从 `tools.file_write` 导入 `file_write` 函数
- **AND** 系统 MUST 调用 `await file_write(**fn_args)` 并返回结果

### Requirement: file_write 纯文本写入
`file_write` tool MUST 将字符串写入文件。

#### Scenario: 写入文本文件
- **WHEN** 调用 `file_write(path="output.txt", content="hello")`
- **THEN** 系统 MUST 将 content 写入 path 指定的文件
- **AND** 系统 MUST 返回写入成功的确认信息

#### Scenario: 覆盖已存在文件
- **WHEN** 调用 `file_write(path="existing.txt", content="new")` 且文件已存在
- **THEN** 系统 MUST 覆盖已有文件内容

#### Scenario: 目录不存在时自动创建
- **WHEN** 调用 `file_write(path="subdir/output.txt", content="hello")` 且 subdir 不存在
- **THEN** 系统 MUST 自动创建父目录

#### Scenario: 写入编码
- **WHEN** 调用 `file_write(path="output.txt", content="hello", encoding="gbk")`
- **THEN** 系统 MUST 使用指定编码写入文件
- **AND** 未指定 encoding 时 MUST 默认使用 UTF-8

### Requirement: file_read tool schema
file_read MUST 注册为 OpenAI function calling tool。

#### Scenario: file_read tool 参数定义
- **WHEN** 系统注册 file_read tool
- **THEN** tool name MUST 为 `"file_read"`
- **AND** parameters MUST 包含 `path`（string, required）：文件路径
- **AND** parameters MUST 包含 `head`（integer, optional, default=20）：返回前 N 行，0 表示全部
- **AND** parameters MUST 包含 `max_chars`（integer, optional, default=3000）：最大返回字符数
- **AND** parameters MUST 包含 `encoding`（string, optional）：文件编码，为空时自动检测（UTF-8 → GBK fallback）

### Requirement: file_write tool schema
file_write MUST 注册为 OpenAI function calling tool。

#### Scenario: file_write tool 参数定义
- **WHEN** 系统注册 file_write tool
- **THEN** tool name MUST 为 `"file_write"`
- **AND** parameters MUST 包含 `path`（string, required）：文件路径
- **AND** parameters MUST 包含 `content`（string, required）：要写入的文本内容
- **AND** parameters MUST 包含 `encoding`（string, optional, default="utf-8"）：文件编码

### Requirement: test_harness_tools 更新
新增 tool 注册后，`test_harness_tools.py` 中的 tool 数量断言 MUST 更新。

#### Scenario: get_all_tools 数量更新
- **WHEN** `file_read`、`file_write`、`format_convert`、`eval_agent` 注册到 `get_all_tools()`
- **THEN** `test_get_all_tools_with_goal` 的 `len(tools) == 36` MUST 更新为 `len(tools) == 40`
- **AND** `test_get_all_tools_without_goal` 的 `len(tools) == 35` MUST 更新为 `len(tools) == 39`

---

## ADDED Requirements (data-pipeline-bind-variables)

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
