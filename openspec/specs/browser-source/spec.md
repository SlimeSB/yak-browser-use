## MODIFIED Requirements

### Requirement: browser_source 底层实现
`browser_source` 工具的底层实现 MUST 从 CDP 方法改为 Playwright `page.content()`。

#### Scenario: 获取页面源码（不缓存）
- **WHEN** LLM 调用 `browser_source()` 不传 `cached` 或 `cached=false`
- **THEN** executor 调用 `bridge.source()`（内部通过 `page.content()` 获取完整 HTML）
- **AND** 返回 HTML 内容和长度

#### Scenario: 使用缓存
- **WHEN** LLM 调用 `browser_source(cached=true)`
- **THEN** executor 调用 `bridge.get_page_html(cached=True)` 从 `bridge._element_map` 读取缓存
- **AND** 缓存不存在时 fallback 到 `bridge.source()`

### Requirement: browser_source 缓存路径
`browser_source(cached=true)` 的缓存路径 MUST 简化为仅依赖 `bridge.get_page_html(cached=True)` 内部缓存，不再先查询 scratchpad。

移除 `_try_scratchpad_source_read()` 函数及其在 `_execute_single_tool_call` 中的调用。`browser_source(cached=true)` 直接走 registry dispatch → `execute_browser_op("source", ...)` → `bridge.get_page_html(cached=True)`。

#### Scenario: 使用 bridge 缓存
- **WHEN** LLM 调用 `browser_source(cached=true)` 且 bridge 内部 `_element_map` 已有缓存的 HTML
- **THEN** `bridge.get_page_html(cached=True)` 直接返回缓存的 HTML
- **AND** 不检查 scratchpad
- **AND** 不调用 `_try_scratchpad_source_read()`

#### Scenario: 缓存未命中时从 CDP 获取
- **WHEN** LLM 调用 `browser_source(cached=true)` 且 bridge 内部无缓存
- **THEN** `bridge.get_page_html(cached=True)` 调用 `page.content()` 获取 HTML
- **AND** 结果存入 `bridge._element_map["raw_html"]` 供后续缓存使用

### Requirement: browser_source 重数据剥离
`_apply_heavy_data_filter` 中 browser_source 分支 MUST 移除 scratchpad 写入逻辑和 `cached` 标记的短路检查，仅保留 HTML 剥离。

删除 `_try_scratchpad_source_read` 后，`result_payload.get("cached")` 分支永远不命中，一并移除。HTML 剥离后 `result_dict["result"]` 仅保留 `{length: N}`；若 LLM 传了 `cached=true` 但 bridge 无缓存，追加 `cached: false` 和提示说明。

#### Scenario: 剥离 HTML 但不写 scratchpad
- **WHEN** `_apply_heavy_data_filter` 处理 `browser_source` 结果
- **THEN** 从 `result_dict` 中移除 `html` 字段
- **AND** `result_dict["result"]` 仅保留 `{length: N}` 信息
- **AND** 不调用 `scratchpad.store_raw_html()`
- **AND** 不检查 `result_payload.get("cached")`（已是死代码）

#### Scenario: LLM 请求缓存但 bridge 无缓存
- **WHEN** LLM 调用 `browser_source(cached=true)` 且 bridge 内部缓存未命中
- **THEN** `result_dict["result"]` 为 `{length: N, cached: false, note: "无缓存，已从 CDP 获取"}`
