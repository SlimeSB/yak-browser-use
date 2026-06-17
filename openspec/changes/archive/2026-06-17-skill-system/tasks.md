## 1. 底层实现：扩展 skill_loader

- [x] 1.0 在 `backend/utils/skill_loader.py` 中将 `SKILL_DIRS` 改为基于 `__file__` 的绝对路径：`[Path(__file__).resolve().parent.parent / "prompts" / "skill"]`，替代原有的相对路径 `[Path("prompts/skill")]`
- [x] 1.1 在 `backend/utils/skill_loader.py` 中新增 `_validate_skill_name(name)` 函数，用正则 `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$` 校验 name 合法性
- [x] 1.2 在 `backend/utils/skill_loader.py` 中新增 `_normalize_skill_path(name)` 函数，遍历 `SKILL_DIRS` 列表，对每个目录优先返回子目录路径 `SKILL_DIR/name/SKILL.md`，其次返回平面文件路径 `SKILL_DIR/name.md`，均不存在返回 None
- [x] 1.3 修改 `backend/utils/skill_loader.py` 中 `skill_view(name)` 函数：先调 `_validate_skill_name(name)` 校验，再用 `_normalize_skill_path` 替代原有的平面文件查找，支持子目录格式优先
- [x] 1.3b 在 `backend/utils/skill_loader.py` 中新增 `_try_parse_yaml(text: str) -> tuple[dict | None, bool]` 函数，解析单段纯 YAML 文本（不含 `---` 分隔符），实现双层容错：
  - 先 `yaml.safe_load` 直接解析
  - 失败则自动修复常见格式问题（替换 tab 为空格、去掉不可见控制字符），再试 `yaml.safe_load`
  - 仍失败则返回 `(None, False)`
  - 修复成功返回 `(parsed_dict, True)`，记录 debug 日志
- [x] 1.3c 修改 `backend/utils/skill_loader.py` 中 `_parse_skill(path)` 函数：提取 frontmatter 文本后调 `_try_parse_yaml` 替代直接 `yaml.safe_load`。自动修复仍失败时，body 返回完整原文（含无效 frontmatter），metadata 为空字典，记录 warning 日志
- [x] 1.4 在 `backend/utils/skill_loader.py` 中新增 `skill_list()` 函数，遍历 `SKILL_DIRS` 列表，优先子目录格式、去重，返回 `[{name, description, tags}]`。**注意**：`name` 必须以目录名/文件名为权威标识符，覆盖 frontmatter 中的 `name` 字段。需要跳过 `.` 开头的隐藏文件和目录，以及 `__pycache__` 目录。返回结果按 `name` 字母序排列
- [x] 1.4b 在 `backend/utils/skill_loader.py` 中新增 `_build_skill_content(name: str, description: str, content: str, tags: list[str] | None = None) -> str` 函数，用参数组装带格式化 frontmatter 的完整内容：
  - 用 `yaml.dump` 序列化 frontmatter（统一格式：键排序 `[description, name, tags]`、缩进 2 空格、无流转格式、`ensure_ascii=False`、`default_flow_style=False`）
  - frontmatter 的 `name` 自动填充为参数 `name`
  - 返回 `"---\n" + dumped + "---\n\n" + content`
- [x] 1.5 在 `backend/utils/skill_loader.py` 中新增 `skill_create(name, description, content, tags=None)` 函数：
  - 调 `_validate_skill_name(name)` 校验
  - 检查同名 skill 不存在（`_normalize_skill_path` 返回 None）
  - `content` 不能为空
  - 调 `_build_skill_content(name, description, content, tags)` 组装完整内容
  - `Path.mkdir(parents=True)` 创建目录，写入 `SKILL.md`
  - 返回 `"Skill 'xxx' created successfully"`
