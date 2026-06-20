## Why

当前工具（captcha、eval_agent、file_read、file_write 等）之间的数据只能通过**落盘**或**经 LLM 上下文中转**传递。eval_agent 扒取大表格时几十 KB 数据绕经 LLM 上下文导致 token 暴涨和数据变形风险；captcha 识别结果无法被下一个 tool 以 in-memory 方式直接获取。每个 tool 各自发明传递方式，缺乏统一机制，技术债务持续累积。

现在做是因为：已有 pipeline 场景（Preset 模式）和 chat 场景（Chat 模式）都需要工具间数据传递，且 eval_agent 的大数据绕行问题已经影响实际使用体验。引入统一的数据总线机制能同时解决两类场景，投入产出比高。

## What Changes

- **新增** `engine/_param_resolver.py`：参数模板解析器，支持 `${path.to.field}` 和 `{_source_key: "name"}` 两种 consumer 语法
- **新增** `ToolContext.shared_store` 字段：运行时内存 dict，作为工具间数据总线
- **新增** `eval_agent` schema 的 `source_key` 参数：LLM 可指定结果存入 shared_store 的 key
- **修改** `Agent.__init__`：新增 `shared_store` 参数，初始化并透传至工具执行链
- **修改** `execute_tool_calls_sequential` / `_execute_single_tool_call`：dispatch 前 resolve 参数模板，dispatch 后按 source_key 写入结果
- **修改** `_handle_eval_agent`：子 Agent 继承父 Agent 的 shared_store 引用
- **修改** `execute_browser_step` / `execute_tool_step` / `execute_goal_step`：新增 `shared_store` 参数
- **修改** `runner_preset.py`：while 循环前创建 shared_store，三种 step 类型执行后统一写入，支持暂停恢复时从 step.json 重建

## Capabilities

### New Capabilities
- `tool-data-bus`: 工具间运行时内存数据总线，支持 Chat 和 Preset 两种模式下的跨工具数据传递，不经过 LLM 上下文或磁盘

### Modified Capabilities
<!-- 无已有能力被修改 -->

## Impact

- **代码**：`tools/registry.py`、`engine/_harness/conversation_loop.py`、`engine/_harness/tool_executor.py`、`engine/runner_preset.py`、`engine/executor.py`，新增 `engine/_param_resolver.py`，合计约 112 行
- **接口**：`Agent.__init__`、`execute_tool_calls_sequential`、`_execute_single_tool_call`、`execute_browser_step`、`execute_tool_step`、`execute_goal_step` 各新增一个可选参数 `shared_store`，均为向后兼容
- **依赖**：无新增外部依赖，纯内存操作
- **系统**：Chat 模式 LLM 需学习 `source_key` / `_source_key` 约定（通过 system prompt 和 schema description），Preset 模式 YAML 编写者需学习 `${step_name.data.field}` 模板语法
- **风险**：暂停恢复时 shared_store 从 step.json 重建，不可序列化值会丢失（约束为仅存 JSON 可序列化类型）
