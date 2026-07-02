## Requirements

### Requirement: browser_snapshot 统一多模式入口

`browser_snapshot` 工具 MUST 提供四种快照模式：`aria`（默认）、`a11y`、`progressive`、`full`。所有模式通过 `bridge`（PlaywrightBridge）执行，不再使用 CDP `Runtime.evaluate`。

#### Scenario: aria 模式（默认）
- **WHEN** LLM 调用 `browser_snapshot()` 或 `browser_snapshot(mode="aria")`
- **THEN** executor 调用 `bridge.aria_snapshot()` 获取 YAML 语义树
- **AND** 返回 LLM 友好的 role/name 层级结构

#### Scenario: a11y 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="a11y")`
- **THEN** executor 调用 `bridge.a11y_snapshot()` 获取结构化元素列表
- **AND** 每个元素带 ref/role/name/nth/selector

#### Scenario: progressive 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive")`
- **THEN** executor 调用 `bridge._progressive_snapshot()` 执行 DOM 深度扫描 + 密度自适应折叠
- **AND** 最多 200 元素，密集容器折叠为 folded_containers

#### Scenario: full 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="full")`
- **THEN** executor 调用 `bridge.capture_snapshot()` 获取 screenshot + HTML
- **AND** 返回结果中标记 `has_screenshot` 和 `has_html`

#### Scenario: a11y 不可用降级
- **WHEN** a11y snapshot 因浏览器环境不可用而失败
- **THEN** 自动降级为 progressive 模式
- **AND** 返回结果中标记 `degraded: true` 和 `_fallback_reason`

### Requirement: browser_snapshot 支持 expand_key 参数

`browser_snapshot` 工具 MUST 新增可选参数 `expand_key`，在 `mode="progressive"` 时指定要展开的折叠容器 key。

#### Scenario: snapshot 同时展开容器
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", expand_key="c_0")`
- **THEN** executor 先执行 progressive snapshot，然后展开 `c_0` 容器
- **AND** 返回结果中包含展开后的元素

### Requirement: browser_snapshot query 匹配

`_progressive_snapshot` 和 `a11y_snapshot` 的 `query` 参数 MUST 使用通用 `_match` 函数，遍历元素所有非 `_` 前缀字段进行匹配。匹配规则为：先匹配字段 key 名（`q in k.lower()`），再匹配 string 值（`q in v.lower()`）。

#### Scenario: query="disabled" 匹配禁用元素
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="disabled")`
- **THEN** 返回的元素列表中包含所有含 `disabled` key 的元素（通过 key 名匹配）

#### Scenario: query="aria-expanded" 通过 key 名匹配
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="aria-expanded")`
- **THEN** 返回的元素列表中包含所有含 `aria_expanded` key 的元素

