## ADDED Requirements

### Requirement: pipeline.yaml 统一读写入口
系统 MUST 提供 `PipelineStore` 类，作为 pipeline.yaml 文件的唯一读写抽象。所有读取、写入、验证操作 MUST 通过该类执行。

#### Scenario: 读取时格式转换在边界完成
- **WHEN** `PipelineStore.load(pipeline_name)` 被调用且 YAML 文件中 browser_ops 为 `[{goto: "url"}, {fill: {selector: "#q", value: "text"}}]`
- **THEN** 返回 `PipelineYaml` 实例，其中 `browser_ops` 已转为内部格式 `[{type: "goto", value: "url"}, {type: "fill", selector: "#q", value: "text"}]`
- **AND** `PipelineYaml.browser_ops` 中所有 op 的 `type` 键明确标识操作类型
- **AND** 传递给 `runner_preset.py` 的 step dict 中 `browser_ops` 保持内部格式，`op.get("type")` 可正常访问

#### Scenario: 保存时格式转换回 YAML 格式
- **WHEN** `PipelineStore.save(pipeline_name, doc)` 被调用且 doc 的 browser_ops 为内部格式 `[{type: "goto", value: "url"}]`
- **THEN** 生成的 YAML 文本中 browser_ops 为 `[{goto: "url"}]`（YAML 格式）
- **AND** 写入磁盘的文件内容与 YAML 格式一致

#### Scenario: 读取不存在 pipeline
- **WHEN** `PipelineStore.load(pipeline_name)` 被调用但对应文件不存在
- **THEN** 抛出 `FileNotFoundError`

#### Scenario: 读取无效 YAML
- **WHEN** `PipelineStore.load(pipeline_name)` 被调用但 YAML 无法解析或无法通过 `PipelineYaml` 验证
- **THEN** 抛出 `yaml.YAMLError` 或 `pydantic.ValidationError`

#### Scenario: 验证 YAML 文本
- **WHEN** `PipelineStore.validate(yaml_text)` 被调用，yaml_text 中 browser_ops 为 YAML 格式
- **THEN** 返回 `PipelineYaml` 实例，`browser_ops` 为内部格式
- **AND** 若验证失败抛出 `pydantic.ValidationError`

### Requirement: 格式转换仅存在于 PipelineStore 边界
browser_ops 的格式转换（`{goto: "url"}` ↔ `{type: "goto", "value": "url"}`）MUST 仅在 PipelineStore 类中执行。`compiler/schema.py` 中的 `_convert_browser_op()` 和 `ops_to_yaml()` MUST 移入 PipelineStore。

#### Scenario: format-convert 工具不受影响
- **WHEN** `format_convert` 工具执行 YAML ↔ JSON 转换
- **THEN** 该工具功能不受 PipelineStore 重构影响

### Requirement: 轻量元数据读取
系统 MUST 提供 `PipelineStore.load_meta(pipeline_name)` 方法用于列表场景。该方法 MUST 仅读取 `name`、`description`、`step_count` 三个字段，不执行 Pydantic 验证、不做 browser_ops 格式转换。

#### Scenario: 列表场景用 load_meta
- **WHEN** `pipeline_list` 工具扫描多个 pipeline
- **THEN** 每个 pipeline 通过 `load_meta()` 获取元数据，不走 `load()` 的全量验证
- **AND** 返回 `{"ok": true, "presets": [...], "step_count": N}`

#### Scenario: load_meta 处理损坏文件
- **WHEN** pipeline.yaml 存在但 YAML 解析失败
- **THEN** `load_meta()` 返回 `description="(parse error)", step_count=0`
- **AND** 不抛出异常

### Requirement: 写入时 strip 默认空值
序列化 `PipelineYaml` 为 YAML 时 MUST 递归去除 `None`、`""`、`[]`、`{}` 值。MUST 不使用 Pydantic 的 `exclude_defaults` 或 `exclude_unset`。

#### Scenario: strip 空值字段
- **WHEN** 模型中某字段值为默认值（用户未显式设置）
- **THEN** 该字段在输出 YAML 中不出现
- **AND** 下次读取时 Pydantic 自动赋予默认值

#### Scenario: 用户手写的空结构保留语义等价
- **WHEN** 用户手写 `params: {}` 于 pipeline.yaml 中
- **THEN** 该字段在 `_strip_defaults()` 后被去除
- **AND** 下一轮读回时 Pydantic 给默认值 `{}`，语义等价

### Requirement: 公共接口接受 YAML 格式 browser_ops
`PipelineStore.add_step()` 和 `PipelineStore.update_step()` 的 browser_ops 参数 MUST 接受 YAML 格式（与文件中一致的 `{goto: "url"}`）。PipelineStore 内部自动转为内部格式存储。

#### Scenario: record_step 传入 YAML 格式 browser_ops
- **WHEN** `record_step.py` 调用 `PipelineStore.add_step()` 并传入 browser_ops `[{goto: "https://x.com"}]`
- **THEN** PipelineStore 自动将其转为内部格式 `[{type: "goto", value: "https://x.com"}]`
- **AND** 返回正确写入的 PipelineYaml 模型

#### Scenario: 内部格式调用方需要 ops_to_yaml 工具
- **WHEN** `generator.py:write_pipeline_learned` 持有内部格式 `[{type: "goto", value: "url"}]`
- **THEN** 可调用 `PipelineStore.ops_to_yaml(ops)` 转为 YAML 格式 `[{goto: "url"}]`
- **AND** 将转换结果传入 `add_step()` 或 `update_step()`

