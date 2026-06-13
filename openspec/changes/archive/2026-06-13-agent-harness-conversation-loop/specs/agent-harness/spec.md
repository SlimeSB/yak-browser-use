## ADDED Requirements

### Requirement: conversation_loop 核心
系统 SHALL 提供 conversation_loop，核心逻辑为：
```
while budget.remaining > 0 and not interrupted:
    1. turn_context.build() — 前置准备
    2. api_messages = prepare_messages(messages, system_prompt)
    3. response = llm.call(api_messages, tools=registered_tools)
    4. if response has tool_calls:
         tool_executor.execute(response.tool_calls, messages)
       else:
         final_response = response.text
         break
    5. check_exit_conditions()
```

#### Scenario: Agent 调工具后循环继续
- **WHEN** LLM 返回 tool_calls
- **THEN** tool_executor 执行并将结果追加到 messages
- **THEN** 循环继续

#### Scenario: Agent 返回文本结束
- **WHEN** LLM 返回纯文本（无 tool_calls）
- **THEN** 循环结束，返回 final_response

### Requirement: harness 子模块
conversation_loop SHALL 内部调用以下子模块：

- `retry_utils.jittered_backoff()` — 重试退避
- `iteration_budget.consume()` — 步数控制
- `error_classifier.classify_api_error()` — 错误分类
- `tool_guardrails.before_call()` / `after_call()` / `reset()` — 调用保护（reset 在每次 turn 开始时调用，清空失败计数）
- `turn_context.build_turn_context()` — turn 前置准备
- `tool_executor.execute_tool_calls()` — 工具调用执行

#### Scenario: 错误时调用 error_classifier
- **WHEN** LLM 调用抛出异常
- **THEN** `classify_api_error()` 被调用
- **THEN** 根据 `ClassifiedError.retryable` 决定是否重试

#### Scenario: budget 耗尽停止
- **WHEN** `IterationBudget.remaining == 0`
- **THEN** 循环结束

### Requirement: iteration_budget 配置
IterationBudget SHALL 默认 50 次 LLM round-trip，用户可通过设置调整。

- 一次 LLM round-trip = 一次 API call（可能包含多个 tool call）
- 低于 10 次的配置 SHALL 被拒绝（最小值保护）
- 可以通过 `ybu config set max_iterations <N>` 修改

#### Scenario: 默认值
- **WHEN** 创建 `IterationBudget()`
- **THEN** `max_total == 50`

### Requirement: tool_executor 执行策略
tool_executor SHALL 在 chat 模式和预设回放模式都通过 executor.py 执行工具操作，两种模式共用同一组 executor。

接口签名 SHALL 为：
```
def execute_tool_calls(messages: list, tool_calls: list, stream_callback=None) -> None
```
（与 Hermes 不同：YBU 没有 `agent` 对象，不需要 `effective_task_id`）

执行逻辑 SHALL 包含：
1. 每次 tool call 前检查 interrupt 标志（用户取消时跳过剩余工具）
2. 解析 function_name + function_args
3. 检查 tool_guardrails.before_call()
4. 委托 executor.py 核心函数执行（execute_browser_op / execute_tool / execute_goal）
5. tool_guardrails.after_call()
6. 结果追加到 messages 列表

chat 模式的工具调用路径（通过核心函数，无文件 I/O）：
```
conversation_loop → tool_executor._execute_single_tool_call()
  → executor.py
    ├── execute_browser_op() → CDP helpers (goto/click/fill/snapshot/scroll/source/eval)
    ├── execute_goal() → agent.py 的 browser-use Agent.run()
    └── execute_tool() → tools/ 中的数据处理函数
```

预设回放模式工具调用路径（与 chat 模式共用 executor）：
```
conversation_loop → PipelineTaskAdapter → TaskDescriptor
  → tool_executor → executor.py (execute_browser/tool/goal_step)
```

#### Scenario: chat 模式与 preset 模式共用 executor.py
- **WHEN** 用户通过 chat 发送 "打开百度"
- **THEN** tool_executor 委托 executor.py 的 execute_browser_op
- **THEN** CompensationRegistry、sanitize_result、超时处理 等基础设施在核心函数中生效
- **THEN** 与 preset 模式使用相同的错误码、超时、输出校验

### Requirement: executor.py 双模接口
executor.py SHALL 为每个执行器提供两层接口：核心执行函数（无文件 I/O，供 chat 模式使用）和 pipeline 包装函数（含文件 I/O，供预设回放使用）。

