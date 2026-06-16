## ADDED Requirements

### Requirement: use_stable_refs 开关

`CDPHelpers` 的构造函数 MUST 支持 `use_stable_refs: bool = False` 参数。默认值为 `False`，保持完全向后兼容。

#### Scenario: 默认旧模式
- **WHEN** 创建 `CDPHelpers(daemon)` 不传 `use_stable_refs`
- **THEN** `use_stable_refs` 为 `False`
- **AND** 所有行为与变更前完全一致（JS 自分配 `@e1..@eN`、`_element_map` 每次清空重建、scroll 不触发 auto-refresh）

#### Scenario: 显式启用新模式
- **WHEN** 创建 `CDPHelpers(daemon, use_stable_refs=True)`
- **THEN** `use_stable_refs` 为 `True`
- **AND** 元素编号使用 CDP `backendNodeId` 生成 `@e_XXXXX` 格式
- **AND** `_ref_map` 页面内持久

### Requirement: CDP backend_node_id 解析

系统 MUST 提供 `_resolve_backend_refs(elements: list[dict]) -> list[dict]` 方法，通过 CDP 为每个元素获取 `backendNodeId` 并替换 `ref` 字段为 `@e_XXXXX` 格式。

#### Scenario: 正常解析
- **WHEN** 调用 `_resolve_backend_refs(elements)` 且所有元素的 selector 在 DOM 中可匹配
- **THEN** 对每个元素依次调用 `DOM.querySelector` 获取 `nodeId`
- **AND** 调用 `DOM.describeNode` 获取 `backendNodeId`
- **AND** 将元素的 `ref` 字段替换为 `@e_{backendNodeId}`
- **AND** 返回修改后的 elements 列表

#### Scenario: selector 匹配失败降级
- **WHEN** 某元素的 selector 在 DOM 中匹配不到（`nodeId` 为 0 或不存在）
- **THEN** 该元素的 `ref` 设为 `@e_unknown_{N}`（N 为降级序号，从 1 自增）
- **AND** 不影响其他元素的解析

#### Scenario: CDP 调用异常降级
- **WHEN** `DOM.querySelector` 或 `DOM.describeNode` 抛出异常
- **THEN** 该元素的 `ref` 设为 `@e_unknown_{N}`（N 为降级序号，从 1 自增）
- **AND** 继续处理后续元素

#### Scenario: 多个元素降级不冲突
- **WHEN** 多个元素均匹配失败
- **THEN** 分别分配 `@e_unknown_1`、`@e_unknown_2` 等，key 不冲突

### Requirement: _ref_map 持久化

系统 MUST 在 `use_stable_refs=True` 时使用 `_ref_map` 替代 `_element_map`。`_ref_map` 在页面内持久，scroll 后增量更新。

#### Scenario: 首次 snapshot 建立映射
- **WHEN** 新模式首次调用 `add_dom_highlights(elements)`
- **THEN** `_ref_map` 以 `@e_XXXXX` 为 key 存储元素信息
- **AND** 包含 `ref`、`tag`、`type`、`text`、`selector`、`value`、`x`、`y`、`width`、`height` 字段

#### Scenario: 再次 snapshot 增量更新
- **WHEN** 新模式再次调用 `add_dom_highlights(elements)` 且部分元素的 `@e_XXXXX` 已存在于 `_ref_map`
- **THEN** 已存在的 key 保留，仅更新位置信息（`x`、`y`、`width`、`height`）
- **AND** 新进入视口的元素新增 key
- **AND** 不再出现在视口的元素不移除（LLM 可能仍持有引用）

#### Scenario: 过期引用自然失效
- **WHEN** DOM 元素被 JS 动态删除后 LLM 引用其 `@e_XXXXX`
- **THEN** `get_element_by_index` 从 `_ref_map` 中仍能查到该 ref
- **AND** 后续 `browser_click` 或 `browser_fill` 使用其 selector 时因 DOM 中不存在而自然报错
- **AND** 错误信息提示元素不存在，LLM 可据此重新 snapshot

#### Scenario: browser_goto 清空映射
- **WHEN** 新模式执行 `browser_goto` 成功
- **THEN** `executor.py` 的 `execute_browser_op` 中调用 `cdp_helpers.reset_ref_map()` 清空 `_ref_map`
- **AND** 后续 snapshot 重新建立映射

### Requirement: MutationObserver 禁用

