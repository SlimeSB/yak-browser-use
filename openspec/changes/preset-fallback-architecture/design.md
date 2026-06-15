## 背景

当前 `engine/runner_preset.py` 的失败恢复路径存在三个断裂点：

1. **Planner 导入断裂**：第 463 行 `from engine.planner import RuntimePlanner` 目标文件不存在，任何恢复尝试都触发 `ImportError`，被 `except Exception` 吞掉后直接进入终端故障。
2. **Stub 函数无意义**：`assess_page_state()` 永远返回 `(False, 0)`，`generate_recovery_plan()` 永远返回 `None`，两者从未被实现。
3. **Agent 入口闲置**：`run_preset_loop()` 是完整可用的 agent 模式入口（基于 `conversation_loop`），但从未与程序化执行路径对接。

约束条件：
- 统一使用主模型，不做模型分层
- `goto` 即检查点，不额外保存
- 不限制替代 ops 数量，让 LLM 自行决定
- 每条恢复路径独立可测，不出现"改到一半不 work"

## 目标 / 非目标

**目标：**
- 建立三层递进式 fallback：Tier 1 retry → Tier 2 Local Planner → Tier 3 Agent Swimlane
- Op 执行失败且重试耗尽后，LLM 单次调用生成替代 ops，不切换执行引擎
- Check 验证失败后，切换到 agent mode，agent 自主决策直到 pipeline 结束
- 清理旧的 broken planner 死代码和 stub 函数

**非目标：**
- 不引入模型分层（不用小模型做 planner、大模型做 agent）
- 不修改 `conversation_loop` 核心 while 循环
- 不修改 `run_preset_loop()` 接口签名
- 不删除 `fallback.py` 中的 stub（仅标记 deprecated，保持向后兼容）

## 关键决策

### 决策 1：check fail 不加 RETRYABLE_ERRORS

**选择**：`CHECK_FAILED` 不加入 `RETRYABLE_ERRORS`，check fail 后跳过 retry 直接进入恢复路径。

**原因**：check 失败意味着页面状态与预期不符，重跑同样的 ops 不会改变结果。retry 在这里是浪费时间和 LLM 预算。

**备选方案**：将 `CHECK_FAILED` 加入 `RETRYABLE_ERRORS` 让 check 也重试。被否决——重试无意义。

### 决策 2：Agent Swimlane 退出信号用 budget.exhaust()

**选择**：在 `IterationBudget` 新增 `exhaust()` 方法，`pipeline_finish` 工具调用它来触发退出。不修改 `conversation_loop` 的 while 循环。

**原因**：`check_exit_conditions` 已经检查 `budget.is_exhausted`，只需让 budget 立即耗尽即可自然退出。这避免了在 while 循环中引入新的退出条件分支，改动最小。

**备选方案**：在 `check_exit_conditions` 中新增 `task_complete` 标志位。被否决——需要在多个函数间传递状态，增加耦合。

### 决策 3：运行时上下文通过 messages 参数注入

**选择**：不修改 `run_preset_loop()` 接口，通过已有的 `messages` 参数注入运行时上下文（已完成步骤、检查点 URL、失败详情）。

**原因**：`run_preset_loop` 已接受 `messages: list[dict] | None = None`，内部直接传给 `run_conversation_loop`。在调用前构建一个包含上下文的 user message 即可，无需改接口。

**备选方案**：新增 `context` 参数或修改 system prompt 构建逻辑。被否决——增加接口复杂度，且 system prompt 由 `preset/system.md` 模板控制，不适合注入运行时数据。

### 决策 4：检查点 URL 从 step_dir/step.json 提取

**选择**：从已执行步骤的 `step_dir/step.json` 中读取 `final_url` 字段作为检查点 URL。

**原因**：`StepNode.goto` 存的是 URL alias（如 `{search_url}`），不是解析后的实际 URL。而每个 browser step 执行后会在 `step.json` 中写入 `final_url`，这是已解析的真实 URL，agent 可以直接 `browser_goto()`。

**备选方案**：从 `StepNode.goto` 提取并手动解析 alias。被否决——需要维护 URL alias 解析逻辑，且 `step.json` 已有现成数据。

### 决策 5：RuntimePlanner API 另起炉灶

**选择**：新 `RuntimePlanner` 的 API 为 `plan_replacement_ops()`，与旧 broken 路径的 `planner.replan_on_failure.replan()` 完全无关。

**原因**：旧路径从未实现过，不存在兼容性负担。新 API 更简洁（4 个参数 vs 旧路径的 6 个参数），语义更清晰。

### 决策 6：实施顺序 Plan A → B → C → D

**选择**：按基础修复 → Op fallback → Check fallback → 入口统一的顺序实施。

**原因**：每个 plan 独立可用、独立可测。Plan A 确保路径不直接断掉，Plan B 让 op 失败可恢复，Plan C 让 check 失败可接管，Plan D 统一入口。不会出现中间状态不可用的情况。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| Local Planner 生成的替代 ops 不可用 | 步骤仍然失败，进入 terminal failure | LLM prompt 包含足够的上下文（goal、failed op、error、简化 HTML），且失败后会正常记录错误日志 |
| Agent Swimlane 中 agent 行为不可控 | agent 可能偏离 pipeline 目标 | system prompt 包含 pipeline 结构，user message 包含检查点 URL 作为锚点，agent 可回退 |
| `budget.exhaust()` 被其他代码误用 | 意外终止 conversation_loop | 仅在 `pipeline_finish` 工具中调用，不在其他地方暴露 |
| 简化 HTML 过大超出 LLM 上下文 | Local Planner 调用失败 | `capture_snapshot_simplified()` 已有截断逻辑，且失败时 fallback 到 terminal failure |

## 迁移计划

1. **Plan A**（基础修复）：无破坏性变更，直接部署。`ERROR_CODES` 新增条目向后兼容。
2. **Plan B**（Local Planner）：新增 `engine/planner.py`，替换 `runner_preset.py` 中的 broken 恢复代码。旧的 stub 函数标记 deprecated 但不删除。
3. **Plan C**（Agent Swimlane）：新增 `pipeline_finish` 工具和 swimlane 函数。`IterationBudget.exhaust()` 是纯新增方法。
4. **Plan D**（入口统一）：CLI/API 新增 `--engine` 参数（注意：现有 `--mode` 参数 auto/static/learn/replay 未被使用，保留不动，新参数用 `--engine` 避免命名冲突），默认值保持现有行为（programmatic），向后兼容。

**回滚**：每个 plan 独立，出问题可单独回滚。Plan A 最简单，Plan B/C 涉及新增文件和修改核心路径，回滚时恢复 `runner_preset.py` 的旧代码即可。

## 待确认问题

- ~~`capture_snapshot_simplified()` 的具体签名和返回值格式~~ — 已确认：`cdp/helpers.py:168`，返回 `{"summary": str, "lists": list, "tables": list, "mode": "simplified"}`
- ~~`step.json` 中 `final_url` 字段是否在所有 browser step 中都有~~ — 已确认：`executor.py:507` 初始化 `final_url: ""`，`goto` op 时写入实际 URL
- `pipeline_finish` 工具是否需要在 chat mode 中也可见——当前设计为所有模式可见，但仅在 swimlane 上下文中 LLM 才会调用
