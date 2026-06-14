## 1. scratchpad + 编排层过滤 + 工具增强（阶段 1）

- [ ] 1.1 新建 `engine/scratchpad.py`：实现 `ScratchpadRecord` dataclass（含 `url`、`title`、`elements`、`element_map`、`raw_html`、`summary`）、模块级 `_scratchpads` dict、`get()`/`store()`/`store_raw_html()`/`_build_summary()`/`sync_element_map()` 函数
- [ ] 1.2 修改 `cdp/helpers.py`：`capture_snapshot()` 和 `capture_snapshot_interactive()` 返回值加 `url`（`window.location.href`）和 `title`（`document.title`）字段——一次 `Runtime.evaluate` 同时获取两者，不增加 CDP 往返
- [ ] 1.3 修改 `engine/_harness/tools.py`：`browser_snapshot` tool schema 加 `mode` 参数（enum: interactive/full/simplified，默认 interactive）；`browser_source` tool schema 加 `cached` 参数（默认 false）；`browser_get_element_by_number` tool description 更新
- [ ] 1.4 修改 `engine/executor.py`：`execute_browser_op()` 中 snapshot handler 默认 mode 从 `"full"` 改为 `"interactive"`（`params.get("mode", "interactive")`）；注意 `execute_browser_step()` 的默认值保持 `"full"` 不变（pipeline YAML 不受影响）
- [ ] 1.5 修改 `engine/_harness/tool_executor.py`：在 `execute_tool_calls_sequential()` 中 `_append_tool_result` 调用前插入编排层过滤逻辑——按 `fn_name` + `mode` 分支处理重数据摘录、scratchpad 写入、摘要生成
- [ ] 1.6 修改 `engine/_harness/tool_executor.py`：`browser_source` 工具执行结果（HTML）走 scratchpad 存储，返回可读摘要（如 `"HTML 源代码已缓存（15,000 字符）"`）；支持 `cached=True` 时从 scratchpad 读取，无缓存时 fall through 到正常 CDP 路径并在结果中附加 `cached: false`
- [ ] 1.7 修改 `engine/_harness/tool_executor.py`：`browser_get_element_by_number` 预执行钩子优先从 scratchpad 的 `element_map` 查找（含 ref 标准化），无缓存时回退到 `cdp_helpers.get_element_by_index()`

## 2. 去子 Agent + goal_run 改造（阶段 2）

- [ ] 2.1 修改 `engine/_harness/tool_executor.py`：`goal_run` 路由改为返回标准提示文本（不再调用 `execute_goal()`）；删除 `_execute_single_tool_call` 中 `is_goal` 相关的 `budget.pause()`/`budget.resume()` 调用
- [ ] 2.2 修改 `engine/agent.py`：stub `run_goal_step()` 返回 `{"status": "success", "skipped": true}`；删除 `_extract_learned_ops()`、`_save_partial_ops()`、`_cleanup_agent_highlights()` 等辅助函数；删除 `browser_use` 导入
- [ ] 2.3 修改 `engine/executor.py`：stub `execute_goal()` 返回 `{"ok": true, "result": "..."}`；stub `execute_goal_step()` 返回 placeholder 结果
- [ ] 2.4 修改 `engine/_harness/tools.py`：更新 `GOAL_RUN_TOOL` description（去掉 "autonomous browser agent" 措辞）；修正 `record_step` 工具描述（去掉 goal_run 残留）

## 3. prompt + skill + 清理（阶段 3）

- [ ] 3.1 新建 `prompts/skill/goal-execution.md`：goal-execution skill 内容（拆解→逐项执行→每步记录→不确定问用户→失败恢复）
- [ ] 3.2 修改 `prompts/chat/system.md`：工具列表中 `goal_run(description)` 描述更新；加入 goal-execution 指引
- [ ] 3.3 修改 `prompts/preset/system.md`：`goal_run(description)` 描述更新
- [ ] 3.4 修改 `prompts/guidance/tool_strategy.md`：整段 "When to use goal_run" 更新为新模式说明
- [ ] 3.5 新建 `prompts/_archived/` 目录，移入 orphan prompts：`replan-after-goal.md`（仅 goal step 使用，stub 化后不再触发）、`fallback-assessment.md`、`navigation-guard.md`、`recovery-plan.md`、`document-clean.md`、`skill/ph-tool-generation.md`。注意：`replan-on-failure.md` **不移入**——它被所有 step 类型的失败恢复路径使用（`runner_preset.py:541`），移入会导致非 goal step 的失败恢复逻辑丢失 prompt 内容

## 4. preset 模式适配 + check 字段（阶段 4）

- [ ] 4.1 修改 `compiler/schema.py`：`StepYaml` 新增 `check: dict | None = None` 字段；`to_step_def()` 传递 `check` 到 `StepDef`
- [ ] 4.2 修改 `compiler/models.py`：`StepDef` dataclass 新增 `check: dict | None = None` 字段；`to_runtime_dict()` 传递 `check` 字段（否则 `runner_preset.py` 无法访问）
- [ ] 4.3 修改 `engine/_harness/tools.py`：`pipeline_update_step` 的 `updates` 参数描述加 `check`；`pipeline_add_step` 的 schema 加可选 `check` 参数
- [ ] 4.4 新增 `engine/executor.py` 的 `run_check()` 函数：支持 `url_contains`、`element_exists`、`text_contains`、`element_visible` 四种检查条件
- [ ] 4.5 修改 `engine/runner_preset.py`：在 step executor 返回后、`machine.end_step()` 之前调用 `run_check()`（如果 `step_def.check` 不为 None 且 step_type != "goal"）；stub goal step 跳过验收；goal step stub 化后跳过 delivery report 写入和 replan_after_goal 调用
- [ ] 4.6 修改 `engine/executor.py` 的 `execute_goal_step`：preset 遇到 `goal_description` 步骤时返回 placeholder（不再 spawn 子 Agent）

## 5. 测试 + 集成验证（阶段 5）

- [ ] 5.1 新建 `tests/test_scratchpad.py`：验证 scratchpad 读写、session 隔离、element_map 自动构建、新快照覆盖旧数据
- [ ] 5.2 新建 `tests/test_orchestration_filter.py`：验证编排层过滤——interactive/full/simplified 三种 mode 的重数据摘录和摘要生成；验证 add_dom_highlights 后 element_map 同步到 scratchpad
- [ ] 5.3 更新 `tests/test_harness_tools.py`：同步工具数量断言（goal_run 保留但行为变化，工具数量不变）
- [ ] 5.4 更新 `tests/test_tool_executor.py`：验证 goal_run 返回提示文本而非 spawn Agent
- [ ] 5.5 运行 `pytest tests/ -x -q` 确保全部通过
- [ ] 5.6 手动验证 chat 模式下复杂任务能通过 todo + browser_* 完成，中途能问用户
