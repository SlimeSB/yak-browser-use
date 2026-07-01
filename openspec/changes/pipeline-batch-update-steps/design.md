## 背景

`pipeline_update_step` 负责在 LLM chat 中动态修改 pipeline.yaml 中的单个 step。当前实现：每次调用 → 加载 pipeline.yaml → 定位 step → 更新 → 验证 → 写盘 → push edit event。当 batch 更新 N 个 step 时，重复 N 次全流程，效率低且 UI 收到 N 次事件。

核心改动在 `pipeline_tools.py` 中的 `pipeline_update_step` 函数和 registry 中的 schema。

## 目标 / 非目标

**目标：**
- `pipeline_update_step` 支持字典格式批量更新多个 step
- 向后兼容旧的 `step_name` + `updates` 调用方式
- 文件 IO 一次完成（一次加载、批量修改、一次写盘）
- 批量错误收集：尝试全部 step 更新后统一返回失败信息

**非目标：**
- 不新增独立工具（如 `pipeline_batch_update_steps`），直接改造现有工具
- 不改变 pipeline.yaml 文件格式
- 不改变 `pipeline_compile` 等其他 pipeline 相关工具

## 关键决策

**为什么改造现有工具而不是新增：**
- `pipeline_update_step` 本身就是为 LLM chat 场景设计
- 一个工具名比两个更易理解（LLM 不会困惑"用哪个"）
- 字典格式天然兼容：单步更新就是 `{"step_name": {...}}`

**接口设计：**
- 主参数改为 `steps_updates: dict` — key 是 step name，value 是 updates dict
- 保留 `step_name` 和 `updates` 两个旧参数，检测到时自动组装为 `{step_name: updates}`
- `required` 从 `["pipeline_name", "step_name", "updates"]` 改为 `["pipeline_name"]`（通过 schema 描述引导）

**批量错误处理：**
- 遍历所有 `steps_updates`，收集每个 step 的更新错误
- 如果有任何失败，返回 `{"ok": False, "error": "[step_1] xxx\n[step_2] yyy"}`
- 如果全部成功，执行写盘
- 注意：`_get_store().update_step()` 修改的是内存中的 Pydantic 模型，写盘前如果某步失败可以直接跳过写盘

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| LLM 混用新旧参数（如同时传 `steps_updates` 和 `step_name`） | 逻辑检测：优先 `steps_updates`，忽略旧参数 |
| 某步更新失败导致全部不写盘 | 行为可接受——YAML 在内存修改，不写盘=回滚 |
| schema `required` 改松后 LLM 可能只传 `pipeline_name` | description 中明确"必须传 steps_updates 或 step_name+updates" |

## 迁移计划

1. 修改 `pipeline_tools.py` 中的 `pipeline_update_step` 函数签名和逻辑
2. 修改 `registry.py` 中 `_PIPELINE_SCHEMAS["pipeline_update_step"]` 的 schema
3. 运行相关测试
4. 无需数据迁移（纯接口行为变更）

## 待确认问题

无
