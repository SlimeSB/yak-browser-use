---
name: ph-tool-generation
description: "编排 _PH- 工具代码的生成、验收、执行和重命名全流程"
version: 1.0.0
metadata:
  tags: [ph-tool, code-generation, pipeline]
---

# PH-Tool Generation

## Trigger

当 pipeline 执行到 `tool_name` 以 `_PH-` 开头的 step，且对应的工具文件 `tools_dir/_PH-xxx.py` 不存在时，使用本 skill 编排代码生成流程。

## Workflow

按以下 14 个原子操作顺序执行：

### Step 1: read_step_definition

读取 step 定义，提取：
- `tool_name`：带 `_PH-` 前缀的工具名
- `real_name`：去掉前缀后的工具名（即 `tool_name[4:]`）
- `description`：步骤描述
- `params`：参数
- `output`：期望的输出文件列表

### Step 2: collect_input_files

从 `input_files` 字典中获取上游文件路径，读取每个文件的内容样本：
- 普通文件：前 500 字符
- HTML 文件：前 2000 字符，统计 `<div>` 和 `<table>` 标签数量
- CSV 文件：前 20 行
- JSON 文件：前 1000 字符

如果文件不存在，标注 `(file not found: <path>)`，不中断流程。

### Step 3: confirm_target_dir

确认 `tools_dir` 和 `output_dir` 路径存在。不存在则创建。

### Step 4: assemble_subagent_goal

组装 subagent 的 goal 模板，必须包含：
- Step 定义（tool_name、real_name、description、params、output）
- 上游输入文件样本（从 Step 2 获取）
- **Whitelist 约束**：读取 `runtime-whitelist.json`，列出 stdlib 和 bundled_deps 可用库，明确说明"只能从 whitelist 中 import"
- 函数签名要求：`def {real_name}(input_files: dict[str, str], output_dir: str, **params) -> None`
- 输出要求：代码写入 `{tools_dir}/{ph_name}.py`

### Step 5: spawn_generator

委托 subagent 根据 goal 模板生成代码并写入 `{tools_dir}/{ph_name}.py`。

### Step 6: verify_file_exists

检查 `{tools_dir}/{ph_name}.py` 是否已写入。
- 不存在 → 回到 Step 5，重试计数 +1

### Step 7: verify_syntax

用 `ast.parse` 检查生成的代码语法是否正确。
- 语法错误 → 回到 Step 5，附带错误信息

### Step 8: verify_imports

检查代码中所有 `import` 语句是否在 whitelist（stdlib + bundled_deps）中。
- 违规 → 回到 Step 5，附带违规库名和"whitelist 是硬性红线"的强调

### Step 9: verify_semantics

主 agent 语义验收：读取生成的代码，对照 step description 判断代码是否真正实现了描述的功能。

**通用检查项：**
- 函数签名是否为 `{real_name}(input_files, output_dir, **params)`
- 是否读取了 `input_files` 中的文件
- 是否写入了输出到 `output_dir`
- 是否有基本的 try/except 错误保护

**场景相关检查项（按 description 判断）：**
- 提取表格类：是否用了 `html.parser`（而非正则）、能否处理空表格、输出是否为 CSV
- 调用 API 类：是否用了 `aiohttp`（而非 `requests`）、是否有重试和超时
- 数据处理类：是否正确处理了边界情况（空数据、格式异常等）

### Step 10: give_feedback

如果语义验收不通过，给出具体、可操作的反馈：
- 具体问题描述（不要只说"失败"）
- 修改建议
- 尽量包含行号

### Step 10a: re_read_file

**主 agent 必须从磁盘重新读取文件**，避免持有 subagent 修改前的旧内容做验收。

### Step 11: exec_tool

调用 `ToolRunner.load_and_call()` 执行工具：
- SYNTAX_ERROR → 回到 Step 5
- RUNTIME_ERROR → 重试执行（最多 3 次），3 次后仍失败标记 failed

### Step 12: validate_output

调用 `Guardian.validate_output()` 验证产出文件。

### Step 13: rename_tool

依次执行：
1. `rename_ph_file()` — 将 `_PH-xxx.py` 重命名为 `xxx.py`
2. `update_pipeline_refs()` — 更新 pipeline YAML 中的工具名引用

**补偿逻辑：**
- `rename_ph_file()` 成功 + `update_pipeline_refs()` 失败 → 将文件改回原名（`xxx.py` → `_PH-xxx.py`）
- 补偿也失败 → 标记 failed，提示人工介入

## Feedback Loop

反馈迭代流程：Step 9 → Step 10 → Step 5 → ... → Step 9（最多 3 轮）
3 轮后仍未通过语义验收 → 标记 failed，记录子 agent 完整对话日志。

## Whitelist Constraints

- 只能 import `runtime-whitelist.json` 中 `stdlib` 和 `bundled_deps` 里的库
- `forbidden` 列表为参考，不在 stdlib 或 bundled_deps 中的 import 都会被拒绝
- whitelist 是硬性红线——客户机 EXE 中不存在未打包的库

## Pitfalls

- subagent 可能用 `requests` 代替 `aiohttp`（requests 不在 whitelist 中）
- subagent 可能用正则解析 HTML 而非 `html.parser`
- 语义验收时主 agent 必须重新读取文件（Step 10a），否则可能验收的是旧代码
- rename 半成功状态需要补偿回滚
- 文件写入 `tools_dir` 可能有权限问题，fallback：主 agent 代写
