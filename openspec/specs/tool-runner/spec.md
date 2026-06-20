## REMOVED Requirements

### Requirement: 移除 _PH- 工具专属方法
`ToolRunner` 类 MUST NOT 包含 `_PH-` 工具专属方法。这些方法仅在 toolgen-test 分支上用于动态代码生成流程，eval 路线不再需要。

**Reason:** eval 路线不做动态代码生成，`_PH-` 工具的执行路径（rename_ph_file、update_pipeline_refs 等）没有使用场景。

**Migration:** 无。`_PH-` 工具从未在 main 分支上正式可用，没有需要迁移的 pipeline。

#### Scenario: is_ph_tool 已移除
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** `is_ph_tool` 方法 MUST NOT 存在

#### Scenario: strip_ph_prefix 已移除
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** `strip_ph_prefix` 方法 MUST NOT 存在

#### Scenario: rename_ph_file 已移除
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** `rename_ph_file` 方法 MUST NOT 存在

#### Scenario: update_pipeline_refs 已移除
- **WHEN** 检查 `ToolRunner` 类的方法列表
- **THEN** `update_pipeline_refs` 方法 MUST NOT 存在

### Requirement: 移除 _PH- 相关的 dead imports 和参数
`tool_runner.py` MUST NOT 包含仅被 `_PH-` 方法使用的 import 和参数。

**Reason:** `guardian` 参数仅被 `_PH-` 分支的 `runner.guardian.validate_output()` 使用。`import shutil` 仅被 `rename_ph_file` 使用。`import yaml` 仅被 `update_pipeline_refs` 使用。类 docstring 中的 `_PH- lifecycle` 描述已过时。

**Migration:** 无。

#### Scenario: guardian 参数已移除
- **WHEN** 检查 `ToolRunner.__init__` 的签名
- **THEN** `guardian` 参数 MUST NOT 存在

#### Scenario: shutil import 已移除
- **WHEN** 检查 `tool_runner.py` 的 import 列表
- **THEN** `import shutil` MUST NOT 存在

#### Scenario: yaml import 已移除
- **WHEN** 检查 `tool_runner.py` 的 import 列表
- **THEN** `import yaml` MUST NOT 存在

#### Scenario: 类 docstring 已更新
- **WHEN** 检查 `ToolRunner` 类的 docstring
- **THEN** `_PH- lifecycle` 描述 MUST NOT 存在

### Requirement: 移除 _PH_PREFIX 常量
`backend/engine/_lifecycle/tool_runner.py` MUST NOT 包含 `_PH_PREFIX` 模块级常量。

**Reason:** `_PH_PREFIX` 仅用于 `_PH-` 工具名称判断，eval 路线不再需要。

**Migration:** 无。

#### Scenario: _PH_PREFIX 已移除
- **WHEN** 检查 `tool_runner.py` 的模块级变量
- **THEN** `_PH_PREFIX` 常量 MUST NOT 存在

### Requirement: 移除 _replace_ph_refs 辅助函数
`backend/engine/_lifecycle/tool_runner.py` MUST NOT 包含 `_replace_ph_refs` 模块级辅助函数。

**Reason:** `_replace_ph_refs` 仅用于 `update_pipeline_refs` 的 YAML 引用替换，eval 路线不再需要。

**Migration:** 无。

#### Scenario: _replace_ph_refs 已移除
- **WHEN** 检查 `tool_runner.py` 的模块级函数
- **THEN** `_replace_ph_refs` 函数 MUST NOT 存在

## MODIFIED Requirements

### Requirement: ToolRunner.load_and_call 保留
`ToolRunner.load_and_call()` MUST 保留，用于常规工具（非 `_PH-`）的执行。

#### Scenario: 加载并执行常规工具
- **WHEN** 调用 `runner.load_and_call(tool_name="filter_data", input_files=..., output_dir=...)`
- **THEN** 系统 MUST 从 tools_dir 加载 `filter_data.py` 模块
- **AND** 系统 MUST 调用模块中的 `filter_data` 函数
- **AND** 系统 MUST 使用 `build_tool_kwargs()` 构造函数参数
- **AND** 系统 MUST 返回 `{"ok": True}` 或 `{"ok": False, "error": "..."}`

