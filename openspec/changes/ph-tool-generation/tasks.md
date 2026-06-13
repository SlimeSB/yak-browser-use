## 1. 准备与基础改造

- [x] 1.1 新建 `runtime-whitelist.json`：在项目根目录创建白名单配置文件，包含 `stdlib`、`bundled_deps`、`forbidden` 三个数组，以及 `description` 和 `notes` 说明字段
- [x] 1.2 验证 `runtime-whitelist.json` 格式：用 `python -c "import json; json.load(open('runtime-whitelist.json'))"` 确认 JSON 格式正确，且 `bundled_deps` 与 `pyproject.toml` 的运行时依赖一致
- [x] 1.3 删除 `prompts/generate-ph-tool.md`：该文件是旧的 LLM prompt 模板，代码生成逻辑已迁移到 `prompts/skill/ph-tool-generation.md` 和 `skill_view()`，不再需要

## 2. 核心实现

- [x] 2.0 新建 `utils/skill_loader.py`：实现轻量版 `skill_view(name)`，在 `prompts/skill/{name}.md` 查找文件，解析 YAML frontmatter，返回 `{metadata, body, linked_files}`。支持 `prompts/skill/` 和可配置的额外路径
- [x] 2.1 新建 `prompts/skill/ph-tool-generation.md`：
  - 创建最小化版本（14 步工作流骨架 + whitelist 约束 + 语义验收指南 + 反馈迭代规范），用 `skill_view('ph-tool-generation')` 验证可加载
  - 再逐步完善细节（场景相关检查项、子 agent goal 模板等），确保与 spec 和 design.md 一致。**注意**：feedback 循环中步骤 10 `give_feedback` 之后有步骤 10a `re_read_file`（主 agent 重新读取文件再验收），需在 skill 文档中体现
  - 格式：YAML frontmatter + Markdown body（参考 `docs/hermes-skill-reference.md` 但放在项目内 `prompts/skill/` 下，不注册到 Hermes 全局目录）
- [x] 2.2 简化 `ToolRunner`——删除生成方法：从 `engine/_lifecycle/tool_runner.py` 中删除 `generate_ph_tool()`、`run_ph_lifecycle()`、`_sniff_input_file()`、`_build_generation_prompt()`、`_extract_code()`，以及相关的 `DEFAULT_MAX_RETRIES` 常量和不再需要的 import。**注意**：`_replace_ph_refs()` 模块级函数 MUST 保留（`update_pipeline_refs` 依赖它进行 YAML 引用替换）
- [x] 2.3 拆分 `atomic_rename_ph`：将 `atomic_rename_ph()` 拆为 `rename_ph_file()`（纯文件移动）和 `update_pipeline_refs()`（纯 YAML 引用更新）两个独立方法。`update_pipeline_refs` 内部调用保留的 `_replace_ph_refs()` 进行引用替换
- [x] 2.4 简化 `runner_preset.py`——_PH- 分支改为纯门禁：将 `_execute_tool_step_with_guardian` 的 `_PH-` 分支替换为纯文件存在性检查，删除 `_default_llm_call_fn()` 函数和 `_PH_PREFIX` 常量
- [x] 2.5 移除 `run_pipeline` 的 `llm_call_fn` 参数：从 `run_pipeline()` 函数签名中删除 `llm_call_fn` 参数。**注意**：扫描确认 4 个外部调用点（`api/routes.py`×2、`cli/run.py`、`cli/pipeline.py`）均未传 `llm_call_fn`，只需改签名 + 清理 `runner_preset.py` 内部经过路径，外部调用点不需要改行
- [x] 2.6 适配 CLI 工具命令：
  - `_cmd_tool_prompt`：先改为硬编码输出一段 subagent goal 模板文本（不再依赖 `_build_generation_prompt`）。后续阶段再改为通过 `skill_view()` 读取 skill 文档中的模板内容
  - `_cmd_tool_run_ph`：改为调用简化后的原子操作（tool_exists → load_and_call → guardian.validate_output → rename_ph_file + update_pipeline_refs）
  - **顺手修** `ToolRunner` 构造函数参数 bug：`cli/tools.py:190` 当前传了 4 个参数 `ToolRunner(wm.tools_dir, parsed.name, events, guardian)` 但 `__init__` 只接受 3 个（`tools_dir, pipeline_name, guardian`），`events` 被错误传给了 `guardian` 形参。修改为 `ToolRunner(wm.tools_dir, parsed.name, guardian)`

## 3. 验证与收尾

- [x] 3.1 语法检查：对 `engine/_lifecycle/tool_runner.py`、`engine/runner_preset.py`、`cli/tools.py` 执行 `ast.parse` 确认语法正确
- [x] 3.2 残留引用扫描：grep 搜索 `generate_ph_tool`、`run_ph_lifecycle`、`_sniff_input_file`、`_build_generation_prompt`、`_extract_code`、`llm_call_fn`、`_PH_PREFIX`（runner_preset.py 中）、`_default_llm_call_fn`，确认项目范围内无残留引用。**注意**：`_replace_ph_refs` MUST 仍存在于 `tool_runner.py` 中（被 `update_pipeline_refs` 调用），`_PH_PREFIX` MUST 仍存在于 `tool_runner.py` 中（被 `is_ph_tool` 和 `strip_ph_prefix` 使用）
- [x] 3.3 运行现有测试：执行 `uv run pytest tests/ -x -q` 确保所有现有测试通过
- [x] 3.4 确认 skill 可加载：用 `skill_view('ph-tool-generation')` 确认能正确解析 frontmatter 并返回 body
- [x] 3.5 确认 `runtime-whitelist.json` 与 `prompts/skill/ph-tool-generation.md` 中引用的 whitelist 内容一致
