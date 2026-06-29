## ADDED Requirements

### Requirement: data_browse 工具注册
系统 MUST 在 `registry.py` 中注册 `data_browse` 工具，LLM 可调用以分页浏览 shared_store 中指定 key 的值。

#### Scenario: 浏览元素列表
- **WHEN** LLM 调用 `data_browse(key="elements", limit=20, offset=0)` 且 shared_store["elements"] 为元素列表
- **THEN** 返回 `{ok: true, key: "elements", offset: 0, limit: 20, total: N, items: ["@e_0 <button> ...", ...]}`
- **AND** 每个元素使用 `_build_snapshot_summary` 的单行格式

#### Scenario: 浏览字符串
- **WHEN** LLM 调用 `data_browse(key="html", limit=500, offset=0)` 且 shared_store["html"] 为字符串
- **THEN** 返回 `{ok: true, key: "html", offset: 0, limit: 500, total: N, preview: "截断后的前 500 字符..."}`

#### Scenario: 浏览字典
- **WHEN** LLM 调用 `data_browse(key="result")` 且值为 dict
- **THEN** 返回 `{ok: true, key: "result", keys: [...], preview: "截断的 repr..."}`

#### Scenario: key 不存在
- **WHEN** LLM 调用 `data_browse(key="nonexistent")`
- **THEN** 返回 `{ok: false, error: "key 'nonexistent' 不存在"}`

#### Scenario: 超出范围
- **WHEN** LLM 调用 `data_browse(key="elements", offset=100)` 且 total 为 50
- **THEN** 返回 `{ok: true, key: "elements", offset: 100, limit: 20, total: 50, items: []}`

#### Scenario: shared_store 不可用
- **WHEN** LLM 调用 `data_browse(key="x")` 但 `ctx.shared_store` 为 None
- **THEN** 返回 `{ok: false, error: "shared_store 不可用"}`
