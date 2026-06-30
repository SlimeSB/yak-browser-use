# PipelinesTab Render

## Requirements

### PipelinesTab 必须从 pipelineStore 获取数据而非 props
PipelinesTab MUST 不再接收 5 个 props，改为内部 `usePipelineStore` selector 以及 `useUiStore` selector。

#### Scenario: 渲染 pipelines 列表
- **WHEN** PipelinesTab 被激活
- **THEN** 组件 MUST 展示来自 `usePipelineStore(s => s.pipelines)` 的卡片列表

#### Scenario: 点击 Run 按钮
- **WHEN** 用户在 PipelinesTab 中点击某个 pipeline 的 "Run" 按钮
- **THEN** PipelinesTab MUST 调 `pipelineStore.setActivePreset(name)` + `uiStore.setActiveTab('exec')`
