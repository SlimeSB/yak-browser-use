## 1. 删除 compiler/diff.py 全家桶

- [x] 1.1 删除 `backend/src/yak_browser_use/compiler/diff.py` 整文件（286 行，含 diff_ops/filter_rejected/add_to_rejected/save_suggestions/merge_extra_ops/extract_summary）
- [x] 1.2 编辑 `backend/src/yak_browser_use/compiler/__init__.py`：删除两行 `from yak_browser_use.compiler.diff import ...` 以及 `__all__` 中对应的 6 个导出名称
- [x] 1.3 删除 `backend/tests/test_compiler_diff.py` 整文件
- [x] 1.4 删除 `electron/src/renderer/components/SuggestionsPanel.tsx`（零前端引用）

## 2. 清理 guardian 残留

- [x] 2.1 编辑 `backend/src/yak_browser_use/cli/run.py`：删除 `from yak_browser_use.engine._lifecycle.guardian import (...)` import 块 + `inject_guardian_config_to_steps(...)` 调用 + `create_guardian_from_frontmatter(...)` 调用 + `guardian=guardian` 关键字参数（第 59-78 行附近）
- [x] 2.2 编辑 `backend/src/yak_browser_use/compiler/schema.py`：删除 `guardian: dict[str, Any] = Field(default_factory=dict)` 字段（第 107 行）+ `to_pipeline_def()` frontmatter dict 中的 `"guardian": self.guardian` 条目（第 123 行）
- [x] 2.3 编辑 `backend/src/yak_browser_use/engine/runner_preset.py`：将 `_execute_tool_step_with_guardian` 重命名为 `_execute_tool_step`，同步更新调用点（第 302 行）

## 3. 删除 InterruptState / 中断恢复死代码

- [x] 3.1 编辑 `backend/src/yak_browser_use/engine/_harness/turn_context.py`：删除整个 `InterruptState` 类（第 43-67 行）+ `save_interrupt_state` 函数（第 84-96 行）
- [x] 3.2 编辑 `backend/src/yak_browser_use/engine/_harness/turn_context.py`：从 `TurnContext` 类中删除 `reset()` 和 `snapshot()` 方法，同时删除 `turn_messages_snapshot` 字段
- [x] 3.3 编辑 `backend/src/yak_browser_use/engine/_harness/conversation_loop.py`：删除 `resume_conversation` 函数（第 371-386 行）
- [x] 3.4 编辑 `backend/src/yak_browser_use/engine/_harness/__init__.py`：删除 `InterruptState`、`save_interrupt_state`、`resume_conversation` 的 import 和 `__all__` 条目
- [x] 3.5 编辑 `backend/tests/test_turn_context.py`：删除 `InterruptState` 相关测试用例（`test_defaults`、`test_with_values`、`test_to_dict_full`、`test_to_dict_minimal`、`test_saves_full_state`、`test_minimal_state`、`test_messages_copied`，约 60 行）
- [x] 3.6 编辑 `backend/tests/test_conversation_loop.py`：删除 `test_resume_conversation` 测试函数（约 20 行）

## 4. 清理 step_machine.py 死错误码

- [x] 4.1 编辑 `backend/src/yak_browser_use/engine/step_machine.py`：从 `NON_RETRYABLE_ERRORS` 集合中移除 `"GUARDIAN_ERROR"` 和 `"REVIEW_INTERRUPT"`

## 5. 附带修复：tool_executor.py pipeline_finish break 位置

- [x] 5.1 编辑 `backend/src/yak_browser_use/engine/_harness/tool_executor.py`：将 `_pipeline_finish` break 移到 browser ops highlight refresh 之后，确保 finish 前最后一个 browser 操作仍触发高亮刷新

## 6. 验证

- [x] 6.1 运行核心单元测试确认无回归（86 passed in 1.50s）
- [x] 6.2 手工验证 `ybu run` CLI 不再报 guardian TypeError
