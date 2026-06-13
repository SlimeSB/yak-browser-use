## 1. 准备与基础改造

- [x] 1.1 修改 `engine/_harness/tools.py`：删除 `EDIT_PIPELINE_TOOL` 变量，新增 `PIPELINE_LOAD_TOOL`、`PIPELINE_LIST_TOOL`、`PIPELINE_UPDATE_STEP_TOOL`、`PIPELINE_ADD_STEP_TOOL`、`PIPELINE_REMOVE_STEP_TOOL`、`PIPELINE_CREATE_TOOL` 共 6 个工具 schema 定义
- [x] 1.2 修改 `get_all_tools()` 函数：用 `PIPELINE_TOOLS` 列表替换 `EDIT_PIPELINE_TOOL`，确保工具顺序为 browser_* → goal_run → pipeline_* → record_step
- [x] 1.3 更新 `tests/test_harness_tools.py`：将工具数量断言从 10/9 改为 15/14，新增 pipeline 工具名检查

## 2. 核心实现

- [x] 2.1 新建 `engine/_harness/pipeline_tools.py`：实现 `pipeline_load`（读取摘要，含 Pydantic 验证和错误处理）
- [x] 2.2 实现 `pipeline_list`：扫描预设目录，返回 name/description/step_count 列表
- [x] 2.3 实现 `pipeline_update_step`：加载 YAML → 定位步骤 → 合并 updates → Pydantic 验证 → 调用 `edit_pipeline()` 写入
- [x] 2.4 实现 `pipeline_add_step`：加载 YAML → 构建 StepYaml → 按 after 位置插入 → Pydantic 验证 → 调用 `edit_pipeline()` 写入
- [x] 2.5 实现 `pipeline_remove_step`：加载 YAML → 删除步骤 → 清理其他步骤的 depends_on → Pydantic 验证 → 调用 `edit_pipeline()` 写入
- [x] 2.6 实现 `pipeline_create`：构建 PipelineYaml → Pydantic 验证 → 直接写入文件（已存在则拒绝）→ 推送 WebSocket 事件
- [x] 2.7 修改 `engine/_harness/tool_executor.py`：在 `_execute_single_tool_call()` 中添加 `pipeline_*` 路由分支，通过 import + dispatch 调用 `pipeline_tools.py` 中的函数

## 3. 验证与收尾

- [x] 3.1 新建 `tests/test_pipeline_tools.py`：覆盖 `pipeline_load`（存在/不存在/空名称/损坏）、`pipeline_list`（空目录/有文件/部分损坏）、`pipeline_update_step`（修改 browser_ops/description/tool_name/goal_description/depends_on、空 updates、步骤不存在、类型互斥）、`pipeline_add_step`（追加/插入/锚点不存在/pipeline 不存在/带依赖）、`pipeline_remove_step`（删除/清理依赖/步骤不存在/删最后一个）、`pipeline_create`（创建/重名/无效名称/空步骤/类型互斥）
- [x] 3.2 运行 `uv run pytest tests/ -v` 确保全部测试通过
- [x] 3.3 确认 `tools/edit_pipeline.py` 和 `tools/record_step.py` 未被修改
