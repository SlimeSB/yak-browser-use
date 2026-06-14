## 背景

当前 `ToolRunner.generate_ph_tool()` 是一个单体 LLM 调用——通过 `_build_generation_prompt()` 构建 prompt，调用 `llm_call_fn` 生成代码，`_extract_code()` 提取后写入文件。`run_ph_lifecycle()` 在此基础上加了最多 3 次重试循环。整个流程存在三个核心问题：

1. **无场景语义验收**：语法检查太弱，会放行逻辑错误的代码；固定规则太死板，不同场景需要不同的评判标准
2. **无 whitelist 约束**：LLM 可能生成 `import pandas` / `import requests` 等代码，在 PyInstaller 单 EXE 部署环境下直接崩溃
3. **无 feedback 迭代**：生成失败只能推倒重来，无法保留已生成的合理部分做增量修复

本项目的最终交付形态是 PyInstaller 单 EXE（含 Chromium），客户机上没有 Python、没有 uv、没有 pip。生成的 `_PH-` 工具代码只能使用 Python stdlib 和 `pyproject.toml` 中声明的依赖。

## 架构对比

### 当前状态

```
Pipeline
  ↓
_execute_tool_step_with_guardian
  ↓  (if _PH-)
run_ph_lifecycle (loop retry ×3)
  ↓
generate_ph_tool  ───→  _build_generation_prompt
  ↓                         ↓
load_and_call           _sniff_input_file
  ↓
atomic_rename_ph (file + YAML 耦合)
```

问题：单体 LLM 调用，无语义检查，无 whitelist 红线，无 feedback 迭代，文件移动和 YAML 引用更新绑在一起。

### 未来状态

```
Pipeline runner_preset
  ↓  (if _PH-)
┌─ 纯门禁：文件存在？→ 执行 | 不存在 → TOOL_NOT_GENERATED
└─ agent 通过 skill 文档编排生成

Skill: ph-tool-generation (prompts/skill/ph-tool-generation.md)
┌── 1.  read_step_definition
│   2.  collect_input_files
│   3.  confirm_target_dir
│   4.  assemble_subagent_goal (含 whitelist)
│   5.  spawn_generator ────────────────────────────┐
│   6.  verify_file_exists ─── 失败？───────────────┤
│   7.  verify_syntax (ast.parse) ── 失败？────────┤
│   8.  verify_imports (whitelist 红线) ─ 失败？───┤
│   9.  verify_semantics (LLM) ── 失败？─→ 10. feedback → 10a. re_read → 5 (×3)
│   11. exec_tool (load_and_call)
│   12. validate_output (Guardian)
└── 13. rename_tool (rename_ph_file + update_pipeline_refs + 补偿回滚)
```

## 目标 / 非目标

**目标：**
- 将单体 LLM 调用拆解为原子化的 agent 编排流程（subagent 生成 + 主 agent 验收）
- 引入 `runtime-whitelist.json` 作为硬性红线，确保生成的代码在客户机 EXE 中可用
- 实现语义验收 + feedback 迭代模式，提升生成成功率
- 将编排流程定义为 skill 文档（`prompts/skill/ph-tool-generation.md`），由 `skill_view()` 加载，便于复用和维护
- 瘦身 `ToolRunner`，只保留纯执行原子操作

**非目标：**
- 不改变 `tools/` 目录下动态 import 的执行路径
- 不修改 Guardian 验证逻辑
- 不涉及前端 UI 变更
- 不改变 pipeline YAML 的结构定义

## 原子操作编排流程（14 步）

Hermes skill `prompts/skill/ph-tool-generation.md` 定义的编排流程按以下编号顺序执行：

