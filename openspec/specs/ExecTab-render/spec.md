# ExecTab Render

## Requirements

### ExecTab 必须从 pipelineStore 获取状态
ExecTab MUST 删除 20 个 props，改为内部 usePipelineStore(selector) + useUiStore(s => s.setActiveTab)。

#### Scenario: 执行管道
- **WHEN** 用户点击运行
- **THEN** ExecTab 内部 MUST 调 pipelineStore.run(params) 并展示进度条，MUST NOT 通过 props.onRun