#### Scenario: load_and_call 通过 build_tool_kwargs 注入 ToolContext
- **WHEN** 目标工具函数签名包含 `ctx` 参数且 `cdp_helpers` 不为 None
- **THEN** `load_and_call` MUST 调用 `build_tool_kwargs(func, cdp_helpers=cdp_helpers, input_files=input_files, output_dir=output_dir, **params)`
- **AND** `build_tool_kwargs` MUST 从 `cdp_helpers.bridge` 构造 ToolContext 实例注入为 `ctx`
- **AND** `load_and_call` MUST 将 `build_tool_kwargs` 返回的 kwargs 传入目标函数
- **AND** `load_and_call` MUST NOT 手动拼接 `input_files`/`output_dir`/`cdp_helpers` 到 kwargs（由 `build_tool_kwargs` 统一处理）

### Requirement: execute_tool 改用 build_tool_kwargs
`backend/engine/executor.py` 的 `execute_tool()` MUST 改用 `build_tool_kwargs()` 构造 kwargs，不再硬编码 `input_files`/`output_dir` 注入。

**Reason:** 新增的 chat-mode tool（`file_read`、`file_write`、`format_convert`）不接受 `input_files`/`output_dir` 参数。硬编码注入会导致 `TypeError`。`build_tool_kwargs` 按函数签名选择性注入，兼容新旧 tool。

**Bridge 提取：** `execute_tool` 当前的 `ToolCDPHelpers(bridge_obj)` 包装逻辑 MUST 移到 `build_tool_kwargs` 内部。`build_tool_kwargs` 从 `cdp_helpers` 提取 bridge 时 MUST 兼容两种路径：
- `cdp_helpers.bridge`（CDPHelpers 的公开属性）
- `cdp_helpers._bridge`（ToolCDPHelpers 的私有属性，兼容旧调用方）

对于签名含 `ctx` 的新 tool，`build_tool_kwargs` MUST 直接构造 `ToolContext(bridge=bridge)` 注入为 `ctx`，不创建 `ToolCDPHelpers` 包装。对于签名含 `cdp_helpers` 但不含 `ctx` 的旧 tool，`build_tool_kwargs` MUST 构造 `ToolCDPHelpers(bridge)` 注入为 `cdp_helpers`。

#### Scenario: 执行接受 input_files 的旧 tool
- **WHEN** `execute_tool(tool_name="filter_data", params={"input_files": {...}, "output_dir": "..."})`
- **THEN** `execute_tool` MUST 调用 `build_tool_kwargs(func, cdp_helpers=cdp_helpers, input_files=..., output_dir=..., **params)`
- **AND** `build_tool_kwargs` MUST 检测到函数签名包含 `input_files`/`output_dir`，注入对应值
- **AND** 旧 tool 行为 MUST 保持不变

#### Scenario: 执行不接受 input_files 的新 tool
- **WHEN** `execute_tool(tool_name="file_read", params={"path": "data.txt", "head": 20})`
- **THEN** `execute_tool` MUST 调用 `build_tool_kwargs(func, cdp_helpers=None, **params)`
- **AND** `build_tool_kwargs` MUST 检测到函数签名不含 `input_files`/`output_dir`，不注入这些参数
- **AND** `file_read` MUST 正常执行，不报 TypeError

#### Scenario: build_tool_kwargs 兼容 ToolCDPHelpers 的 _bridge
- **WHEN** `cdp_helpers` 是 `ToolCDPHelpers` 实例（有 `_bridge` 属性）
- **THEN** `build_tool_kwargs` MUST 通过 `getattr(cdp_helpers, "bridge", None) or getattr(cdp_helpers, "_bridge", cdp_helpers)` 提取 bridge
- **AND** 提取到的 bridge MUST 是 `PlaywrightBridge` 实例
