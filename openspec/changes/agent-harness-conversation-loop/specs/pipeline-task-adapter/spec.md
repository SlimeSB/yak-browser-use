## ADDED Requirements

### Requirement: PipelineTaskAdapter
系统 SHALL 提供 `PipelineTaskAdapter` 模块，用于将 compiler 输出的 StepDef[] 转为 conversation_loop 可消费的 task 描述。

转换流程：
```
compiler → StepDef[] → PipelineTaskAdapter
  → 1. 提取 pipeline 元信息（name, goal, frontmatter）
  → 2. 将每个 step_def 转为 StepInfo（key, name, description, type, status）
  → 3. 生成 TaskDescriptor（pipeline_name + steps + progress）
  → 4. TaskDescriptor.format() → markdown 文本 → 注入 conversation_loop system prompt
```

PipelineTaskAdapter 只在预设回放模式中使用。chat 模式下不经过此模块。

#### Scenario: 预设转 TaskDescriptor
- **WHEN** 用户选择预设回放
- **THEN** compiler 解析 agent.md → StepDef[]
- **THEN** PipelineTaskAdapter(step_defs, frontmatter) → TaskDescriptor
- **THEN** descriptor.pipeline_name == agent.md 中的 name
- **THEN** descriptor.steps[0].status == "pending"

### Requirement: TaskDescriptor.format()
TaskDescriptor SHALL 提供 `format()` 方法，返回 markdown 格式的 task 描述文本。

输出格式：
```
## Pipeline: {name}
目标: {goal}

进度: {completed}/{total}

### 步骤列表
- [待完成] {step1.name}: {step1.description}
- [已完成] {step2.name}: {step2.description}
- [待完成] {step3.name}: {step3.description}

你可以通过 pipeline_control 工具管理进度。
```

#### Scenario: format 输出可读
- **WHEN** TaskDescriptor 包含 3 步（1 已完成，2 待完成）
- **THEN** format() 输出包含 "[已完成]" 和 "[待完成]" 标记
