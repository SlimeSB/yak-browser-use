## ADDED Requirements

### Requirement: use_stable_refs 开关
系统 MUST 支持 `use_stable_refs: bool = False` 参数。默认值为 `False`，保持完全向后兼容。

#### Scenario: 默认旧模式
- **WHEN** 创建 `CDPHelpers(daemon)` 不传 `use_stable_refs`
- **THEN** `use_stable_refs` 为 `False`
- **AND** 元素编号使用 JS 自分配 `@e1..@eN`

#### Scenario: 显式启用新模式
- **WHEN** 创建 `CDPHelpers(daemon, use_stable_refs=True)`
- **THEN** `use_stable_refs` 为 `True`
- **AND** 元素编号使用 CDP `backendNodeId` 生成 `@e_XXXXX` 格式

### Requirement: CDP backend_node_id 解析
系统 MUST 提供 `_resolve_backend_refs(elements: list[dict]) -> list[dict]` 方法，通过 CDP 为每个元素获取 `backendNodeId` 并替换 `ref` 字段为 `@e_XXXXX` 格式。

#### Scenario: 正常解析
- **WHEN** 调用 `_resolve_backend_refs(elements)` 且所有元素的 selector 在 DOM 中可匹配
- **THEN** 对每个元素依次调用 `DOM.querySelector` 获取 `nodeId`
- **AND** 调用 `DOM.describeNode` 获取 `backendNodeId`
- **AND** 将元素的 `ref` 字段替换为 `@e_{backendNodeId}`

#### Scenario: selector 匹配失败降级
- **WHEN** 某元素的 selector 在 DOM 中匹配不到
- **THEN** 该元素的 `ref` 设为 `@e_unknown_{N}`
- **AND** 不影响其他元素的解析

#### Scenario: CDP 调用异常降级
- **WHEN** `DOM.querySelector` 或 `DOM.describeNode` 抛出异常
- **THEN** 该元素的 `ref` 设为 `@e_unknown_{N}`

### Requirement: _ref_map 持久化 vs _element_map 临时

#### Scenario: 新模式 _ref_map 持久化
- **WHEN** `use_stable_refs=True`
- **THEN** `_ref_map` 在页面内持久，scroll 后增量更新
- **AND** `browser_goto` 时清空
- **AND** 已存在的 key 仅更新位置信息，不删除过期引用

#### Scenario: 旧模式 _element_map 临时
- **WHEN** `use_stable_refs=False`
- **THEN** `_element_map` 每次 snapshot 清空重建
- **AND** `remove_dom_highlights()` 清空 `_element_map`

### Requirement: 高亮编号注入与移除
系统 MUST 支持向浏览器页面注入交互元素的高亮编号标签，以及通过编号查询元素信息。

#### Scenario: 首次注入高亮
- **WHEN** 调用 `add_dom_highlights(elements=existing_elements)`
- **THEN** 页面 DOM 中出现 `#ybu-highlights` 容器
- **AND** 每个高亮元素显示对应的编号标签（蓝色背景、白色文字）
- **AND** 高亮元素设置 `pointer-events: none`
- **AND** 不执行额外的 JS 扫描

#### Scenario: 连续两次注入不重复
- **WHEN** 连续两次调用 `add_dom_highlights()`
- **THEN** 第二次调用前自动移除旧高亮

#### Scenario: 无交互元素时注入
- **WHEN** 页面无可交互元素
- **THEN** 返回 `{ok: true, count: 0, element_map: {}}`

#### Scenario: 移除高亮
- **WHEN** 调用 `remove_dom_highlights()`
- **THEN** 页面 DOM 中 `#ybu-highlights` 容器被移除
- **AND** 新模式：`_ref_map` 保持不变
- **AND** 旧模式：`_element_map` 被清空

### Requirement: 按编号查询元素信息
系统 MUST 支持通过编号从缓存中查询元素信息，不走 DOM 查询。

#### Scenario: ref 归一化兼容
- **WHEN** 调用 `get_element_by_index(ref)`
- **THEN** 支持旧格式（`@e3`, `e3`, `3`→`@e3`）
- **AND** 支持新格式（`@e_12345`, `e_12345`, `12345`→`@e_12345`）

#### Scenario: 查询不存在的编号
- **WHEN** 调用 `get_element_by_index("@e999")` 且缓存中不存在
- **THEN** 返回 `{ref: "@e999", error: "not found"}`

### Requirement: Agent 查询元素工具
系统 MUST 提供 `browser_lookup_selector` 工具（原 `browser_get_element_by_number`）供 Agent 调用，输入编号返回元素详情。

### Requirement: 操作后自动刷新高亮
系统 MUST 在 goto/click/fill 操作成功后自动刷新高亮编号。新模式下 scroll 操作也触发刷新。

#### Scenario: goto/click/fill 后刷新
- **WHEN** 执行成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮

#### Scenario: 新模式 scroll 后刷新
- **WHEN** `use_stable_refs=True` 且 `browser_scroll` 执行成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮

#### Scenario: 旧模式 scroll 后不刷新
- **WHEN** `use_stable_refs=False` 且 `browser_scroll` 执行成功
- **THEN** 不触发高亮刷新

#### Scenario: snapshot 后不刷新
- **WHEN** 执行 `browser_snapshot` 成功
- **THEN** 不触发高亮刷新

### Requirement: MutationObserver 控制
#### Scenario: 新模式禁用 MutationObserver
- **WHEN** `use_stable_refs=True`
- **THEN** 注入的 JS 代码中不包含 MutationObserver 和 ResizeObserver

#### Scenario: 旧模式保持 Observer
- **WHEN** `use_stable_refs=False`
- **THEN** 注入的 JS 代码中包含 MutationObserver 和 ResizeObserver

### Requirement: @eN/@e_XXXXX 作为 click/fill selector
系统 MUST 支持 Agent 直接使用 `@eN` 或 `@e_XXXXX` 作为 click/fill 的 selector。当 `element_map` 不可用时，通过 `cdp_helpers.get_element_by_index()` 做 fallback 查询。

### Requirement: Chat 模式首次注入
系统 MUST 在 chat 模式对话启动时异步注入首次高亮，不阻塞对话消息循环。注入失败静默忽略。

### Requirement: Agent goal run 注入/清理
系统 MUST 在 Agent goal run 启动前注入高亮编号（复用 `capture_snapshot_interactive()` 结果），结束后清理所有高亮元素（包括 browser-use 的 `.browser-use-highlight` 和 YBU 的 `#ybu-highlights`）。
