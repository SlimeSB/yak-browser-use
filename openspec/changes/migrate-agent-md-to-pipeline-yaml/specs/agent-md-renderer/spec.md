## MODIFIED Requirements

<!-- 注：agent-md-renderer 既有行为在 openspec/specs/ 中无正式 spec，本次变更将其从 Markdown+YAML 混合渲染改为纯 YAML 渲染。 -->



### Requirement: 渲染步骤定义为文本
系统 MUST 通过 `render_steps_to_pipeline()` 函数将步骤定义列表渲染为文本。输出格式从 Markdown+YAML 混合（含 `#` 标题、`>` 引用块、缩进 YAML）改为纯 YAML。

#### Scenario: 渲染为合法 YAML
- **WHEN** 调用 `render_steps_to_pipeline()` 传入步骤列表
- **THEN** 返回合法的 YAML 文本，可被 `yaml.safe_load()` 解析

#### Scenario: 不输出 Markdown 标记
- **WHEN** 渲染 steps
- **THEN** 输出中不包含 `#`、`##`、`>` 等 Markdown 前缀符号

### Requirement: 移除旧渲染函数
系统 MUST 移除 `render_steps_to_agent_md()` 函数。

#### Scenario: 旧函数不可调用
- **WHEN** 尝试调用 `render_steps_to_agent_md()`
- **THEN** 引发 ImportError
