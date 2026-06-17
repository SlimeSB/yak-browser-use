## ADDED Requirements

### Requirement: 创建 skill (skill_create)

系统 MUST 提供 `skill_create` 工具，允许 Agent 创建新的 skill。frontmatter 由参数自动生成，Agent 无需手写 YAML。

#### Scenario: 成功创建 skill

- **WHEN** Agent 调用 `skill_create(name="web-search", description="用浏览器搜索中文资料", content="## 步骤\n1. 打开百度\n2. 输入关键词")`
- **AND** `name` 通过白名单正则 `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$` 校验
- **AND** 同名 skill 不存在
- **AND** `content` 非空
- **THEN** 系统自动创建 `backend/prompts/skill/web-search/SKILL.md`
- **AND** frontmatter 由参数自动生成：`name: web-search`、`description: 用浏览器搜索中文资料`
- **AND** 返回 `{"ok": true, "result": "Skill 'web-search' created successfully"}`

#### Scenario: 创建时带 tags

- **WHEN** Agent 调用 `skill_create(name="web-search", description="搜索", content="...", tags=["search", "web"])`
- **THEN** frontmatter 包含 `tags: [search, web]`

#### Scenario: 创建时自动过滤 system tag

- **WHEN** Agent 调用 `skill_create(name="my-skill", description="...", content="...", tags=["system", "utility"])`
- **THEN** frontmatter 中的 tags 自动移除 `system`，只包含 `[utility]`
- **AND** 不报错，不通知用户 system 被过滤

#### Scenario: 创建时 tags 含空字符串拒绝

- **WHEN** Agent 调用 `skill_create(name="my-skill", description="...", content="...", tags=["valid", ""])`
- **THEN** 系统返回 `{"ok": false, "error": "tags cannot be empty"}`

#### Scenario: 创建时 tags 去重

- **WHEN** Agent 调用 `skill_create(name="my-skill", description="...", content="...", tags=["search", "search"])`
- **THEN** frontmatter 中的 tags 去重，只包含 `[search]`

#### Scenario: 创建已存在的 skill

- **WHEN** Agent 调用 `skill_create(name="goal-execution", ...)` 且该 skill 已存在
- **THEN** 系统返回 `{"ok": false, "error": "Skill 'goal-execution' already exists"}`

#### Scenario: name 不合法拒绝创建

- **WHEN** Agent 调用 `skill_create(name="../etc/passwd", ...)` 或 `skill_create(name="Malicious", ...)` 或 `skill_create(name="-test", ...)`
- **THEN** 系统返回 `{"ok": false, "error": "Invalid skill name: '...'"}`

#### Scenario: content 为空拒绝创建

- **WHEN** Agent 调用 `skill_create(name="test", description="...", content="")`
- **THEN** 系统返回 `{"ok": false, "error": "content is required"}`

#### Scenario: name 或 description 参数缺失

- **WHEN** Agent 调用 `skill_create(name="test")` 或 `skill_create(description="...")`
- **THEN** 系统返回 `{"ok": false, "error": "..."}` 指明缺少必填参数

### Requirement: 编辑 skill (skill_edit)

系统 MUST 提供 `skill_edit` 工具，允许 Agent 替换已有 skill 的 body 部分，frontmatter 保持不变。支持 `raw` 模式整体替换。

#### Scenario: 成功编辑子目录格式 skill（默认 raw=False）

- **WHEN** Agent 调用 `skill_edit(name="goal-execution", content="## 新正文\n...")` 且该 skill 以子目录格式存在
- **THEN** 系统读取原文件，保留 frontmatter 不变，body 替换为新 content
- **AND** 返回 `{"ok": true, "result": "Skill 'goal-execution' updated successfully"}`

#### Scenario: 编辑平面文件 skill 时自动迁移（默认 raw=False）

- **WHEN** Agent 调用 `skill_edit(name="goal-execution", content="...")` 且该 skill 仅以平面文件格式存在
- **THEN** 系统创建子目录，写入 SKILL.md（frontmatter 从原文件提取），删除旧平面文件
- **AND** 返回 `{"ok": true, "result": "Skill 'goal-execution' updated successfully (migrated from flat file format)"}`

#### Scenario: content 中的 frontmatter 被忽略（默认 raw=False）

- **WHEN** Agent 调用 `skill_edit(name="test", content="---\nname: ignore\n---\n\n## 正文")` 且 content 自带了 frontmatter
- **THEN** 系统忽略 content 中的 frontmatter，只取 `---` 之后的内容作为 body
- **AND** 原文件 frontmatter 保持不变

#### Scenario: raw=True 成功写入含 frontmatter 的完整内容

