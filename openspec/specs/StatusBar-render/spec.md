# StatusBar Render

## Requirements

### StatusBar 必须从 pipelineStore 和 connectionStore 获取状态
StatusBar MUST 删除 2 个 props：`events`（来自 pipelineStore）、`connected`（来自 connectionStore），改为内部 selector。

#### Scenario: 显示连接状态
- **WHEN** 渲染 StatusBar
- **THEN** MUST 展示一个 conn-dot 指示器 + 连接/断开文案，数据来自 `useConnectionStore(s => s.connected)`

#### Scenario: 显示步骤进度
- **WHEN** pipelineStore.events 含 step_start/step_end
- **THEN** MUST 显示 "步骤 stepDone/stepTotal"

#### Scenario: 就绪状态
- **WHEN** stepTotal === 0
- **THEN** MUST 显示"就绪"文案