## MODIFIED Requirements

### Requirement: pipeline_create 内部实现
`pipeline_create` 工具 MUST 通过 `PipelineStore.save()` 写入 pipeline.yaml，而非 `yaml.dump` + `open("x")`。

#### Scenario: 创建 pipeline 使用 PipelineStore
- **WHEN** `pipeline_create` 被调用
- **THEN** 通过 `PipelineStore.save()` 替代 `yaml.dump` + `open("x")`
- **AND** 返回 JSON 包含 `ok: true`

### Requirement: pipeline_load 内部实现
`pipeline_load` 工具 MUST 通过 `PipelineStore.load()` 读取 pipeline.yaml，返回中包含 model 元数据。

#### Scenario: 读取 pipeline 使用 PipelineStore
- **WHEN** `pipeline_load` 被调用
- **THEN** 通过 `PipelineStore.load()` 替代 `_load_pipeline_yaml()`
- **AND** browser_ops 格式由 PipelineStore 自动转为内部格式

### Requirement: pipeline_list 使用 load_meta
`pipeline_list` 工具 MUST 通过 `PipelineStore.load_meta()` 替代 `yaml.safe_load` + 手读 dict。

#### Scenario: 列表 pipeline 使用 load_meta
- **WHEN** `pipeline_list` 被调用
- **THEN** 每个 pipeline 通过 `PipelineStore.load_meta()` 获取元数据
- **AND** 不做全量 Pydantic 验证和 browser_ops 格式转换

### Requirement: pipeline_update_step 内部实现
`pipeline_update_step` 工具 MUST 通过 `PipelineStore.update_step()` 操作步骤字典。

#### Scenario: 更新步骤使用 PipelineStore
- **WHEN** `pipeline_update_step` 被调用
- **THEN** step 字典操作委托 `PipelineStore.update_step()`

### Requirement: pipeline_add_step 内部实现
`pipeline_add_step` 工具 MUST 通过 `PipelineStore.add_step()` 操作步骤字典。

#### Scenario: 添加步骤使用 PipelineStore
- **WHEN** `pipeline_add_step` 被调用
- **THEN** step 字典操作委托 `PipelineStore.add_step()`

### Requirement: pipeline_remove_step 内部实现
`pipeline_remove_step` 工具 MUST 通过 `PipelineStore.remove_step()` 操作步骤字典。

#### Scenario: 删除步骤使用 PipelineStore
- **WHEN** `pipeline_remove_step` 被调用
- **THEN** step 字典操作委托 `PipelineStore.remove_step()`
- **AND** 同时清理其他步骤的 `depends_on` 引用

### Requirement: serialize 使用 _strip_defaults
`_dump_pipeline_yaml()` MUST 使用 `_strip_defaults()` 替代 `exclude_defaults=True`。

#### Scenario: dump 使用 strip
- **WHEN** `_dump_pipeline_yaml()` 序列化 PipelineYaml
- **THEN** 使用 `_strip_defaults()` 递归去除空值
- **AND** 不使用 `exclude_defaults=True`

### Requirement: record_step 通过 PipelineStore 写入
`record_step.py` MUST 使用 PipelineStore 读写 pipeline.yaml，不再手搓 raw dict 和直接调用 `yaml.dump`。不再手写 browser_ops 格式猜测逻辑。

#### Scenario: record_step 追加步骤
- **WHEN** `record_step` 工具被调用以追加新步骤
- **THEN** 通过 `PipelineStore.load()` 读取、`PipelineStore.add_step()` 新增、`PipelineStore.save()` 写入
- **AND** browser_ops 格式由 PipelineStore 自动转换

#### Scenario: record_step 更新已有步骤
- **WHEN** `record_step` 工具被调用且步骤名已存在
- **THEN** 通过 `PipelineStore.update_step()` 更新
- **AND** 返回与旧版相同格式的结果

### Requirement: generator.write_pipeline_learned 通过 PipelineStore 写入
`generator.py:write_pipeline_learned()` MUST 使用 PipelineStore 读写操作，不再直接 `yaml.safe_load` + 手写 `ops_to_yaml`。

#### Scenario: write_pipeline_learned 更新 browser_ops
- **WHEN** `write_pipeline_learned` 被调用
- **THEN** 通过 `PipelineStore.load()` 读取、修改 browser_ops 字段、`PipelineStore.save()` 写入
- **AND** browser_ops 格式由 PipelineStore 自动转换

### Requirement: pipeline_compile 格式统一
`pipeline_compile()` 在生成 browser_ops 时 MUST 使用 `PipelineStore.ops_to_yaml()` 而非手搓 `{op_type: value}`。

#### Scenario: pipeline_compile 生成 browser_ops
- **WHEN** `pipeline_compile` 从对话历史生成步骤列表
- **THEN** browser_ops 格式通过 `PipelineStore.ops_to_yaml()` 保证与存储格式一致
- **AND** 生成的 dict 可直接传入 `pipeline_create`

### Requirement: to_step_def 不做格式转换
`StepYaml.to_step_def()` MUST 直接使用 `self.browser_ops`（PipelineStore 已在 load 时转为内部格式），不再调用 `_convert_browser_op()`。

#### Scenario: to_step_def 简化
- **WHEN** `to_step_def()` 被调用
- **THEN** `resolved_browser_ops` 直接从 `self.browser_ops` 赋值
- **AND** 不再调用 `_convert_browser_op()`
