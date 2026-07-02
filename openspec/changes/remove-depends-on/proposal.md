## Why

`depends_on` 是 StepDef/StepYaml 上的字段，用于声明步骤间的显式依赖关系。实际执行引擎（StepMachine + runner_preset）使用完全顺序的执行模型（`_index += 1`），从未消费该字段。`build_graph` 虽根据 `depends_on` 计算 DAG，但产出仅用于测试和展示，不被运行时调度。该字段在 7 个生产文件和 5 个测试文件中散布 36 处引用，增加了代码认知负担和维护成本，却没有带来任何实际功能。浏览器自动化场景天然是顺序执行（每个步骤修改浏览器状态，后续步骤隐式依赖前序），未来也不存在并行引擎与之配合的可能。因此需要彻底清除 `depends_on`。

## What Changes

- **schema.py**: 删除 `StepYaml.depends_on` 字段定义及 `to_step_def()` 中的传参
- **models.py**: 删除 `StepDef.depends_on` 字段及 `to_runtime_dict()` 中的输出
- **graph.py**: 删除 `build_graph` 中基于 `depends_on` 的显式分支，只保留隐式顺序边
- **pipeline_store.py**: 删除 `update_step` 中的 depends_on 处理，删除 `remove_step` 中的 depends_on 清理逻辑
- **generator.py**: 删除 `generate_handler_prompt` 输出的 `depends_on` 键
- **pipeline_tools.py**: 删除 `pipeline_view` 输出中的 depends_on、`pipeline_add_step` 的 depends_on 参数及处理
- **registry.py**: 删除 3 处 tool schema 描述中的 depends_on 相关说明
- **测试文件**（5 个）: 删除 depends_on 相关的测试用例和数据

## Capabilities

### New Capabilities

—

### Modified Capabilities

—

## Impact

- **7 个生产文件被修改**：schema.py、models.py、graph.py、pipeline_store.py、generator.py、pipeline_tools.py、registry.py
- **5 个测试文件被修改**：conftest.py、test_compiler_parser.py、test_compiler_graph.py、test_compiler_generator.py、test_pipeline_tools.py、test_pipeline_store.py
- **行为变化**：`build_graph` 的节点 deps 将永远为顺序边，不再支持非顺序 DAG；`StepYaml` 不再接受 `depends_on` 字段（Pydantic v2 默认 `extra='ignore'`，存量 YAML 静默忽略）
- **无运行时影响**：执行引擎和 StepMachine 行为不变
