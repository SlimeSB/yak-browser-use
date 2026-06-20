## ADDED Requirements

### Requirement: 共享数据存储初始化与生命周期

系统 MUST 在 Agent 或 Preset pipeline 启动时初始化一个运行时内存 dict（shared_store），并在运行结束时自动销毁，不落盘。

#### Scenario: Chat 模式 Agent 初始化 shared_store
- **WHEN** Agent 被创建且未传入 shared_store 参数
- **THEN** Agent 内部自动创建一个空 dict 作为 shared_store
- **AND** 该 dict 通过 ToolContext 传递给所有 tool handler

#### Scenario: Chat 模式 Agent 接收外部 shared_store
- **WHEN** Agent 被创建时传入了 shared_store 参数
- **THEN** Agent 使用传入的 dict 引用（非拷贝），子 Agent 写入对父 Agent 可见

#### Scenario: Preset 模式 pipeline 初始化 shared_store
- **WHEN** run_pipeline 开始执行
- **THEN** 在 while 循环前创建一个空 dict 作为 shared_store
- **AND** 该 dict 传递给 execute_browser_step、execute_goal_step、execute_tool_step

#### Scenario: 运行结束销毁 shared_store
- **WHEN** Agent.run() 或 run_pipeline() 正常结束或异常退出
- **THEN** shared_store 随作用域销毁，不写入磁盘

### Requirement: 参数模板解析 — `${}` 语法

系统 MUST 在 dispatch tool 之前扫描 args 中的 `${path.to.field}` 模板标记，从 shared_store 按路径取值替换。

#### Scenario: 字符串中的模板替换
- **WHEN** args 中包含 `"${captcha_step.data.text}"` 且 shared_store 中存在对应路径
- **THEN** 该字符串被替换为 shared_store 中对应路径的实际值

#### Scenario: 普通字符串不触发替换
- **WHEN** args 中的字符串不包含 `${...}` 模式
- **THEN** 该字符串原样保留

#### Scenario: 路径不存在时的处理
- **WHEN** 模板路径在 shared_store 中不存在
- **THEN** 替换为 `__RESOLVE_FAILED__:<原始路径>`
- **AND** 返回 errors 列表包含该路径，不抛出异常

#### Scenario: dict 中的模板替换
- **WHEN** args 的 dict 值中包含 `{"file": "${table_step.data.path}"}`
- **THEN** 仅替换 dict 值中的模板字符串，dict 结构保持不变

#### Scenario: list 中的模板替换
- **WHEN** args 的 list 值中包含 `["${a}", "${b}"]`
- **THEN** 递归替换 list 中每个元素的模板字符串

#### Scenario: 嵌套引用不支持
- **WHEN** 模板中包含 `${${a}.b}` 形式的嵌套引用
- **THEN** 该模板不被解析，原样保留

#### Scenario: resolve_params 返回值结构
- **WHEN** resolve_params 完成解析
- **THEN** 返回 `(resolved_params, errors)` 元组
- **AND** `resolved_params` 是解析后的 params 副本（原始 params 不被修改）
- **AND** `errors` 是 `[<path>, ...]` 列表，无错误时为空列表

### Requirement: 参数模板解析 — `_source_key` consumer 语法

系统 MUST 支持 `{_source_key: "name"}` 格式的 consumer 引用，在 resolve_params 阶段将整个 dict 替换为 shared_store 中对应 key 的 data 值。

#### Scenario: _source_key 整块替换
- **WHEN** args 中包含 `{"content": {"_source_key": "extracted_table"}}` 且 shared_store 中存在该 key
- **THEN** 该 dict 被替换为 `shared_store["extracted_table"]["data"]` 的值

#### Scenario: _source_key 引用不存在的 key
- **WHEN** `_source_key` 引用的 key 在 shared_store 中不存在
- **THEN** 替换为 `__RESOLVE_FAILED__:_source_key:<key>`
- **AND** 返回 errors 列表包含该 key，不抛出异常

#### Scenario: _source_key 替换后值类型保持
- **WHEN** `_source_key` 引用的 shared_store 值为 dict 类型
- **THEN** 替换后的值保持 dict 类型不变
- **AND** 同理 list、str、int、float、bool、None 均保持原始类型

#### Scenario: _source_key 不入 schema
- **WHEN** LLM 在 tool call 参数中传入 `{_source_key: "name"}`
- **THEN** resolve_params 在 schema 校验之前将其替换为实际数据
- **AND** schema 校验看到的是替换后的合法值

### Requirement: 参数模板解析器接口 — resolve_params

系统 MUST 提供 `resolve_params(params, shared_store)` 函数，返回解析后的副本和 errors 列表，不修改原始 params。

#### Scenario: 函数签名
- **WHEN** 调用 `resolve_params(params, shared_store)` 且 params 和 shared_store 均为有效值
- **THEN** 返回 `(resolved_params, errors)` 元组
- **AND** `resolved_params` 是解析后的 params 副本（原始 params 不受影响）
- **AND** `errors` 是 `[failed_path: str, ...]` 列表，无解析失败时为空列表

#### Scenario: 解析成功时 errors 为空
- **WHEN** params 中所有 `${...}` 和 `_source_key` 引用均已正确解析
- **THEN** errors 返回空列表 `[]`