- **WHEN** Agent 调用 `skill_edit(name="broken-skill", content="---\nname: fixed-skill\ndescription: 修复后的 skill\n---\n\n## 正文", raw=True)`
- **AND** `content` 包含合法的 YAML frontmatter（可解析为 mapping，含 `name` 和 `description` 字段）
- **THEN** 系统用 `content` 整体替换文件内容
- **AND** 返回 `{"ok": true, "result": "Skill 'broken-skill' updated successfully"}`

#### Scenario: raw=True 时 content 不含合法 frontmatter 拒绝

- **WHEN** Agent 调用 `skill_edit(name="test", content="纯文本无 frontmatter", raw=True)`
- **THEN** 系统返回 `{"ok": false, "error": "content must contain valid YAML frontmatter with 'name' and 'description' fields"}`

#### Scenario: raw=True 时 content frontmatter 缺少必填字段拒绝

- **WHEN** Agent 调用 `skill_edit(name="test", content="---\ntags: [foo]\n---\n\nbody", raw=True)`
- **AND** content 的 frontmatter 缺少 `name` 或 `description` 字段
- **THEN** 系统返回 `{"ok": false, "error": "content must contain valid YAML frontmatter with 'name' and 'description' fields"}`

#### Scenario: raw=True 编辑时移除 system tag 拒绝

- **WHEN** Agent 调用 `skill_edit(name="goal-execution", content="---\nname: goal-execution\ndescription: x\n---\n\n## 正文", raw=True)` 且原 skill 的 frontmatter 含 `tags: [system, goal]`
- **AND** 新 content 的 frontmatter 不含 `system` tag
- **THEN** 系统返回 `{"ok": false, "error": "cannot remove 'system' tag from pre-installed skill"}`

#### Scenario: 编辑不存在的 skill

- **WHEN** Agent 调用 `skill_edit(name="nonexistent", content="...")`
- **THEN** 系统返回 `{"ok": false, "error": "Skill 'nonexistent' not found"}`

#### Scenario: edit 时 name 不合法

- **WHEN** Agent 调用 `skill_edit(name="../etc/passwd", content="...")`
- **THEN** 系统返回 `{"ok": false, "error": "Invalid skill name: '...'"}`

#### Scenario: content 为空拒绝编辑

- **WHEN** Agent 调用 `skill_edit(name="test", content="")`
- **THEN** 系统返回 `{"ok": false, "error": "content is required"}`

### Requirement: 删除 skill (skill_delete)

系统 MUST 提供 `skill_delete` 工具，允许 Agent 删除 skill，支持记录合并去向。

#### Scenario: 成功删除子目录格式 skill

- **WHEN** Agent 调用 `skill_delete(name="web-search")` 且该 skill 以子目录格式存在
- **THEN** 系统删除 `backend/prompts/skill/web-search/` 整个目录
- **AND** 返回 `{"ok": true, "result": "Skill 'web-search' deleted successfully"}`

#### Scenario: 成功删除平面文件格式 skill

- **WHEN** Agent 调用 `skill_delete(name="goal-execution")` 且该 skill 仅以平面文件格式存在
- **THEN** 系统删除 `backend/prompts/skill/goal-execution.md`
- **AND** 返回 `{"ok": true, "result": "Skill 'goal-execution' deleted successfully"}`

#### Scenario: 删除时记录 absorbed_into

- **WHEN** Agent 调用 `skill_delete(name="old-skill", absorbed_into="new-skill")`
- **THEN** 系统删除 skill 并返回 `{"ok": true, "result": "Skill 'old-skill' deleted, absorbed into 'new-skill'. Note: content was NOT automatically merged — please use skill_edit on 'new-skill' to incorporate any relevant content."}`

#### Scenario: 子目录与平面文件同时存在时删除

- **WHEN** Agent 调用 `skill_delete(name="goal-execution")` 且子目录和平面文件同时存在
- **THEN** 系统先删除子目录，再检查并删除平面文件
- **AND** 返回 `{"ok": true, "result": "Skill 'goal-execution' deleted successfully"}`

#### Scenario: 删除含 system tag 的预置 skill 被拒绝

- **WHEN** Agent 调用 `skill_delete(name="goal-execution")` 且该 skill 的 frontmatter 含 `tags: [system, goal]`
- **THEN** 系统返回 `{"ok": false, "error": "Cannot delete pre-installed skill 'goal-execution' (protected by 'system' tag)"}`
- **AND** 不执行任何文件操作

#### Scenario: 删除不存在的 skill

- **WHEN** Agent 调用 `skill_delete(name="nonexistent")`
- **THEN** 系统返回 `{"ok": false, "error": "Skill 'nonexistent' not found"}`

#### Scenario: delete 时 name 不合法

- **WHEN** Agent 调用 `skill_delete(name="../../malicious")`
- **THEN** 系统返回 `{"ok": false, "error": "Invalid skill name: '...'"}`
- **AND** 不执行任何文件操作
