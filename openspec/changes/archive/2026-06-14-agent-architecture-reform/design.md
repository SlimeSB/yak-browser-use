## 背景

当前系统使用两层 Agent 架构：主 LLM（`conversation_loop`）通过 `goal_run` 工具委托复杂任务给 browser-use 子 Agent。子 Agent 拥有独立的 LLM 实例和浏览器连接，运行时主循环阻塞等待。这种架构在以下场景中暴露出问题：

- **子 Agent 无法与用户交互**：遇到不确定情况（如多个相似按钮、验证码、登录确认）只能猜测或失败
- **自学习路径断裂**：子 Agent 的操作记录通过 `_extract_learned_ops`（stub）提取，不会自动写入 pipeline YAML
- **上下文膨胀**：每次 `browser_snapshot()` 返回的 HTML（可达 15KB）和截图 base64 全部进入 messages 永久保留

browser-use Agent 的核心能力（`capture_snapshot_interactive`、`add_dom_highlights`、`get_element_by_index`）已实现在 `cdp/helpers.py` 中作为纯工具函数。去掉 browser-use 依赖的条件已经成熟。

**相关方**：chat 模式用户（需要交互式任务执行）、preset 模式用户（需要程序化验收）、prompt 维护者。

## 目标 / 非目标

**目标：**
- 消除两层 Agent 架构，主 LLM 通过 `todo` + `browser_*` 工具自主管理复杂任务
- 主 LLM 遇到不确定情况时能输出文字直接问用户
- 重数据（HTML、截图、@eN 列表）不进 messages，通过 scratchpad 隔离
- `goal_run` 保留为模式切换信号，不破坏现有 tool schema 兼容性
- 为 preset 模式提供 `check` 程序化验收基础设施

**非目标：**
- 不实现视觉模型接入（`browser_vision` 预留接口，首版不做）
- 不处理 todo 步骤导致的 messages 线性增长（量级远小于重数据，后续观测再处理）
- 不实现 scratchpad 文件持久化（首版纯内存，后续按需加）
- 不实现 preset 模式下的完整自动化验收（阶段 4 仅 placeholder）

## 关键决策

### 决策 1：去掉子 Agent，而非改造子 Agent

**选择**：`goal_run` 不再 spawn browser-use Agent，改为返回模式切换提示文本。

**备选方案**：在 browser-use Agent 中注入 `clarify` 工具，通过共享状态/异常穿透实现用户交互。

**取舍原因**：
- 注入 `clarify` 需要修改 browser-use 库或通过 monkey-patch，维护成本高
- 共享状态穿透在异步阻塞场景下复杂度高，容易引入竞态
- browser-use 的核心能力已是 CDP 层纯函数，去掉子 Agent 不损失功能
- 去掉子 Agent 后主 LLM 可以直接控制每一步，自学习路径自然打通

### 决策 2：scratchpad 在 tool_executor 编排层统一处理

**选择**：CDP 层（`cdp/helpers.py`）不感知 scratchpad，全部过滤逻辑集中在 `tool_executor.py`。CDP 层仅做一处小改：`capture_snapshot()` 和 `capture_snapshot_interactive()` 返回值增加 `url` 和 `title` 字段（一次 `Runtime.evaluate` 同时获取 `window.location.href` + `document.title`，不增加 CDP 往返）。

**备选方案**：编排层在过滤时额外调一次 CDP 获取 url/title。

**取舍原因**：
- CDP helper 返回值更丰富是合理的职责（它本来就负责"描述当前页面状态"）
- 编排层额外调 CDP 会增加一次往返，且需要访问 cdp_helpers 内部方法
- CDP 层仍然不感知 scratchpad 的存在，只是返回值字段更完整

### 决策 3：按 mode 分支而非双层探测

**选择**：编排层过滤代码按 `fn_name` + `mode` 显式分支处理。

**备选方案**：同时探测 `result_dict["result"]`（嵌套）和 `result_dict`（顶层）两层。

**取舍原因**：
- 不同 mode 的数据结构差异大：interactive 的 elements 在嵌套层，full 的 html/screenshot 在顶层
- 双层探测可能误判（如 interactive 结果恰好含 `html` 字段）
- 显式分支更清晰，后续维护者容易理解数据流向
- interactive 模式需额外处理降级路径：`capture_snapshot_interactive()` 降级时 `**full` 展开，`screenshot_base64` 和 `html` 进入 `result["result"]` 嵌套层。编排层检测 `degraded: true` 标记后同样摘除这些重数据

### 决策 4：scratchpad 同时存 elements 列表 + element_map 字典

**选择**：`ScratchpadRecord` 同时包含 `elements: list[dict]` 和 `element_map: dict[str, str]`。

