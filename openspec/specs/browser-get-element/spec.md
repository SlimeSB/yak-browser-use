## MODIFIED Requirements

### Requirement: 预执行钩子
`browser_get_element_by_number` 的 scratchpad 查询 MUST 在 `_execute_single_tool_call` 路由层实现，在调 `execute_browser_op` 之前 short-circuit。

#### Scenario: 预执行钩子命中 scratchpad
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 或 `browser_get_element_by_number(ref="@e_12345")` 且 scratchpad 中有缓存的 `element_map`
- **THEN** `_execute_single_tool_call` 在 `browser_` 分支中检测到 `op_type == "get_element_by_number"`
- **AND** 从 `scratchpad.get().element_map` 中查找对应 ref 的 CSS selector
- **AND** 从 `scratchpad.get().elements` 列表中查找完整元素信息
- **AND** 直接返回 `{"ok": True, "result": {ref, tag, type, text, selector}}`
- **AND** 不调用 `execute_browser_op()`，不触发 CDP

#### Scenario: 预执行钩子未命中，回退到 CDP
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 但 scratchpad 中无缓存或找不到该 ref
- **THEN** 回退到 `execute_browser_op("get_element_by_number", fn_args, cdp_helpers)`
- **AND** 走正常的 CDP 查找路径（`cdp_helpers.get_element_by_index(ref)`）

### Requirement: 两条查找路径
`browser_get_element_by_number` MUST 支持两条查找路径，各自服务不同场景。旧模式使用 `_element_map`，新模式使用 `_ref_map`。

#### Scenario: 路径 A — scratchpad 缓存（chat 模式主路径）
- **WHEN** chat 模式下 LLM 先调 `browser_snapshot(interactive)` 再调 `browser_get_element_by_number`
- **THEN** 预执行钩子从 scratchpad 的 `element_map` 命中
- **AND** 不触发 CDP 调用，零延迟返回

#### Scenario: 路径 B — CDP 映射（preset 模式 / 回退路径）
- **WHEN** preset 模式或 scratchpad 无缓存时调用 `browser_get_element_by_number`
- **THEN** 回退到 `execute_browser_op` → `cdp_helpers.get_element_by_index(ref)`
- **AND** 从 CDP 的 `_element_map`（旧模式）或 `_ref_map`（新模式）查找

### Requirement: scratchpad 优先查找
`browser_get_element_by_number(ref)` MUST 优先从 scratchpad 的 `element_map` 查找元素，无缓存时回退到 CDP 的 `_element_map`（旧模式）或 `_ref_map`（新模式）。

#### Scenario: scratchpad 有缓存时直接查找
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 或 `browser_get_element_by_number(ref="@e_12345")` 且 scratchpad 中有缓存的 `element_map`
- **THEN** 从 `scratchpad.get().element_map` 中查找对应 ref 的 CSS selector
- **AND** 不触发 CDP 调用
- **AND** 返回元素的完整信息（ref、tag、type、text、selector）

#### Scenario: scratchpad 无缓存时回退到 CDP
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")` 但 scratchpad 中无缓存
- **THEN** 回退到 `cdp_helpers.get_element_by_index("@e5")` 从 `_element_map` 或 `_ref_map` 查找

#### Scenario: 两处都无缓存
- **WHEN** scratchpad 和 CDP 映射都找不到指定 ref
- **THEN** 返回错误信息 `{"ref": "<ref>", "error": "元素引用 <ref> 未找到"}`

#### Scenario: scratchpad element_map 自动构建
- **WHEN** `browser_snapshot(mode="interactive")` 执行后 scratchpad 被更新
- **THEN** `scratchpad.store()` 自动从 elements 列表构建 `element_map`
- **AND** `element_map` 格式：旧模式为 `{"@e1": "button#submit", ...}`，新模式为 `{"@e_12345": "button#submit", ...}`

### Requirement: add_dom_highlights 后同步 scratchpad
`add_dom_highlights()` 在 goto/click/fill 后自动触发并重建 CDP 的映射。编排层 MUST 在此时同步更新 scratchpad 的 `element_map`，避免两个 map 不一致导致 scratchpad 缓存命中率下降。

#### Scenario: goto 后同步
- **WHEN** `browser_goto` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 编排层从 `add_dom_highlights()` 返回值中获取 `element_map`
- **AND** 提取每个 ref 的 `selector` 字段，构建扁平 map `{ref: selector}`
- **AND** 调用 `scratchpad.sync_element_map(elements)` 更新 scratchpad 的 `element_map`
- **AND** 不覆盖 scratchpad 的其他字段

#### Scenario: click 后同步
- **WHEN** `browser_click` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 同样同步 scratchpad 的 `element_map`

#### Scenario: fill 后同步
- **WHEN** `browser_fill` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 同样同步 scratchpad 的 `element_map`

#### Scenario: 新模式 scroll 后同步
- **WHEN** `use_stable_refs=True` 且 `browser_scroll` 执行成功后 `add_dom_highlights()` 被调用
- **THEN** 同样同步 scratchpad 的 `element_map`

#### Scenario: 同步后两个 map 一致
- **WHEN** scratchpad 的 `element_map` 被同步更新
- **THEN** 后续 `browser_get_element_by_number` 调用优先命中 scratchpad 缓存
- **AND** 不再需要频繁回退到 CDP 映射

### Requirement: ref 归一化兼容 @e_XXXXX 格式

`_normalize_ref(ref, use_stable_refs=False)` 函数 MUST 新增 `use_stable_refs` 参数，用于区分纯数字输入应归一化为旧格式 `@eN` 还是新格式 `@e_XXXXX`。带 `@` 前缀和 `e_` 前缀的输入可自动识别格式，无需依赖此参数。

#### Scenario: @e_XXXXX 格式直接通过（两种模式通用）
- **WHEN** 调用 `_normalize_ref("@e_12345")`
- **THEN** 返回 `"@e_12345"`

#### Scenario: e_XXXXX 格式归一化（两种模式通用）
- **WHEN** 调用 `_normalize_ref("e_12345")`
- **THEN** 返回 `"@e_12345"`

#### Scenario: 纯数字输入 — 新模式
- **WHEN** 调用 `_normalize_ref("12345", use_stable_refs=True)`
- **THEN** 返回 `"@e_12345"`

#### Scenario: 纯数字输入 — 旧模式
- **WHEN** 调用 `_normalize_ref("3", use_stable_refs=False)`
- **THEN** 返回 `"@e3"`

#### Scenario: 旧格式仍然兼容（两种模式通用）
- **WHEN** 调用 `_normalize_ref("@e3")` 或 `_normalize_ref("e3")`
- **THEN** 返回 `"@e3"`
