## ADDED Requirements

### Requirement: 将步骤列表渲染为 pipeline.yaml 文本
系统 MUST 通过 `render_steps_to_pipeline(steps, pipeline_name, ...) -> str` 函数将步骤定义列表渲染为合法的 `pipeline.yaml` 文本。渲染过程为：构建 `PipelineYaml` 对象 → `.model_dump(exclude_none=True)` → `yaml.dump()`。

#### Scenario: 渲染基本流水线
- **WHEN** 调用 `render_steps_to_pipeline()` 传入步骤列表（含 browser、tool、goal 步骤各一个）
- **THEN** 返回合法的 YAML 文本，包含 `name` 和 `steps` 字段，可被 `yaml.safe_load()` 重新解析

#### Scenario: 渲染不含可选字段的流水线
- **WHEN** 步骤不含 `description`、`depends_on` 等可选字段
- **THEN** 输出的 YAML 中不包含值为 null/空列表/空字符串的字段

#### Scenario: 渲染含多行描述的流水线
- **WHEN** `description` 包含多行文本（含换行符）
- **THEN** 输出合法 YAML 文本，描述中的换行符被正确保留

### Requirement: 废弃旧渲染函数
系统 MUST 移除 `render_steps_to_agent_md()` 函数，由 `render_steps_to_pipeline()` 替代。新函数输出纯 YAML 而非 Markdown+YAML 混合格式。

#### Scenario: 旧渲染函数不可用
- **WHEN** 代码尝试调用 `render_steps_to_agent_md()`
- **THEN** 引发 `ImportError` 或 `AttributeError`，因为该函数已从模块中移除