- [x] 1.6 在 `backend/utils/skill_loader.py` 中新增 `skill_edit(name, content, raw=False)` 函数：
  - 调 `_validate_skill_name(name)` 校验
  - 用 `_normalize_skill_path(name)` 找到现有文件（不存在则返回错误）
  - `raw=False`（默认）：读取原文件，提取 frontmatter 部分（保留原 frontmatter 文本不变），body 替换为 `content`。如果原文件是平面文件格式，自动迁移为子目录格式（创建目录，写入 SKILL.md，删旧文件）
  - `raw=True`：用 `content` 整体替换文件。需校验 `content` 包含合法 frontmatter（可解析为 mapping，含 `name` 和 `description` 字段），校验失败返回错误。对于含 `system` tag 的预置 skill，校验新 frontmatter 保留 `system` tag
  - 返回 `"Skill 'xxx' updated successfully"`，迁移时追加 `" (migrated from flat file format)"`
- [x] 1.6b 在 `backend/utils/skill_loader.py` 的 `skill_create()` 中添加 `system` tag 自动过滤逻辑：如果 `tags` 参数包含 `"system"`，静默移除
- [x] 1.6c 在 `backend/utils/skill_loader.py` 的 `skill_create()` 中添加 tags 校验逻辑：空字符串 tag 拒绝（返回错误），重复 tag 自动去重
- [x] 1.6d 在 `backend/utils/skill_loader.py` 的 `skill_edit()` 中添加 `raw=True` 模式下的 frontmatter 校验：需可解析为 mapping，含 `name` 和 `description` 字段，否则返回错误
- [x] 1.6e 在 `backend/utils/skill_loader.py` 的 `skill_edit()` 中添加 `raw=True` 模式下 `system` tag 保护：新 frontmatter 必须保留 `system` tag（如果原文件有），否则返回错误
- [x] 1.7 在 `backend/utils/skill_loader.py` 中新增 `skill_delete(name, absorbed_into=None)` 函数：
   - 调 `_validate_skill_name(name)` 校验
   - 用 `_normalize_skill_path(name)` 找到现有文件（不存在则返回错误）
   - 检查 frontmatter 是否含 `system` tag，含则拒绝删除，返回错误信息
   - 子目录格式用 `shutil.rmtree()` 删除整个目录，然后检查并删除同名的平面文件（避免孤儿文件）
   - 平面文件格式直接删除文件
   - `absorbed_into` 非空时追加到返回信息，**明确告知 Agent 内容未自动合并**

## 2. 工具接口层：新建 skill_tools

- [x] 2.1 新建 `backend/engine/_harness/skill_tools.py`，实现 `skill_list()` 薄包装：调 `skill_loader.skill_list()`，返回序列化为 JSON 字符串，异常转 `{"ok": false, "error": "..."}`
- [x] 2.2 在 `backend/engine/_harness/skill_tools.py` 中实现 `skill_view(name)` 薄包装：调 `skill_loader.skill_view()` 获取 `source` 路径，直接读原始文件返回完整文本（含 frontmatter，无论是否有效 YAML），异常转 `{"ok": false, "error": "..."}`
- [x] 2.3 在 `backend/engine/_harness/skill_tools.py` 中实现 `skill_create(name, description, content, tags=None)` 薄包装：调 `skill_loader.skill_create()`
- [x] 2.4 在 `backend/engine/_harness/skill_tools.py` 中实现 `skill_edit(name, content, raw=False)` 薄包装：调 `skill_loader.skill_edit()`
- [x] 2.5 在 `backend/engine/_harness/skill_tools.py` 中实现 `skill_delete(name, absorbed_into=None)` 薄包装：调 `skill_loader.skill_delete()`
- 所有包装函数统一返回格式 `{"ok": true, "result": "..."}` 或 `{"ok": false, "error": "..."}`

## 3. Tool 注册与路由

