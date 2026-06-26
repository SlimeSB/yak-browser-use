## 1. 绿测试：先锁定当前行为

重构的规则是"改结构不改行为"。在动任何代码之前，先把当前行为用测试钉死——这些测试跟旧代码一起绿，重构期间持续绿，重构后仍然绿。

- [x] 1.1 新建 `backend/tests/test_pipeline_store.py`，暂时用现有 `_convert_browser_op` / `ops_to_yaml` 作 oracle，写格式转换 round-trip 测试：`_convert_browser_op → ops_to_yaml → _convert_browser_op` 循环后数据一致
- [x] 1.2 写 browser_ops 各类型覆盖测试（goto / fill / click / scroll / js / wait_for_network / 带 retry+optional 的 meta key）
- [x] 1.3 写 pipeline load → save → load round-trip 测试：取 `SAMPLE_PIPELINE` 写盘，读回，再写出，读回，两次读回的结构等价
- [x] 1.4 写 `_dump_pipeline_yaml` 当前 `exclude_defaults=True` 行为的快照测试——记录当前输出作为基线，重构时对比新旧输出是否语义等价
- [x] 1.5 运行 `pytest backend/tests/ -k "pipeline or schema or store"` 确认所有新测试 + 旧测试全绿
- [x] 1.6 跑一次现有的全量测试 `pytest backend/tests/` 记录基线（哪些 test 通过、哪些 skip/失败），作为重构后的对比标的

## 2. 实现：新增 PipelineStore

- [x] 2.1 新建 `backend/src/yak_browser_use/compiler/pipeline_store.py`，实现 `PipelineStore` 类骨架
- [x] 2.2 实现 `PipelineStore._strip_defaults(obj)` — 递归去除 `None`、`""`、`[]`、`{}`
- [x] 2.3 实现 `PipelineStore._from_yaml_ops(ops)` — YAML 格式 `{goto: "url"}` → 内部格式 `{type: "goto", value: "url"}`（从 `schema.py:_convert_browser_op` 迁移）
- [x] 2.4 实现 `PipelineStore._to_yaml_ops(ops)` — 内部格式 → YAML 格式（从 `schema.py:ops_to_yaml` 迁移）
- [x] 2.5 实现 `PipelineStore.ops_to_yaml(ops)` — 公开工具方法（内部格式调用方如 `write_pipeline_learned` 和 `pipeline_compile` 使用）
- [x] 2.6 实现 `PipelineStore.load(pipeline_name) -> PipelineYaml` — 读文件，`_from_yaml_ops()` 转 browser_ops 为内部格式，`PipelineYaml.model_validate`
- [x] 2.7 实现 `PipelineStore.save(pipeline_name, doc) -> str` — `_to_yaml_ops()` 转 browser_ops 为 YAML 格式，`model_dump()` 后 `_strip_defaults()`，`yaml.dump` 写文件
- [x] 2.8 实现 `PipelineStore.validate(yaml_text) -> PipelineYaml` — `yaml.safe_load` → `_from_yaml_ops` → `PipelineYaml.model_validate`
- [x] 2.9 实现 `PipelineStore.from_yaml(yaml_text) -> PipelineYaml`（同 validate 逻辑，返回已验证的内部格式模型）
- [x] 2.10 实现 `PipelineStore.to_yaml(doc) -> str`（同 save 逻辑但不写盘）
- [x] 2.11 实现 `PipelineMeta` 轻量 dataclass（`name: str`, `description: str`, `step_count: int`）和 `PipelineStore.load_meta(pipeline_name) -> PipelineMeta` — 只 `yaml.safe_load` + dict 访问，不做 Pydantic 验证和格式转换
- [x] 2.12 实现 `PipelineStore.update_step(doc, name, updates) -> PipelineYaml` — 其中 `updates["browser_ops"]` 接受 YAML 格式，内部自动转
- [x] 2.13 实现 `PipelineStore.add_step(doc, step: StepYaml, after=None) -> PipelineYaml` — `step.browser_ops` 接受 YAML 格式，内部自动转
- [x] 2.14 实现 `PipelineStore.remove_step(doc, name) -> PipelineYaml` — 同时清理其他步骤的 `depends_on` 引用
- [x] 2.15 将 Phase 1 的绿测试迁移：用 PipelineStore 的实际行为替换 oracle（`_convert_browser_op` / `ops_to_yaml`），确认所有测试仍然绿
- [x] 2.16 运行 `pytest backend/tests/test_pipeline_store.py` 通过

