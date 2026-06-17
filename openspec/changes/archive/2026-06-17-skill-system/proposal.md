## Why

YBU 目前没有动态 skill 系统。`backend/prompts/skill/` 下只有一个静态文件 `goal-execution.md`，靠 `backend/prompts/_loader.py` 按文件名读到 system prompt 里。LLM Agent 无法列出可用 skill、查看 skill 内容、或动态创建/更新/删除 skill（把做成功的工作流沉淀下来）。

项目已有 `backend/utils/skill_loader.py` 提供了基础的 `skill_view()` 函数用于加载平面文件格式的 skill，但缺少列表、管理和子目录格式支持。现在做是因为 skill 系统是让 Agent 具备"学习能力"的基础设施——Agent 完成复杂任务后可以把工作流存成 skill 以便后续复用。

## What Changes

- **新增** 五个 Agent 可调用的 tool：`skill_list`、`skill_view`、`skill_create`、`skill_edit`、`skill_delete`，通过 `tool_executor` 路由
- **扩展** `backend/utils/skill_loader.py`：新增 `skill_list()`、`skill_create()`、`skill_edit()`、`skill_delete()` 函数，`skill_view()` 扩展支持子目录格式（`prompts/skill/<name>/SKILL.md`）
- **新建** `backend/engine/_harness/skill_tools.py`：薄包装层，调 `skill_loader` 并做异常转换
- **修改** `backend/engine/_harness/tools.py`：新增五个 tool schema 常量，`get_all_tools()` 中追加
- **修改** `backend/engine/_harness/tool_executor.py`：新增 `skill_*` 路由分支
- **修改** `backend/prompts/_loader.py`：新增 `load_skill()` 函数
- **修改** `backend/prompts/chat/system.md`：告知 LLM skill 工具存在
- **迁移** `backend/prompts/skill/goal-execution.md` → `goal-execution/SKILL.md`（加 YAML frontmatter）
- **新建** `backend/prompts/skill/skill-authoring/SKILL.md`：meta-skill，指导 LLM 如何编写 skill

## Capabilities

### New Capabilities
- `skill-list`: Agent 可以列出所有可用 skill，返回每个 skill 的名称、描述和标签
- `skill-view`: Agent 可以查看某个 skill 的完整内容（含 frontmatter 和 body）
- `skill-create(name, description, content, tags?)`: Agent 创建新 skill，frontmatter 由系统自动生成
- `skill-edit(name, content)`: Agent 替换 skill 的 body 部分，frontmatter 保持不变
- `skill-delete(name, absorbed_into?)`: Agent 删除 skill，支持记录合并去向
- `skill-authoring`: 预置 meta-skill，指导 LLM 如何编写符合规范的 skill（body 结构、命名规则、触发条件）
- `load-skill`: 代码层加载 skill body（去 frontmatter），供 system prompt 注入使用
- `system-prompt`: system prompt 告知 LLM 五个 skill 工具的用法，并引用 skill-authoring 写作指南

### Modified Capabilities

## Impact

- **代码**：`backend/utils/skill_loader.py`（扩展）、`backend/engine/_harness/tools.py`（追加）、`backend/engine/_harness/tool_executor.py`（追加路由）、`backend/prompts/_loader.py`（新增函数）、`backend/prompts/chat/system.md`（追加文本）
- **新增文件**：`backend/engine/_harness/skill_tools.py`
- **数据**：`backend/prompts/skill/goal-execution.md` 迁移为子目录格式，向下兼容（平面文件 fallback）
- **接口**：无破坏性变更，纯追加
- **依赖**：无新增外部依赖
