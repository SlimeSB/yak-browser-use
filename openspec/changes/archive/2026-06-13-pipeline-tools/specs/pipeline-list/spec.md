## ADDED Requirements

### Requirement: 列出所有 pipeline 预设
系统 MUST 提供 `pipeline_list` 工具，列出 workspace 下所有可用的 pipeline 预设文件。

#### Scenario: 存在多个预设
- **WHEN** Agent 调用 `pipeline_list`
- **THEN** 返回 JSON 包含 `ok: true` 和 `presets` 数组
- **AND** 每个 preset 包含 `name`、`description`、`step_count`

#### Scenario: 无预设文件
- **WHEN** 预设目录为空或不存在
- **THEN** 返回 JSON 包含 `ok: true` 和空的 `presets` 数组

#### Scenario: 部分文件解析失败
- **WHEN** 某些 `.pipeline.yaml` 文件无法解析
- **THEN** 对应 preset 的 `description` 标注 `(parse error)`，`step_count` 为 0，不影响其他正常文件
