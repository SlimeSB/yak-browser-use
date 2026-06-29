## 1. 测试先行（E 步骤）

- [ ] 1.1 删除 `test_harness_tools.py` 中 `test_goal_run_tool()`、`test_get_all_tools_with_goal`、`test_get_all_tools_without_goal`、`test_get_browser_tools()`
- [ ] 1.2 删除 `test_registry.py` 中 `_goal_run_handler` import、`TestGoalRunHandler` 测试类、`"goal_run" in names` 断言、`"record_step" not in names` 断言
- [ ] 1.3 修改 `test_prompts_loader.py` 中 `"goal_run" in text` 断言，改为其他唯一标记

## 2. 删除代码（A 步骤）

- [ ] 2.1 删除 `backend/src/yak_browser_use/tools/record_step.py` 文件
- [ ] 2.2 删除 `tools/registry.py` 中 `_goal_run_handler` 函数和 `registry.register("goal_run", ...)` 注册
- [ ] 2.3 简化 `engine/_harness/tools.py` 中 `get_all_tools()`：删除 `include_goal_run` 参数
- [ ] 2.4 删除 `engine/_harness/tools.py` 中 `get_browser_tools()` 函数
- [ ] 2.5 删除 `engine/_harness/__init__.py` 中 `get_browser_tools` 的 re-export
- [ ] 2.6 删除 `tool_executor.py` 中 `if not ok and fn_name == "goal_run"` 分支
- [ ] 2.7 删除 `tools/registry.py` 中 `record_step` 的注释行

## 3. 更新 Prompt（B 步骤）

- [ ] 3.1 修改 `prompts/chat/system.md`：`Use goal_run to set...` 改为直接描述复杂目标处理方式
- [ ] 3.2 修改 `prompts/guidance/tool_strategy.md`：`### When to use goal_run` 改为 `### When to use complex goal mode`，去掉调 goal_run 步骤
- [ ] 3.3 修改 `prompts/skill/goal-execution/SKILL.md`：去掉 `（通过 goal_run）` 引用
- [ ] 3.4 修改 `iteration_budget.py` docstring：`"for goal_run"` 改为 `"for CDP reconnect"`
- [ ] 3.5 修改 `tool_executor.py` docstring：`(paused during goal_run)` 改为 `(paused during CDP reconnect)`

## 4. 更新 Active Spec（C 步骤）

- [ ] 4.1 更新 `openspec/specs/goal-run/spec.md`：描述 goal-run 作为纯 skill，添加 REMOVED 说明
- [ ] 4.2 更新 `openspec/specs/goal-execution/spec.md`：去掉所有"调 goal_run 后"引用
- [ ] 4.3 更新 `openspec/specs/tool-registration/spec.md`：删除 `include_goal_run` 参数相关 scenario
- [ ] 4.4 更新 `openspec/specs/eval-agent/spec.md`：`类似 goal_run、pipeline_finish` 改为 `类似 pipeline_finish`

## 5. 更新文档（D 步骤）

- [ ] 5.1 更新 `README.md`：去掉 `goal_run /` 引用
- [ ] 5.2 更新 `README.zh-CN.md`：去掉 `goal_run` 引用
- [ ] 5.3 更新 `docs/architecture-overview.md`：去掉或更新 goal_run 作为 tool 的引用

## 6. 验证

- [ ] 6.1 运行 `pytest` 确认所有测试通过
- [ ] 6.2 运行 lint 检查无新增问题
- [ ] 6.3 确认 `goal-execution` SKILL.md 的 system tag 仍有效注入
