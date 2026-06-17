# load-skill Specification

## Purpose
TBD - created by archiving change skill-system. Update Purpose after archive.
## Requirements
### Requirement: 加载 skill body（去 frontmatter）

系统 MUST 提供 `load_skill(name)` 函数，返回 skill 的 body 部分（去掉 YAML frontmatter），供 system prompt 等代码层使用。

#### Scenario: 成功加载子目录格式 skill

- **WHEN** 代码调用 `load_skill("goal-execution")` 且 `backend/prompts/skill/goal-execution/SKILL.md` 存在
- **THEN** 系统返回去掉 frontmatter 后的 body 文本

#### Scenario: 成功加载平面文件格式 skill（fallback）

- **WHEN** 代码调用 `load_skill("goal-execution")` 且子目录格式不存在但 `backend/prompts/skill/goal-execution.md` 存在
- **THEN** 系统返回去掉 frontmatter 后的 body 文本

#### Scenario: skill 不存在

- **WHEN** 代码调用 `load_skill("nonexistent")` 且两种格式均不存在
- **THEN** 系统返回空字符串 `""`，并记录 warning 日志

#### Scenario: SKILL.md 无 YAML frontmatter

- **WHEN** 代码调用 `load_skill("no-frontmatter")` 且文件无 `---` 分隔符
- **THEN** 系统返回文件的全部文本内容（视为 body）

#### Scenario: SKILL.md 包含无效 YAML frontmatter（自动修复失败）

- **WHEN** 代码调用 `load_skill("broken-frontmatter")` 且 frontmatter YAML 解析失败，自动修复仍失败
- **THEN** 系统以文件的完整文本内容作为 body（视 frontmatter 为 body 的一部分）
- **AND** 记录 warning 日志

