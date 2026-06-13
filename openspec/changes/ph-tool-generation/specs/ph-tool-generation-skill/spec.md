## ADDED Requirements

### Requirement: Skill 触发条件
当 pipeline 遇到 `tool_name` 以 `_PH-` 开头的 step 时，主 agent MUST 使用 `ph-tool-generation` skill 进行编排，而非直接调用 `ToolRunner.generate_ph_tool()`。

#### Scenario: 检测到 _PH- 前缀的步骤
- **WHEN** pipeline 执行到一个 step，其 `tool_name` 为 `_PH-extract_table`
- **THEN** 主 agent MUST 加载 `ph-tool-generation` skill
- **AND** 按 skill 定义的 14 个原子操作顺序执行编排流程

#### Scenario: 非 _PH- 前缀的步骤
- **WHEN** pipeline 执行到一个 step，其 `tool_name` 为 `csv_parser`（不以 `_PH-` 开头）
- **THEN** 主 agent MUST NOT 使用 `ph-tool-generation` skill
- **AND** 走正常的工具执行路径

### Requirement: 原子操作编排流程
Skill MUST 定义 14 个原子操作的完整编排流程，按编号顺序执行：

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
| 13 | `rename_tool` | 依次调用 `rename_ph_file()` 和 `update_pipeline_refs()`；若后者失败则执行补偿回滚 |

#### Scenario: 正常流程全部通过
- **WHEN** subagent 生成的代码通过所有验收检查（文件存在、语法正确、import 在白名单中、语义正确）
- **THEN** 流程 MUST 继续执行 `exec_tool`（原子操作 11）
- **AND** 执行成功后 MUST 执行 `validate_output`（原子操作 12）
- **AND** 验证通过后 MUST 执行 `rename_tool`（原子操作 13）

#### Scenario: 文件不存在
- **WHEN** 原子操作 6（`verify_file_exists`）发现目标文件不存在
- **THEN** 流程 MUST 回到原子操作 5（`spawn_generator`），重新委托 subagent 生成代码
- **AND** 重试计数 MUST 加 1

#### Scenario: 语法错误
- **WHEN** 原子操作 7（`verify_syntax`）使用 `ast.parse` 发现语法错误
- **THEN** 流程 MUST 回到原子操作 5（`spawn_generator`），重新委托 subagent 生成代码
- **AND** 错误信息 MUST 包含具体的语法错误位置和内容

#### Scenario: import 不在白名单中
- **WHEN** 原子操作 8（`verify_imports`）发现代码使用了不在 whitelist 中的库
- **THEN** 流程 MUST 回到原子操作 5（`spawn_generator`）
- **AND** 反馈信息 MUST 明确指出违规的库名
- **AND** 反馈信息 MUST 强调 whitelist 是硬性红线

#### Scenario: 语义验收不通过
- **WHEN** 原子操作 9（`verify_semantics`）发现代码未正确实现 step 描述的功能
- **THEN** 流程 MUST 执行原子操作 10（`give_feedback`），将具体问题发给 subagent
- **AND** subagent MUST 基于反馈修改代码后重新写入
- **AND** 流程 MUST 执行原子操作 10a（`re_read_file`），主 agent 重新从磁盘读取文件
- **AND** 流程 MUST 回到原子操作 9 重新验收

#### Scenario: 执行时 SYNTAX_ERROR
- **WHEN** 原子操作 11（`exec_tool`）调用 `load_and_call` 返回 SYNTAX_ERROR
- **THEN** 流程 MUST 回到原子操作 5（`spawn_generator`），重新生成代码

#### Scenario: 执行时 RUNTIME_ERROR
- **WHEN** 原子操作 11（`exec_tool`）调用 `load_and_call` 返回 RUNTIME_ERROR
- **THEN** 流程 MUST 重试执行（最多 3 次）
- **AND** 3 次后仍失败 MUST 标记为 failed

#### Scenario: 反馈迭代达到上限
- **WHEN** 反馈迭代（原子操作 9 → 10 → 10a → 5 → 9）达到最大轮数 3 次仍未通过语义验收
- **THEN** 流程 MUST 标记为 failed
- **AND** MUST 记录子 agent 完整对话日志供排查

#### Scenario: rename 半成功时执行补偿
- **WHEN** 原子操作 13（`rename_tool`）中 `rename_ph_file()` 返回 `{"ok": True}`
- **AND** 随后 `update_pipeline_refs()` 返回 `{"ok": False}`
- **THEN** agent 编排层 MUST 将文件改回原名（`xxx.py` → `_PH-xxx.py`）
- **AND** MUST 返回错误信息说明 rename 失败原因
- **AND** MUST NOT 标记 step 为 completed

#### Scenario: 补偿操作也失败
- **WHEN** 回滚重命名也失败（如权限问题）
- **THEN** MUST 记录错误日志，包含当前文件状态
- **AND** MUST 标记 step 为 failed，提示人工介入

