## MODIFIED Requirements

### Requirement: 预执行钩子
`browser_get_element_by_number` 的 scratchpad 查询 MUST 在 `_execute_single_tool_call` 路由层实现，在调 `execute_browser_op` 之前 short-circuit。

#### Scenario: 预执行钩子命中 scratchpad
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 且 scratchpad 中有缓存的 `element_map`
- **THEN** `_execute_single_tool_call` 在 `browser_` 分支中检测到 `op_type == "get_element_by_number"`
- **AND** 从 `scratchpad.get().element_map` 中查找 `@e5` 对应的 CSS selector
- **AND** 从 `scratchpad.get().elements` 列表中查找完整元素信息
- **AND** 直接返回 `{"ok": True, "result": {ref, tag, type, text, selector}}`
- **AND** 不调用 `execute_browser_op()`，不触发 CDP

#### Scenario: 预执行钩子未命中，回退到 CDP
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 但 scratchpad 中无缓存或找不到该 ref
- **THEN** 回退到 `execute_browser_op("get_element_by_number", fn_args, cdp_helpers)`
- **AND** 走正常的 CDP `_element_map` 查找路径（`cdp_helpers.get_element_by_index(ref)`）
- **AND** 这条路径主要服务 preset 模式（preset 不经过 chat 的 conversation_loop，scratchpad 可能为空）

### Requirement: 两条查找路径
`browser_get_element_by_number` MUST 支持两条查找路径，各自服务不同场景。

#### Scenario: 路径 A — scratchpad 缓存（chat 模式主路径）
- **WHEN** chat 模式下 LLM 先调 `browser_snapshot(interactive)` 再调 `browser_get_element_by_number`
- **THEN** 预执行钩子从 scratchpad 的 `element_map` 命中
- **AND** 不触发 CDP 调用，零延迟返回

#### Scenario: 路径 B — CDP _element_map（preset 模式 / 回退路径）
- **WHEN** preset 模式或 scratchpad 无缓存时调用 `browser_get_element_by_number`
- **THEN** 回退到 `execute_browser_op` → `cdp_helpers.get_element_by_index(ref)`
- **AND** 从 CDP 的 `_element_map`（由 `add_dom_highlights()` 维护）查找

### Requirement: scratchpad 优先查找
`browser_get_element_by_number(ref)` MUST 优先从 scratchpad 的 `element_map` 查找元素，无缓存时回退到 CDP 的 `_element_map`。

#### Scenario: scratchpad 有缓存时直接查找
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 且 scratchpad 中有缓存的 `element_map`
- **THEN** 从 `scratchpad.get().element_map` 中查找 `@e5` 对应的 CSS selector
- **AND** 不触发 CDP 调用
- **AND** 返回元素的完整信息（ref、tag、type、text、selector）

#### Scenario: scratchpad 无缓存时回退到 CDP
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 但 scratchpad 中无缓存
- **THEN** 回退到 `cdp_helpers.get_element_by_index("@e5")` 从 `_element_map` 查找
- **AND** `_element_map` 由 `add_dom_highlights()` 在 goto/click/fill 后自动填充

#### Scenario: 两处都无缓存
- **WHEN** scratchpad 和 CDP `_element_map` 都找不到 `@e5`
- **THEN** 返回错误信息 `{"ref": "@e5", "error": "元素引用 @e5 未找到"}`

#### Scenario: scratchpad element_map 自动构建
- **WHEN** `browser_snapshot(mode="interactive")` 执行后 scratchpad 被更新
- **THEN** `scratchpad.store()` 自动从 elements 列表构建 `element_map`
- **AND** `element_map` 格式为 `{"@e1": "button#submit", "@e2": "input[name='q']", ...}`

### Requirement: add_dom_highlights 后同步 scratchpad
`add_dom_highlights()` 在 goto/click/fill 后自动触发并重建 CDP 的 `_element_map`。编排层 MUST 在此时同步更新 scratchpad 的 `element_map`，避免两个 map 不一致导致 scratchpad 缓存命中率下降。

#### Scenario: goto 后同步
- **WHEN** `browser_goto` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 编排层从 `add_dom_highlights()` 返回值中获取 `element_map`（`{ref: {ref, tag, type, text, selector, ...}}` 嵌套结构）
- **AND** 提取每个 ref 的 `selector` 字段，构建扁平 map `{ref: selector}`
- **AND** 调用 `scratchpad.sync_element_map(elements)` 更新 scratchpad 的 `element_map`
- **AND** 不覆盖 scratchpad 的其他字段（url、title、raw_html 等保持不变，直到下次 snapshot）

#### Scenario: click 后同步
- **WHEN** `browser_click` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 同样同步 scratchpad 的 `element_map`

#### Scenario: fill 后同步
- **WHEN** `browser_fill` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 同样同步 scratchpad 的 `element_map`

#### Scenario: 同步后两个 map 一致
- **WHEN** scratchpad 的 `element_map` 被同步更新
- **THEN** 后续 `browser_get_element_by_number` 调用优先命中 scratchpad 缓存
- **AND** 不再需要频繁回退到 CDP `_element_map`
