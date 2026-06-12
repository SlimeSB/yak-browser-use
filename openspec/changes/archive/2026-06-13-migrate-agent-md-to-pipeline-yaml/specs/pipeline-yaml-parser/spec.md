## ADDED Requirements

### Requirement: 解析 pipeline.yaml 为内部格式
系统 MUST 通过 `parse_pipeline(text: str) -> AgentMD` 函数将 pipeline.yaml 文本解析为内部 `AgentMD` 对象。解析过程为：`yaml.safe_load()` → `PipelineYaml.model_validate()` → `to_agent_md()`。

#### Scenario: 解析完整 pipeline.yaml
- **WHEN** 调用 `parse_pipeline()` 传入合法的 YAML 文本
- **THEN** 返回 `AgentMD` 对象，包含正确的 `name`、`description`、`steps` 列表，每个 step 为 `StepDef`

#### Scenario: 解析含多个步骤的流水线
- **WHEN** YAML 包含混合类型的步骤（browser + tool + goal）
- **THEN** 每个步骤的 `step_type` 根据其包含的字段自动推断

#### Scenario: 解析非法 YAML
- **WHEN** 传入语法错误的 YAML 文本（如缩进不一致）
- **THEN** 抛出包含 `yaml.YAMLError` 的异常

#### Scenario: 解析格式正确但 schema 不合法的 YAML
- **WHEN** YAML 语法正确但缺少必填字段 `name`
- **THEN** 抛出 `pydantic.ValidationError`，错误信息指明 `name` 字段缺失

### Requirement: 向后兼容废弃
系统 MUST NOT 再支持 `agent.md` 混合格式的解析。`parse_agent_md()` 函数被移除，由 `parse_pipeline()` 替代。输入的格式必须是纯 YAML（`*.pipeline.yaml`）。

#### Scenario: 尝试解析旧 agent.md 格式
- **WHEN** 向新解析器传入 Markdown+YAML 混合格式的 agent.md 文本
- **THEN** 系统 MUST 抛出 `yaml.YAMLError` 或 `pydantic.ValidationError`，拒绝旧格式

### Requirement: 参数注入
系统 MUST 提供 `inject_params_to_pipeline(yaml_text: str, params: dict) -> str` 函数，将流水线定义中的 `{{param_name}}` 占位符替换为实际参数值。替换流程为：`yaml.safe_load()` → 递归遍历 dict/list 结构替换字符串值中的 `{{key}}` → `yaml.dump()`。禁止在 YAML 文本层做 `str.replace`。

#### Scenario: 替换单个参数
- **WHEN** yaml_text 包含 `name: "{{pipeline_id}}"`，params 为 `{"pipeline_id": "order-001"}`
- **THEN** 输出 YAML 中对应字符串值变为 `"order-001"`

#### Scenario: 替换多处同参数
- **WHEN** 同一个 `{{param_name}}` 出现在 YAML 文档的多处
- **THEN** 所有出现均被替换

#### Scenario: 参数不存在
- **WHEN** `{{nonexistent}}` 出现在 yaml_text 但不在 params 中
- **THEN** 保留 `{{nonexistent}}` 原样不动，记录 WARNING 日志

#### Scenario: 参数值含 YAML 特殊字符
- **WHEN** yaml_text 包含 `name: "{{title}}"`，params 为 `{"title": "Report: Q1 Revenue"}` 
- **THEN** 因替换在 YAML 解析后的结构层完成，`:` 不会破坏 YAML 语法，最终输出 `name: "Report: Q1 Revenue"`

### Requirement: 保留 StepDef 和 AgentMD dataclass
系统 MUST 保持 `StepDef` 和 `AgentMD` dataclass 定义不变，`StepDef.to_runtime_dict()` 方法签名和行为不变。Pydantic 模型仅在解析层使用，不暴露给 engine。

#### Scenario: StepDef.to_runtime_dict() 行为不变
- **WHEN** 通过新解析器获得的 StepDef 调用 `to_runtime_dict()`
- **THEN** 返回的 dict 结构与该 StepDef 通过旧解析器获得时完全一致
