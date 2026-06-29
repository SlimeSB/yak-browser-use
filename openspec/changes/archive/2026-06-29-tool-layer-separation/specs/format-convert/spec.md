## MODIFIED Requirements

### Requirement: format_convert 仅返回元信息
`format_convert` MUST 保留在 registry 中，LLM SHALL 可调用，但仅返回元信息，SHALL NOT 返回转换后的文件内容。

`format_convert` 函数本身 MUST 保留完整功能，供 `read_data` 内部 Python import 调用。

#### Scenario: format_convert 返回元信息
- **WHEN** LLM 调用 `format_convert(source="downloads/data.xlsx", target="downloads/data.csv")`
- **THEN** 系统 MUST 执行格式转换
- **AND** 系统 MUST 返回 `{"ok": True, "source": "downloads/data.xlsx", "target": "downloads/data.csv", "source_fmt": "xlsx", "target_fmt": "csv"}`
- **AND** 系统 MUST NOT 返回转换后的文件内容

#### Scenario: format_convert tool schema 保留注册
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中 MUST 包含 `format_convert`

#### Scenario: Agent 工具内部调用可获取完整结果
- **WHEN** `read_data` 读取二进制文件时
- **THEN** `read_data` MUST 通过 `from yak_browser_use.tools.format_convert import format_convert` 调用
- **AND** 调用 MUST 返回完整转换后内容（不受元信息限制）
