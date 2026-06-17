## 背景

YBU 的 skill 目前只有一个静态文件 `goal-execution.md`，由 `prompts/_loader.py` 加载到 system prompt。项目已有 `backend/utils/skill_loader.py` 提供 `skill_view()` 和 `_parse_skill()`，但仅支持平面文件格式（`prompts/skill/{name}.md`），缺少列表、管理和子目录格式。

本次设计借鉴 Hermes 的 skill 系统，取其核心 CRUD 模式，去掉 curator、hub、安全扫描等 YBU 不需要的部分。

## 目标 / 非目标

**目标：**
- Agent 可通过 `skill_list` 列出所有可用 skill
- Agent 可通过 `skill_view` 查看 skill 完整内容
- Agent 可通过 `skill_create` / `skill_edit` / `skill_delete` 三个独立工具管理 skill
- 预置 `skill-authoring` meta-skill，指导 LLM 如何编写符合规范的 skill
- 支持子目录格式（`prompts/skill/<name>/SKILL.md`）作为主要存储格式
- 向下兼容平面文件格式（`prompts/skill/<name>.md`）作为 fallback
- 路径穿越防护，确保 Agent 无法写入 skill 目录之外

**非目标：**
- skill 内容的安全扫描
- skill 自动归档/过期
- `build_system_prompt()` 会遍历所有 `system` tag skill 自动注入到 system prompt
- skill 模版系统（references/templates/assets 子目录）
- frontmatter `platforms` 字段做平台过滤

## 关键决策

### 决策 1：复用 `utils/skill_loader.py` 而非新建独立模块

**选择**：扩展已有的 `backend/utils/skill_loader.py`，新增 `skill_list()`、`skill_create()`、`skill_edit()`、`skill_delete()`，`skill_view()` 扩展子目录支持。

**原因**：已有 `_parse_skill()` 解析 frontmatter 的逻辑。新建独立模块会导致两套 frontmatter 解析代码。

**备选方案**：在 `engine/_harness/` 下新建独立模块。被否决，因为会重复 frontmatter 解析逻辑。

### 决策 2：三层架构（loader → skill_tools → tool_executor）

**选择**：
- `utils/skill_loader.py`：底层，负责文件 I/O、frontmatter 解析、name 校验
- `engine/_harness/skill_tools.py`：薄包装层，调 loader 并做异常转换
- `engine/_harness/tool_executor.py`：路由层，按 fn_name 分发

**原因**：`utils/` 层不依赖 `engine/`，`prompts/_loader.py` 可直接调 `utils/skill_loader` 而不引入循环依赖。`skill_tools.py` 作为中间层隔离 tool executor 的异常处理逻辑。

### 决策 3：子目录格式为主，平面文件为 fallback

**选择**：`skill_list` 和 `skill_view` 优先查找 `prompts/skill/<name>/SKILL.md`，找不到时 fallback 到 `prompts/skill/<name>.md`。`skill_create` 只创建子目录格式。

**原因**：子目录格式为每个 skill 提供独立命名空间，未来可扩展 references/templates 等子文件。平面文件 fallback 保证现有 `goal-execution.md` 在迁移前仍可访问。

### 决策 4：`_validate_skill_name` 用正则白名单

**选择**：`name` 只允许 `[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?`，即小写字母、数字、连字符，首尾不能是连字符，总长 1-64。

