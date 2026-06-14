## MODIFIED Requirements

### Requirement: browser_source cached 参数
`browser_source` 工具的 schema MUST 新增可选的 `cached` 参数，支持从 scratchpad 读取缓存的 HTML。

#### Scenario: 默认从 CDP 获取
- **WHEN** LLM 调用 `browser_source()` 不传 cached 参数或 `cached=False`
- **THEN** 调用 `cdp_helpers.get_page_html()` 从 CDP 获取最新 HTML
- **AND** HTML 内容写入 scratchpad
- **AND** messages 中只返回 `{length: <字节数>}`

#### Scenario: cached=True 从 scratchpad 读取
- **WHEN** LLM 调用 `browser_source(cached=True)` 且 scratchpad 中有缓存的 HTML
- **THEN** 从 scratchpad 读取 `raw_html` 字段
- **AND** 不触发 CDP 调用
- **AND** 返回 `{length: <字节数>, cached: true}`

#### Scenario: cached=True 但无缓存
- **WHEN** LLM 调用 `browser_source(cached=True)` 但 scratchpad 中无缓存的 HTML
- **THEN** 回退到 CDP 获取
- **AND** 返回 `{length: <字节数>, cached: false, note: "无缓存，已从 CDP 获取"}`

### Requirement: browser_source 预执行钩子
`browser_source` 的 cached 查询 MUST 在 `_execute_single_tool_call` 路由层实现，在调 `execute_browser_op` 之前 short-circuit。

#### Scenario: cached=True 命中缓存
- **WHEN** LLM 调用 `browser_source(cached=True)` 且 scratchpad 中有缓存的 HTML
- **THEN** `_execute_single_tool_call` 在 `browser_` 分支中检测到 `op_type == "source" and fn_args.get("cached")`
- **AND** 从 `scratchpad.get().raw_html` 读取 HTML
- **AND** 直接返回 `{"ok": True, "result": {"length": len(html), "cached": true}}`
- **AND** 不调用 `execute_browser_op()`，不触发 CDP

#### Scenario: cached=True 未命中缓存
- **WHEN** LLM 调用 `browser_source(cached=True)` 但 scratchpad 中无缓存
- **THEN** 回退到 `execute_browser_op("source", fn_args, cdp_helpers)`
- **AND** 走正常的 CDP 获取 + 后置过滤流程

#### Scenario: cached=False 或默认
- **WHEN** LLM 调用 `browser_source()` 不传 cached 或 `cached=False`
- **THEN** 预执行钩子不拦截，正常走 `execute_browser_op`
- **AND** 后置过滤将 HTML 写入 scratchpad，messages 只留 `{length}`

### Requirement: browser_source 重数据隔离
`browser_source()` 的返回结果 MUST 经过编排层过滤，完整 HTML 不进 messages。

#### Scenario: HTML 写入 scratchpad
- **WHEN** `browser_source()` 成功获取 HTML
- **THEN** 编排层将 HTML 从 `result_dict` 顶层移除
- **AND** HTML 写入 `scratchpad.raw_html`
- **AND** `result_dict["result"]` 替换为 `{length: <字节数>}`

#### Scenario: HTML 获取失败
- **WHEN** `browser_source()` 获取 HTML 失败
- **THEN** 不触发 scratchpad 写入
- **AND** 错误信息正常进入 messages
