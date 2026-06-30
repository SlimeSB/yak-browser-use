### Requirement: progressive 模式 query 匹配扩展到所有字段

`_progressive_snapshot` 的 `query` 参数 MUST 遍历元素所有非 `_` 前缀字段进行匹配，不再限制为固定的 4 个字段。匹配规则为：先匹配字段 key 名（`q in k.lower()`），再匹配 string 值（`q in v.lower()`）。

#### Scenario: query="disabled" 匹配禁用元素

- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="disabled")`
- **THEN** 返回的元素列表中包含所有含 `disabled` key 的元素（通过 key 名匹配）
- **AND** 不包含没有 `disabled` key 的元素

#### Scenario: query="aria-expanded" 通过 key 名匹配

- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="aria-expanded")`
- **THEN** 返回的元素列表中包含所有含 `aria_expanded` key 的元素（通过 key 名匹配）
- **AND** 无论 `aria_expanded` 值为 `"true"` 还是 `"false"`，均被匹配

#### Scenario: query="submit" 匹配 type=submit 的元素

- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="submit")`
- **THEN** 返回的元素列表中包含 `type: "submit"` 的 input/button 元素（通过 string 值匹配）
- **AND** 也包含 text 或 tag 中含 "submit" 的元素

#### Scenario: boolean false 不可搜索

- **WHEN** 页面中存在 `<button>Enabled</button>`（无 disabled 属性，即 disabled=false）
- **AND** LLM 调用 `browser_snapshot(mode="progressive", query="false")`
- **THEN** 该元素不会因为 "false" 而被匹配（因为不存在 `disabled` key，且 query 不匹配空字符串）
- **NOTE** 这是 known tradeoff：条件写入策略下，`disabled=False` 和"不存在 disabled 属性"对 LLM 不可区分

### Requirement: a11y 模式 query 匹配使用通用 `_match`

`a11y_snapshot` 的 `query` 参数 MUST 使用与 progressive 相同的 `_match` 函数，遍历所有非 `_` 前缀字段进行匹配（key 名匹配要求 value 非空）。

#### Scenario: query="disabled" 在 a11y 模式下匹配

- **WHEN** LLM 调用 `browser_snapshot(mode="a11y", query="disabled")`
- **THEN** 返回的元素列表中包含 `disabled: "true"` 的元素（通过 key 名匹配 `disabled` 字段，值为 `"true"` 非空）
- **AND** `disabled: ""` 的元素不被匹配（空值 key 名不命中）

#### Scenario: a11y query 匹配 value 字段

- **WHEN** 页面中存在 `<input value="search keyword">`
- **AND** LLM 调用 `browser_snapshot(mode="a11y", query="keyword")`
- **THEN** 返回的元素列表中包含该 input（通过 value 字段匹配 "keyword"）
