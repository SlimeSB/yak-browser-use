## Why

当前 pipeline.yaml 的读写操作散落在至少 7 个文件中，各自独立 `import yaml`，走不同的解析路径（Pydantic vs raw dict）、不同的写入策略（`exclude_defaults=True` vs 直接 `yaml.dump`）、不同的格式转换逻辑（`_convert_browser_op` vs 手搓）。没有一个统一的"管道文档"抽象。

具体问题：

- **写入路径分散 5 条**：`pipeline_tools.py`（Pydantic CRUD）、`record_step.py`（raw dict 直写）、`generator.py`（`write_pipeline_learned` 又一组 YAML 操作）、`edit_pipeline.py`（文本覆盖）、`routes.py`（API 保存）。每条路径对 checkpoint、事件推送、validate 的处理都不一致。
- **双层模型**：`schema.py` 有 `StepYaml/PipelineYaml`（Pydantic），`models.py` 有 `StepDef/PipelineDef`（dataclass），两者之间的 `to_step_def()` 有 40 行手写映射，包含格式转换、类型收窄、派生字段计算。
- **格式双轨**：内部格式 `{type: "goto", value: "url"}` 与 YAML 格式 `{goto: "url"}` 通过 `_convert_browser_op()` 和 `ops_to_yaml()` 双向转换，逻辑分散在 schema.py 和 record_step.py 中。
- **`exclude_defaults=True` 导致字段丢失**：`_dump_pipeline_yaml()` 会丢弃默认值字段（空字符串、空列表），用户手写的内容在 round-trip 后被吃掉。
- **`record_step.py` 绕过 Pydantic 验证**：直接操作 raw dict 写入 YAML，不经过 schema 校验。

现在做是因为 Hermes 集成计划中 `pipeline_tools.py` 未来会被删除（`engine/_harness/` 整体替换），在那之前先把 CRUD 集中到一个干净的抽象层，后续切换 Hermes 时只需改这个层的消费端。

## What Changes

- **新增** `compiler/pipeline_store.py`：PipelineStore 类，提供 pipeline.yaml 的 load / save / validate / from_yaml / to_yaml / update_step / add_step / remove_step 统一接口。所有 YAML 读写强制走此入口。
- **修改** `tools/record_step.py`：不再手搓 raw dict + `yaml.dump`，改用 `PipelineStore.append_step()`。
- **修改** `compiler/generator.py`：`write_pipeline_learned()` 改用 `PipelineStore`。
- **修改** `engine/_harness/pipeline_tools.py`：`_load_pipeline_yaml()` 和 `_dump_pipeline_yaml()` 委托给 `PipelineStore`；去掉 `exclude_defaults=True`。
- **修改** `compiler/schema.py`：`_convert_browser_op()` 和 `ops_to_yaml()` 移入 `PipelineStore` 作为私有方法，外部不再调用。
- **修改** `compiler/models.py`：对齐 `StepDef` 字段类型，减少与 `StepYaml` 的差异（`input_ref` 统一允许 `None`，`browser_ops` 统一允许 `None`）。
- **不删** 任何现有文件。不改变 YAML 格式（保持 `{goto: "url"}` 作为对外格式）。不改变执行器（runner_preset、step_machine、graph、resolver 不动）。不影响 Hermes 桥接。

## Capabilities

### New Capabilities
- `pipeline-store`: 统一的 pipeline YAML 文档读写抽象层，封装 load/save/validate/CRUD 全部操作，所有写入路径强制走同一入口

### Modified Capabilities
- `browser-eval`: browser_ops 的格式转换（`_convert_browser_op` / `ops_to_yaml`）从 schema.py 移入 PipelineStore，不做行为变更
- `pipeline-create`: 创建 pipeline 时通过 PipelineStore 写入，而非直接 `yaml.dump` + `open("x")`
- `pipeline-add-step`: 添加步骤时委托 PipelineStore
- `pipeline-update-step`: 更新步骤时委托 PipelineStore；去掉 `exclude_defaults=True`，改为后处理 strip 空值
- `pipeline-remove-step`: 删除步骤时委托 PipelineStore
- `pipeline-load`: 读取 pipeline 时委托 PipelineStore
- `pipeline-list`: 列表查询通过 PipelineStore 读取元数据
- `goal-execution`: 记录步骤（record_step）改用 PipelineStore 写回

## Impact

- **代码**：新增 `compiler/pipeline_store.py`（~120 行）；修改 `record_step.py`（~30 行）、`generator.py:write_pipeline_learned`（~20 行）、`pipeline_tools.py`（~50 行）、`schema.py`（删除转换函数 ~20 行）、`models.py`（类型对齐 ~10 行）、`routes.py`（~10 行）。总计 ~130 新增 + ~140 修改 + ~20 删除。
- **接口**：现有 `pipeline_*` 工具函数的签名和返回值不变，内部实现改为委托 PipelineStore。API 路由不变。
- **依赖**：无新增外部依赖。PipelineStore 只依赖 `yaml` 和 `pydantic`（已有）。
- **数据**：pipeline.yaml 格式不变，已有文件完全兼容。格式转换（`{goto: "url"}` ↔ `{type: "goto", "value": "url"}`）移到 PipelineStore 内部。
- **风险**：改动集中在编译器层，执行器（runner_preset、step_machine）完全不碰，回退安全。
