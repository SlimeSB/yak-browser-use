## ADDED Requirements

### Requirement: 高亮编号注入

系统 MUST 支持向浏览器页面注入交互元素的高亮编号标签。旧模式（`use_stable_refs=False`）编号使用 `@e1, @e2, ...` 自增格式；新模式（`use_stable_refs=True`）编号使用 `@e_XXXXX` 格式（CDP backend_node_id）。高亮覆盖层使用 `position: absolute` 定位，JS 渲染时通过 `rect.left + window.scrollX` / `rect.top + window.scrollY` 转换坐标。

#### Scenario: 首次注入高亮
- **WHEN** 调用 `add_dom_highlights()` 且页面存在可交互元素
- **THEN** 页面 DOM 中出现 `#ybu-highlights` 容器，包含 `data-ybu-highlight` 属性标记的高亮元素，数量与可交互元素一致
- **AND** 每个高亮元素显示对应的编号标签（蓝色背景、白色文字）
- **AND** 高亮元素设置 `pointer-events: none`，不拦截用户交互

#### Scenario: 无交互元素时注入
- **WHEN** 调用 `add_dom_highlights()` 且页面无可交互元素
- **THEN** 返回 `{ok: true, count: 0, element_map: {}}`
- **AND** 页面 DOM 中不出现 `#ybu-highlights` 容器

#### Scenario: 连续两次注入不重复
- **WHEN** 连续两次调用 `add_dom_highlights()`
- **THEN** 第二次调用前自动移除旧高亮
- **AND** 页面中只有一份高亮元素，无重复

#### Scenario: 传入已有元素列表避免重复扫描
- **WHEN** 调用 `add_dom_highlights(elements=existing_elements)` 传入已有的元素列表
- **THEN** 不执行 `_inject_simplify_js` 扫描，直接使用传入的元素列表渲染高亮

### Requirement: 高亮编号移除

系统 MUST 支持移除页面上的所有高亮编号标签。旧模式同时清空 Python 侧的映射缓存；新模式仅移除 DOM 元素，保留持久化映射。

#### Scenario: 旧模式移除高亮并清空映射
- **WHEN** `use_stable_refs=False` 时调用 `remove_dom_highlights()`
- **THEN** 页面 DOM 中 `#ybu-highlights` 容器被移除
- **AND** `CDPHelpers._element_map` 缓存被清空

#### Scenario: 新模式移除高亮但保留映射
- **WHEN** `use_stable_refs=True` 时调用 `remove_dom_highlights()`
- **THEN** 页面 DOM 中 `#ybu-highlights` 容器被移除
- **AND** `CDPHelpers._ref_map` 保持不变

#### Scenario: 重复移除不报错
- **WHEN** 连续两次调用 `remove_dom_highlights()`
- **THEN** 第二次调用不报错，静默成功

### Requirement: 按编号查询元素信息

系统 MUST 支持通过编号从 Python 侧缓存中查询元素信息，不走 DOM 查询。输入 ref 支持 `"@e3"`、`"e3"`、`"3"`（旧模式 `use_stable_refs=False` 时 `"3"`→`@e3`）和 `"@e_12345"`、`"e_12345"`、`"12345"`（新模式 `use_stable_refs=True` 时 `"12345"`→`@e_12345`），内部归一化后查询。

#### Scenario: 查询旧格式存在的编号
- **WHEN** 调用 `get_element_by_index("@e3")` 且缓存中存在该编号
- **THEN** 返回 `{ref: "@e3", tag: "button", text: "登录", selector: "#login-btn", bounds: {x, y, w, h}}`

#### Scenario: 查询新格式存在的编号
- **WHEN** 调用 `get_element_by_index("@e_12345")` 且缓存中存在该编号
- **THEN** 返回 `{ref: "@e_12345", tag: "button", text: "登录", selector: "#login-btn", bounds: {x, y, w, h}}`

#### Scenario: 查询新格式纯数字输入
- **WHEN** `use_stable_refs=True` 时调用 `get_element_by_index("12345")` 且缓存中存在 `@e_12345`
- **THEN** 归一化为 `@e_12345` 后查询成功

#### Scenario: 查询不存在的编号
- **WHEN** 调用 `get_element_by_index("@e999")` 且缓存中不存在该编号
- **THEN** 返回 `{ref: "@e999", error: "not found"}`

#### Scenario: 查询前未注入高亮
- **WHEN** 调用 `get_element_by_index("@e3")` 但此前未调用 `add_dom_highlights()`
- **THEN** 返回 `{ref: "@e3", error: "no highlights injected"}`

### Requirement: Agent 查询元素工具

系统 MUST 提供 `browser_get_element_by_number` 工具供 Agent 调用，输入编号返回元素详情。Agent 拿到信息后可用 `browser_click` 等工具执行操作。

#### Scenario: Agent 查询编号对应的元素
- **WHEN** Agent 调用 `browser_get_element_by_number(ref="@e3")`
- **THEN** 返回元素信息 `{tag, text, selector, bounds}`
- **AND** Agent 可使用返回的 `selector` 调用 `browser_click` 执行点击