核心执行函数签名（chat 模式 tool_executor 直接调用）：

```python
# 浏览器原子操作 — 无 step_dir/run_dir 依赖
async def execute_browser_op(
    op_type: str,        # "goto"|"click"|"fill"|"snapshot"|"scroll"|"source"|"eval"
    params: dict,        # {url, selector, text, code, direction, ...}
    cdp_helpers: object,
) -> dict
# 返回: {ok, result, error, duration_ms, screenshot_base64?, html?}

# 工具执行 — 无 step_dir/run_dir 依赖
async def execute_tool(
    tool_name: str,
    params: dict,
    tools_dir: Path,
    cdp_helpers: object | None = None,
) -> dict
# 返回: {ok, result, error, duration_ms, output_files?}

# Goal 执行 — 无 step_dir/run_dir 依赖
async def execute_goal(
    description: str,
    cdp_helpers: object,
    pipeline_name: str,
    tools_dir: Path,
    frontmatter: dict | None = None,
    agent_md_path: Path | None = None,
    system_prompt: str = "",
) -> dict
# 返回: {ok, result, error, duration_ms, learned_ops?}
```

Pipeline 包装函数（现有签名，内部调核心函数 + 文件写入）：
```python
# execute_browser_step 内部: 遍历 step["browser_ops"] → 逐条调 execute_browser_op()
#   → 写 screenshot/page.html 到 step_dir → CompensationRegistry
# execute_tool_step 内部: 调 execute_tool() → 写 output_files → _check_outputs()
# execute_goal_step 内部: 调 execute_goal() → 写 learned_ops.json + agent_history.json
```

CompensationRegistry、sanitize_result、超时处理、敏感数据脱敏 SHALL 在核心执行函数中生效。

#### Scenario: chat 模式调用核心函数
- **WHEN** tool_executor 在 chat 模式下调 browser_goto("https://baidu.com")
- **THEN** 调用 `execute_browser_op("goto", {"url": "https://baidu.com"}, cdp_helpers)`
- **THEN** 不创建 step_dir / run_dir，不写文件
- **THEN** 返回 `{ok: True, result: {...}, error: None, duration_ms: 342}`

#### Scenario: preset 模式走包装函数
- **WHEN** 预设回放执行 browser step
- **THEN** 调用 `execute_browser_step(step_def, cdp_helpers, step_dir, run_dir)`
- **THEN** 内部调用 `execute_browser_op()` + 写 screenshot/page.html 到 step_dir
- **THEN** CompensationRegistry 写入 step.json

### Requirement: tool_guardrails chat 模式配置
chat 模式 SHALL 使用独立的 `ToolCallGuardrailConfig`，阈值比 Hermes 默认值更宽松：

```python
ToolCallGuardrailConfig(
    hard_stop_enabled=False,           # 默认不硬停 — chat 模式不打断用户
    # warn 阈值（触发后附加 [Tool loop warning]，不阻止执行）
    exact_failure_warn_after=5,        # 同参数失败 5 次才 warn（Hermes 默认 2）
    same_tool_failure_warn_after=6,    # 同工具失败 6 次才 warn（Hermes 默认 3）
    no_progress_warn_after=3,          # 幂等同结果 3 次 warn（Hermes 默认 2）
    # block 阈值（触发后阻止执行，合成 tool result 返回给 Agent）
    exact_failure_block_after=10,      # 同参数失败 10 次 block（Hermes 默认 5）
    same_tool_failure_halt_after=15,   # 同工具失败 15 次 halt（Hermes 默认 8）
    no_progress_block_after=8,         # 幂等同结果 8 次 block（Hermes 默认 5）
)
```

**设计哲学**: chat 模式下让 Agent 自主判断修正策略，guardrail 是安全网而非裁判。宽松阈值确保 Agent 有足够空间试错，同时防止死循环。

#### Scenario: Agent 连续 3 次点同一个不存在的 selector
- **WHEN** Agent 连续 3 次调用 browser_click("#missing") 都失败
- **THEN** guardrail 不触发 warn（阈值 5，3 < 5）
- **THEN** Agent 仍有空间自主发现并修正

#### Scenario: Agent 连续 6 次点同一个不存在的 selector
- **WHEN** Agent 连续 6 次调用 browser_click("#missing") 都失败
- **THEN** guardrail 触发 warn（6 ≥ 5）
- **THEN** tool result 后附加 `[Tool loop warning: browser_click with these exact arguments has failed 6 times...]`
- **THEN** Agent 看到 warning 后自主更换策略

