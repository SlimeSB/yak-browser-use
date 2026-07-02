## 背景

`depends_on` 是 `StepYaml`（schema.py）、`StepDef`（models.py）上的字段，用于声明步骤间显式依赖。`build_graph`（graph.py）读取它来构建 DAG，但该 DAG 的产出（节点 deps、edges）不被执行引擎消费。实际运行时（runner_preset.py + StepMachine）使用 `_index += 1` 的完全顺序推进。该字段还散布在 pipeline_store 的增删改逻辑、generator 的 prompt 输出、pipeline_tools 的工具参数、registry 的 schema 描述中，以及 5 个测试文件中。

## 目标 / 非目标

**目标：**
- 彻底移除所有生产代码和测试代码中对 `depends_on` 的引用
- `build_graph` 只保留隐式顺序边（`elif i > 0` 分支）
- 执行引擎行为零变更

**非目标：**
- 不改变 StepMachine 的执行模型
- 不改变 YAML 序列化/反序列化行为
- 不清除用户存量 YAML 中的 `depends_on`（Pydantic v2 忽略即可）

## 关键决策

| 决策 | 选型 | 原因 |
|---|---|---|
| schema.py 的 depends_on 字段 | 直接删除 | 纯字段删除，无副作用。Pydantic v2 默认 `extra='ignore'`，存量包含 depends_on 的 YAML 加载时静默忽略 |
| graph.py 的分支处理 | 删除 `if step.depends_on:` 整个分支 | 保留顺序边 `elif i > 0` 即可，行为不变 |
| pipeline_store.py remove_step 的清理 | 删除依赖清理循环 | remove_step 的行为变为"只删除步骤，不做额外清理" |
| pipeline_tools.py pipeline_add_step 参数 | 从函数签名移除 | 对应 registry schema 描述一并移除 |
| 测试文件处理 | 删除相关用例和数据 | 不保留"deprecated"测试 |

## 风险 / 权衡

- **无运行风险**：执行引擎不消费 depends_on，删除后行为不变
- **存量 YAML 兼容**：Pydantic v2 `extra='ignore'` 保证包含 depends_on 的旧文件正常加载
- **graph.py 测试覆盖率下降**：删除 2 个 DAG 专用测试（`test_explicit_depends_on_replaces_sequential`、`test_depends_on_by_name`），不影响其余 13 个测试
- **pipeline_store 测试覆盖率下降**：删除 3 个 depends_on 专用测试，`test_update_step_description_and_depends` 精简为仅测 description

## 迁移计划

该变更无多阶段发布需求。一次性实施后：
1. 提交代码
2. 运行全量测试确认 pass
3. 存量 YAML 文件无需迁移

## 待确认问题

无
