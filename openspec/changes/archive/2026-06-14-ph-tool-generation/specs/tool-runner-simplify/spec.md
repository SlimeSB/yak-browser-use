## ADDED Requirements

### Requirement: 保留的原子操作方法
`ToolRunner` MUST 保留以下纯执行原子操作方法：`tool_exists()`、`is_ph_tool()`、`strip_ph_prefix()`、`load_and_call()`、`_clear_module_cache()`。

### Requirement: 保留模块级辅助函数
`ToolRunner` 模块 MUST 保留 `_replace_ph_refs()` 模块级辅助函数，因为新增的 `update_pipeline_refs()` 方法依赖它进行 YAML 引用替换。

#### Scenario: _replace_ph_refs 仍可用
- **WHEN** `update_pipeline_refs()` 需要替换 YAML 中的工具名引用
- **THEN** MUST 调用 `_replace_ph_refs(data, ph_name, real_name)` 递归替换所有字符串引用
- **AND** 函数 MUST 保持现有实现不变

### Requirement: 保留的原子操作方法（续）

#### Scenario: tool_exists 检查文件存在
- **WHEN** 调用 `runner.tool_exists("csv_parser")`
- **THEN** 如果 `tools_dir/csv_parser.py` 存在则返回 `True`
- **AND** 如果文件不存在则返回 `False`

#### Scenario: is_ph_tool 检查前缀
- **WHEN** 调用 `runner.is_ph_tool("_PH-extract_table")`
- **THEN** 返回 `True`
- **AND** 调用 `runner.is_ph_tool("csv_parser")` 返回 `False`

#### Scenario: strip_ph_prefix 去前缀
- **WHEN** 调用 `runner.strip_ph_prefix("_PH-extract_table")`
- **THEN** 返回 `"extract_table"`

#### Scenario: load_and_call 加载并执行
- **WHEN** 调用 `runner.load_and_call(tool_name, input_files, output_dir, **params)`
- **THEN** MUST 动态加载 `tools_dir/{tool_name}.py` 模块
- **AND** MUST 调用模块中的同名函数
- **AND** 返回 `{"ok": True}` 或 `{"ok": False, "error": ...}`

#### Scenario: _clear_module_cache 卸载缓存
- **WHEN** 调用 `runner._clear_module_cache("pipeline_tool_xxx_name")`
- **THEN** MUST 从 `sys.modules` 中移除对应模块
- **AND** 确保下次 import 时重新加载

### Requirement: 新增 rename_ph_file 方法
`ToolRunner` MUST 新增 `rename_ph_file(ph_name)` 方法，只负责文件移动操作：将 `_PH-xxx.py` 重命名为 `xxx.py`，不涉及 pipeline YAML 引用更新。

#### Scenario: 正常重命名
- **WHEN** 调用 `runner.rename_ph_file("_PH-extract_table")`
- **AND** 文件 `tools_dir/_PH-extract_table.py` 存在
- **THEN** 文件 MUST 被移动到 `tools_dir/extract_table.py`
- **AND** MUST 清除旧模块名对应的缓存
- **AND** 返回 `{"ok": True, "old": "_PH-extract_table", "new": "extract_table"}`

#### Scenario: 源文件不存在
- **WHEN** 调用 `runner.rename_ph_file("_PH-extract_table")`
- **AND** 文件 `tools_dir/_PH-extract_table.py` 不存在
- **THEN** 返回 `{"ok": False, "error": "... not found"}`

### Requirement: 新增 update_pipeline_refs 方法
`ToolRunner` MUST 新增 `update_pipeline_refs(ph_name, real_name, pipeline_path)` 方法，只负责更新 pipeline YAML 文件中的工具名引用，不涉及文件移动。

#### Scenario: 正常更新引用
- **WHEN** 调用 `runner.update_pipeline_refs("_PH-extract_table", "extract_table", pipeline_path)`
- **AND** pipeline YAML 中存在对 `_PH-extract_table` 的引用
- **THEN** YAML 中所有 `_PH-extract_table` 引用 MUST 被替换为 `extract_table`
- **AND** 返回 `{"ok": True}`

#### Scenario: pipeline 路径不存在
- **WHEN** 调用 `runner.update_pipeline_refs("_PH-extract_table", "extract_table", None)`
- **THEN** 返回 `{"ok": False, "error": "No pipeline path"}`

#### Scenario: YAML 解析失败
- **WHEN** pipeline YAML 文件存在但内容格式损坏
- **THEN** 返回 `{"ok": False, "error": ...}`，包含具体错误信息

