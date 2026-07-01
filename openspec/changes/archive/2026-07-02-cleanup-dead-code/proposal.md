## Why

随着 yak-browser-use 项目的迭代，后端积累了一些未完成功能的基础设施和废弃代码。这些代码通过 codegraph 结构分析确认了零生产调用者，属于典型的"设计过度但从未接入"的残留物。它们增加了代码库的理解成本，让新读者误以为系统已经具备了这些能力（审批回滚、中断恢复等）。

本次清理分为两类：
1. **安全清理** — 4 类死代码，已确认删除后不影响任何现有行为
2. **预留说明** — `CompensationRegistry` 虽当前无实效，但 `StepMachine` 的基础设施将在后续 preset failure → agent recovery 中被复用，暂不清理

## What Changes

### 安全清理（本次执行）

- **guardian 残留清理**：移除 `cli/run.py` 对已删除 guardian 模块的 import 和调用；移除 `compiler/schema.py` 中的 `guardian` 字段；重命名 `runner_preset.py` 中的 `_execute_tool_step_with_guardian` → `_execute_tool_step`
- **`compiler/diff.py` 全家桶**：删除整个 `diff.py` 文件（含 `diff_ops`、`filter_rejected`、`add_to_rejected`、`save_suggestions`、`merge_extra_ops`、`extract_summary` 6 个函数）及其对应的 `compiler/__init__.py` 导出
- **删除 `electron/src/renderer/components/SuggestionsPanel.tsx`**：无人引用的前端审批 UI 组件
- **删除 `tests/test_compiler_diff.py`**：仅测试死代码的测试文件
- **`GUARDIAN_ERROR` / `REVIEW_INTERRUPT` 错误码清理**：从 `step_machine.py` 的 `NON_RETRYABLE_ERRORS` 中移除从未被产生的错误码
- **InterruptState / 中断恢复死代码**：删除 `InterruptState` 类、`save_interrupt_state`、`resume_conversation`、`TurnContext.reset()` / `snapshot()` 方法，以及对应的 `__init__.py` 导出和测试用例

### 附带修复（发现的小 bug，顺手修）

- **`tool_executor.py` `_pipeline_finish` break 位置移动**：将 break 放在 browser ops highlight refresh 之后，确保 finish 前最后一次 browser 操作（如 click/goto）仍能触发页面高亮刷新。这是原本逻辑顺序的 bug，break 提前导致最后一个操作后 UI 看不到高亮更新。

### 暂不清理（规划中）

- **`CompensationRegistry`**（`engine/_lifecycle/compensation.py`）：当前无实效，但 `StepMachine` 的 `advance(goto=)`、`replace_remaining()`、`fork_back()` 等方法将被预设为后续 failure recovery 的基础设施。等 agent recovery 的 change 建成后再清理或重构
- **`runner_preset.py` 中的 `compensation_history` / `compromised_ops` 收集逻辑**：同上，暂不动，对接下来的 design 有参考价值

## Capabilities

### New Capabilities

本次无新增能力，纯清理。

### Modified Capabilities

- `pipeline-execution`（内部实现简化，外部行为不变）
- `compiler-api`（移除导出符号，但它们在当前代码库内无实际消费者）

## Impact

**受影响的文件（共 12 个）：**

| 文件 | 操作 |
|---|---|
| `backend/src/yak_browser_use/cli/run.py` | 删除 guardian import + 调用 + 参数 |
| `backend/src/yak_browser_use/compiler/schema.py` | 删除 guardian 字段 + frontmatter 传值 |
| `backend/src/yak_browser_use/engine/runner_preset.py` | 函数改名 `_execute_tool_step_with_guardian` → `_execute_tool_step` |
| `backend/src/yak_browser_use/compiler/__init__.py` | 删除 diff.py 相关 import + export |
| `backend/src/yak_browser_use/compiler/diff.py` | 整文件删除 |
| `backend/tests/test_compiler_diff.py` | 整文件删除 |
| `electron/src/renderer/components/SuggestionsPanel.tsx` | 整文件删除 |
| `backend/src/yak_browser_use/engine/step_machine.py` | 删除 `GUARDIAN_ERROR` / `REVIEW_INTERRUPT` 错误码 |
| `backend/src/yak_browser_use/engine/_harness/turn_context.py` | 删除 `InterruptState` + `save_interrupt_state` + `reset/snapshot` |
| `backend/src/yak_browser_use/engine/_harness/conversation_loop.py` | 删除 `resume_conversation` |
| `backend/src/yak_browser_use/engine/_harness/__init__.py` | 删除 InterruptState 相关 export |
| `backend/tests/test_conversation_loop.py` / `test_turn_context.py` | 删除相关测试用例 |

**不影响的文件：**

- `compiler/diff.py` 的 6 个函数在测试外无生产消费者 → 安全
- `InterruptState` 系列在测试外无生产调用 → 安全
- `SuggestionsPanel.tsx` 前端无引用 → 安全

**外部接口不变：** 本次变更不影响 API 契约、CLI 命令、前端路由或用户可见行为。
