# LogTab Render

## Requirements

### LogTab 必须从 pipelineStore 获取状态
LogTab MUST 删除 14 个 props，全部改为内部 usePipelineStore(selector)。

### clearEvents action 必须在 pipelineStore 中定义
由于 LogTab 依赖清空 events 能力，MUST 在 pipelineStore 中定义 clearEvents action。
