## Why

`goal_run` tool 的 handler 只返回一段提示文字，而 `goal-execution` SKILL.md（tag:system）已在每次对话中自动注入几乎相同的指令。LLM 调用 `goal_run` tool 只是多消耗一次 round-trip，无实际收益。同时，`record_step.py` 整文件是死代码——零生产调用者，其功能已被 `pipeline_add_step` 合并。

本次变更清理这些死代码，简化 `goal_run` 从 tool 到纯 skill 的迁移，减少约 180 行代码和 1 个冗余文件。

## What Changes

- **删除** `backend/src/yak_browser_use/tools/record_step.py`（134 行死代码）
- **删除** `tools/registry.py` 中 `_goal_run_handler` 函数及其 `registry.register("goal_run", ...)` 注册
- **删除** `engine/_harness/tools.py` 中 `include_goal_run` 参数、`get_browser_tools()` 函数
- **删除** `engine/_harness/__init__.py` 中 `get_browser_tools` 的 re-export
- **删除** `tool_executor.py` 中 `if not ok and fn_name == "goal_run"` 无意义分支
- **更新** `prompts/chat/system.md` 去掉 `goal_run` 引用，改为直接描述复杂目标处理方式
- **更新** `prompts/guidance/tool_strategy.md` 去掉 `goal_run` 调用步骤
- **更新** `prompts/skill/goal-execution/SKILL.md` 去掉 `（通过 goal_run）` 引用
- **更新** `iteration_budget.py` 和 `tool_executor.py` 中注释，去掉 "goal_run" 字样
- **更新** active specs（goal-run、goal-execution、tool-registration、eval-agent）
- **更新** README 及文档中 goal_run 引用
- **删除** 相关测试（test_goal_run_tool、test_get_all_tools_with_goal 等）
- **保留** pipeline YAML 中 `op_type == "goal_run"` 逻辑（YAML step 类型，非 LLM tool）

## Capabilities

### Modified Capabilities
- `goal-run`: 从 tool 行为变更为纯 skill 行为，不再注册为 LLM 可调用 tool
- `goal-execution`: 去掉 "调 goal_run 后" 的引用，改为 "当用户提出复杂目标时"
- `tool-registration`: 删除 `include_goal_run` 参数相关场景
- `eval-agent`: 去掉 goal_run 作为示例 tool 的引用

## Impact

- 受影响文件：~20 个（包括源码、prompt、spec、文档、测试）
- 净减少约 180 行代码
- 删除 1 个文件（record_step.py）
- 不影响 pipeline YAML 兼容性（op_type == "goal_run" 保留）
- 不影响终端用户功能——goal_run 始终是 no-op，删除后 LLM 直接走 skill 指令
