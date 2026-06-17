## ADDED Requirements

### Requirement: 查看 skill 完整内容

系统 MUST 提供一个 `skill_view` 工具，允许 Agent 查看某个 skill 的完整 Markdown 内容（含 YAML frontmatter 和 body）。

#### Scenario: 查看子目录格式 skill

- **WHEN** Agent 调用 `skill_view(name="goal-execution")` 且 `backend/prompts/skill/goal-execution/SKILL.md` 存在
- **THEN** 系统返回 `{"ok": true, "result": "<完整文件内容>"}`，`result` 为完整 Markdown 文本（含 frontmatter）

#### Scenario: 查看平面文件格式 skill（fallback）

- **WHEN** Agent 调用 `skill_view(name="goal-execution")` 且子目录格式不存在但 `backend/prompts/skill/goal-execution.md` 存在
- **THEN** 系统返回 `{"ok": true, "result": "<完整文件内容>"}`，`result` 为完整 Markdown 文本（含 frontmatter）

#### Scenario: skill 不存在

- **WHEN** Agent 调用 `skill_view(name="nonexistent")` 且两种格式均不存在
- **THEN** 系统返回 `{"ok": false, "error": "Skill 'nonexistent' not found"}`

#### Scenario: name 包含非法字符

- **WHEN** Agent 调用 `skill_view(name="../etc/passwd")`
- **THEN** 系统拒绝操作，返回 `{"ok": false, "error": "..."}` 指明 name 未通过白名单校验（正则 `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`）

#### Scenario: name 参数缺失

- **WHEN** Agent 调用 `skill_view()` 未提供 name 参数
- **THEN** 系统返回 `{"ok": false, "error": "..."}` 指明缺少 name 参数

#### Scenario: frontmatter YAML 解析失败（自动修复失败）

- **WHEN** Agent 调用 `skill_view(name="broken-skill")` 且该 skill 的 YAML frontmatter 解析失败，自动修复仍失败
- **THEN** 系统返回 `{"ok": true, "result": "<完整文件内容>"}`，`result` 为完整 Markdown 文本（含无效 frontmatter）
- **AND** 不因解析失败中断操作，让 LLM 能读取原始内容后调用 `skill_edit` 修复
