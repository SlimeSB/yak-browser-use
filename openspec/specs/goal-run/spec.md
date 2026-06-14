## MODIFIED Requirements

### Requirement: goal_run 工具行为
系统 MUST 将 `goal_run` 工具的行为从 spawn browser-use 子 Agent 改为返回模式切换提示文本，引导主 LLM 使用 `todo` + `browser_*` 工具逐步执行复杂任务。

#### Scenario: goal_run 返回模式切换提示
- **WHEN** LLM 调用 `goal_run(description="在淘宝搜索机械键盘")`
- **THEN** 工具返回 `{"ok": true, "result": "目标已设定: 在淘宝搜索机械键盘\n\n请用 todo 工具将目标拆解为 3-6 个步骤逐项执行。每步完成后调 record_step。不确定时直接问我。"}`
- **AND** 不再创建 browser-use Agent 实例
- **AND** 不再调用 `engine.agent.run_goal_step()`

#### Scenario: goal_run tool schema 保留
- **WHEN** 系统注册工具列表
- **THEN** `GOAL_RUN_TOOL` 的 schema 结构保持不变
- **AND** `name` 仍为 `"goal_run"`
- **AND** `description` 更新为反映新模式（不再提及 "autonomous browser agent"）

#### Scenario: goal_run 不再暂停外层预算
- **WHEN** `goal_run` 工具被执行
- **THEN** 不再调用 `budget.pause()` 或 `budget.resume()`
- **AND** 外层 `IterationBudget` 正常消耗（每次 goal_run 调用消耗 1 个 token）

### Requirement: run_goal_step stub 化
`engine.agent.run_goal_step()` MUST 不再创建 browser-use Agent，改为返回 stub 结果。

#### Scenario: run_goal_step 返回 stub
- **WHEN** `run_goal_step(step_def, ...)` 被调用
- **THEN** 返回 `{"status": "success", "skipped": true, "message": "Goals execute via todo + browser_* in chat mode"}`
- **AND** 不导入 `browser_use` 模块
- **AND** 不创建 `browser_use.Agent` 或 `browser_use.Browser` 实例

### Requirement: execute_goal stub 化
`engine.executor.execute_goal()` MUST 不再委托给 `run_goal_step()`，改为返回 stub 结果或直接删除。

#### Scenario: execute_goal 返回 stub
- **WHEN** `execute_goal(description, ...)` 被调用
- **THEN** 返回 `{"ok": true, "result": "Goal execution delegated to main LLM via todo + browser_* tools"}`
- **AND** 不调用 `engine.agent.run_goal_step()`

## REMOVED Requirements

### Requirement: browser-use Agent 创建
**Reason**: 去掉两层 Agent 架构，主 LLM 直接通过 browser_* 工具执行任务。

**Migration**: `run_goal_step()` 和 `execute_goal()` 改为 stub 实现。调用方（`tool_executor.py` 的 goal_run 路由、`executor.py` 的 `execute_goal_step`）改为返回提示文本或 placeholder。

### Requirement: _extract_learned_ops 自学习提取
**Reason**: 子 Agent 的自学习路径是 stub 实现，去掉子 Agent 后不再需要。

**Migration**: 删除 `_extract_learned_ops()` 和 `_save_partial_ops()` 函数。主 LLM 通过 `record_step` 工具实时写入 pipeline，自学习路径自然打通。

### Requirement: IterationBudget goal_run 暂停
**Reason**: `goal_run` 不再 spawn 子 Agent，不需要暂停外层预算。

**Migration**: 删除 `_execute_single_tool_call` 中 `is_goal` 相关的 `budget.pause()`/`budget.resume()` 调用。CDP 重连时的 `budget.pause()` 保留（通用错误恢复逻辑）。

### Requirement: record_step 工具描述
**Reason**: `record_step` 工具描述中包含对 goal_run / browser-use 子 Agent 的过时引用，去掉子 Agent 后需同步更新。

**Migration**: 修正 `engine/_harness/tools.py` 中 `record_step` 的工具描述，移除"配合 goal_run 使用"、"子 Agent" 等过时措辞。

### Requirement: orphan prompts 归档
**Reason**: 以下 prompt 文件仅被 goal step / browser-use 子 Agent 相关路径引用，去掉子 Agent 并 stub 化 goal step 后不再被任何代码触发，因此归档到 `prompts/_archived/`。

**Migration**:
- 移入 `prompts/_archived/` 的文件：`replan-after-goal.md`、`fallback-assessment.md`、`navigation-guard.md`、`recovery-plan.md`、`document-clean.md`、`skill/ph-tool-generation.md`
- `replan-on-failure.md` 不移入——它被所有 step 类型的失败恢复路径使用（`runner_preset.py`），移入会导致非 goal step 的失败恢复逻辑丢失 prompt 内容
