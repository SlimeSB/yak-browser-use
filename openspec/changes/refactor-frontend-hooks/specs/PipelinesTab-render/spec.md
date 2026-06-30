## ADDED Requirements

### Requirement: PipelinesTab 必须从 pipelineStore 获取数据而非 props
PipelinesTab MUST 不再接收 `pipelines`、`onRefresh`、`onSelectPreset`、`onTabChange`、`onDeletePipeline` 这 5 个 props，改为内部 `usePipelineStore` selector 读取 pipelines / refreshPipelines / deletePipeline / setActivePreset，以及 `useUiStore` selector 提供 tab 切换能力。

#### Scenario: 渲染 pipelines 列表
- **WHEN** PipelinesTab 被激活
- **THEN** 组件 MUST 展示来自 `usePipelineStore(s => s.pipelines)` 的卡片列表，MUST NOT 用 props.pipelines

#### Scenario: 点击 Run 按钮
- **WHEN** 用户在 PipelinesTab 中点击某个 pipeline 的 "Run" 按钮
- **THEN** PipelinesTab MUST 调 `pipelineStore.setActivePreset(name)` + `uiStore.setActiveTab('exec')`，MUST NOT 通过 props.onSelectPreset + props.onTabChange

#### Scenario: 点击 Delete 按钮
- **WHEN** 用户在 PipelinesTab 中点击删除按钮并确认
- **THEN** PipelinesTab MUST 调 `pipelineStore.deletePipeline(name)`，MUST NOT 通过 props.onDeletePipeline

#### Scenario: 点击 Refresh 按钮
- **WHEN** 用户点击 PipelinesTab 的 Refresh 按钮
- **THEN** PipelinesTab MUST 调 `pipelineStore.refreshPipelines()`，MUST NOT 通过 props.onRefresh