### Requirement: rename 补偿逻辑
当 `rename_ph_file()` 成功但 `update_pipeline_refs()` 失败时，agent 编排层 MUST 执行补偿操作将文件改回原名，避免系统处于不一致状态。

#### Scenario: update_pipeline_refs 失败时回滚
- **WHEN** 原子操作 13（`rename_tool`）中 `rename_ph_file()` 返回 `{"ok": True}`
- **AND** 随后 `update_pipeline_refs()` 返回 `{"ok": False}`
- **THEN** agent 编排层 MUST 将 `extract_table.py` 改回 `_PH-extract_table.py`
- **AND** MUST 返回错误信息说明 rename 失败原因
- **AND** MUST NOT 标记 step 为 completed

#### Scenario: 补偿操作也失败
- **WHEN** 回滚重命名也失败（如权限问题）
- **THEN** MUST 记录错误日志，包含当前文件状态
- **AND** MUST 标记 step 为 failed，提示人工介入

## REMOVED Requirements

### Requirement: 移除 generate_ph_tool 方法
`ToolRunner` MUST NOT 包含 `generate_ph_tool()` 方法。代码生成逻辑已迁移到 Hermes skill `ph-tool-generation` 的 agent 编排层。

**Reason**: 单体 LLM 调用无法满足语义验收和 whitelist 约束需求，拆解为 agent 编排流程后该方法不再需要。

**Migration**: 调用方应改用 `ph-tool-generation` Hermes skill 进行代码生成编排。

#### Scenario: generate_ph_tool 不存在
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** MUST NOT 包含名为 `generate_ph_tool` 的方法

### Requirement: 移除 run_ph_lifecycle 方法
`ToolRunner` MUST NOT 包含 `run_ph_lifecycle()` 方法。生命周期编排逻辑已迁移到 Hermes skill `ph-tool-generation`。

**Reason**: 与 `generate_ph_tool` 同理，编排逻辑应由 agent 层负责。

**Migration**: 调用方应改用 `ph-tool-generation` Hermes skill 进行完整的生命周期编排。

#### Scenario: run_ph_lifecycle 不存在
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** MUST NOT 包含名为 `run_ph_lifecycle` 的方法

### Requirement: 移除辅助生成函数
`ToolRunner` 模块 MUST NOT 包含 `_sniff_input_file()`、`_build_generation_prompt()`、`_extract_code()` 三个模块级辅助函数。

**Reason**: 这些函数仅服务于已删除的 `generate_ph_tool()`，不再需要。

**Migration**: 无需迁移，这些函数的功能已融入 Hermes skill 的原子操作中。

#### Scenario: 辅助函数不存在
- **WHEN** 在 `engine/_lifecycle/tool_runner.py` 中搜索 `_sniff_input_file`、`_build_generation_prompt`、`_extract_code`
- **THEN** MUST NOT 找到任何定义或引用

### Requirement: 移除 atomic_rename_ph 方法
`ToolRunner` MUST NOT 包含 `atomic_rename_ph()` 方法。该方法的功能已拆分为 `rename_ph_file()` 和 `update_pipeline_refs()` 两个独立方法。

**Reason**: 将文件操作和 YAML 操作分离，使 agent 编排层可以更精细地控制流程，也便于单独测试和错误处理。

**Migration**: 原来调用 `atomic_rename_ph()` 的地方应改为依次调用 `rename_ph_file()` 和 `update_pipeline_refs()`。

#### Scenario: atomic_rename_ph 不存在
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** MUST NOT 包含名为 `atomic_rename_ph` 的方法

### Requirement: 适配 _cmd_tool_prompt CLI 命令
`cli/tools.py` 中的 `_cmd_tool_prompt()` 函数当前依赖 `_build_generation_prompt()`（即将删除）。变更后 MUST 改为输出 Hermes skill 的 subagent goal 模板文本，而非旧的 LLM prompt。

#### Scenario: _cmd_tool_prompt 输出 goal 模板
- **WHEN** 用户执行 `yak tools prompt <pipeline.yaml>`
- **THEN** MUST 遍历所有 `_PH-` 步骤
- **AND** 对每个步骤 MUST 输出组装好的 subagent goal 模板文本（含 step 定义、whitelist 约束、函数签名要求）
- **AND** MUST NOT 导入或调用 `_build_generation_prompt`（该函数已删除）

#### Scenario: _cmd_tool_prompt 无 _PH- 步骤
- **WHEN** pipeline 中没有任何 `_PH-` 前缀的步骤
- **THEN** MUST 输出提示信息 "No _PH- tool steps found"
- **AND** MUST 正常退出（不报错）
