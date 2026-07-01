## ADDED Requirements

### Requirement: browser_extract_list SHALL 在 chat registry 中可用

Agent 可在对话中调用 `browser_extract_list` 从当前页面提取列表数据。

#### Scenario: 通用列表提取（无 selector 无 fields）

- **WHEN** Agent 调用 `browser_extract_list()` 且不传 selector/fields
- **THEN** handler MUST 执行 `EXTRACT_LIST_JS`（通用 li/role=listitem 提取）
- **AND** 返回 `{"ok": true, "items": [...], "count": N}`

#### Scenario: 自定义 selector 提取

- **WHEN** Agent 调用 `browser_extract_list(selector=".bili-video-card")`
- **THEN** handler MUST 生成 JS 用 `document.querySelectorAll('.bili-video-card')` 匹配元素
- **AND** 每个元素提取 `text`、`href`（第一个 `<a>` 的 href）
- **AND** selector 中的单引号 MUST 被转义为 `\'`（防止 JS 注入）

#### Scenario: 自定义字段映射提取

- **WHEN** Agent 调用 `browser_extract_list(selector=".item", fields={"title": "h3", "link": "@href"})`
- **THEN** handler MUST 生成 JS 对每个匹配元素调用 `el.querySelector('h3').textContent` 和 `el.getAttribute('href')`
- **AND** 返回结果中每个 item MUST 含 `title` 和 `link` 字段

#### Scenario: 结果存入 shared_store（完整数据）

- **WHEN** Agent 调用 `browser_extract_list(output_to="videos")`
- **THEN** handler MUST 将**完整**结果数组存入 `ctx.shared_store["videos"]`
- **AND** 返回中 MUST 含 `"_output_to": "videos"`

#### Scenario: 大列表返回截断但 shared_store 存完整数据

- **WHEN** 提取结果超过 50 项且提供了 `output_to`
- **THEN** handler MUST 将完整数据存入 `ctx.shared_store`
- **AND** 返回给 LLM 的 items MUST 截断为前 50 项
- **AND** 返回中 MUST 含 `"_truncated": true, "total": <实际总数>`, `"count": 50`

#### Scenario: 大列表截断（无 output_to）

- **WHEN** 提取结果超过 50 项且未提供 `output_to`
- **THEN** 返回 items MUST 截断为前 50 项
- **AND** 返回中 MUST 含 `"_truncated": true, "total": <实际总数>`

---

### Requirement: browser_extract_table SHALL 在 chat registry 中可用

#### Scenario: 自动提取表格

- **WHEN** Agent 调用 `browser_extract_table()`
- **THEN** handler MUST 执行 `EXTRACT_TABLE_JS`
- **AND** 返回 `{"ok": true, "headers": [...], "rows": [[...], ...]}`

#### Scenario: 指定 selector 提取表格

- **WHEN** Agent 调用 `browser_extract_table(selector=".data-table")`
- **THEN** handler MUST 仅从匹配元素内提取表头和数据行

#### Scenario: 表格结果存入 shared_store

- **WHEN** Agent 调用 `browser_extract_table(output_to="my_table")`
- **THEN** handler MUST 将完整结果 `{"headers": [...], "rows": [...]}` 存入 `ctx.shared_store["my_table"]`
- **AND** 返回中 MUST 含 `"_output_to": "my_table"`

#### Scenario: 大表格行数截断

- **WHEN** 表格超过 100 行
- **THEN** 返回中 rows MUST 截断为前 100 行
- **AND** 返回中 MUST 含 `"_truncated": true, "total_rows": <实际行数>`
- **AND** 若提供了 `output_to`，shared_store 中 MUST 存完整数据

---

### Requirement: browser_extract_details SHALL 在 chat registry 中可用

#### Scenario: 通用详情提取

- **WHEN** Agent 调用 `browser_extract_details()`
- **THEN** handler MUST 执行 `EXTRACT_DETAILS_JS`
- **AND** 返回 `{"ok": true, "text": "页面文本", "details": [{"label": "...", "value": "..."}]}`

#### Scenario: 指定 detail 容器

- **WHEN** Agent 调用 `browser_extract_details(selector="#product-details")`
- **THEN** handler MUST 仅在指定容器内提取 key-value 对

#### Scenario: 详情结果存入 shared_store

- **WHEN** Agent 调用 `browser_extract_details(output_to="product_info")`
- **THEN** handler MUST 将完整结果存入 `ctx.shared_store["product_info"]`
- **AND** 返回中 MUST 含 `"_output_to": "product_info"`
