---
name: skill-authoring
description: 指导 LLM Agent 如何编写符合规范的 skill 文档
tags: [system, meta, skill]
---

## 何时创建 Skill

满足以下任一条件时，应创建 skill 将工作流沉淀下来：

- 完成了一个 3 步以上的复杂任务，且该任务具有通用性
- 发现了一个可复用的操作模式（如"搜索中文资料"、"填写表单"等）
- 用户明确要求将某段操作保存为 skill

## Body 结构规范

Skill 的 body 是纯 Markdown，**不需要**包含 YAML frontmatter（frontmatter 由 `skill_create` 的参数自动生成）。

推荐结构：

```markdown
## 使用场景
描述什么情况下应使用本 skill。

## 操作步骤
1. 第一步
2. 第二步
3. ...

## 注意事项
- 常见陷阱
- 边界情况处理
```

## 命名规则

- 只允许小写字母、数字、连字符（`-`）
- 首尾不能是连字符
- 总长 1-64 字符
- 示例：`web-search`、`fill-form`、`extract-table`

## 工具使用说明

### skill_create — 创建新 skill

```
skill_create(name="web-search", description="用浏览器搜索中文资料", content="## 使用场景\n...", tags=["search", "web"])
```

- `name`：skill 标识符（kebab-case）
- `description`：简短描述，会写入 frontmatter
- `content`：纯 Markdown body，**不要**包含 YAML frontmatter
- `tags`：可选标签数组，`system` tag 会被自动过滤（预置 skill 专用）

### skill_edit — 编辑已有 skill

```
skill_edit(name="web-search", content="## 新正文\n...")
```

- 默认模式：只替换 body，frontmatter 保持不变
- `content` 是纯 body，不要包含 frontmatter
- 如需修复 frontmatter，使用 `raw=true` 模式整体替换

### skill_delete — 删除 skill

```
skill_delete(name="old-skill", absorbed_into="new-skill")
```

- `absorbed_into`：记录内容合并去向，但**系统不会自动合并**——你需要手动用 `skill_edit` 将相关内容写入目标 skill
- 含 `system` tag 的预置 skill 不可删除

### skill_list / skill_view — 查看 skill

- `skill_list()`：列出所有可用 skill
- `skill_view(name="xxx")`：查看 skill 完整内容（含 frontmatter）
