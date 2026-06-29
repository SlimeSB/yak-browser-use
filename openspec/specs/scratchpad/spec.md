## REMOVED Module

### Requirement: scratchpad 存储
**Reason**: scratchpad 模块被整体移除，其功能由 `_apply_heavy_data_filter` 当场构建 summary 替代，不再需要持久化缓存层。

**Migration**: `_apply_heavy_data_filter` 中 browser_snapshot 分支改为当场调用内联的 summary 构建函数，不再调用 `scratchpad.store()`。browser_source cached 路径直接依赖 `bridge.get_page_html(cached=True)` 的内部缓存。

### Requirement: store_raw_html 增量更新
**Reason**: 同 scratchpad 存储，`raw_html` 缓存由 bridge 内部的 `_element_map` 承担，不再需要 scratchpad 层。

**Migration**: browser_source 的 HTML 缓存由 `bridge.get_page_html(cached=True)` 内部处理，`_apply_heavy_data_filter` 不再调用 `scratchpad.store_raw_html()`。

### Requirement: element_map 自动构建
**Reason**: `element_map` 字段在 2026-06 已被注释掉，chat 模式走 `bridge._ref_map`，preset 模式在 `execute_browser_step` 中本地构建。scratchpad 的 element_map 从未被使用。

**Migration**: 无，element_map 已是死代码。

### Requirement: 摘要生成
**Reason**: 摘要生成逻辑迁移到 `tool_executor._build_snapshot_summary()` 内联函数，不再依赖 `ScratchpadRecord` 数据结构。

**Migration**: `scratchpad._build_summary(record)` 改为 `_build_snapshot_summary(elements, url, title)`，输入从 record 对象变为独立参数。

### Requirement: element_map 同步
**Reason**: `sync_element_map` 已在 2026-06 被注释掉，无调用者。

**Migration**: 无，已是死代码。
