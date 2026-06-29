## ADDED Requirements

### Requirement: eval agent 调度链
eval_agent 需要 `llm_call` 启动 subagent LLM 循环，MUST 穿透 3 层函数签名传递。

#### Scenario: llm_call 参数传递链
- **WHEN** `run_conversation_loop` 调用 `execute_tool_calls_sequential`
- **THEN** `execute_tool_calls_sequential` 的签名 MUST 新增 `llm_call` 参数
- **AND** `execute_tool_calls_sequential` MUST 将 `llm_call` 传递给 `_execute_single_tool_call`
- **AND** `_execute_single_tool_call` 的签名 MUST 新增 `llm_call` 参数
- **AND** `eval_agent` handler MUST 使用传入的 `llm_call` 启动 subagent 的 `run_conversation_loop`

### Requirement: eval agent 启动与执行
系统 MUST 提供 eval_agent tool，允许主 LLM 启动 eval agent subagent 处理复杂 DOM 操作或验证码识别。

eval agent 内部调用 `run_conversation_loop()`（而非 `run_preset_loop()`），因为 eval agent 使用自定义 system prompt 和受限 tool 集合，不依赖 PipelineTaskAdapter 的 step_defs → TaskDescriptor 转换。

eval_agent 在 `_execute_single_tool_call()` 中 MUST 有专用 handler（类似 `pipeline_finish`），因为 `eval_agent` 需要 `llm_call` 参数来启动 subagent 的 LLM 循环，而 `llm_call` 不在 `execute_tool()` 的调度链中。

#### Scenario: 主 LLM 启动 eval agent
- **WHEN** 主 LLM 调用 `eval_agent(purpose="提取表格", snapshot="...")`
- **THEN** `_execute_single_tool_call` MUST 识别 `fn_name == "eval_agent"` 并路由到 eval_agent 专用 handler
- **AND** handler MUST 从调用链获取 `llm_call`（通过 `execute_tool_calls_sequential` → `_execute_single_tool_call` 的 `llm_call` 参数传入）
- **AND** handler MUST 构造 EvalAgent 实例，注入 prompt 模板和 JS 函数库
- **AND** handler MUST 调用 `run_conversation_loop()` 启动 eval agent 的 LLM 循环
- **AND** `run_conversation_loop` 的 system_prompt MUST 为 eval agent 专用 prompt（默认 `prompts/eval_agent/system.md`）
- **AND** `run_conversation_loop` 的 tools MUST 为受限 tool 集合（browser_eval、browser_snapshot、browser_click、browser_fill、browser_wait、browser_source、browser_scroll），不包含 pipeline_* 工具
- **AND** eval agent MUST 共享主流程的 CDP 连接（通过 cdp_helpers 传入）
- **AND** handler MUST 同步阻塞等待 eval agent 完成，将结果返回给主 LLM

#### Scenario: eval agent 迭代试错
- **WHEN** eval agent 的 LLM 在 `run_conversation_loop` 中执行
- **THEN** eval agent MUST 先调用 browser_snapshot() 观察页面状态
- **AND** eval agent MUST 调用 browser_eval(code=js) 执行 JS 代码
- **AND** eval agent MUST 根据 eval 结果判断是否完成
- **AND** 未完成时 MUST 调整 JS 代码并再次 eval

#### Scenario: eval agent 成功完成
- **WHEN** eval agent 判断任务完成
- **THEN** eval agent MUST 返回数据摘要给主流程
- **AND** CSV 落盘和 pipeline yaml 写入 MUST 为可选功能：仅在 `output_dir` 或 `pipeline_path` 可用时执行
- **AND** chat 模式下 `output_dir` 和 `pipeline_path` 不可用，eval agent MUST 仅返回数据摘要（不写文件）