#### Scenario: 部分路径解析失败时 errors 包含失败路径
- **WHEN** params 中包含 `${bad.path}` 但 shared_store 中不存在对应路径
- **THEN** errors 中包含 `"bad.path"` 字符串
- **AND** resolved_params 中对应位置已被替换为 `__RESOLVE_FAILED__:bad.path`
- **AND** 其他成功解析的路径不受影响

#### Scenario: 无模板引用时返回原始副本
- **WHEN** params 中不含任何 `${...}` 模板或 `_source_key`
- **THEN** resolved_params 是对原始 params 的深拷贝
- **AND** errors 为空列表
- **AND** 原始 params 不变

### Requirement: Chat 模式 Producer 写入

系统 MUST 支持 tool handler 根据 LLM 传入的 `source_key` 参数将结果写入 shared_store。

#### Scenario: 有 source_key 时写入
- **WHEN** LLM 调用 tool 时传了 `source_key` 参数且 dispatch 返回 `{ok, result, ...}`
- **THEN** dispatch 层将结果包装为 `{ok, data}` 写入 `shared_store[source_key]`
- **AND** 包装格式为 `{"ok": result["ok"], "data": result}`

#### Scenario: 无 source_key 时不写入
- **WHEN** LLM 调用 tool 时未传 `source_key` 参数
- **THEN** dispatch 层不将结果写入 shared_store

#### Scenario: source_key 在 dispatch 层的完整处理流程
- **WHEN** LLM 调用 tool 时传了 `source_key` 参数
- **THEN** dispatch 层从 args 中提取 `source_key` 的值并保存
- **AND** 以原始 args 调用 handler（handler 忽略不识别的 `source_key` 参数）
- **AND** handler 返回后将结果包装写入 `shared_store[source_key]`

#### Scenario: shared_store 为 None 时 source_key 写入降级
- **WHEN** LLM 传了 `source_key` 但 shared_store 为 None
- **THEN** 静默跳过写入，不报错，不影响 handler 正常返回

#### Scenario: 解析失败信息反馈给 LLM
- **WHEN** `_execute_single_tool_call` 或 `execute_tool_step` 调用 `resolve_params` 后 errors 列表非空
- **THEN** dispatch 层将 errors 格式化为前置警告字符串 `"⚠️ 参数模板解析失败: [path1, path2]"`
- **AND** 该前置警告拼接到 tool result 的 content 文本开头，与正常结果用 `\n\n` 分隔
- **AND** tool result 的 `ok` 字段仍为 True（不因解析失败而标记工具失败）
- **AND** LLM 看到 `__RESOLVE_FAILED__` 占位符和警告后可自行纠正参数重试

#### Scenario: eval_agent 的 source_key
- **WHEN** LLM 调用 eval_agent 时传了 `source_key` 参数
- **THEN** handler 在子 Agent 完成后将最终结果包装写入 `shared_store[source_key]`

### Requirement: Preset 模式 step 结果自动写入

系统 MUST 在 Preset 模式每个 step 执行完成后，将 step 结果统一包装为 `{ok, data}` 写入 shared_store，key 为 step name。

#### Scenario: browser step 写入
- **WHEN** browser step 执行完成
- **THEN** step 结果包装为 `{ok: status == "completed", data: step_result}` 写入 `shared_store[step_name]`

#### Scenario: tool step 写入
- **WHEN** tool step 执行完成
- **THEN** step 结果包装为 `{ok: status == "completed", data: step_result}` 写入 `shared_store[step_name]`

#### Scenario: goal step 写入
- **WHEN** goal step 执行完成
- **THEN** step 结果包装为 `{ok: status == "completed", data: step_result}` 写入 `shared_store[step_name]`

#### Scenario: Preset 模板引用前序 step
- **WHEN** YAML 中 step B 的 params 包含 `${step_a.data.final_url}`
- **THEN** resolve_params 从 shared_store 中取出 step_a 的 final_url 替换该模板

#### Scenario: tool step resolve 覆盖 registry 和 fallback 两条路径
- **WHEN** Preset 模式 tool step 执行时调用 resolve_params
- **THEN** 解析后的 `core_params` 同时用于 `registry.dispatch()` 和 fallback `execute_tool()` 两条路径
- **AND** 两条路径收到的参数一致，均为模板解析后的实际值

### Requirement: Eval Agent shared_store 继承

系统 MUST 在创建 eval_agent 子 Agent 时，将父 Agent 的 shared_store 引用传递给子 Agent。

#### Scenario: 子 Agent 继承 shared_store
- **WHEN** `_handle_eval_agent` 创建子 Agent
- **THEN** 子 Agent 的 shared_store 参数传入父 Agent 的 shared_store 引用（同一 dict 对象）

#### Scenario: 子 Agent 写入对父 Agent 可见
- **WHEN** 子 Agent 内部的 tool 调用写入了 shared_store
- **THEN** 父 Agent 在子 Agent 返回后能直接读取到该数据

### Requirement: Preset 暂停恢复 shared_store 重建

系统 MUST 在 Preset 模式从暂停状态恢复时，从已完成 step 的 step.json 文件重建 shared_store。

#### Scenario: 从 step.json 重建
- **WHEN** pipeline 从暂停状态恢复执行
- **THEN** 遍历已完成 step 的 step_dir/step.json，读取内容重建 shared_store
- **AND** 每个 step 的 key 为 step name，value 为 `{ok, data}` 包装格式

#### Scenario: 不可序列化值丢失
- **WHEN** step.json 中某些字段无法被 JSON 解析
- **THEN** 这些字段在重建时丢失，不影响其他字段的恢复
