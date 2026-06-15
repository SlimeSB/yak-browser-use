## Why

当前 preset mode（程序化 pipeline 执行）的失败恢复路径处于断裂状态：`engine/planner.py` 不存在导致任何恢复尝试都触发 `ImportError` 后直接终端故障；`assess_page_state()` 和 `generate_recovery_plan()` 均为 stub，永远返回无意义结果；`run_preset_loop()` 虽然是完整可用的 agent 模式入口，但从未与程序化执行路径对接。结果就是：任何一个 op 失败或 check 不通过，pipeline 直接挂掉，没有任何有效的自动恢复能力。

本次变更建立三层递进式 fallback 架构，让 pipeline 执行在遇到失败时能逐级降级恢复，而不是直接终端故障。

## What Changes

- **新增** `engine/planner.py` — `RuntimePlanner` 类，单次 LLM 调用生成替代 browser_ops
- **新增** `pipeline_finish` 工具 — agent swimlane 的退出信号，通过 `budget.exhaust()` 实现
- **新增** swimlane agent 函数 — check fail 后收集运行时上下文，启动 `run_preset_loop` 接管执行
- **修改** `engine/runner_preset.py` — 失败路径重构：retry 耗尽后走 Local Planner，check fail 后走 Agent Swimlane；移除旧的 broken planner 导入
- **修改** `engine/executor.py` — `ERROR_CODES` 补充 `CHECK_FAILED`
- **修改** `engine/_harness/iteration_budget.py` — 新增 `exhaust()` 方法
- **修改** `engine/_harness/tool_executor.py` — 注册 `pipeline_finish` 工具执行分支
- **修改** `engine/_harness/tools.py` — `PIPELINE_TOOLS` 新增 `pipeline_finish` 工具定义
- **修改** `engine/_lifecycle/fallback.py` — `assess_page_state()` 和 `generate_recovery_plan()` 标记 deprecated
- **修改** CLI/API — 支持 `--engine programmatic|agent` 参数（Plan D，最后实施）

## Capabilities

### New Capabilities
- `local-planner`: op 执行失败且重试耗尽后，LLM 单次调用生成替代 browser_ops，不切换执行引擎
- `agent-swimlane`: check 验证失败后，收集运行时上下文（已完成步骤、检查点 URL、当前页面状态），启动 conversation_loop 让 agent 自主完成剩余 pipeline
- `pipeline-finish-tool`: agent swimlane 中的退出信号工具，agent 调用后正常结束 pipeline
- `mode-selection`: CLI/API 支持 `--engine programmatic|agent` 选择执行引擎

### Modified Capabilities
- `preset-execution`: 失败路径从"直接终端故障"改为"三层递进恢复（retry → Local Planner → Agent Swimlane）"

## Impact

- **engine/runner_preset.py** — 核心改动，失败路径逻辑重构
- **engine/planner.py** — 新文件，不依赖旧 broken 路径
- **engine/_harness/conversation_loop.py** — 不修改核心 while 循环，退出信号通过 budget 实现
- **engine/_harness/tool_executor.py** — 新增 pipeline_finish 工具执行分支
- **engine/_harness/tools.py** — 新增工具定义
- **engine/_harness/iteration_budget.py** — 新增 exhaust() 方法
- **engine/executor.py** — 新增错误码
- **engine/_lifecycle/fallback.py** — 标记 deprecated，不删除（保持向后兼容）
- **cli/run.py** — 新增 `--engine` 参数（Plan D）
- **api/routes.py** — 新增 `engine` 字段（Plan D）
