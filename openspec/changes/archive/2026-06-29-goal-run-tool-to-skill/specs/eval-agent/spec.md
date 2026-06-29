## MODIFIED Requirements

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
