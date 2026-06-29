## ADDED Requirements

### Requirement: pipeline_view 返回完整 browser_ops
当 `pipeline_view(name="xxx")` 返回 pipeline 详情时，每个 step MUST 包含完整的 `browser_ops` 列表，而非仅 `browser_op_count` 计数。

#### Scenario: 返回含 browser_ops 的 step
- **WHEN** pipeline 中某 step 定义了 `browser_ops: [{goto: "https://baidu.com"}, {fill: {selector: "#kw", text: "关键词"}}]`
- **THEN** `pipeline_view` 返回的该 step 中 MUST 包含 `browser_ops` 列表，内容为两个 op 的完整定义

#### Scenario: 返回 tool 类型 step
- **WHEN** pipeline 中某 step 定义了 `tool_name: "captcha"`
- **THEN** `pipeline_view` 返回的该 step 中 MUST 包含 `tool_name` 字段
- **AND** MUST NOT 包含 `browser_ops` 字段

#### Scenario: 返回 goal 类型 step
- **WHEN** pipeline 中某 step 定义了 `goal_description: "提取数据"`
- **THEN** `pipeline_view` 返回的该 step 中 MUST 包含 `goal_description` 字段
- **AND** MUST NOT 包含 `browser_ops` 和 `tool_name` 字段

### Requirement: pipeline_view 内部使用 to_yaml 格式
`browser_ops` 列表 MUST 以 `PipelineStore.ops_to_yaml()` 格式返回（即 `{goto: "url"}` 而非 `{type: "goto", value: "url"}`）。

#### Scenario: ops 返回 YAML 格式
- **WHEN** pipeline 内部的 browser_ops 以 `{type: "goto", value: "https://baidu.com"}` 存储
- **THEN** `pipeline_view` 返回时 MUST 转换为 `{goto: "https://baidu.com"}`
- **AND** LLM 看到的内容与 pipeline.yaml 文件一致
