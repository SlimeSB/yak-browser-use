## 0. 共享前置条件（Plan B 和 Plan C 都需要）

- [x] 0.1 `engine/runner_preset.py` — `run_pipeline()` 签名新增 `llm_call` 参数（`Callable | None = None`），供 Local Planner 和 Agent Swimlane 共用
- [x] 0.2 `cli/run.py` — `_execute_pipeline()` 创建 `llm_call` 并传入 `run_pipeline()`（`engine/runner.py` 仅为 re-export，无需修改）
- [x] 0.3 `api/routes.py` — pipeline 执行路由创建 `llm_call` 并传入 `run_pipeline()`（否则 API 路径无法使用 fallback）

## 1. Plan A：基础修复

- [x] 1.1 `engine/executor.py` — `ERROR_CODES` 字典新增 `"CHECK_FAILED": "Step check validation failed"`
- [x] 1.2 `engine/_lifecycle/fallback.py` — `assess_page_state()` 函数体顶部加 `# DEPRECATED: 已被 Agent Swimlane 替代，保留仅为向后兼容` 注释
- [x] 1.3 `engine/_lifecycle/fallback.py` — `generate_recovery_plan()` 函数体顶部加 `# DEPRECATED: 已被 RuntimePlanner 替代，保留仅为向后兼容` 注释
- [x] 1.4 验证：check fail 后 error_code 为 `CHECK_FAILED`，`needs_retry()` 返回 False，不触发重试

## 2. Plan B：Op Fail → Local Planner

- [x] 2.1 新建 `engine/planner.py` — 实现 `RuntimePlanner` 类，包含 `__init__(self, llm_call)` 和 `async plan_replacement_ops(*, failed_op, goal_description, error_message, simplified_html) -> list[dict] | None`
- [x] 2.2 `engine/planner.py` — 实现 `_build_planner_prompt()` 构建 LLM prompt（包含失败操作、目标、错误、简化 HTML）
- [x] 2.3 `engine/planner.py` — 实现 `_parse_ops_response()` 从 LLM 响应中解析 browser_ops 数组
- [x] 2.4 `engine/runner_preset.py` — 替换旧 planner 恢复代码（`# ── Planner: recovery planning ──` 注释开始的整个 block）：retry 耗尽后调用 `RuntimePlanner.plan_replacement_ops()`，成功则**直接修改当前 step 的 `browser_ops` 字段**（注意：`machine.replace_remaining()` 替换的是后续步骤，不是当前步骤） + `continue`；失败则进入 terminal failure
- [x] 2.5 `engine/runner_preset.py` — 添加 Local Planner 连续失败计数器（超过 3 次进入 terminal failure，记录完整错误链：原始错误 + 恢复失败原因）
- [ ] 2.6 验证：构造一个包含不存在选择器的 pipeline，确认 op 失败 → retry → Local Planner → 替代 ops 执行

## 3. Plan C：Check Fail → Agent Swimlane

- [x] 3.1 `engine/_harness/iteration_budget.py` — `IterationBudget` 新增 `exhaust()` 方法：`self._used = self.max_total`
- [x] 3.2 `engine/_harness/tools.py` — `PIPELINE_TOOLS` 新增 `pipeline_finish` 工具定义（status: "completed"|"failed", summary: string，`required: ["status"]`）
- [x] 3.3 `engine/_harness/tool_executor.py` — `_execute_single_tool_call()` 在 `elif fn_name.startswith("pipeline_")` 分支**之前**（即 line 212 之前）新增 `elif fn_name == "pipeline_finish"` 分支，调用 `budget.exhaust()` 并返回 `{"ok": True, "status": status, "summary": summary}`
- [x] 3.4 `engine/runner_preset.py` — 新增 import：`from engine._harness.conversation_loop import run_preset_loop, ConversationResult` 和 `from engine._harness.iteration_budget import IterationBudget`
- [x] 3.5 `engine/runner_preset.py` — 实现 `_collect_checkpoints(run_dir, machine) -> list[str]` 遍历已完成步骤，从 `step_dir/step.json` 提取 `final_url`（跳过空 URL）
- [x] 3.6 `engine/runner_preset.py` — 实现 `_extract_final_url(step_dir) -> str | None` 从 `step.json` 读取 URL（若 `final_url` 为空则返回 None）
- [x] 3.7 `engine/runner_preset.py` — 实现 `_run_swimlane_agent()` 函数：调用 `cdp_helpers.capture_snapshot_simplified()` 获取当前页面状态 → 收集已完成步骤和检查点 → 构建包含运行时上下文的 user message → 创建 `IterationBudget` → 调用 `run_preset_loop()`
- [x] 3.8 `engine/runner_preset.py` — 失败路径中，`CHECK_FAILED` 错误码 → 调用 `_run_swimlane_agent()`
- [x] 3.9 `engine/runner_preset.py` — swimlane 返回后处理 `ConversationResult`：
  - [x] 3.9a `ConversationResult.final_response` 非空且未被中断 → 正常 finalise（复用 `run_pipeline()` 末尾的 finalise 逻辑：写 version snapshot、执行树、emit run_end）
  - [x] 3.9b `ConversationResult.budget.is_exhausted` 且 `final_response` 为空 → 从 `ConversationResult.messages` 中查找最后一条包含 `pipeline_finish` 的 tool 结果消息，若 status="failed" 则记录 agent 提供的失败摘要；否则记录 "budget exhausted" 错误
  - [x] 3.9c `ConversationResult.interrupted` → 标记 pipeline 失败，记录 "agent interrupted" 错误
- [ ] 3.10 验证：构造一个 check 预期 URL 不匹配的 pipeline，确认 check fail → Agent Swimlane → agent 自主完成

## 4. Plan D：入口统一

- [x] 4.1 `__main__.py` — `run` 子命令新增 `--engine` 参数（choices: programmatic/agent，默认 programmatic）。注意：现有 `--mode` 参数（auto/static/learn/replay）未被使用，保留不动，新参数用 `--engine` 避免命名冲突
- [x] 4.2 `cli/run.py` — `_cmd_run()` 接受 `engine` 参数，agent 模式直接调用 `run_preset_loop()`，跳过 `run_pipeline()`
- [x] 4.3 `api/routes.py` — pipeline 执行路由接受 `engine` 字段（"programmatic" | "agent"）
- [ ] 4.4 验证：`ybu run pipeline.yaml --engine agent` 走 agent 路径，默认走 programmatic 路径

## 5. 清理与收尾

- [x] 5.1 确认 `engine/runner_preset.py` 中不再有 `from engine.planner import RuntimePlanner` 的旧导入（已替换为新调用）
- [x] 5.2 确认 `engine/runner_preset.py` 中不再调用 `assess_page_state()`（`generate_recovery_plan()` 从未在 runner_preset.py 中被调用，仅需确认 fallback.py 中已标记 deprecated）
- [x] 5.3 运行现有测试套件，确认无回归
- [ ] 5.4 端到端测试：正常 pipeline 执行不受影响