**原因**：白名单比黑名单（过滤 `..`、`/`、`\`）更安全，且与 Hermes 的命名规范一致。

### 决策 4b：`_try_parse_yaml` 双层容错（读路径专用）

**选择**：提取 `_try_parse_yaml(text)` 函数，先 `yaml.safe_load`，失败则自动修复常见格式问题（tab→空格、去不可见控制字符）后重试，再失败则返回 `(None, False)`。仅 `_parse_skill`（读路径）调用——写路径不走解析，直接用 `yaml.dump` 从参数生成清洁 frontmatter。

**原因**：skill 文件由 LLM 生成或人工编辑，格式错误是大概率事件。读路径需要容错（降级纯 body by 日志警告）。写路径不走解析，直接 `yaml.dump` 从参数生成，从源头避免格式问题。

### 决策 4c：`skill_create` frontmatter 由参数生成，`skill_edit` 支持 raw 模式

**选择**：
- `skill_create(name, description, content, tags=None)`：frontmatter 的 `name`、`description`、`tags` 直接从参数生成，`content` 是纯 body（无 frontmatter）。系统用 `_build_skill_content(name, description, content, tags)` 组装完整文件写入。
- `skill_edit(name, content, raw=False)`：
  - `raw=False`（默认）：保留原 frontmatter 不变，只替换 body 部分。`content` 是纯 body，忽略其中可能自带的 frontmatter。
  - `raw=True`：用 `content` 整体替换文件（含 frontmatter）。需校验 `content` 包含合法的 YAML frontmatter（可解析为 mapping，含 `name` 和 `description` 字段），校验失败返回错误。

**原因**：LLM 不用手写 YAML frontmatter，减少参数冗余和格式错误。两个工具职责清晰——create 写新文件，edit 改正文不动元数据。

### 决策 4d：frontmatter `name` 是 display label，参数 `name` 是 identifier

**选择**：`skill_view` 和 `skill_list` 等所有读写操作均以参数 `name`（即目录名）作为唯一标识符。`skill_create` 时 frontmatter 的 `name` 自动填充为参数 `name`，后续 `skill_edit` 不修改 frontmatter。

**原因**：参数 `name`（目录名）是系统级唯一 ID（如 `web-search-cn`），frontmatter 的 `name` 是供人类阅读的 display label。两者始终一致（create 时自动填充），不存在不一致问题。

### 决策 5：`absorbed_into` 仅记录不执行

**选择**：`skill_delete(name, absorbed_into="xxx")` 仅在返回值中记录合并去向，不自动修改目标 skill 内容。

**原因**：自动合并 skill 内容涉及语义理解，应由 Agent 自行处理。`absorbed_into` 仅作为元数据记录，返回值中明确告知 Agent 内容未自动合并。

### 决策 6：`system` tag 保护预置 skill

**选择**：使用 `system` tag 标识预置 skill，提供防误删保护：
- `skill_create` 自动过滤 `system` tag（不允许用户创建的 skill 声明自己为 system，静默移除不报错）
- `skill_delete` 拒绝删除含 `system` tag 的 skill
- `skill_edit`（非 raw 模式）不允许移除 `system` tag；raw 模式写入时需保持 `system` tag 存在
- `tag` 在 YAML 中允许不出现，出现则不允许为空值

**原因**：预置 skill（goal-execution、skill-authoring）是系统基础设施，误删会导致 system prompt 加载异常。`system` tag 作为不可伪造的保护标记，确保 Agent 无法绕过。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|:----|:-----|:-----|
| Agent 误删重要 skill | 丢失预置工作流 | 预置 skill 可通过文件权限保护 |
| Agent 创建低质量 skill | skill 目录膨胀 | 后续可加 curator 自动清理，本轮不做 |
| 路径穿越 | 写入任意文件 | `_validate_skill_name` 白名单校验，所有 name 参数入口统一校验 |
| `skill_loader.py` 改动影响现有 `skill_view()` 调用方 | ph-tool-generation 流程中断 | `skill_view()` 接口不变，仅扩展路径查找逻辑 |
| LLM 生成的 frontmatter 格式错误 | skill_view/skill_list 中断 | 双层容错：程序化自动修复，修复失败则降级返回纯 body，由 LLM 自行修复 |
| 预置 skill 被 Agent 误删 | system prompt 加载异常 | `system` tag 保护：delete/非 raw edit 拒绝操作 |

## 迁移计划

1. 扩展 `skill_loader.py`（新增函数，不破坏现有接口）
2. 新建 `skill_tools.py`（独立文件，无依赖风险）
3. 追加 tool schema 和路由（纯追加，不影响现有功能）
4. 创建 `skill-authoring/SKILL.md`（meta-skill，指导 LLM 写 skill）
5. 迁移 `goal-execution.md` → `goal-execution/SKILL.md`（加 frontmatter，删旧文件）
6. 更新 system prompt 告知 LLM

**回滚**：删除 `skill_tools.py`，回退 `tools.py`/`tool_executor.py`/`_loader.py`/`system.md` 的追加内容，恢复 `goal-execution.md` 平面文件。

## 待确认问题

- ~~`SKILL_DIRS` 当前使用相对路径 `Path("prompts/skill")`，是否需要在 `skill_loader.py` 中改为基于项目根的绝对路径？~~ **已确认**：改为基于 `backend/` 目录的绝对路径（`Path(__file__).resolve().parent.parent / "prompts" / "skill"`），与 `prompts/_loader.py` 的 `_PROMPTS_DIR = Path(__file__).parent` 模式一致，确保无论 CWD 在哪都能正确解析。
