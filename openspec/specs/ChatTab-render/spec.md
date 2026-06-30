# ChatTab Render

## Requirements

### ChatTab 必须从 store 获取数据而非 props
ChatTab MUST 不再接收 23 个 props，全部改为内部 selector 读取 chatStore / connectionStore / pipelineStore。

### ChatTab 组件内 nextMsgId 必须迁移到共享工具
MUST 保留 
extMsgId 工具函数在 electron/src/renderer/utils/nextMsgId.ts（与 interpolate 同级）或 types.ts 中不动；chatStore MUST 从该导入引用，不得在 store 内自增计数器。

### ChatTab 组件内 api.chat 调用必须迁移到 chatStore
ChatTab 当前内部直接 wait api.chat()，迁移后 MUST 改为调 chatStore.send(text)，由 chatStore 内部统一封装 api 调用。
