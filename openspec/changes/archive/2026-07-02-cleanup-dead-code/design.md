## 背景

yak-browser-use 后端的 `compiler/diff.py`、`engine/_harness/turn_context.py`、`engine/_lifecycle/compensation.py`、`engine/_lifecycle/guardian.py`（已删除但残留 import）、`engine/step_machine.py`、`cli/run.py` 等模块中包含多套从未接入生产逻辑的"概念骨架"。它们的设计意图（审批回滚、中断恢复、op补偿）本身是合理的，但因为种种原因从未被实现到可工作状态。

本次清理的动机不是"这些设计错了"，而是：**
1. 这些死代码已经确认不会被当前架构复用（Guardian 审批、InterruptState 恢复）
2. 它们的语义容易误导读者（CompensationRegistry 让人以为系统有 rollback 能力）
3. 删掉它们能减少未来开发者的认知负担

## 目标 / 非目标

**目标：**
- 移除零生产调用者的死代码，减少代码库体积和误读风险
- 不影响任何现有行为（API 契约、CLI 命令、前端路由、测试覆盖率中非死代码部分）

**非目标：**
- 不实现新的 failure recovery 机制（那是后续 separate change）
- 不重构 `StepMachine` 的 DAG 基础设施（它将被复用）
- 不动 `CircuitBreakerMixin`（活代码，有 9 个生产调用点）

## 关键决策

### 为什么删 `InterruptState` 而不保留"以防万一"

`InterruptState` 设计的场景是"subagent 执行中途被中断 → 保存完整状态 → 恢复"。但当前主 agent 采用更简洁的模式：取消 = 用户停止当前 run，后续消息会带着完整 `session.messages` 历史新开一轮对话。没有"恢复中断执行"的需求，所以在未来可预见的设计方向上这套机制都不会被需要。

### 为什么 `CompensationRegistry` 暂不清理

`engine/_lifecycle/compensation.py` 本身确实是死代码（`CompensationRegistry`、`OpRecord`、`UNDO_MAP` 全部零生产调用）。但 `StepMachine`（`engine/step_machine.py`）的以下方法将被后续 preset failure → agent recovery 功能直接复用：

- `advance(goto=label)` — LLM 决策后跳到指定 step
- `replace_remaining(new_steps)` — LLM 生成修正后的后续 step 列表
- `fork_back()` — 回到 goto 之前的 fork 点
- `resume_from_index` — 执行前可指定起始位置
- `to_execution_tree()` — 序列化当前 DAG 状态喂给 LLM

`StepMachine` 的 docstring（"Manages sequential step execution with retry, fork, and recovery support"）说明它从一开始就是为 LLM recovery 设计的。`run_pipeline` 的 terminal failure `break` 是功能未完成的标志，不是设计意图。

因此：**`CompensationRegistry` 对接 change 完成后清理，当前保留作为参考。`StepNode.compromised_ops` 字段也保留到那时再评估。**

### 为什么 `compiler/diff.py` 和 `SuggestionsPanel.tsx` 要一起删

它们是 Guardian 审批流水线的两端：`diff.py` 发现 agent 的多余操作 + 写 rejected/suggestions；`SuggestionsPanel.tsx` 展示审批 UI。随着 Guardian 核心删除，这两端都是完全的孤儿代码。

## 风险 / 权衡

| 风险 | 缓解手段 |
|---|---|
| 误删间接依赖 | 已通过 codegraph 全量扫描确认零生产调用者 |
| 现有测试引用被删代码 | 删除测试文件中的死代码专用测试用例 |
| 后续 agent recovery 发现需要某些被删设施 | git 历史完整保留，可回溯；且保留 `StepMachine` 作为 receiver |
| `NON_RETRYABLE_ERRORS` 修改导致某处隐式依赖 | `GUARDIAN_ERROR` / `REVIEW_INTERRUPT` 从未被任何代码产生，移除后无影响范围 |

## 迁移计划

本次变更无需数据迁移，无需 API 兼容性安排。

**回滚策略：** 标准 `git revert`。被删文件的完整内容在 git 历史中可用。

**执行顺序：**
1. 先删纯死代码（diff.py + SuggestionsPanel.tsx + test_compiler_diff.py）
2. 再删 guardian 残留（cli/run.py + schema.py + runner_preset.py 改名）
3. 再删 InterruptState 系列（turn_context.py + conversation_loop.py + __init__.py 导出 + 测试用例）
4. 最后清理 `step_machine.py` 的死错误码
5. 删完后跑全量测试确认无回归

## 待确认问题

- 无。所有被删项已确认零生产调用者。
