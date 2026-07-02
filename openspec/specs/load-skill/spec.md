## Requirements

### Requirement: 加载 skill body（去 frontmatter）

系统 MUST 提供 `load_skill(name)` 函数（位于 `backend/prompts/_loader.py`），返回 skill 的 body 部分（去掉 YAML frontmatter），供 system prompt 等代码层使用。内部通过 `skill_loader.skill_view(name)` 实现。

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

### Requirement: 加载 prompt 模板

系统 MUST 提供 `load_prompt(name, **variables)` 函数（位于 `backend/prompts/_loader.py`），加载 `prompts/{name}.md` 模板文件并支持 `{variable}` 占位符替换。未提供的变量保持原样（不抛 KeyError）。

### Requirement: 构建 system prompt

`build_system_prompt()` MUST 加载 `prompts/chat/system.md` 基础 prompt，然后追加所有带 `system` tag 的 skill body 文本。使用 `skill_list(include_body=True)` 一次性获取全部 skill 内容。
