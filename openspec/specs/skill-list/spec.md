# skill-list Specification

## Purpose
TBD - created by archiving change skill-system. Update Purpose after archive.
## Requirements
### Requirement: 列出所有可用 skill

系统 MUST 提供一个 `skill_list` 工具，允许 Agent 列出所有可用 skill 的名称、描述和标签。

#### Scenario: 列出所有 skill

- **WHEN** Agent 调用 `skill_list()`
- **THEN** 系统返回 `{"ok": true, "result": "<JSON 字符串>"}`，`result` 是 JSON 序列化的数组，每个元素包含 `name`、`description`、`tags` 字段
- **AND** 优先扫描子目录格式（`backend/prompts/skill/<name>/SKILL.md`），其次扫描平面文件（`backend/prompts/skill/<name>.md`）
- **AND** 同一名称的子目录格式优先于平面文件，不重复列出
- **AND** 返回结果按 `name` 字母序排列
- **AND** 跳过 `.` 开头的隐藏文件和目录，以及 `__pycache__` 目录

#### Scenario: 名称权威性（目录名为标识符）

- **WHEN** 子目录名为 `goal-execution` 但 `SKILL.md` 中 frontmatter 写 `name: goal_execution`
- **THEN** 系统以目录名 `goal-execution` 作为返回的 `name` 字段（权威标识符）
- **AND** frontmatter 的 `name` 字段仅作为 metadata 内的显示名称，不改变标识符
- **AND** 后续 `skill_view("goal-execution")` 用目录名查找

#### Scenario: skill 目录为空

- **WHEN** `prompts/skill/` 下无任何 skill 文件
- **THEN** 系统返回 `{"ok": true, "result": "[]"}`

#### Scenario: skill 目录不存在

- **WHEN** `prompts/skill/` 目录不存在
- **THEN** 系统返回 `{"ok": true, "result": "[]"}`

#### Scenario: SKILL.md 无 YAML frontmatter

- **WHEN** 某个 SKILL.md 文件没有 `---` frontmatter 分隔符
- **THEN** 系统以目录名作为 `name`，`description` 为空字符串，`tags` 为空数组

#### Scenario: SKILL.md 包含无效 YAML frontmatter（自动修复失败）

- **WHEN** 某个 SKILL.md 的 frontmatter 部分 YAML 解析失败，且程序化自动修复仍失败
- **THEN** 系统以目录名作为 `name`，`description` 为空字符串，`tags` 为空数组，不中断整个列表操作
- **AND** 写入日志警告，记录文件名和解析错误

#### Scenario: SKILL.md frontmatter 自动修复成功

- **WHEN** 某个 SKILL.md 的 frontmatter 包含可修复的格式问题（如 tab 缩进、不可见控制字符）
- **THEN** 系统自动修复后正常解析
- **AND** 以修复后的 metadata 返回 name/description/tags
- **AND** 写入 debug 日志记录修复详情（不覆盖源文件）

