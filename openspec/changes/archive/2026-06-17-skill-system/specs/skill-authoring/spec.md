## ADDED Requirements

### Requirement: skill-authoring 预置 meta-skill

系统 MUST 预置一个 `skill-authoring` skill 文档，指导 LLM Agent 如何编写符合规范的 skill。

#### Scenario: skill-authoring 可通过 skill_view 查看

- **WHEN** Agent 调用 `skill_view(name="skill-authoring")`
- **THEN** 系统返回该 skill 的完整 Markdown 内容

#### Scenario: skill-authoring 可通过 skill_list 列出

- **WHEN** Agent 调用 `skill_list()`
- **THEN** 返回结果中包含 `skill-authoring`，含 name、description、tags

### Requirement: skill-authoring 内容规范

`skill-authoring` skill 文档 MUST 包含以下内容：

#### Scenario: Frontmatter 说明

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档说明 frontmatter 由系统自动生成，Agent 无需手写 YAML
- **AND** 说明 `skill_create` 的 `description` 参数会写入 frontmatter，应填写清晰简短的描述

#### Scenario: Body 结构说明

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档包含 body 结构指导：使用场景 → 操作步骤 → 注意事项

#### Scenario: skill_edit 行为说明

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档说明 `skill_edit` 的 `content` 参数是纯 body，不包含 frontmatter（保留原 frontmatter 不变）
- **AND** 说明若需修复 frontmatter，可用 `raw=True` 模式整体替换

#### Scenario: skill_delete 行为说明

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档说明 `skill_delete` 支持 `absorbed_into` 参数记录合并去向，方便将旧 skill 的内容合并到新 skill

#### Scenario: 命名规则说明

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档说明命名规则：小写字母、数字、连字符，首尾不能是连字符，总长 1-64 字符

#### Scenario: 触发条件说明

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档说明何时应创建 skill：完成 3 步以上的复杂任务后、发现可复用的通用模式时

#### Scenario: skill_create 调用示例

- **WHEN** Agent 阅读 `skill-authoring` 内容
- **THEN** 文档包含 `skill_create(name="...", description="...", content="...", tags=[...])` 的完整调用示例
