## REMOVED Requirements

### Requirement: pipeline SHALL NOT retain guardian approval infrastructure
**Reason:** Guardian 审批机制的设计初衷是为 LLM 操作增加人工审批层，但该功能从未完成对接。核心模块 `engine/_lifecycle/guardian.py` 已被删除，但残留的 import/调用/frontmatter 字段散落在多个文件中。保留这些残留只会误导读者以为系统存在审批能力。

**Migration:** 删除 `cli/run.py` 中的 guardian import/call/参数传递；删除 `compiler/schema.py` 中的 `guardian` 字段及其 frontmatter 传值；重命名 `runner_preset.py` 的 `_execute_tool_step_with_guardian` 为 `_execute_tool_step`。

- **WHEN** 执行 `ybu run` CLI 命令或 API `/api/run` 端点
- **THEN** pipeline SHALL 正常执行所有 steps，不引用 guardian 模块

#### Scenario: CLI run after guardian cleanup
- **WHEN** 用户执行 `ybu run some_pipeline.yaml`
- **THEN** pipeline SHALL 成功执行，不因 guardian import 失败而崩溃（当前代码会因为 `run_pipeline` 不接受 `guardian` 参数而 TypeError）

#### Scenario: API run after guardian cleanup
- **WHEN** 通过 `/api/run` 端点执行 pipeline
- **THEN** pipeline SHALL 成功执行，`frontmatter` 中不再包含 `guardian` 字段

---

### Requirement: pipeline SHALL NOT include dead error codes in RETRYABLE/NON_RETRYABLE classification
**Reason:** `step_machine.py` 的 `NON_RETRYABLE_ERRORS` 包含 `GUARDIAN_ERROR` 和 `REVIEW_INTERRUPT`，这两个错误码在代码库中从未被任何代码产生。它们属于 Guardian 审批系统的残留。

**Migration:** 从 `NON_RETRYABLE_ERRORS` 中移除 `GUARDIAN_ERROR` 和 `REVIEW_INTERRUPT`。

- **WHEN** step 执行产生任何错误码
- **THEN** `StepMachine.needs_retry()` SHALL 仅基于当前存在的错误码（`BROWSER_ERROR`, `TIMEOUT_ERROR`, `RUNTIME_ERROR` 为 RETRYABLE；`SYNTAX_ERROR`, `INPUT_ERROR`, `OUTPUT_ERROR`, `PATH_ERROR` 为 NON_RETRYABLE）做出判断

#### Scenario: Step fails with BROWSER_ERROR after cleanup
- **WHEN** browser step 产生 `BROWSER_ERROR` 且 step 配置了 `max_retries > 0`
- **THEN** StepMachine SHALL 按照配置进行 retry，不被误判为 NON_RETRYABLE

---

### Requirement: pipeline SHALL NOT reference InterruptState or resume capability
**Reason:** `InterruptState` / `save_interrupt_state` / `resume_conversation` / `TurnContext.reset/snapshot` 是为 subagent 中断恢复场景设计的。当前主 agent 架构下，取消 = 用户在下一轮带着完整 session 历史messages 继续对话，不存在"恢复中断执行"的需求。

**Migration:** 删除 `turn_context.py` 中的 `InterruptState` 类和 `save_interrupt_state` 函数；删除 `TurnContext.reset()` 和 `TurnContext.snapshot()` 方法；删除 `conversation_loop.py` 中的 `resume_conversation` 函数；删除 `engine/_harness/__init__.py` 中的相关导出；删除 `test_conversation_loop.py` 和 `test_turn_context.py` 中的对应测试用例。

- **WHEN** 用户取消当前 pipeline 运行
- **THEN** system SHALL 停止当前执行，将 session 标记为 `cancelled`，后续用户消息会开启新一轮对话（保留完整 messages 历史）

#### Scenario: User cancels chat mid-execution
- **WHEN** 用户在 conversation loop 执行过程中点击取消
- **THEN** session.status SHALL 设为 "cancelled"，`ConversationResult.interrupted = True`，下一轮 `process_chat_message` 带着已有 `session.messages` 继续

---

### Requirement: pipeline SHALL keep StepMachine DAG operations intact
**Reason:** `StepMachine.advance(goto=)`, `replace_remaining()`, `fork_back()`, `resume_from_index`, `to_execution_tree()` 将被后续 preset failure → agent recovery change 复用。

**Migration:** 不修改 `StepMachine` 的任何逻辑。仅清理从调用侧传入的 unused `GUARDIAN_ERROR` / `REVIEW_INTERRUPT` 错误码。

- **WHEN** runner_preset 调用 StepMachine 的 goto/replace_remaining/fork_back 时
- **THEN** StepMachine SHALL 行为不变
