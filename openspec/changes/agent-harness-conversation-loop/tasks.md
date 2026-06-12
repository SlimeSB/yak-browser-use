## 1. Phase 0: 基础设施

- [x] 1.1 Create `engine/_harness/__init__.py` and module structure
- [x] 1.2 Enhance `prompts/_loader.py` with template variable support (custom `{variable}` replacement, not str.format() — avoid KeyError from natural `{}` in prompt files)
- [x] 1.3 Extract `retry_utils.py` (jittered_backoff) from Hermes
- [x] 1.4 Extract `iteration_budget.py` from Hermes (default max_total=50). Include goal_run budget pause/resume logic.
- [x] 1.5 Extract `error_classifier.py` (FailoverReason, ClassifiedError, classify_api_error) from Hermes. Only handles LLM API errors, never browser errors.
- [x] 1.6 Extract `tool_guardrails.py` (ToolCallGuardrailConfig, ToolCallGuardrailState) from Hermes. Chat mode uses relaxed config: exact_failure_warn_after=5, same_tool_failure_warn_after=6, hard_stop_enabled=False.
- [x] 1.7 Extract `turn_context.py` (TurnContext, build_turn_context) from Hermes. Include interrupt/resume state save + restore.
- [x] 1.8 Add unit tests for all Phase 0 modules
- [x] 1.9 py_compile verify all files
- [x] 1.10 Refactor `executor.py`: extract shared infrastructure classes (CompensationRegistry, sanitize_result, PathGuard helpers). Add core execution functions (execute_browser_op, execute_tool, execute_goal) without file I/O dependencies for chat mode. Keep existing pipeline wrappers (execute_browser_step, execute_tool_step, execute_goal_step) that call core functions + write artifacts.

## 2. Phase 1: 核心引擎

- [x] 2.1 Extract `tool_executor.py` (execute_tool_calls_sequential) from Hermes (去掉 concurrent，browser 操作只需要串行)
- [x] 2.2 Adapt tool_executor for chat mode: delegate to executor.py (execute_browser_step/tool_step/goal_step), do not bypass executor.py
- [x] 2.3 Extract `conversation_loop.py` core loop from Hermes (remove gateway/plugin/persist code)
- [x] 2.4 Create `PipelineTaskAdapter` and `TaskDescriptor` for preset replay mode
- [x] 2.5 Register browser tools (goto, click, fill, snapshot, scroll, source, eval)
- [x] 2.6 Register goal_run tool (browser-use Agent integration, wraps agent.py)
- [x] 2.7 Add unit tests for Phase 1

## 3. Phase 2: chat + 交互

- [x] 3.1 Rewrite `engine/agent.py` to integrate conversation_loop + tools + goal_run
- [x] 3.2 Split `engine/runner.py` into `runner.py` (chat mode conversation_loop entry) and `runner_preset.py` (preset replay, reuses existing pipeline logic: StepMachine, retry, recovery, Guardian)
- [x] 3.3 Implement CDP error handling in tool_executor (capture + normalize + return to Agent, no auto-classification). CDP reconnect with 3x exponential backoff (1s/2s/4s).
- [ ] 3.4 Implement multi-tab management: Target.createTarget for new sessions, Target.attachToTarget on tab switch, CDP event-based target tracking
- [x] 3.5 Implement conversation interrupt save/restore (messages + budget + error state serialization)
- [x] 3.6 Create `api/service.py` with session/chat/pipeline management
- [x] 3.7 Add WebSocket event push + chat endpoint to `api/server.py`
- [ ] 3.8 Implement Electron frontend WebSocket client for IPC
- [x] 3.9 Create prompt files: `prompts/chat/system.md`, `prompts/preset/system.md`, `prompts/guardrails/{exact_failure,same_tool_failure,no_progress}.md`, `prompts/guidance/{tool_strategy,error_recovery}.md`
- [x] 3.10 Implement preset save/load (conversation history → agent.md via compiler)
- [ ] 3.11 Update Electron frontend for chat UI (message list, input, browser preview)

## 4. Phase 3: 收尾

- [ ] 4.1 Integration tests (chat → browser operation → export)
- [x] 4.2 Verify existing tests still pass
- [ ] 4.3 Clean up deprecated code paths
- [ ] 4.4 Update docs
