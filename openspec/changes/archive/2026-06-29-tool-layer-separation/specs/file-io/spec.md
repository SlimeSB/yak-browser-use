## MODIFIED Requirements

### Requirement: file_read 仅返回元信息
`file_read` tool 通过 LLM handler 调用时 MUST 仅返回元信息，SHALL NOT 返回文件原始文本内容。

`file_read` 函数本身 MUST 保留完整读取能力，供 `read_data` 内部 Python import 调用。

#### Scenario: file_read handler 返回元信息
- **WHEN** LLM 调用 `file_read(path="downloads/data.csv")`
- **THEN** handler MUST 执行路径校验和存在性检查
- **AND** handler MUST 返回 `{"ok": True, "path": "downloads/data.csv", "size": <bytes>, "encoding": "utf-8"}`
- **AND** handler MUST NOT 返回文件内容

#### Scenario: Agent 工具内部调用可获取完整内容
- **WHEN** `read_data` 内部通过 `from yak_browser_use.tools.file_read import file_read` 调用
- **THEN** 调用 MUST 返回文件完整文本内容（不受元信息限制）

### Requirement: file_write workspace 子目录沙箱
`file_write` tool 通过 LLM handler 调用时 MUST 限定写入路径为 workspace 的子目录。写作业空间根目录 SHALL 被拒绝。

`file_write` 函数本身 MUST 保留完整写入能力，供 Agent 工具内部调用。

#### Scenario: 写入 workspace 子目录
- **WHEN** LLM 调用 `file_write(path="downloads/output.csv", content="...")` 且当前 pipeline 上下文可用
- **THEN** handler MUST 解析到 `WORKSPACES_ROOT/<pipeline>/downloads/output.csv`
- **AND** 写入 MUST 成功
- **AND** handler MUST 返回 `{"ok": True, "path": "...", "size": <bytes>}`

#### Scenario: 写入 workspace 根目录被拒绝
- **WHEN** LLM 调用 `file_write(path="pipeline.yaml", content="...")` 或路径解析后无子目录层级
- **THEN** handler MUST 返回 `{"ok": False, "error": "workspace 根目录不可写，请使用 pipeline_* 系列工具"}`
- **AND** 文件 SHALL NOT 被创建或覆盖

#### Scenario: 无 pipeline 上下文时降级
- **WHEN** LLM 调用 `file_write` 但 `ctx.pipeline_name` 为 None
- **THEN** handler MUST 回退到原有行为（不应用沙箱）

### Requirement: file_read tool schema 调参
`file_read` 的 tool schema MUST 移除 `head`、`max_chars` 参数（移至 `read_data`）。`encoding` 参数 SHALL 保留，用于 handler 返回元信息中的编码字段。

#### Scenario: file_read schema 参数简化
- **WHEN** 系统注册 `file_read` tool
- **THEN** parameters MUST 包含 `path`（string, required）
- **AND** parameters MUST 包含 `encoding`（string, optional）
- **AND** parameters MUST NOT 包含 `head`、`max_chars`