### Requirement: Subagent Goal 模板
Skill MUST 包含标准化的 subagent goal 模板，模板 MUST 包含步骤定义、上游输入文件摘要、可用库白名单、约束条件和任务描述。

#### Scenario: Goal 模板包含 whitelist 约束
- **WHEN** 组装 subagent goal（原子操作 4）
- **THEN** goal 文本 MUST 包含完整的 whitelist 信息（stdlib 列表、bundled_deps 列表、forbidden 列表）
- **AND** goal 文本 MUST 明确说明"只能从 whitelist 中 import"

#### Scenario: Goal 模板包含输入文件摘要
- **WHEN** 组装 subagent goal（原子操作 4）
- **THEN** goal 文本 MUST 包含上游输入文件的前 500 字符摘要
- **AND** 摘要 MUST 包含文件路径和内容预览

#### Scenario: Goal 模板包含函数签名约束
- **WHEN** 组装 subagent goal（原子操作 4）
- **THEN** goal 文本 MUST 要求生成的函数签名为 `{real_name}(input_files, output_dir, **params) -> None`
- **AND** goal 文本 MUST 要求代码写入 `{tools_dir}/{ph_name}.py`

### Requirement: 语义验收指南
Skill MUST 包含语义验收指南，定义通用检查项和场景相关检查项。通用检查项 MUST 包括函数签名、输入输出处理、错误保护、import 白名单。场景相关检查项 MUST 按 step description 的自然语言语义判断。

#### Scenario: 通用检查——函数签名
- **WHEN** 主 agent 执行语义验收（原子操作 9）
- **THEN** MUST 检查生成的函数签名是否为 `{real_name}(input_files, output_dir, **params)`

#### Scenario: 通用检查——输入输出处理
- **WHEN** 主 agent 执行语义验收（原子操作 9）
- **THEN** MUST 检查代码是否读取了 `input_files` 中的文件
- **AND** MUST 检查代码是否写入了输出到 `output_dir`

#### Scenario: 通用检查——错误保护
- **WHEN** 主 agent 执行语义验收（原子操作 9）
- **THEN** MUST 检查代码是否有基本的 try/except 保护

#### Scenario: 场景检查——提取表格类
- **WHEN** step description 描述为"从 HTML 中提取表格并输出 CSV"
- **THEN** 主 agent MUST 检查代码是否使用了 `html.parser`（在 whitelist 中）
- **AND** MUST 检查代码能否处理空表格或格式异常的情况
- **AND** MUST 检查输出是否为 CSV 格式

#### Scenario: 场景检查——调用 API 类
- **WHEN** step description 描述为"调用远程 API 获取数据"
- **THEN** 主 agent MUST 检查代码是否使用了 `aiohttp`（而非 `requests`——requests 不在 whitelist 中）
- **AND** MUST 检查代码是否有重试和超时处理

### Requirement: 上游输入文件样本获取
在原子操作 2（`collect_input_files`）中，主 agent MUST 读取上游输入文件内容作为 subagent goal 的上下文。由于 `_sniff_input_file()` 已随 `ToolRunner` 瘦身删除，主 agent MUST 自行读取文件。

#### Scenario: 读取输入文件样本
- **WHEN** 主 agent 执行原子操作 2（`collect_input_files`）
- **THEN** MUST 从 `input_files` 字典中获取文件路径
- **AND** MUST 读取每个文件的前 500 字符作为样本
- **AND** 对于 HTML 文件 SHOULD 统计 `<div>` 和 `<table>` 标签数量
- **AND** 对于 CSV 文件 SHOULD 读取前 20 行
- **AND** 对于 JSON 文件 SHOULD 读取前 1000 字符

#### Scenario: 输入文件不存在
- **WHEN** `input_files` 中某个路径指向的文件不存在
- **THEN** 样本 MUST 标注 `(file not found: <path>)`
- **AND** MUST NOT 中断整个流程

### Requirement: 反馈迭代规范
当语义验收发现问题时，主 agent MUST 给出具体、可操作的反馈，而非简单的"失败"。反馈 SHOULD 包含具体行号和修改建议。

#### Scenario: 给出具体反馈
- **WHEN** 语义验收发现代码用正则解析 HTML 但不够健壮
- **THEN** 反馈 MUST 包含具体问题描述（如"用正则解析 HTML 在复杂表格面前很脆弱"）
- **AND** 反馈 MUST 包含修改建议（如"改用 `html.parser` 解析，同时处理空表格的情况"）
- **AND** 反馈 SHOULD 包含具体行号（如"第 15 行 `print()` 应该是 `f.write()`"）

#### Scenario: 反馈后 subagent 修改代码
- **WHEN** subagent 收到反馈
- **THEN** subagent MUST 基于反馈修改代码
- **AND** subagent MUST 保留已生成的合理部分，只修复问题
- **AND** subagent MUST 将修改后的代码重新写入同一文件路径
