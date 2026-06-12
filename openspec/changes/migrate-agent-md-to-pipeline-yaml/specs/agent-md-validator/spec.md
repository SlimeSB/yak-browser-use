## MODIFIED Requirements

<!-- 注：agent-md-validator 既有行为在 openspec/specs/ 中无正式 spec，本次变更将其从手动字段检查改为 Pydantic schema 校验。 -->



### Requirement: 校验流水线定义
系统 MUST 通过 `validate_pipeline()` 函数校验流水线定义的合法性。校验方式从手动字段检查（检查 frontmatter、标题、步骤字段存在性）改为 Pydantic schema 校验。

#### Scenario: 必填字段缺失
- **WHEN** pipeline.yaml 缺少 `name` 字段
- **THEN** `validate_pipeline()` 返回校验失败，错误信息指明缺少的字段路径

#### Scenario: 步骤列表为空
- **WHEN** pipeline.yaml 的 `steps` 为空列表
- **THEN** `validate_pipeline()` 返回校验失败

#### Scenario: 合法文件校验通过
- **WHEN** pipeline.yaml 包含合法的 `name` 和至少一个步骤
- **THEN** `validate_pipeline()` 返回校验通过，或返回解析后的 PipelineYaml 对象

### Requirement: 移除旧校验逻辑
系统 MUST 移除 `validate_agentmd()` 函数及其中手动检查 frontmatter/标题/步骤字段的逻辑。

#### Scenario: 旧校验函数不可用
- **WHEN** 尝试调用 `validate_agentmd()`
- **THEN** 引发 ImportError
