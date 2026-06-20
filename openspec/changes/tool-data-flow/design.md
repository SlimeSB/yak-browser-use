## 背景

当前工具（captcha、eval_agent、file_read、file_write 等）之间的数据只能通过落盘或经 LLM 上下文中转传递。eval_agent 扒取大表格时几十 KB 数据绕经 LLM 上下文导致 token 暴涨；captcha 识别结果无法被下一个 tool 以 in-memory 方式直接获取。每个 tool 各自发明传递方式，缺乏统一机制。

现有架构中：
- **Chat 模式**：`Agent._step()` → `execute_tool_calls_sequential()` → `_execute_single_tool_call()` → `RegistryToolContext` → `registry.dispatch()`。ToolContext 有 7 个字段（cdp_helpers、tools_dir、pipeline_name、budget、llm_call、interrupt_check、stream_callback），无数据共享能力。
- **Preset 模式**：`run_pipeline()` 循环中按 step_type 分发到 `execute_browser_step` / `execute_goal_step` / `execute_tool_step`，step 结果写入 `step_dir/step.json` 文件，后续 step 通过 `_resolve_input_files()` 按路径约定读取前序 step 的输出文件。无运行时内存数据传递。
- **eval_agent**：`_handle_eval_agent` 创建子 Agent 时传入 cdp_helpers、budget 等依赖，但不共享任何数据存储。

约束：不引入新外部依赖，不改变已有 tool handler 签名，Chat 和 Preset 两种模式共用同一套机制。

## 目标 / 非目标

**目标：**
- 提供统一的工具间运行时内存数据总线（shared_store），Chat 和 Preset 模式通用
- 支持参数模板解析（`${path.to.field}` 和 `{_source_key: "name"}`），让 consumer tool 引用 producer tool 的结果
- eval_agent 子 Agent 继承父 Agent 的 shared_store，子 Agent 内部写入对父 Agent 可见
- Preset 暂停恢复时从 step.json 重建 shared_store

**非目标：**
- 不实现持久化存储（那是 params.json 的职责）
- 不改造已有 tool handler 内部逻辑（resolve_params 在 dispatch 之前完成，handler 无感知）
- 不支持嵌套模板引用（`${${a}.b}`）
- 不改变 LLM function calling 的 schema 校验流程

## 关键决策

### 1. 包装层用 `data` 而非 `result`

写入 shared_store 时统一包装为 `{ok, data}`：

```python
shared_store[key] = {
    "ok": step_result["status"] == "completed",
    "data": step_result,
}
```

**原因：** tool handler 返回 `{ok, result: {...}}`，step_result 本身也包含 `result` 字段。如果包装层也用 `result`，路径变成 `${step.result.result.text}`——两层 `result` 语义不同但同名，极易混淆。用 `data` 后路径为 `${step.data.result.text}`，语义清晰。

### 2. 双 consumer 语法：`${}` 和 `_source_key`

| 语法 | 使用场景 | 谁写 | 示例 |
|------|---------|------|------|
| `${step_name.data.field}` | Preset YAML | 人类编写 pipeline | `content: "${captcha_step.data.text}"` |
| `{_source_key: "name"}` | Chat mode | LLM 调用 tool | `content: {_source_key: "extracted_table"}` |

**原因：** Preset 模式 step name 是固定的，人类可以直接写模板字符串。Chat 模式 LLM 调用 tool 时，`_source_key` 作为 dict 值更自然（LLM 传 JSON 参数），且 `_source_key` 不入 schema，在 resolve_params 阶段被替换，对 schema 校验透明。

实现统一：`_source_key` 内部转为 `${key.data}` 走同一路径解析逻辑。

### 3. Chat 模式用显式 source_key，不用自动 key

Chat 模式 Producer 侧由 LLM 传 `source_key` 参数指定 key，而非自动用 tool name 作为 key。

**原因：** 同一 tool 可被多次调用（如 3 次 browser_snapshot），自动 key 需要计数器，LLM 难以预测 key 名。显式指定更可靠。无 `source_key` 时不写入 store，避免无用数据堆积。

### 4. resolve_params 返回副本，不修改原始参数

`resolve_params(params, shared_store)` 在 dispatch 前执行，**返回解析后的副本**，原始 params dict 不变。dispatch 层将返回的副本传给 handler。

**原因：** 返回副本而非原地修改的考量：
- **函数纯度** — resolve_params 无副作用，同一输入始终返回同一输出，容易测试和推理
- **避免隐式耦合** — 如果 handler 引用的 params 在 dispatch 过程中被偷偷改了，debug 困难。副本保证 handler 看到的 params 只来自一次明确的 resolve
- **schema 校验透明** — `_source_key` 不在 schema 中，resolve 时替换到副本里，原始 LLM 传来的 params 保留完整记录，便于审计和日志

### 5. 不持久化，暂停恢复从 step.json 重建

shared_store 是运行时内存 dict，不写磁盘。暂停恢复时从已完成 step 的 `step_dir/step.json` 重建。

**原因：** 持久化是 params.json 的职责。shared_store 存结构化数据（dict/list/str/int/float/bool/None），均为 JSON 可序列化类型，从 step.json 重建覆盖所有场景。约束 shared_store 值类型避免不可序列化数据丢失。

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| `_source_key` 不入 schema，LLM 可能遗忘此约定 | 在 consumer tool 的 schema description 中提示；system prompt 中说明用法 |
| 模板路径拼写错误导致解析失败 | 失败时替换为 `__RESOLVE_FAILED__:<path>`，不 raise，LLM 可自纠正 |
| Preset 暂停恢复时 shared_store 重建不完整 | 约束值为 JSON 可序列化类型；文档注明限制 |
| 子 Agent 共享父 Agent store 可能意外覆盖 | 子 Agent 只能通过 `source_key` 写入（Chat 模式），key 由父 Agent 的 LLM 控制 |
| 传递链变长，函数签名膨胀 | 所有新增参数均为可选（默认 None），向后兼容 |

## 迁移计划

1. **Phase 1**：新建 `_param_resolver.py`，修改 ToolContext、Agent、tool_executor 传递链，Chat 模式先上线
2. **Phase 2**：修改 runner_preset.py 和 executor.py，Preset 模式上线
3. **Phase 3**：更新 system prompt 和 tool schema description，引导 LLM 使用 `source_key` / `_source_key`
4. **回滚**：所有新增参数均为可选（默认 None），移除 shared_store 创建和 resolve_params 调用即可回退到原有行为，不影响已有功能

## 待确认问题

- `source_key` 是否只加到 `eval_agent` schema，还是也加到 `captcha`、`file_read` 等可能作为 producer 的工具？建议先只加 `eval_agent`，按需扩展。
- system prompt 中 `_source_key` 约定的措辞需要与 prompt 维护者对齐。