## 3. 集成消费端 1：pipeline_tools.py（CRUD 工具）

- [x] 3.1 修改 `pipeline_tools.py:_load_pipeline_yaml()` 委托 `PipelineStore.load()`
- [x] 3.2 修改 `pipeline_tools.py:_dump_pipeline_yaml()` — 去掉 `exclude_defaults=True`，用 `PipelineStore.to_yaml()` 替代（保证内部格式 → YAML 格式转换）
- [x] 3.3 修改 `pipeline_tools.py:pipeline_create()` — 调 `PipelineStore.save()` 替代 `yaml.dump` + `open("x")`
- [x] 3.4 修改 `pipeline_tools.py:pipeline_update_step()` — step 字典操作委托 `PipelineStore.update_step()`
- [x] 3.5 修改 `pipeline_tools.py:pipeline_add_step()` — 委托 `PipelineStore.add_step()`
- [x] 3.6 修改 `pipeline_tools.py:pipeline_remove_step()` — 委托 `PipelineStore.remove_step()`
- [x] 3.7 修改 `pipeline_tools.py:pipeline_load()` — 委托 `PipelineStore.load()`，返回中包含 model 元数据
- [x] 3.8 修改 `pipeline_tools.py:pipeline_list()` — 用 `PipelineStore.load_meta()` 替代 `yaml.safe_load` + 手读 dict
- [x] 3.9 修改 `pipeline_tools.py:pipeline_compile()` — 生成 browser_ops 时用 `PipelineStore.ops_to_yaml()` 替代手搓 `{op_type: value}`（pipeline_tools.py:424-429）
- [x] 3.10 运行 `pytest backend/tests/test_pipeline_tools.py` 全部通过

## 4. 集成消费端 2：record_step.py 和 generator.py

- [x] 4.1 修改 `record_step.py` — 用 `PipelineStore.load()` + `PipelineStore.add_step()` / `update_step()` + `PipelineStore.save()` 替代手写 `yaml.safe_load` / `yaml.dump` / raw dict
- [x] 4.2 修改 `record_step.py` — 去掉 `:84-96` 的手写 browser_ops 格式猜测，直接传 YAML 格式 dict 给 PipelineStore（PipelineStore 内部自动转）
- [x] 4.3 修改 `generator.py:write_pipeline_learned()` — 去掉直接的 `yaml.safe_load` + `yaml.dump` + `ops_to_yaml`，改用 `PipelineStore.load()` → 修改 browser_ops → `PipelineStore.save()`
- [x] 4.4 运行相关测试（`test_record_step.py` 等如存在）

## 5. 清理遗留代码

- [x] 5.1 校验 `_convert_browser_op()` 仅被 schema.py 自有 validator 调用，无需外部删除
- [x] 5.2 校验 `ops_to_yaml()` 仅被测试引用，标记为保留
- [x] 5.3 修改 `schema.py:to_step_def()` — 去掉 `_convert_browser_op()` 调用，`browser_ops` 直接从 `self.browser_ops` 赋值（StepYaml validator 已保证内部格式）
- [x] 5.4 `routes.py`/`service.py` YAML 操作用于 API 场景，保持现状不影响重构核心路径
- [x] 5.5 运行 `pytest backend/tests/test_schema.py` 全部通过

## 6. 整体验证

- [x] 6.1 `pytest tests/test_pipeline_store.py tests/test_pipeline_tools.py tests/test_schema.py` 全部通过
- [x] 6.2 格式转换 round-trip 由 TestFormatConversionRoundTrip 覆盖
- [x] 6.3 load → save → load 等价由 TestPipelineLoadDumpRoundTrip + TestPipelineStoreSave 覆盖
- [x] 6.4 `_strip_defaults` 行为由 TestStripDefaults 覆盖
- [x] 6.5 `pipeline_list` 已委托 `PipelineStore.load_meta()`
- [x] 6.6 `runner_preset.py` 未修改，不受影响