| # | 操作名 | 说明 |
|---|--------|------|
| 1 | `read_step_definition` | 读取 step 定义（tool_name、description、params、output） |
| 2 | `collect_input_files` | 汇总上游输入文件路径，读取文件内容样本（前 500 字符） |
| 3 | `confirm_target_dir` | 确认 `tools_dir` 和 `output_dir` 路径存在 |
| 4 | `assemble_subagent_goal` | 组装 subagent goal 模板（含 step 定义、输入样本、whitelist、约束） |
| 5 | `spawn_generator` | 委托 subagent 生成代码并写入 `{tools_dir}/{ph_name}.py` |
| 6 | `verify_file_exists` | 检查目标文件是否已写入 |
| 7 | `verify_syntax` | 用 `ast.parse` 检查语法正确性 |
| 8 | `verify_imports` | 检查所有 import 是否在 whitelist（stdlib + bundled_deps）中 |
| 9 | `verify_semantics` | 主 agent 语义验收：代码是否实现了 step description 描述的功能 |
| 10 | `give_feedback` | 将语义验收发现的问题反馈给 subagent，要求增量修复 |
| 10a | `re_read_file` | 主 agent 重新读取文件，避免持有旧内容做验收 |
| 11 | `exec_tool` | 调用 `ToolRunner.load_and_call()` 执行工具 |
| 12 | `validate_output` | 调用 `Guardian.validate_output()` 验证产出文件 |
| 13 | `rename_tool` | 依次调用 `rename_ph_file()` 和 `update_pipeline_refs()`，含补偿逻辑 |

## 关键决策

### 0. Skill 加载机制

Agent 需要一种按名称加载 skill 工作流的方式。`skill_view('ph-tool-generation')` 是 Hermes 框架的函数，不在本项目内。方案：手搓一个轻量版。

```
skill_view(name)
  → 在 prompts/skill/{name}.md 查找文件
  → 解析 YAML frontmatter
  → 返回 {metadata, body, linked_files}
```

位置：`utils/skill_loader.py` 或内联到 agent 工具集。具体放在哪个模块由实施阶段决定。

### 1. 反馈迭代中的文件重新读取

在 `give_feedback`（步骤 10）之后、subagent 重新生成代码之后、主 agent 再次验收之前，添加 `re_read_file`（步骤 10a）：主 agent 必须从磁盘重新读取文件内容，避免持有旧版本做验收。

原因：
- subagent 修改代码后写入同一文件路径，主 agent 的上下文可能仍保留旧代码
- 不重新读取会导致"改对了但验收的是旧代码"的假阳性失败
- 此步骤是 agent 编排层的约定，不需要 Python 层支持

### 2. 语义验收 + 反馈迭代 vs 传统语法检查

选择语义验收模式。原因：
- 语法检查只能发现 `SyntaxError`，无法发现逻辑错误（如"用正则解析 HTML 提取表格"虽然语法正确但功能脆弱）
- 固定规则（如"函数名必须包含 X"）太死板，不同场景需要不同的评判标准
- 场景相关的语义验收只有 LLM 能做到——主 LLM 读取 step description 和生成的代码，判断代码是否真的实现了描述的功能
- 给反馈让 subagent 修复而非推倒重来，保留已生成的合理部分，节省 token

### 3. 分层设计：Python 层 vs Agent 编排层

Python 层（`ToolRunner`）只保留纯执行原子操作（load、exec、rename），Agent 编排层（skill 文档 + `skill_view()`）负责构建上下文 → spawn subagent 生成 → 语义验收 → 反馈迭代。原因：
- Python 层操作是确定性的，不需要 LLM 参与
- Agent 编排层需要 LLM 的判断能力（语义验收），放在 skill 中更灵活
- 分层后各自职责清晰，便于测试和维护

### 4. whitelist 作为硬性红线

`verify_imports` 在 `verify_semantics` 之前执行，import 不在 whitelist 中直接打回。原因：
- 这是 runtime 硬性约束——客户机 EXE 中不存在未打包的库，import 就会崩溃
- 先做 import 检查可以避免语义验收通过但 runtime 崩溃的情况
- whitelist 需要随 `pyproject.toml` 同步更新

