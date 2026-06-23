---
name: goal-execution
description: 指导 Agent 自主执行复杂多步目标的工作流（拆解→执行→记录→失败恢复）
tags: [system, goal, execution, workflow]
---

## 目标执行模式

当用户设定了一个复杂目标（通过 `goal_run`）后，你需要自主管理执行过程。

### 工作流程

1. **拆解目标**：用 `todo` 工具将目标拆解为 3-6 个具体步骤，每个步骤应该是单一可执行的操作
2. **逐步执行**：按顺序执行每个步骤，使用 `browser_*` 工具完成浏览器操作
3. **每步记录**：每个步骤成功完成后调 `record_step` 写入 pipeline
4. **不确定问用户**：遇到模糊、多选、验证等不确定情况时，输出文字描述并等待用户回复
5. **失败恢复**：某步失败时，用 `browser_snapshot(mode="simplified")` 确认当前页面状态，分析原因后重试或调整策略

### 工具使用优先级

| 场景 | 优先工具 | 说明 |
|------|---------|------|
| 了解页面结构 | `browser_snapshot(mode="simplified")` | token 最少，含标题/链接/表格 |
| 找可交互元素 | `browser_snapshot(mode="interactive", in_viewport=true, query="关键词")` | 精准匹配，减少噪音 |
| 查看完整 HTML | `browser_source()` | 大数据自动缓存到 scratchpad |
| 查询元素详情 | `browser_get_element_by_number(@e_XXXXX)` | 优先从缓存读取，无需 CDP 调用 |
| 执行操作 | `browser_click` / `browser_fill` / `browser_goto` | 直接操作 |

### 记录规则

- 中间试探性操作（如"看看这个元素是什么"）**不调** `record_step`
- 只有确认有效的操作才记录
- 用 `step_1`、`step_2` 等命名步骤
- **反幻觉原则**：`record_step` 的 `op_args` 必须来自你实际执行的 `browser_*` 调用参数，不得凭空编造 selector、URL 或任何操作参数
- 不要在执行前预先填充 pipeline 的 browser_ops —— 先操作、验证、再记录

### 失败恢复

1. 某步操作失败 → 调 `browser_snapshot(mode="simplified")` 确认当前页面状态
2. 元素不存在 → 用 `browser_get_element_by_number` 重新定位，或换用其他选择器
3. 重试 1-2 次后仍失败 → 输出文字告诉用户当前情况，询问如何继续

### 何时询问用户

- 页面有多个相似按钮/链接，不确定选哪个
- 遇到验证码或登录页面
- 用户指令模糊，存在多种合理理解
- 操作连续失败 2 次以上