#### Scenario: Agent 查询未注入的编号
- **WHEN** Agent 调用 `browser_get_element_by_number(ref="@e999")` 且高亮未注入或编号不存在
- **THEN** 返回错误信息，提示编号不存在或高亮未注入

### Requirement: 操作后自动刷新高亮

系统 MUST 在 goto/click/fill 操作成功后自动刷新高亮编号。新模式（`use_stable_refs=True`）下 scroll 操作也触发刷新。

#### Scenario: goto 后刷新
- **WHEN** 执行 `browser_goto` 成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮

#### Scenario: click 后刷新
- **WHEN** 执行 `browser_click` 成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮

#### Scenario: fill 后刷新
- **WHEN** 执行 `browser_fill` 成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮

#### Scenario: 新模式 scroll 后刷新
- **WHEN** `use_stable_refs=True` 且执行 `browser_scroll` 成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮

#### Scenario: 旧模式 scroll 后不刷新
- **WHEN** `use_stable_refs=False` 且执行 `browser_scroll` 成功
- **THEN** 不触发高亮刷新

#### Scenario: snapshot 后不刷新
- **WHEN** 执行 `browser_snapshot` 成功
- **THEN** 不触发高亮刷新

### Requirement: Chat 模式首次注入

系统 MUST 在 chat 模式对话启动时异步注入首次高亮，不阻塞对话消息循环。注入失败静默忽略。

#### Scenario: 对话启动时注入
- **WHEN** `run_conversation_loop()` 启动，在进入消息循环前
- **THEN** 异步调用 `add_dom_highlights()` 注入高亮
- **AND** 注入过程不阻塞用户发送第一条消息

#### Scenario: 注入失败不影响对话
- **WHEN** 首次注入因页面未加载等原因失败
- **THEN** 静默忽略错误，对话正常启动
- **AND** 后续 goto/click/fill 操作仍会触发刷新

### Requirement: Agent 启动前注入高亮

系统 MUST 在 Agent goal run 启动前注入高亮编号，复用已有的 `capture_snapshot_interactive()` 结果避免重复 DOM 扫描。

#### Scenario: Agent 启动前注入
- **WHEN** `run_goal_step()` 中已通过 `capture_snapshot_interactive()` 获取元素列表
- **THEN** 使用已有元素列表调用 `add_dom_highlights(elements=elements)` 注入高亮
- **AND** 不执行额外的 DOM 扫描

### Requirement: Agent 结束后清理高亮

系统 MUST 在 Agent goal run 结束后清理所有高亮元素，包括 browser-use 的 `.browser-use-highlight` 和 YBU 的 `#ybu-highlights`。

#### Scenario: 清理 BU 和 YBU 高亮
- **WHEN** Agent goal run 结束（正常或异常）
- **THEN** `_cleanup_agent_highlights()` 同时移除 `.browser-use-highlight` 和 `#ybu-highlights`
- **AND** 清理通过 `agent_browser._cdp_client` 执行，无需额外参数

### Requirement: @eN 在 chat 模式下的 fallback 解析

系统 MUST 支持 chat 模式下 Agent 直接使用 `@eN` 或 `@e_XXXXX` 作为 click/fill 的 selector。当 `element_map` 不可用时，通过 `cdp_helpers.get_element_by_index()` 做 fallback 查询。

#### Scenario: chat 模式下 @eN 解析
- **WHEN** Agent 调用 `browser_click(selector="@e3")` 且 `element_map` 为 None
- **THEN** `_resolve_element_ref` 通过 `cdp_helpers.get_element_by_index("@e3")` 查询
- **AND** 返回对应的 CSS selector 用于执行点击

#### Scenario: chat 模式下 @e_XXXXX 解析
- **WHEN** Agent 调用 `browser_click(selector="@e_12345")` 且 `element_map` 为 None
- **THEN** `_resolve_element_ref` 通过 `cdp_helpers.get_element_by_index("@e_12345")` 查询
- **AND** 返回对应的 CSS selector 用于执行点击

#### Scenario: pipeline 模式下 @eN 解析
- **WHEN** pipeline 执行 click 且 `element_map` 已由 snapshot 构建
- **THEN** `_resolve_element_ref` 直接从 `element_map` 解析，不走 `cdp_helpers` fallback

### Requirement: 新模式禁用 MutationObserver

系统 MUST 在新模式（`use_stable_refs=True`）下，`add_dom_highlights()` 注入的 JS 代码中不包含 MutationObserver 和 ResizeObserver 初始化，避免 DOM 变化时 `simplifyDom()` 重绘生成 `@e1..@eN` 顺序 ref 导致 badge 显示错误。

#### Scenario: 新模式不注入 Observer
- **WHEN** `use_stable_refs=True` 时调用 `add_dom_highlights(elements)`
- **THEN** 注入的 JS 代码中不包含 `MutationObserver` 和 `ResizeObserver` 初始化
- **AND** 高亮仅在显式调用 `add_dom_highlights()` 时刷新

#### Scenario: 旧模式保持 Observer
- **WHEN** `use_stable_refs=False` 时调用 `add_dom_highlights(elements)`
- **THEN** 注入的 JS 代码中包含 `MutationObserver` 和 `ResizeObserver` 初始化
- **AND** 行为与变更前完全一致
