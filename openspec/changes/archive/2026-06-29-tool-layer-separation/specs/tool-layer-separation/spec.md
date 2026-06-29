## ADDED Requirements

### Requirement: 三层工具架构
系统 MUST 将工具分为三层注册：Agent 工具、Browser ops、底层工具。所有工具 SHALL 对 LLM 可见，但底层工具仅返回元信息（`ok`、`path`、`size`、`encoding`、`target` 等），不返回文件原始内容。

#### Scenario: Agent 工具可被 LLM 调用并返回结构化内容
- **WHEN** LLM 请求 `get_all_tools()` 获取工具列表
- **THEN** 返回的工具列表 MUST 包含 Agent 工具：`pipeline_view`、`pipeline_add_step`、`pipeline_update_step`、`pipeline_remove_step`、`pipeline_create`、`pipeline_compile`、`read_data`
- **AND** MUST 包含 Browser ops 工具：所有 `browser_*` 前缀工具
- **AND** `read_data` SHALL 是唯一可返回文件全文内容的工具

#### Scenario: 底层工具仅返回元信息
- **WHEN** LLM 调用 `file_read`、`file_write`、`format_convert`
- **THEN** handler MUST 执行操作并返回 `{"ok": true, ...元信息字段...}`
- **AND** MUST NOT 返回文件原始文本内容
- **AND** LLM 可通过返回的元信息（path、size、encoding、target 等）编写 pipeline YAML

#### Scenario: Agent 工具内部可调用底层工具
- **WHEN** Agent 工具（如 `read_data`）执行时需要读写文件
- **THEN** Agent 工具 SHALL 通过 Python import 直接调用 `file_read`、`file_write`、`format_convert`
- **AND** 内部调用路径不受元信息限制

### Requirement: file_write workspace 沙箱
`file_write` 通过 registry handler 调用时 MUST 限定写入路径为 workspace 的子目录。写作业空间根目录 SHALL 被拒绝。

#### Scenario: 写入 workspace 子目录
- **WHEN** 调用 `file_write(path="downloads/output.csv")` 且当前 pipeline 上下文可用
- **THEN** handler MUST 解析到 `WORKSPACES_ROOT/<pipeline>/downloads/output.csv`
- **AND** 写入 MUST 成功
- **AND** 返回 `{"ok": True, "path": "...", "size": <bytes>}`

#### Scenario: 写入 workspace 根目录被拒绝
- **WHEN** 调用 `file_write(path="pipeline.yaml")` 或路径解析后无子目录层级
- **THEN** handler MUST 返回 `{"ok": False, "error": "workspace 根目录不可写，请使用 pipeline_* 系列工具"}`
- **AND** 文件 SHALL NOT 被创建或覆盖

#### Scenario: 无 pipeline 上下文时降级
- **WHEN** 调用 `file_write` 但 `ctx.pipeline_name` 为 None
- **THEN** handler MUST 回退到原有行为（不应用沙箱），保持向后兼容

### Requirement: validate_path workspace 子目录解析
`validate_path` 函数 MUST 支持 `pipeline` 参数时解析到 workspace 目录。

#### Scenario: 带 pipeline 参数的路径解析
- **WHEN** 调用 `validate_path(path="downloads/data.csv", pipeline="my-pipeline")`
- **THEN** 系统 MUST 解析为 `WORKSPACES_ROOT/my-pipeline/downloads/data.csv`