### Requirement: turn_context retry 重置
`build_turn_context()` 在每次 turn 开始时 SHALL 重置所有 retry 计数器（tool_retries、json_retries、empty_content_retries 等）。

#### Scenario: turn 开始重置计数
- **WHEN** 用户开始新的对话回合
- **THEN** 所有 retry 计数器归零
- **THEN** 上一轮的 retry 记录不会影响本轮

### Requirement: error_classifier 范围
error_classifier SHALL 只处理 LLM API 调用错误，不处理浏览器工具执行错误。

LLM 错误：HTTP 状态码异常、SDK 异常、网络超时、rate limit、auth 失败
浏览器错误：元素未找到、超时、DOM 操作失败——由 tool_executor 捕获后标准化为错误信息返回给 Agent，Agent 在下一轮对话中自主判断修复策略。

### Requirement: CDP 错误处理（chat 模式）
tool_executor 在 chat 模式下捕获 CDP/executor 异常后 SHALL 不自动重试分类，而是标准化错误信息并返回给 Agent。

错误处理层次 SHALL 为：
- **元素未找到**（ValueError "Element not found"）→ 返回具体错误信息（哪种工具、什么参数、什么错误），Agent 在下一轮修正 selector 或改用其他方法
- **超时**（TimeoutError）→ tool_executor 内部重试 1 次（与 executor.py 的 DEFAULT_OP_TIMEOUT 一致），仍失败则回报
- **CDP 连接断开** → 自动重连（3 次指数退避，每次间隔 1s/2s/4s），全部失败则报给用户
- **不可恢复错误**（权限错误、Chrome 崩溃）→ 直接报给用户，终止当前 task

tool_executor SHALL 不调用 error_classifier.classify_api_error() 来处理浏览器错误，浏览器错误不经过 LLM 错误分类流程。

#### Scenario: 元素未找到时 Agent 自主修复
- **WHEN** Agent 调用 browser_click("#nonexistent")
- **THEN** CDP 返回 ValueError("Element not found")
- **THEN** tool_executor 捕获并返回标准化错误信息到 messages
- **THEN** Agent 在下一轮自主决定换 selector 或先 snapshot 页面

#### Scenario: CDP 超时重试后回报
- **WHEN** CDP 操作超时（TimeoutError）
- **THEN** tool_executor 内部重试 1 次
- **THEN** 如果仍超时，回报标准化错误信息
- **THEN** Agent 在下一轮决定是否换页面或减少操作

### Requirement: 中断保存与恢复
conversation_loop SHALL 支持用户中断时的状态保存和恢复。

中断时 SHALL 保存：
- 当前 messages 列表（完整对话历史 + 已执行的 tool results）
- 当前 iteration_budget 剩余计数
- 最后一次 tool call 的错误信息（如有）
- Agent 的当前意图上下文（最后几条 message）

恢复时 SHALL：
- 重新加载保存的 messages（不丢失对话上下文）
- 重置 retry 计数器（turn_context reset）
- 恢复 iteration_budget 计数器
- Agent 从对话历史中理解当前状态，继续执行（不重头开始）

#### Scenario: 中断后恢复
- **WHEN** 用户中断一个正在执行的 task
- **THEN** 系统保存会话状态（messages + budget + 错误）
- **THEN** 用户下一次发送消息时，conversation_loop 从保存状态恢复
- **THEN** Agent 理解自己之前做到哪一步，从断点继续

### Requirement: goal_run 预算控制
当 Agent 调用 goal_run 工具时，外层 conversation_loop SHALL 暂停迭代预算计数，内层 browser-use Agent 完成后恢复。

- goal_run 执行期间不消耗外层 iteration_budget
- goal_run 完成后，外层消耗 1 次 LLM round-trip（因为 Agent 需要接收 goal_run 的结果并决定下一步）
- conversation_loop 默认在 prompt 中指导 Agent 优先使用原子工具，goal_run 仅限需要 browser-use 自主推理的复杂场景

#### Scenario: goal_run 不消耗外层预算
- **WHEN** Agent 调用 goal_run("在页面中找到评分最高的商品")
- **THEN** 外层 iteration_budget 暂停
- **THEN** 内层 browser-use Agent 自主执行（可能有多次 LLM 调用）
- **THEN** goal_run 完成后返回值到外层
- **THEN** 外层消耗 1 次 budget（Agent 接收结果并决策）
