# Hermes Skill 格式参考

> 快速参考：Hermes skill = YAML frontmatter + Markdown body，存为 `SKILL.md`
> 加载方式：`skill_view('skill-name')` 或 Hermes 自动加载

---

## 最小示例

```markdown
---
name: my-skill
description: "一句话描述这个 skill 做什么"
version: 1.0.0
---

# My Skill

## Trigger

什么条件下使用本 skill。

## Workflow

### Step 1: 做什么
具体操作说明。

### Step 2: 做什么

## Pitfalls

- 坑 1
- 坑 2
```

---

## 完整示例（含 metadata）

```markdown
---
name: code-review-workflow
description: "系统化处理代码审查报告——分类、分批、批量修复审查发现的问题"
version: 2.1.0
author: 酒狐
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, automation, workflow]
    related_skills: [opencode-spec-review, requesting-code-review]
---

# Code Review Workflow

## When to use

- 审查结果中有多个需要修复的问题
- 需要批量处理审查发现的问题
- 主人说"把审查发现的问题修掉"

## Workflow

### Step 1: 分类问题

将发现的问题按类型分类：

| 类型 | 处理方式 |
|:-----|:---------|
| Blocker | 必须修 |
| Major | 应该修 |
| Minor | 有时间再修 |
| Nitpick | 忽略 |

### Step 2: 分批修复

...

## Pitfalls

- OpenCode 的 pty 模式不能 background
- 修复后必须重新审查
```

---

## Skill 目录结构规范

```
~/AppData/Local/hermes/skills/
├── <category>/
│   ├── <skill-name>/
│   │   ├── SKILL.md              ← 主文件（必需）
│   │   ├── references/           ← 参考文件（可选）
│   │   │   └── api.md
│   │   ├── templates/            ← 模板文件（可选）
│   │   │   └── config.yaml
│   │   └── scripts/              ← 脚本文件（可选）
│   │       └── validate.py
```

注意：`skill_manage(action='create')` 会自动创建目录结构和 SKILL.md。`skill_view(name)` 加载时返回 SKILL.md 内容和 linked_files 列表。可以通过 `skill_view(name, file_path='references/api.md')` 访问关联文件。

---

## 常用字段说明

| frontmatter 字段 | 类型 | 必填 | 说明 |
|:-----------------|:-----|:----:|:-----|
| `name` | string | ✅ | skill 名称，kebab-case |
| `description` | string | ✅ | 一句话描述 |
| `version` | string | | semver 版本号 |
| `author` | string | | 作者 |
| `license` | string | | 许可证 |
| `platforms` | string[] | | 支持的平台 |
| `metadata.hermes.tags` | string[] | | 标签，用于搜索 |
| `metadata.hermes.related_skills` | string[] | | 相关 skill 名 |

---

## 加载方式

```python
# 在 Hermes 会话中：
skill_view('skill-name')
# → 返回 SKILL.md 内容 + linked_files 列表

skill_view('skill-name', file_path='references/example.md')
# → 返回 references/example.md 的内容
```

---

## 现有 skill 示例参考

可用 `skill_view('任意现有skill名')` 查看实际例子，如：
- `skill_view('plan')` — 规划模式 skill
- `skill_view('opencode-spec-review')` — spec 审查 skill
- `skill_view('ph-tool-generation')` — 如果已创建