#### Scenario: query="submit" 匹配 type=submit 的元素
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="submit")`
- **THEN** 返回的元素列表中包含 `type: "submit"` 的 input/button 元素（通过 string 值匹配）

#### Scenario: boolean false 不可搜索
- **WHEN** 页面中存在 `<button>Enabled</button>`（无 disabled 属性）
- **AND** LLM 调用 `browser_snapshot(mode="progressive", query="false")`
- **THEN** 该元素不会因为 "false" 而被匹配

#### Scenario: a11y 模式 query 匹配
- **WHEN** LLM 调用 `browser_snapshot(mode="a11y", query="disabled")`
- **THEN** 返回的元素列表中包含 `disabled: "true"` 的元素（通过 key 名匹配 `disabled` 字段，值为 `"true"` 非空）
- **AND** `disabled: ""` 的元素不被匹配（空值 key 名不命中）

### Requirement: browser_snapshot 重数据剥离

`_apply_heavy_data_filter` 中 browser_snapshot 的重数据剥离逻辑 MUST 当场构建 summary 返回，不再依赖 scratchpad 持久化存储。

#### Scenario: a11y/progressive 模式当场生成摘要
- **WHEN** LLM 调用 `browser_snapshot(mode="a11y")` 且结果包含 elements
- **THEN** `_apply_heavy_data_filter` 当场生成中文摘要
- **AND** `result_dict["result"]` 替换为该摘要字符串
- **AND** 不调用任何 scratchpad 函数

#### Scenario: full 模式剥离重数据
- **WHEN** LLM 调用 `browser_snapshot(mode="full")` 且结果包含 screenshot_base64 和 html
- **THEN** 从 `result_dict` 中移除 `screenshot_base64` 和 `html`
- **AND** `result_dict["result"]` 替换为简短确认消息

#### Scenario: aria 模式不处理
- **WHEN** LLM 调用 `browser_snapshot(mode="aria")`
- **THEN** `_apply_heavy_data_filter` 直接返回，不修改 result

### Requirement: 交互元素快照（interactive 模式）

系统 MUST 提供 `a11y_snapshot()` 或等效方法提取页面中所有可交互元素。旧模式（`use_stable_refs=False`）使用 `@eN` 顺序编号；新模式（`use_stable_refs=True`）使用 CDP `backendNodeId` 生成 `@e_XXXXX` 编号。

#### Scenario: 返回数据格式
- **WHEN** interactive 快照成功执行
- **THEN** 返回 dict 中每个元素包含 `ref`、`tag`、`type`、`text`、`selector` 字段

#### Scenario: 新模式 ref 格式
- **WHEN** `use_stable_refs=True`
- **THEN** 每个元素的 `ref` 字段格式为 `@e_{backendNodeId}`
- **AND** 编号在元素 DOM 生命周期内稳定不变

#### Scenario: 旧模式 ref 格式
- **WHEN** `use_stable_refs=False`
- **THEN** 每个元素的 `ref` 字段格式为 `@e1..@eN`

#### Scenario: 降级链
- **WHEN** JS 执行失败
- **THEN** 回退到 `capture_snapshot()` full 模式
- **AND** 返回 dict 中标记 `degraded: true`

### Requirement: 简化页面摘要快照（simplified 模式）

系统 MUST 提供简化页面摘要功能，生成页面摘要和检测到的列表/表格结构。

#### Scenario: 返回数据格式
- **WHEN** simplified 快照成功执行
- **THEN** 返回 dict `{"summary": "...", "lists": [...], "tables": [...], "mode": "simplified"}`

#### Scenario: simplified 模式降级链
- **WHEN** simplify-dom.js 执行失败或无结果
- **THEN** 回退到 `capture_snapshot()` full 模式
- **AND** 返回 dict 中标记 `degraded: true`

### Requirement: DOM 化简脚本

系统 MUST 提供 `assets/simplify-dom.js` 脚本，通过 Playwright `page.evaluate()` 注入浏览器执行，支持 interactive 和 simplified 两种模式。

#### Scenario: interactive 模式执行
- **WHEN** 调用 `simplifyDom({ mode: "interactive" })`
- **THEN** 返回 JSON 对象包含 `mode: "interactive"` 和 `elements` 数组
- **AND** 每个元素包含 `ref`、`tag`、`type`、`text`、`selector` 字段

#### Scenario: simplified 模式执行
- **WHEN** 调用 `simplifyDom({ mode: "simplified" })`
- **THEN** 返回 JSON 对象包含 `mode: "simplified"`、`summary`、`lists`、`tables` 字段

#### Scenario: 可见性判断
- **WHEN** 元素 `offsetParent === null` 或 `getBoundingClientRect()` 返回的宽/高为 0
- **THEN** 该元素被视为不可见，不被包含在结果中

#### Scenario: 视口内判断
- **WHEN** 元素 `getBoundingClientRect()` 返回的位置完全在视口外
- **THEN** 该元素不被包含在 interactive 结果中

#### Scenario: 脚本不存在时的降级
- **WHEN** `assets/simplify-dom.js` 文件不存在或无法读取
- **THEN** 返回 None，调用方进入降级链的下一级

### Requirement: 高亮编号注入与移除

系统 MUST 支持向浏览器页面注入交互元素的高亮编号标签，以及通过编号查询元素信息。

#### Scenario: 注入高亮
- **WHEN** 调用 `add_dom_highlights(elements=existing_elements)`
- **THEN** 页面 DOM 中出现 `#ybu-highlights` 容器
- **AND** 每个高亮元素显示对应的编号标签（蓝色背景、白色文字）

#### Scenario: 移除高亮
- **WHEN** 调用 `remove_dom_highlights()`
- **THEN** 页面 DOM 中 `#ybu-highlights` 容器被移除
- **AND** `use_stable_refs=True` 时 `_ref_map` 保持不变
- **AND** `use_stable_refs=False` 时 `_element_map` 被清空

#### Scenario: 按编号查询元素
- **WHEN** 调用 `get_element_by_index("@e3")` 或 `get_element_by_index("@e_12345")`
- **THEN** 支持旧格式 `@eN` 和新格式 `@e_XXXXX`
- **AND** 纯数字输入根据 `use_stable_refs` 自动归一化

#### Scenario: 操作后自动刷新高亮
- **WHEN** 执行 `browser_goto`/`browser_click`/`browser_fill` 成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮
- **AND** 新模式下 `browser_scroll` 也触发刷新

#### Scenario: 新模式禁用 MutationObserver
- **WHEN** `use_stable_refs=True`
- **THEN** 注入的 JS 代码中不包含 MutationObserver 和 ResizeObserver
- **AND** 高亮仅在显式调用 `add_dom_highlights()` 时刷新

### Requirement: browser_source 重数据剥离

`_apply_heavy_data_filter` 中 browser_source 分支 MUST 将 HTML 写入 shared_store，返回结果仅含元信息，不含 HTML 原文。不依赖 scratchpad 持久化存储。

#### Scenario: 不写 scratchpad
- **WHEN** `_apply_heavy_data_filter` 处理 `browser_source` 结果
- **THEN** HTML 写入 shared_store（由 handler 完成）
- **AND** result_dict 仅保留元信息
- **AND** 不调用 `scratchpad.store_raw_html()`
