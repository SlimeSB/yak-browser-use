## ADDED Requirements

### Requirement: system prompt 告知 skill 工具

`backend/prompts/chat/system.md` MUST 包含 skill 工具的使用说明，告知 LLM 五个 skill 工具的用途和用法。

#### Scenario: system prompt 包含 skill 工具列表

- **WHEN** system prompt 被加载
- **THEN** 内容包含 `skill_list`、`skill_view`、`skill_create`、`skill_edit`、`skill_delete` 五个工具的名称和简要说明

#### Scenario: system prompt 引用 skill-authoring

- **WHEN** system prompt 被加载
- **THEN** 内容包含对 `skill-authoring` 的引用，告知 LLM 可用 `skill_view("skill-authoring")` 查看 skill 编写指南

#### Scenario: system prompt 鼓励创建 skill

- **WHEN** system prompt 被加载
- **THEN** 内容包含建议：完成复杂任务后可用 `skill_create` 将工作流存为 skill

### Requirement: build_system_prompt 自动注入所有 system tag skill

系统 MUST 提供 `build_system_prompt()` 函数，封装 system prompt 的组装逻辑，含所有 `system` tag skill 的自动注入。

#### Scenario: system tag skill 存在时自动注入

- **WHEN** 代码调用 `build_system_prompt()`
- **AND** 存在一个或多个 `tags` 含 `system` 的 skill（如 `goal-execution`）
- **THEN** 返回的 prompt 包含 `load_prompt("chat/system")` 的原始内容
- **AND** 在原始内容后依次追加每个 `system` tag skill 的 body 内容（以 `\n\n` 分隔）

#### Scenario: 无 system tag skill 时不崩

- **WHEN** 代码调用 `build_system_prompt()`
- **AND** 不存在任何 `tags` 含 `system` 的 skill
- **THEN** 直接返回 `load_prompt("chat/system")` 的原始内容
- **AND** 不追加任何内容
- **AND** 不抛出异常
