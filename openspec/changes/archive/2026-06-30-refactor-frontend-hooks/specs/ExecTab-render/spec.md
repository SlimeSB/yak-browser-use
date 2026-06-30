## ADDED Requirements

### Requirement: ExecTab 必须从 pipelineStore 获取状态
ExecTab MUST 删除以下 **20 个** props：`activePreset`、`setActivePreset`、`pipelines`、`loading`、`connected`、`currentRunId`、`cancelling`、`preset`、`params`、`pendingReview`、`stages`、`events`、`result`、`resultErrors`、`onRun`、`onParamChange`、`onCancel`、`onReviewApprove`、`onReviewReject`、`onTabChange`，改为内部 `usePipelineStore(selector)` + `useUiStore(s => s.setActiveTab)`（for onTabChange）。

#### Scenario: 执行管道
- **WHEN** 用户点击运行
- **THEN** ExecTab 内部 MUST 调 `pipelineStore.run(params)` 并展示进度条，MUST NOT 通过 props.onRun
