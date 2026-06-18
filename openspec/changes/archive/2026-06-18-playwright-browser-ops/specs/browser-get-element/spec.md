## MODIFIED Requirements

### Requirement: browser_get_element_by_number 底层实现
`browser_get_element_by_number` 工具的底层实现 MUST 通过 `bridge.get_element_by_index()` 查询元素映射，而非通过 `cdp_helpers.get_element_by_index()`。

#### Scenario: 查询已缓存元素
- **WHEN** LLM 调用 `browser_get_element_by_number(ref="@e5")`
- **THEN** executor 调用 `bridge.get_element_by_index("@e5")`
- **AND** 从元素映射缓存中查找对应元素信息
- **AND** 返回元素详情或 `{"ref": "@e5", "error": "not found"}`
