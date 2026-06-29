## ADDED Requirements

### Requirement: data_keys 工具注册
系统 MUST 在 `registry.py` 中注册 `data_keys` 工具，LLM 可调用以列出 shared_store 中所有 key。

#### Scenario: 列出所有 key
- **WHEN** LLM 调用 `data_keys()`
- **THEN** 返回 `{ok: true, keys: [{name, type, size}]}`
- **AND** `type` 为 `"list"`、`"dict"`、`"str"` 或 `"other"`
- **AND** `size` 为元素数（list/dict）或字符数（str）

#### Scenario: shared_store 为空
- **WHEN** LLM 调用 `data_keys()` 且 shared_store 为空
- **THEN** 返回 `{ok: true, keys: []}`

#### Scenario: shared_store 不可用
- **WHEN** LLM 调用 `data_keys()` 但 `ctx.shared_store` 为 None
- **THEN** 返回 `{ok: false, error: "shared_store 不可用"}`
