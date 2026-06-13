## Why

当前 `ToolRunner.generate_ph_tool()` 是单体 LLM 调用——一次 prompt 生成完整工具代码，缺少场景语义验收。LLM 生成的代码可能使用了不在 whitelist 中的库（如 pandas、requests），在 PyInstaller 单 EXE 部署环境下会直接崩溃。此外，生成失败时缺少 feedback 迭代机制，只能推倒重来，浪费 token 且成功率低。

本次变更将单体生成拆解为原子化的 agent 编排流程：subagent 负责代码生成+写文件，主 agent 按场景语义验收，发现问题给反馈让 subagent 修复，流程定义为 skill 文档（`prompts/skill/ph-tool-generation-skill.md`）由 `skill_view()` 加载。同时引入 `runtime-whitelist.json` 作为硬性红线，确保生成的代码在客户机 EXE 环境中可用。

## What Changes

- **新建** `runtime-whitelist.json` — subagent 可用库白名单配置，分 stdlib / bundled_deps / forbidden 三类，作为 runtime 环境的真相源
- **新建** `utils/skill_loader.py` — 轻量版 `skill_view(name)`，按名称从 `prompts/skill/` 加载 skill 文档
- **新建** `prompts/skill/ph-tool-generation-skill.md` — skill 工作流文档（借 Hermes 格式：YAML frontmatter + Markdown body），含 14 个原子操作编排、whitelist 约束、语义验收指南和反馈迭代模式
- **简化** `ToolRunner` — 删除 `generate_ph_tool()`、`run_ph_lifecycle()` 等约 250 行生成代码；将 `atomic_rename_ph()` 拆为 `rename_ph_file()` 和 `update_pipeline_refs()` 两个独立原子操作
- **简化** `runner_preset.py` — `_PH-` 分支改为纯门禁（只检查文件是否存在），删除 `_default_llm_call_fn()`、`_PH_PREFIX` 常量、`llm_call_fn` 参数
- **清理调用链** — 移除所有 `run_pipeline(llm_call_fn=...)` 调用点中的 `llm_call_fn` 参数
- **适配 CLI** — `cli/tools.py` 中的 `_cmd_tool_run_ph` 改为调用简化后的原子操作
- **测试验证** — 确保所有现有测试通过，无残留引用

## Capabilities

### New Capabilities
- `runtime-whitelist`: 运行时库白名单配置，定义 subagent 生成代码时可用的 Python 库范围，作为 PyInstaller EXE 部署的硬性约束
- `ph-tool-generation-skill`: skill 编排流程，将 _PH- 工具代码生成拆解为 14 个原子操作（含 feedback 循环中的 `re_read_file`），含语义验收和反馈迭代。定义在 `prompts/skill/ph-tool-generation-skill.md`，由 `skill_view()` 加载
- `tool-runner-simplify`: ToolRunner 瘦身，删除单体生成逻辑，拆分为纯执行原子操作
- `preset-gate-only`: runner_preset 的 _PH- 分支简化为纯门禁检查，不再编排任何流程

## Impact

- **代码**：`engine/_lifecycle/tool_runner.py`（删 ~250 行，改 ~30 行）、`engine/runner_preset.py`（改 ~20 行，删 ~15 行）、`cli/tools.py`（改 ~20 行）
- **配置**：新建 `runtime-whitelist.json`（项目根目录）
- **工具**：新建 `utils/skill_loader.py`（~30 行）
- **Skill 文档**：新建 `prompts/skill/ph-tool-generation-skill.md`
- **调用链**：所有 `run_pipeline(llm_call_fn=...)` 调用点需移除 `llm_call_fn` 参数
- **测试**：需确认现有测试用例是否需要更新（部分测试可能覆盖了被删除的方法）
- **向后兼容**：`run_pipeline` 签名变更（移除 `llm_call_fn`）是 **BREAKING** 变更，所有调用方需同步更新