#### Scenario: eval agent 达到预算上限
- **WHEN** eval agent 的 `run_conversation_loop` 达到 IterationBudget 上限（默认 max_total=10）
- **THEN** eval agent MUST 返回失败反馈给主 LLM
- **AND** 失败反馈 MUST 包含最后一次 eval 的结果和错误信息

### Requirement: eval agent 阻塞语义
eval_agent tool handler MUST 在 eval agent 执行期间同步阻塞，并提供超时和取消机制。

#### Scenario: eval agent 超时
- **WHEN** eval agent 的 `run_conversation_loop` 执行超过 timeout 秒（默认 120 秒）
- **THEN** tool handler MUST 通过 `asyncio.wait_for` 取消执行
- **AND** MUST 返回 `{"ok": False, "error": "eval agent 超时", "partial_result": "..."}` 给主 LLM

#### Scenario: 主流程取消传播
- **WHEN** 主流程的 `run_conversation_loop` 被中断（用户取消或 budget 耗尽）
- **THEN** eval agent 的 `run_conversation_loop` MUST 通过 `interrupt_check` 回调感知取消
- **AND** eval agent MUST 尽快退出并返回部分结果

#### Scenario: eval agent 的 budget 独立于主流程
- **WHEN** eval agent 内部消耗 LLM 调用
- **THEN** eval agent 的 IterationBudget MUST 独立于主流程的 budget
- **AND** eval agent 的 budget 耗尽 MUST NOT 影响主流程的 budget

### Requirement: eval agent 配置化
EvalAgent MUST 支持通过构造参数注入 prompt 模板和 JS 函数库。

#### Scenario: 注入自定义 prompt 模板
- **WHEN** 创建 `EvalAgent(prompt_template="...")`
- **THEN** eval agent 的 system prompt MUST 使用注入的模板
- **AND** 模板 MUST 支持变量渲染（如 `{purpose}`、`{snapshot}`）

#### Scenario: 注入 JS 函数库
- **WHEN** 创建 `EvalAgent(js_functions=[isVisible, retryUntil])`
- **THEN** eval agent 的可用 JS 函数 MUST 包含注入的函数
- **AND** 内置函数和自定义函数 MUST 格式一致，无区别对待

#### Scenario: 使用默认配置
- **WHEN** 创建 `EvalAgent()` 不传参数
- **THEN** eval agent MUST 使用默认 prompt 模板（`prompts/eval_agent/system.md`）
- **AND** eval agent MUST 使用默认 JS 函数库（`prompts/eval_agent/js_lib.js`）

### Requirement: eval agent 内部记录
eval agent MUST 在内部记录每次 eval 操作，完成时写入 pipeline yaml。

#### Scenario: 记录每次 eval
- **WHEN** eval agent 执行一次 browser_eval(code=js)
- **THEN** eval agent MUST 记录一条可读日志（eval 的 JS 代码 + 返回结果摘要）

#### Scenario: 完成时写入 pipeline yaml
- **WHEN** eval agent 成功完成任务且 tool handler 传入了 `pipeline_path`
- **THEN** eval agent MUST 将执行过程追加写入 pipeline yaml 文件
- **AND** 主 LLM MUST NOT 接触 yaml 写入逻辑

### Requirement: eval_agent tool schema
eval_agent MUST 注册为 OpenAI function calling tool，schema 如下。

#### Scenario: eval_agent tool 参数定义
- **WHEN** 系统注册 eval_agent tool
- **THEN** tool name MUST 为 `"eval_agent"`
- **AND** description MUST 包含"启动子 Agent 处理复杂 DOM 操作或验证码识别，会额外消耗 LLM token，仅在 browser_eval 无法直接完成时使用"
- **AND** parameters MUST 包含 `purpose`（string, required）：eval agent 的任务目标描述
- **AND** parameters MUST 包含 `snapshot`（string, required）：当前页面的 simplified snapshot 文本
- **AND** parameters MUST 包含 `max_attempts`（integer, optional, default=3）：最大 eval 尝试次数
