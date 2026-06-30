## ADDED Requirements

### Requirement: LogTab 必须从 pipelineStore 获取状态
LogTab MUST 删除以下 **14 个** props：`currentRunId`、`stepNames`、`getStepStatus`、`events`、`onClearEvents`、`result`、`resultErrors`、`loading`、`stepStarts`、`stepEnds`、`preset`、`pendingReview`、`onReviewApprove`、`onReviewReject`，全部改为内部 `usePipelineStore(selector)`。

#### Scenario: 查看运行日志
- **WHEN** LogTab 被激活
- **THEN** 组件 MUST 展示来自 `usePipelineStore(s => s.events)` 的时间线，MUST NOT 用 props.events

#### Scenario: 列出 pipeline steps
- **WHEN** pipelineStore.stepNames 非空
- **THEN** LogTab MUST 将 stepNames 渲染为左边栏步骤列表；每一步调用 `pipelineStore.getStepStatus(name)` 决定样式

#### Scenario: 显示 step 运行状态
- **WHEN** 用户查看某个 step 的状态
- **THEN** LogTab MUST 展示 done（✓）、current（●）、pending（数字）、error（✗）、review（⚠）五种状态图标 + 文案

#### Scenario: 显示运行结果
- **WHEN** pipelineStore.result 非 null
- **THEN** LogTab MUST 渲染 ResultTable 展示 result + resultErrors；MUST NOT 依赖 props.result

#### Scenario: 显示 artifacts 摘要
- **WHEN** LogTab 被激活
- **THEN** MUST 显示摘要区：`步骤数 stepEnds/stepStarts`、`pipeline title`、`events 数`、`loading?/completed?/ready?` 状态

#### Scenario: 待审核 pendingReview
- **WHEN** pipelineStore.pendingReview 非 null
- **THEN** LogTab MUST 显示"待审核"卡片（review-card），包含：原因（reason）、操作列表（extraOps）、approve/reject 按钮

#### Scenario: 用户 approve 审核
- **WHEN** 用户在 review-card 中点击 Approve 按钮
- **THEN** LogTab MUST 调 `pipelineStore.reviewApprove('approved via log')`，不通过 props.onReviewApprove；调用前清空本地 logRejectReason 和 showingLogReject 状态

#### Scenario: 用户 reject 审核
- **WHEN** 用户在 review-card 中输入原因后点击 Reject 按钮
- **THEN** LogTab MUST 验证非空后调 `pipelineStore.reviewReject(reason)`；reason 必须 trim 后非空；reject 成功后清空本地 logRejectReason 状态

#### Scenario: loading 状态展示
- **WHEN** pipelineStore.loading === true
- **THEN** LogTab 摘要区 MUST 显示进行中颜色 + 文案；steps 列表中 current 状态步骤 MUST 显示"运行中"

#### Scenario: clear events
- **WHEN** 用户点击"清空日志"按钮
- **THEN** LogTab MUST 调 `pipelineStore.clearEvents()`（action 重置 events=[]），不通过 props.onClearEvents

#### Scenario: 显示 currentRunId
- **WHEN** pipelineStore.currentRunId 非空
- **THEN** 步骤栏 MUST 展示 `runId.slice(0,8)` 的截断格式

#### Scenario: 本地 reject 状态是组件内部状态
- **WHEN** 用户开始 reject 流程（点击"拒绝"按钮）
- **THEN** showingLogReject 和 logRejectReason MUST 为组件内 useState，不得进入 zustand store

### Requirement: clearEvents action 必须在 pipelineStore 中定义
由于 LogTab 依赖清空 events 能力，MUST 在 pipelineStore 中定义 `clearEvents` action。