### 5. `atomic_rename_ph` 拆分为两个独立操作 + 补偿逻辑

将原有的 `atomic_rename_ph()` 拆为 `rename_ph_file()`（纯文件移动）和 `update_pipeline_refs()`（纯 YAML 引用更新）。原因：
- 两个操作职责不同，拆分后 agent 编排层可以更精细地控制流程
- 文件移动失败不影响 pipeline YAML，反之亦然
- 便于单独测试和错误处理

**补偿逻辑**：当 `rename_ph_file()` 成功但 `update_pipeline_refs()` 失败时，agent 编排层必须将文件改回原名（`xxx.py` → `_PH-xxx.py`），避免系统处于文件已改名但 YAML 仍引用旧名的半成功状态。如果补偿操作也失败，标记 step 为 failed 并提示人工介入。

### 6. `runner_preset` 的 _PH- 分支改为纯门禁

`_execute_tool_step_with_guardian` 的 `_PH-` 分支不再编排任何流程，只检查工具文件是否存在。原因：
- 代码生成已由 agent 编排层（Hermes skill）负责
- runner_preset 只需确保执行前文件已就绪
- 简化后 runner_preset 不再依赖 LLM 回调，移除 `llm_call_fn` 参数

## 风险 / 权衡

| 风险 | 严重度 | 缓解 |
|:-----|:------:|:-----|
| `llm_call_fn` 参数散布多处调用点 | 🟡 | Task 5 grep 全量扫描，确保无遗漏 |
| 现有测试覆盖了 `run_ph_lifecycle` | 🟡 | Task 7 确认测试用例是否需要更新或删除 |
| subagent 写文件到 `tools_dir` 权限问题 | 🟡 | skill 注明 fallback：主 agent 代写 |
| whitelist 有遗漏——subagent 用了不在列表中的 stdlib 库 | 🟡 | 主 LLM 语义验收时做 import 检查，发现遗漏则补充到 `runtime-whitelist.json` |
| 未来新增依赖忘记更新 whitelist | 🟡 | 在 `pyproject.toml` 新增依赖时需同步更新 `runtime-whitelist.json` 的 bundled_deps。可选方案：将来在 CI 中加一个脚本对比两者是否一致 |
| 语义验收过度消耗主 LLM tokens | 🟢 | 只验收生成的代码（通常 <200 行），tokens 可控 |
| feedback 循环无法收敛 | 🟢 | 设最大轮数 3，超限标记 failed，记录子 agent 完整对话日志供排查 |
| rename 半成功（文件改名但 YAML 更新失败） | 🟡 | agent 编排层执行补偿：将文件改回原名；补偿失败则标记 failed 提示人工介入 |

## 迁移计划

1. 新建 `runtime-whitelist.json`（Task 1）
2. 新建 `utils/skill_loader.py`——轻量版 `skill_view()`（Task 2.0）
3. 新建 `prompts/skill/ph-tool-generation.md`（Task 2.1）— 先用 `skill_view()` 验证可加载，再逐步完善
4. 简化 `ToolRunner`，删除生成方法，拆分 `atomic_rename_ph`（Task 2.2, 2.3）
5. 简化 `runner_preset.py`，_PH- 分支改为纯门禁（Task 2.4）
6. 清理 `llm_call_fn` 参数：只改 `run_pipeline` 签名，外部调用点已无传参（Task 2.5）
7. 适配 CLI 工具命令；顺手修 `cli/tools.py:190` 的构造函数参数 bug（Task 2.6）
8. 测试验证（Task 3）

回滚：恢复 `tool_runner.py`、`runner_preset.py`、`cli/tools.py` 的旧版本，删除 `runtime-whitelist.json`、`utils/skill_loader.py`、`prompts/skill/ph-tool-generation.md`。

## 待确认问题

- 无
