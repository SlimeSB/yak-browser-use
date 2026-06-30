## ADDED Requirements

### Requirement: ChatTab 必须从 store 获取数据而非 props
ChatTab MUST 不再接收以下 **23 个** props，全部改为内部 selector 读取 chatStore / connectionStore / pipelineStore：

| prop | 来源 store | selector |
|------|-----------|----------|
| `messages`, `setMessages` | chatStore | `useChatStore(s => s.chatMessages)` |
| `connected` | connectionStore | `useConnectionStore(s => s.connected)` |
| `activePreset` | pipelineStore | `usePipelineStore(s => s.activePreset)` |
| `currentSessionId` | chatStore | `useChatStore(s => s.currentSessionId)` |
| `loadingSession` | chatStore | `useChatStore(s => s.loadingSession)` |
| `onNewSession` | chatStore | `useChatStore(s => s.newSession)` |
| `onArchiveSession` | chatStore | `useChatStore(s => s.archiveSession)` |
| `onSelectSession` | chatStore | `useChatStore(s => s.selectSession)` |
| `pendingEdit` | chatStore | `useChatStore(s => s.activePendingEdit)` |
| `onConfirmEdit` | chatStore | `useChatStore(s => s.confirmEdit)` |
| `onRevertEdit` | chatStore | `useChatStore(s => s.revertEdit)` |
| `treeNodes` | chatStore | `useChatStore(s => s.selectTreeNodes)` |
| `expandedNodes` | chatStore | `useChatStore(s => s.expandedNodes)` |
| `onToggleExpand` | chatStore | `useChatStore(s => s.toggleExpand)` |
| `sidebarCollapsed` | uiStore | `useUiStore(s => s.sidebarCollapsed)` |
| `onToggleSidebar` | uiStore | `useUiStore(s => s.setSidebarCollapsed)` |
| `pipelineEditor` | pipelineStore | `usePipelineStore(s => s.pipelineEditor)` |
| `onPipelineEditorChange` | pipelineStore | `usePipelineStore(s => s.setPipelineEditor)` |
| `onRefreshPipeline` | pipelineStore | `usePipelineStore(s => s.refreshPipeline)` |
| `onDeletePipeline` | pipelineStore | `usePipelineStore(s => s.deletePipeline)` |
| `onSavePipeline` | pipelineStore | `usePipelineStore(s => s.savePipeline)` |
| `reversed` | uiStore | `useUiStore(s => s.chatLayoutReversed)` |
| `theme` | uiStore | `useUiStore(s => s.theme)` |

#### Scenario: 渲染聊天消息列表
- **WHEN** ChatTab 渲染
- **THEN** 组件 MUST 通过 `useChatStore(s => s.chatMessages)` 获取消息列表，MUST NOT 用 props.messages

#### Scenario: 发送消息
- **WHEN** 用户点击发送按钮
- **THEN** ChatTab 内部 MUST 调用 `chatStore.send(text)`，MUST NOT 暴露给 App.tsx 的回调；send 内部 MUST 调 api.chat 并在失败时追加错误 assistant 消息

#### Scenario: 切换 session（pipeline expanded）
- **WHEN** 用户在 sidebar 点击某个 session tree node
- **THEN** ChatTab MUST 调 `chatStore.selectSession(id)`，MUST NOT 通过 props.onSelectSession

#### Scenario: 点击 sidebar 标题展开/折叠 tree
- **WHEN** 用户点击 tree node header（pipeline 名称）
- **THEN** ChatTab MUST 调 `chatStore.toggleExpand(name)`，内部 MUST 同时 switchPipeline(name) 切换当前活动 preset

#### Scenario: 创建新 session
- **WHEN** 用户点击"+"按钮（header 旁的新建按钮）
- **THEN** ChatTab MUST 调 `chatStore.newSession()`，MUST NOT 通过 props.onNewSession；disabled 状态 MUST 依赖 loadingSession && messages.length === 0

