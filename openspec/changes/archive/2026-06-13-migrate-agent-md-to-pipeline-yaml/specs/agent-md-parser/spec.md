## MODIFIED Requirements

<!-- 注：agent-md-parser 既有行为在 openspec/specs/ 中无正式 spec，本次变更将其从 Markdown+YAML 混合解析改为纯 YAML 解析，实质为破坏性重写。 -->

### Requirement: 移除 Markdown 格式支持
系统 MUST NOT 再支持 `agent.md` 的 Markdown 标题/引用块/缩进 YAML 混合语法。`parse_agent_md()` 函数被移除。

#### Scenario: 旧格式不支持
- **WHEN** 传入含 `# 标题`、`## 步骤`、`> 描述` 的 agent.md 文本给新解析器
- **THEN** 系统 MUST 抛出 `yaml.YAMLError` 或 `pydantic.ValidationError`，拒绝旧格式