**原因**：
- `browser_get_element_by_number` 需要 ref→selector 快速查找，`element_map` 直接满足
- `elements` 列表保留完整元素信息（tag、type、text），供 LLM 摘要和未来扩展使用
- 两者在 `store()` 时从同一份 elements 数据构建，无额外 CDP 调用

### 决策 5：`browser_get_element_by_number` 回退路径 + 双 map 同步

**选择**：优先从 scratchpad 的 `element_map` 查找，无缓存时回退到 `cdp_helpers.get_element_by_index()`。同时，`add_dom_highlights()` 在 goto/click/fill 后触发时，编排层同步更新 scratchpad 的 `element_map`。

**原因**：
- `_element_map` 由 `add_dom_highlights()` 在 goto/click/fill 后自动填充，即使没有 scratchpad 缓存回退路径仍可用
- 但如果不主动同步，scratchpad 的 `element_map` 只在 `browser_snapshot(interactive)` 时更新，中间窗口期两个 map 不一致，导致频繁回退到 CDP
- 编排层在 `add_dom_highlights()` 后调用 `scratchpad.sync_element_map()`，保持两个 map 一致，scratchpad 缓存命中率最大化

### 决策 6：`run_check()` 由 runner_preset 调用

**选择**：`run_check()` 由 `runner_preset.py` 在 step executor 返回后调用，而非在 StepMachine 内部。

**原因**：
- StepMachine 当前没有 step 完成回调/hook 机制，加回调会增加 StepMachine 的复杂度
- `runner_preset.py` 已经是 step 执行的编排者，它依次调用 executor、检查结果、决定下一步——加 `run_check()` 是自然的扩展
- `check` 验收对 browser/tool/goal 三种 step 类型都适用，在 runner_preset 层统一处理避免重复

## 风险 / 权衡

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 去掉子 Agent 后复杂任务 LLM 自主完成率下降 | 用户体验 | goal-execution skill 提供详细指引；保留 `goal_run` tool schema 作为模式切换信号 |
| scratchpad 纯内存实现在进程重启后丢失 | 会话中断后需重新 snapshot | 首版可接受；后续按需加文件持久化 |
| `browser_snapshot` 默认 mode 从 `full` 改为 `interactive` | 现有依赖 full 模式默认行为的调用方可能受影响 | chat mode 下 LLM 可显式指定 `mode="full"`；preset pipeline YAML 中 snapshot op 的 mode 不受影响 |
| 删除 `run_goal_step` 中 browser-use 相关代码 | 如果有其他模块间接引用 browser-use 可能导入失败 | 保留 browser-use 作为可选依赖；仅删除 agent.py 中的直接引用 |
| budget pause/resume 清理不完整 | 预算计数异常 | 明确只删除 `is_goal` 相关逻辑，CDP 重连的 pause 保留 |

## 迁移计划

1. **阶段 1**：新建 scratchpad 模块 + 编排层过滤 + 工具增强（不改行为，只加重数据隔离）
2. **阶段 2**：去掉子 Agent（agent.py / executor.py 简化）+ goal_run 改造 + budget 清理
3. **阶段 3**：prompt 更新 + goal-execution skill + orphan prompts 清理
4. **阶段 4**：preset 模式适配（placeholder）
5. **阶段 5**：全量测试验证

**回滚策略**：每个阶段独立可回滚。阶段 1 只加重数据隔离不改变行为；阶段 2 如果出问题可以恢复 `run_goal_step` 的 browser-use 实现。

**兼容性**：
- `goal_run` tool schema 保留，LLM 仍可调用，只是后端行为从 spawn Agent 变为返回提示文本
- `browser_snapshot` 新增 `mode` 参数带默认值，不传 mode 的调用方行为从 full 变为 interactive（chat mode 下）
- pipeline YAML 中 snapshot op 的 mode 显式指定，不受默认值变更影响

## 待确认问题

- ~~browser-use 库是否被 engine/agent.py 以外的模块引用？~~ → 保留 browser-use 为可选依赖，仅删除 agent.py 中的直接 import；如其他模块引用则在阶段 2 实施时一并清理
- ~~test_harness_tools.py 中的工具数量断言具体值是多少？~~ → 工具数量不变（goal_run 保留但行为变化），阶段 5 实施时确认无需修改
- ~~preset 模式下的 goal step fallback 策略~~ → goal step stub 化后返回 placeholder 结果并跳过验收；若 pipeline YAML 包含 goal step，runner_preset 直接返回 `{"ok": true, "result": "Goal step skipped (stub)", "skipped": true}`，不尝试回退到 Agent 模式
