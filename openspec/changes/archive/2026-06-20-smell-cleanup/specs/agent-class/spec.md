## ADDED Requirements

### Requirement: Agent 状态收拢为属性
`conversation_loop.py` 的 `run_conversation_loop()` 中的局部状态变量（`turn_count`、`final_response`、`consecutive_llm_failures`、`interrupted`、`last_content_with_tools`）MUST 收拢为 `Agent` 类的实例属性。

#### Scenario: 状态通过属性访问
- **WHEN** 创建 `Agent` 实例后调用 `await agent.run()`
- **THEN** `agent._state.turn_count` 记录已完成的轮次
- **AND** `agent._state.interrupted` 标记是否被中断
- **AND** `agent._state.final_response` 存储最终的文本回复

### Requirement: Agent 对外接口兼容
`Agent` 类 MUST 保持与原有 `run_conversation_loop()` 和 `run_preset_loop()` 的一致对外行为。`backend/engine/runner.py` 的 `run_chat_loop()` 和 `backend/engine/runner_preset.py` 的 `run_pipeline()` SHOULD 只需将函数调用改为实例化 `Agent`。

#### Scenario: chat 模式兼容
- **WHEN** 通过 `run_chat_loop()` 启动聊天
- **THEN** 对话循环行为与重构前一致
- **AND** `ConversationResult` 的字段值一致

#### Scenario: preset 模式兼容
- **WHEN** 通过 `run_preset_loop()` 启动预设执行
- **THEN** preset 执行行为与重构前一致

### Requirement: Agent 职责边界
`Agent` 类 MUST NOT 引入不属于 `run_conversation_loop()` 的职责。`eval_agent`、`step_machine`、`pipeline_tools` 的逻辑 MUST 保持在各自模块中，不拉入 `Agent`。

#### Scenario: eval_agent 保持独立
- **WHEN** `eval_agent` 工具被调用
- **THEN** `Agent` 通过 `_execute_tool()` 分发到 `eval_agent` handler
- **AND** eval_agent 的逻辑保持在 `backend/engine/eval_agent.py` 中

#### Scenario: eval_agent handler 内部使用 Agent
- **WHEN** `_handle_eval_agent` 需要启动子对话循环
- **THEN** 内部实例化 `Agent(llm_call=..., system_prompt=..., tools_registry=..., ...)` 并调用 `await agent.run()`
- **AND** 不再直接调用 `run_conversation_loop()` 函数
- **AND** 返回的 `ConversationResult` 字段与重构前一致

### Requirement: 事件统一 emit
`Agent` 类 MUST 提供 `_emit(event_type, **data)` 方法，所有 stream_callback 事件通过该方法发出。事件 type 字符串 MUST 在 `Agent` 中集中定义，不在代码中散落字符串字面量。

#### Scenario: emit turn_start 事件
- **WHEN** `Agent._step()` 开始新轮次
- **THEN** 调用 `self._emit("turn_start", turn=turn_count, budget_remaining=budget.remaining)`
- **AND** 如果 `self._on_event` 已设置，回调收到 `{"type": "turn_start", "turn": N, "budget_remaining": M}`

#### Scenario: 无回调时不报错
- **WHEN** `_on_event` 为 `None` 时调用 `self._emit(...)`
- **THEN** 不抛出异常，静默跳过

### Requirement: Guardrail 配置注入
`Agent` MUST 在 `run()` 入口处理 guardrail 配置：根据 `preset_mode` 决定使用默认宽松配置还是传入配置，并将 `guardrail_config` 注入到 `guardrail_state.config`。该逻辑必须与当前 `run_conversation_loop()` 第 88-94 行的行为一致。

#### Scenario: chat 模式默认宽松配置
- **WHEN** `Agent` 以 `preset_mode=False` 运行且未传入 `guardrail_config`
- **THEN** `guardrail_state.config` 被设置为 `create_chat_guardrail_config()` 的结果

#### Scenario: preset 模式不使用默认配置
- **WHEN** `Agent` 以 `preset_mode=True` 运行
- **THEN** 不自动设置默认 guardrail config