#### Scenario: 删除 pipeline（delete 按钮）
- **WHEN** 用户点击 header 上的删除图标（pipeline active 且 name !== '__chat__'）
- **THEN** ChatTab MUST confirm 后调 `pipelineStore.deletePipeline(name)`，MUST NOT 通过 props.onDeletePipeline

#### Scenario: 折叠 sidebar
- **WHEN** 用户点击左栏 header 旁的折叠按钮（◀）
- **THEN** ChatTab MUST 调 `uiStore.setSidebarCollapsed(true)`；按钮文案 MUST 根据 sidebarCollapsed 状态切换 ▶ / ◀

#### Scenario: pipeline edit diff 展示
- **WHEN** chatStore.activePendingEdit 非 null
- **THEN** ChatTab MUST 显示 diff-bar：显示 explanation、original vs modified Monaco diff editor、Confirm/Revert 按钮；Confirm 调 `chatStore.confirmEdit(editId)`，Revert 调 `chatStore.revertEdit(editId)`

#### Scenario: pipeline 编辑
- **WHEN** 用户在 Monaco editor 中编辑 pipeline 内容
- **THEN** ChatTab MUST 调 `pipelineStore.setPipelineEditor(text)` 同步更新 store；工具栏的 Save 按钮调 `pipelineStore.savePipeline()`

#### Scenario: reset chat
- **WHEN** 用户点击 header 中的 Reset 按钮
- **THEN** ChatTab MUST 调 `chatStore.resetChat()`（内部调 api.chatReset 并清空 chatMessages）

#### Scenario: cancel chat
- **WHEN** 用户点击发送按钮变为 Stop 状态时再次点击
- **THEN** ChatTab MUST 调 `chatStore.cancelChat()`（内部调 api.chatCancel 并追加 system 消息）

#### Scenario: 输入框 disabled 条件
- **WHEN** 发送按钮 MUST disabled
- **THERE** 条件：`!input.trim() || !connected`（input.trim() 为空 或 浏览器未连接）；textarea disabled 条件：`!connected || sending`

#### Scenario: send button 文本/样式切换
- **WHEN** sending === true
- **THEN** button 文案 MUST 为 t('chat.stop') + MUST 使用 btn-danger 样式；否则文案为 t('chat.send') + btn-primary

#### Scenario: treeNodes 在 ChatTab 内部 useMemo 组装
- **WHEN** chatStore.chatSessions / pipelineSessions / pipelines 任一变化
- **THEN** ChatTab MUST 通过 `useChatStore(s => s.selectTreeNodes)` selector 获取 treeNodes，selector 内部 MUST 基于这三个字段 memoized 组装：1 个 __chat__ 节点 + pipelines.map 节点，每个节点挂 sessions

#### Scenario: splitRatio 保留为组件 useState
- **WHEN** 用户拖拽 chat 区分割条
- **THEN** splitRatio MUST 为 ChatTab 内部 useState（localStorage 持久化 key='chat-split-ratio'），MUST NOT 进入 store

#### Scenario: expandedThinks / expandedToolErrors / sessionStatus 是组件 useState
- **WHEN** 用户交互展开某个 think block 或 tool output
- **THEN** 这类临时 UI 状态 MUST 保留在 ChatTab 内部 useState，MUST NOT 进入 store

### Requirement: ChatTab 组件内 api.chat 调用必须迁移到 chatStore
ChatTab 当前内部直接 `await api.chat()`，迁移后 MUST 改为调 `chatStore.send(text)`，由 chatStore 内部统一封装 api 调用。

#### Scenario: 组件内 api.chat 被替换
- **WHEN** Review ChatTab.tsx 迁移后代码
- **THEN** 文件 MUST 不再有 `import * as api from '../../apiClient'` 和 `await api.chat(...)` 调用；所有 chat 操作 MUST 通过 chatStore action
