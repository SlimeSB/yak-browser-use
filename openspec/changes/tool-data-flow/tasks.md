## 1. 基础组件

- [ ] 1.1 新建 `engine/_param_resolver.py`：实现 `resolve_params(params, shared_store)` 函数，支持 `${path.to.field}` 模板替换、`{_source_key: "name"}` 整块替换、dict/list 递归扫描、路径不存在时返回 `__RESOLVE_FAILED__:<path>` 和 errors 列表

- [ ] 1.2 `tools/registry.py`：ToolContext dataclass 新增 `shared_store: dict | None = None` 字段

- [ ] 1.3 `tools/registry.py`：eval_agent schema 新增可选 `source_key` 参数（type: string, description 说明用途）

- [ ] 1.4 新建 `tests/test_param_resolver.py`：单元测试 cover 递归 dict/list/string 替换、`_source_key` 替换、路径不存在返回 errors、深拷贝不修改原始、空 shared_store、边界值（None/空字符串/嵌套 5 层）

## 2. Chat 模式传递链

- [ ] 2.1 `engine/_harness/conversation_loop.py`：Agent.__init__ 新增 `shared_store` 参数（默认 None），初始化 `self._shared_store = shared_store or {}`

- [ ] 2.2 `engine/_harness/conversation_loop.py`：`run_conversation_loop` 新增 `shared_store` 参数，透传给 Agent

- [ ] 2.3 `engine/_harness/tool_executor.py`：`execute_tool_calls_sequential` 新增 `shared_store` 参数，透传给 `_execute_single_tool_call`

- [ ] 2.4 `engine/_harness/tool_executor.py`：`_execute_single_tool_call` 新增 `shared_store` 参数；创建 RegistryToolContext 时传入 shared_store；dispatch 前调用 `resolve_params(fn_args, shared_store)`；dispatch 后若 fn_args 含 `source_key` 则写入 `shared_store[source_key] = {"ok": result["ok"], "data": result}`

- [ ] 2.5 `engine/_harness/tool_executor.py`：`_handle_eval_agent` 新增 `shared_store` 形参；创建子 Agent 时传入 `shared_store=shared_store`；返回前若 fn_args 含 `source_key` 则将最终结果包装写入 `shared_store[source_key]`
    - **说明**：eval_agent 有 source_key 时，2.4 的通用写入逻辑应跳过 eval_agent（因为 eval_agent handler 返回的是摘要文本而非子 Agent 完整结果）。通用写入 `_execute_single_tool_call` 中加条件：若 tool name 为 `eval_agent` 且 args 含 source_key，不执行通用写入，由 2.5 专用逻辑处理。

- [ ] 2.6 `engine/_harness/tool_executor.py`：`_execute_single_tool_call` 和 `engine/executor.py` `execute_tool_step` 中，resolve_params 返回的 errors 非空时，将 errors 格式化为 `"⚠️ 参数模板解析失败: [path1, path2]"` 前置到 tool result content 文本，与正常结果用 `\n\n` 分隔。ok 字段保持 True。

## 3. Preset 模式集成

- [ ] 3.1 `engine/executor.py`：`execute_tool_step` 新增 `shared_store` 参数（默认 None），创建 RegistryToolContext 时传入 shared_store，dispatch 前调用 `resolve_params(core_params, shared_store)`

- [ ] 3.2 `engine/executor.py`：`execute_browser_step` 新增 `shared_store` 参数（默认 None），在执行各 browser_ops 前调用 `resolve_params` 解析 op 值（如 `${step_a.data.url}` 作为 goto 目标）。op 结构为 `[{op_type: value, ...}, ...]`，需递归解析每个 op dict 中的 string 值。

- [ ] 3.3 `engine/executor.py`：`execute_goal_step` 新增 `shared_store` 参数（默认 None），用于透传至 swimlane agent 的 preset_loop 调用链中

- [ ] 3.4 `engine/runner_preset.py`：while 循环前创建 `shared_store = {}`；三种 step 类型调用处传入 shared_store；每个 step 执行后统一写入 `shared_store[step_def["name"]] = {"ok": step_result["status"] == "completed", "data": step_result}`

- [ ] 3.5 `engine/runner_preset.py`：暂停恢复逻辑中，从已完成 step 的 `step_dir/step.json` 重建 shared_store

## 4. LLM 引导

- [ ] 4.1 在 consumer tool（file_write 等）的 schema description 中提示 `_source_key` 用法

- [ ] 4.2 在 system prompt（guidance/tool_strategy）中添加 shared_store 使用说明，引导 LLM 使用 `source_key` / `_source_key`

## 5. 验证

- [ ] 5.1 验证 Chat 模式：Agent 创建 shared_store → tool A 写入 → tool B 通过 `_source_key` 引用 → 数据正确传递

- [ ] 5.2 验证 Preset 模式：pipeline YAML 中 step B 通过 `${step_a.data.field}` 引用 step A 结果 → 模板正确解析

- [ ] 5.3 验证 eval_agent 继承：父 Agent 调用 eval_agent(source_key="table") → 子 Agent 内部写入 shared_store → 父 Agent 后续 tool 通过 `_source_key` 读取

- [ ] 5.4 验证解析失败处理：模板路径不存在时返回 `__RESOLVE_FAILED__` 而非崩溃；检查 tool result 文本前置了 `⚠️` 警告

- [ ] 5.5 验证向后兼容：不传 shared_store 时所有已有功能不受影响