系统 MUST 在新模式（`use_stable_refs=True`）下禁用 `add_dom_highlights()` 注入的 MutationObserver 和 ResizeObserver，避免 DOM 变化时 `simplifyDom()` 重绘生成 `@e1..@eN` 顺序 ref 导致 badge 显示错误。

#### Scenario: 新模式不注入 Observer
- **WHEN** `use_stable_refs=True` 时调用 `add_dom_highlights(elements)`
- **THEN** 注入的 JS 代码中不包含 `MutationObserver` 和 `ResizeObserver` 初始化
- **AND** 高亮仅在显式调用 `add_dom_highlights()` 时刷新

#### Scenario: 旧模式保持 Observer
- **WHEN** `use_stable_refs=False` 时调用 `add_dom_highlights(elements)`
- **THEN** 注入的 JS 代码中包含 `MutationObserver` 和 `ResizeObserver` 初始化
- **AND** 行为与变更前完全一致

### Requirement: simplified snapshot 不污染映射

系统 MUST 在新模式（`use_stable_refs=True`）下，`capture_snapshot_simplified()` 不调用 `add_dom_highlights()`，避免 JS scan 生成的 `@e1..@eN` 顺序 ref 覆盖持久化的 `@e_XXXXX` 映射。

#### Scenario: 新模式 simplified snapshot 跳过 highlight
- **WHEN** `use_stable_refs=True` 时调用 `capture_snapshot_simplified()`
- **THEN** 不调用 `add_dom_highlights()`
- **AND** 返回 simplified 摘要数据

#### Scenario: 旧模式 simplified snapshot 保持 highlight
- **WHEN** `use_stable_refs=False` 时调用 `capture_snapshot_simplified()`
- **THEN** 调用 `add_dom_highlights()` 注入高亮
- **AND** 行为与变更前完全一致

### Requirement: remove_dom_highlights 不清空持久化映射

系统 MUST 在新模式（`use_stable_refs=True`）下，`remove_dom_highlights()` 仅移除页面 DOM 中的高亮元素，不清空 `_ref_map`。

#### Scenario: 新模式 remove 保留映射
- **WHEN** `use_stable_refs=True` 时调用 `remove_dom_highlights()`
- **THEN** 页面 DOM 中 `#ybu-highlights` 容器被移除
- **AND** `_ref_map` 保持不变

#### Scenario: 旧模式 remove 清空映射
- **WHEN** `use_stable_refs=False` 时调用 `remove_dom_highlights()`
- **THEN** 页面 DOM 中 `#ybu-highlights` 容器被移除
- **AND** `_element_map` 被清空
- **AND** 行为与变更前完全一致

### Requirement: ref 归一化兼容 @e_XXXXX 格式

`get_element_by_index()` MUST 兼容 `@e_XXXXX` 格式的 ref 输入。`_normalize_ref(ref, use_stable_refs=False)` MUST 新增 `use_stable_refs` 参数区分纯数字输入的格式选择。

#### Scenario: @e_XXXXX 格式直接匹配
- **WHEN** 调用 `get_element_by_index("@e_12345")` 且 `_ref_map` 中存在该 key
- **THEN** 直接返回对应元素信息

#### Scenario: e_XXXXX 格式归一化
- **WHEN** 调用 `get_element_by_index("e_12345")`
- **THEN** 归一化为 `@e_12345` 后查询

#### Scenario: 纯数字输入 — 新模式
- **WHEN** 调用 `get_element_by_index("12345")` 且 `use_stable_refs=True`
- **THEN** 归一化为 `@e_12345` 后查询

#### Scenario: 纯数字输入 — 旧模式
- **WHEN** `use_stable_refs=False` 时调用 `get_element_by_index("3")`
- **THEN** 归一化为 `@e3` 后查询
- **AND** 行为与变更前完全一致

### Requirement: browser_scroll 触发 auto-refresh

系统 MUST 在新模式（`use_stable_refs=True`）下，`browser_scroll` 执行成功后自动调用 `add_dom_highlights()` 刷新高亮和 `_ref_map`。

#### Scenario: 新模式 scroll 后刷新
- **WHEN** `use_stable_refs=True` 且 `browser_scroll` 执行成功
- **THEN** 自动调用 `add_dom_highlights()` 刷新高亮
- **AND** `_ref_map` 中已有元素的 `@e_XXXXX` 不变，新元素新增

#### Scenario: 旧模式 scroll 后不刷新
- **WHEN** `use_stable_refs=False` 且 `browser_scroll` 执行成功
- **THEN** 不触发高亮刷新
- **AND** 行为与变更前完全一致
