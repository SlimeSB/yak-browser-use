## ADDED Requirements

### Requirement: _PH- 工具不存在时自动生成

当 pipeline 执行到 `_PH-` 前缀的工具步骤且对应 `.py` 文件不存在时，系统 MUST 自动触发 inline 生成流程，而非返回 `TOOL_NOT_GENERATED` 错误。

#### Scenario: Preset 模式下 _PH- 工具不存在
- **WHEN** pipeline 执行到 `tool_name: _PH-crack-captcha` 步骤且 `userdata/workspaces/{pipeline}/tools/_PH-crack-captcha.py` 不存在
- **THEN** 系统自动触发 inline 生成流程：捕获页面状态 → 调 LLM 生成代码 → 安全检查 → 写入磁盘 → 执行

#### Scenario: Chat 模式下 _PH- 工具不存在
- **WHEN** chat 模式 LLM 调用 `_PH-crack-captcha` 工具且对应文件不存在
- **THEN** `tool_executor.py` 的 `else` 分支触发 inline 生成流程（共用 `_inline_generate_and_execute`）。`conversation_loop` 需将 `llm_call` 沿 `execute_tool_calls_sequential` → `_execute_single_tool_call` → `execute_tool` 传递链下传，使 inline 生成流程可调用 LLM

#### Scenario: _PH- 工具已存在
- **WHEN** pipeline 执行到 `_PH-crack-captcha` 步骤且对应 `.py` 文件已存在
- **THEN** 系统通过 `ToolRunner.load_and_call` 加载模块，创建 `ToolContext` 实例并注入为 `ctx` 参数执行（替代旧的直接传 `cdp_helpers` 方式），不触发生成流程。`load_and_call` 需将工具函数的返回值（`dict`）透传为执行结果，而非丢弃后返回 `{"ok": True}`

> **迁移说明**：已有的 `_PH-` 工具（如 `_PH-extract-table.py`）当前接收 `cdp_helpers` 参数。本次变更后 `load_and_call` 改为注入 `ctx: ToolContext`。已有工具需手动更新函数签名（`cdp_helpers` → `ctx`），或在新 `load_and_call` 中保留 `cdp_helpers` 兼容注入（检测函数签名决定注入方式）。

### Requirement: 页面状态捕获

Inline 生成流程 MUST 在调用 LLM 前捕获当前页面状态，包括简化版 DOM 摘要和当前 URL。

#### Scenario: 成功捕获页面状态
- **WHEN** 调用 `cdp_helpers.capture_snapshot_simplified()` 和 `cdp_helpers.js("window.location.href")`
- **THEN** 系统获取页面标题、标题层级、链接列表、表格摘要、文本内容，以及当前 URL

#### Scenario: 页面状态捕获失败时降级
- **WHEN** `capture_snapshot_simplified()` 抛出异常
- **THEN** 系统使用空字符串作为页面摘要，继续生成流程（不中断）

### Requirement: LLM 代码生成与提取

系统 MUST 通过 `llm_call` 调用 LLM 生成工具函数体，并从响应中提取 Python 代码。`llm_call` 返回的响应对象包含 `.completion`（str，LLM 文本输出，注意不是 `.content`）和 `.tool_calls`（list | None，本次调用传 `tools=[]` 故始终为 None）。

#### Scenario: LLM 返回 markdown code block
- **WHEN** `llm_call` 返回的 `.completion` 包含 ` ```python ... ``` ` 代码块
- **THEN** 系统用正则提取第一个匹配的代码块内容作为函数体

#### Scenario: LLM 返回纯文本代码
- **WHEN** `llm_call` 返回的 `.completion` 不包含 markdown code block
- **THEN** 系统将整段 `.completion` 作为函数体（fallback）

### Requirement: 代码写入与外壳注入

系统 MUST 将 LLM 生成的函数体注入标准外壳后写入磁盘。外壳包含必要的 import 语句和函数签名包装。函数名使用 `strip_ph_prefix(tool_name)` 的结果，并将连字符替换为下划线以符合 Python 标识符规范（如 `_PH-crack-captcha` → `crack_captcha`）。

#### Scenario: 写入 _PH- 工具文件
- **WHEN** 工具名为 `_PH-crack-captcha`，LLM 返回有效函数体
- **THEN** 系统将 `strip_ph_prefix` 结果 `crack-captcha` 中的连字符替换为下划线，生成函数名 `crack_captcha`，注入外壳后写入 `userdata/workspaces/{pipeline}/tools/_PH-crack-captcha.py`

### Requirement: 生成失败重试

当生成的代码执行失败时，系统 MUST 进行最多 3 次重试，每次重试将错误信息和页面状态反馈给 LLM。

#### Scenario: 首次执行失败后重试
- **WHEN** 生成的代码执行抛出异常
- **THEN** 系统将异常信息附加到 prompt 中，重新调用 LLM 生成代码

#### Scenario: 重试 3 次后仍失败
- **WHEN** 连续 3 次生成+执行均失败
- **THEN** 系统返回终端失败，pipeline 终止

#### Scenario: 重试成功
- **WHEN** 第 2 次重试生成的代码执行成功
- **THEN** 系统继续正常流程：rename + schema 注册 + pipeline 继续

### Requirement: 生成后 rename 与引用更新

生成的 `_PH-{name}.py` 执行成功后，系统 MUST 将其 rename 为 `{name}.py`，并更新 pipeline YAML 中的工具引用。

#### Scenario: Rename 成功
- **WHEN** `_PH-crack-captcha.py` 执行成功
- **THEN** 系统将其 rename 为 `crack-captcha.py`，pipeline YAML 中 `_PH-crack-captcha` 替换为 `crack-captcha`
