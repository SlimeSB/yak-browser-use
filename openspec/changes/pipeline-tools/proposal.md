## Why

当前 Agent 对 pipeline 的操作能力严重不足：只能通过 `edit_pipeline` 全量替换 YAML 内容，无法增量修改；也没有读取 pipeline 的能力。Agent 在执行任务时需要先了解 pipeline 结构再做修改，但缺乏 `pipeline_load` / `pipeline_list` 这类只读工具，导致 LLM 只能"盲写"整份 YAML，token 消耗大且容易出错。

本次变更将 `edit_pipeline` 拆分为 6 个扁平工具（load/list/update_step/add_step/remove_step/create），让 Agent 可以像操作 CRUD 一样精确控制 pipeline，同时复用现有的 checkpoint + diff + WebSocket 安全机制。

## What Changes

- **删除** `EDIT_PIPELINE_TOOL`（全量替换 YAML 的工具定义）
- **新增** 6 个 pipeline 操作工具 schema：`pipeline_load`、`pipeline_list`、`pipeline_update_step`、`pipeline_add_step`、`pipeline_remove_step`、`pipeline_create`
- **新建** `engine/_harness/pipeline_tools.py`，实现上述 6 个工具的核心逻辑
- **修改** `engine/_harness/tool_executor.py`，在 `_execute_single_tool_call` 中添加 `pipeline_*` 路由分支
- **不动** `tools/edit_pipeline.py` 和 `tools/record_step.py`，新工具内部调用 `edit_pipeline()` 复用安全机制
- **更新** `tests/test_harness_tools.py` 中的工具数量断言（10/9 → 15/14）
- **新建** `tests/test_pipeline_tools.py` 覆盖 6 个新工具

## Capabilities

### New Capabilities
- `pipeline-load`: 读取 pipeline 摘要（步骤列表、类型、依赖关系、required_params），不返回完整 YAML
- `pipeline-list`: 列出 workspace 下所有可用的 pipeline 预设
- `pipeline-update-step`: 增量修改 pipeline 中某个步骤的字段，修改 browser_ops 或 tool_name 时自动清除互斥字段
- `pipeline-add-step`: 追加或插入新步骤
- `pipeline-remove-step`: 删除指定步骤并清理依赖引用
- `pipeline-create`: 从步骤列表创建新的 pipeline 预设

### Modified Capabilities
- `tool-registration`: `get_all_tools()` 返回的工具列表从 10 个变为 15 个（含 goal_run），从 9 个变为 14 个（不含 goal_run）

## Impact

- **代码**：`engine/_harness/tools.py`（schema 替换）、`engine/_harness/tool_executor.py`（路由分支）、新建 `engine/_harness/pipeline_tools.py`
- **测试**：`tests/test_harness_tools.py`（断言更新）、新建 `tests/test_pipeline_tools.py`
- **接口**：`get_all_tools()` 返回值变化，调用方（`api/service.py`、`engine/_harness/__init__.py`）无需修改
- **安全机制**：所有写操作复用 `tools/edit_pipeline.py` 的 checkpoint + difflib + WebSocket push
- **向后兼容**：删除 `edit_pipeline` 工具是 **BREAKING** 变更，LLM 不再能调用该工具名；但 `tools/edit_pipeline.py` 文件保留不动，内部函数仍可被新工具调用