- [x] 3.1 在 `backend/engine/_harness/tools.py` 中新增 `SKILL_LIST_TOOL`、`SKILL_VIEW_TOOL`、`SKILL_CREATE_TOOL`、`SKILL_EDIT_TOOL`、`SKILL_DELETE_TOOL` 五个 schema 常量
- [x] 3.2 在 `backend/engine/_harness/tools.py` 的 `get_all_tools()` 函数中追加五个 skill tool schema
- [x] 3.3 在 `backend/engine/_harness/tool_executor.py` 的 `_execute_single_tool_call()` 中新增 `skill_list`、`skill_view`、`skill_create`、`skill_edit`、`skill_delete` 五个 elif 路由分支。**注意**：skill 工具返回的是 `{"ok": true, "result": "..."}` 格式，不是 pipeline 工具的 JSON 字符串格式，路由时不应做 `json.loads`，应直接返回 skill_tools 函数的返回 dict

## 4. Prompt 集成

- [x] 4.1 在 `backend/prompts/_loader.py` 中新增 `load_skill(name)` 函数，调 `utils.skill_loader.skill_view()` 获取 body。**注意**：`skill_view` 失败时返回 `{"error": "..."}`，`load_skill` 应捕获此情况返回空字符串 `""` 并记录 warning 日志
- [x] 4.2 在 `backend/prompts/chat/system.md` 中添加 Skill 系统说明段，告知 LLM 五个 skill 工具（skill_list / skill_view / skill_create / skill_edit / skill_delete）的用法，引用 `skill-authoring` 写作指南
- [x] 4.3 在 `backend/prompts/_loader.py` 中新增 `build_system_prompt()` 函数，封装 system prompt 的组装逻辑，含自动加载的 skill 注入。**实现方式**：
  ```python
  def build_system_prompt() -> str:
      prompt = load_prompt("chat/system")
      from utils.skill_loader import skill_list
      skills = skill_list()
      for s in skills:
          if "system" in (s.get("tags") or []):
              body = load_skill(s["name"])
              if body:
                  prompt += "\n\n" + body
      return prompt
  ```
- [x] 4.4 将 `backend/engine/agent.py:79`、`backend/engine/runner.py:59`、`backend/api/service.py:136` 中 `load_prompt("chat/system")` 替换为 `build_system_prompt()`。**注意**：
  - `system.md` 第 39 行已有 `"- See skill: goal-execution for detailed workflow"`，这是一个指令性的引用（引导 LLM 调 `skill_view("goal-execution")` 查看），**保留不动**

## 5. 预置 skill

- [x] 5.1 创建 `backend/prompts/skill/skill-authoring/SKILL.md`：meta-skill，指导 LLM 如何编写 skill（body 结构、命名规则、触发条件、skill_create/skill_edit/skill_delete 调用示例，不涉及 frontmatter 编写——因为 frontmatter 由系统自动生成）
- [x] 5.2 将 `backend/prompts/skill/goal-execution.md` 迁移为子目录格式：创建 `goal-execution/SKILL.md`，添加 YAML frontmatter（name: goal-execution, description: "指导 Agent 自主执行复杂多步目标的工作流（拆解→执行→记录→失败恢复）", tags: [system, goal, execution, workflow]），删除旧平面文件

## 5b. 修复遗留问题

- [x] 5b.1 删除 `backend/prompts/chat/system.md` 第 17 行的 `edit_pipeline(...)` 僵尸引用（该 tool 已被拆分为 `pipeline_add_step`/`pipeline_update_step`/`pipeline_remove_step` 等）

## 6. 验证

- [x] 6.1 验证 `skill_list` 能列出 `goal-execution` 和 `skill-authoring` skill，返回正确的 name/description/tags
- [x] 6.2 验证 `skill_view("goal-execution")` 和 `skill_view("skill-authoring")` 能返回完整内容（含 frontmatter）
- [x] 6.3 验证 `skill_create` 能创建新 skill，`skill_edit` 能更新 body，`skill_delete` 能删除
- [x] 6.4 验证路径穿越防护：非法 name（含 `..`、大写、连字符开头/结尾、空字符串）被白名单正则拒绝
- [x] 6.5 验证 `load_skill("goal-execution")` 能返回去掉 frontmatter 的 body
