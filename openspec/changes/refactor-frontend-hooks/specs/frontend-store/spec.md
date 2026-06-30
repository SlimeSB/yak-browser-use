## ADDED Requirements

### Requirement: uiStore 必须提供所有全局 UI 偏好状态
系统 MUST 提供 `uiStore`，暴露 `activeTab`、`theme`、`chatLayoutReversed`、`sidebarCollapsed` 字段以及对应的 setter action。所有 UI 偏好 MUST 在变更时同步写入 localStorage 以保持持久化。

#### Scenario: 用户切换 Tab
- **WHEN** 用户点击某个 Tab 按钮
- **THEN** 系统 MUST 调用 `uiStore.setActiveTab(tabName)`，且所有订阅该字段的组件 MUST 收到新值

#### Scenario: 用户切换主题
- **WHEN** 用户在设置中点击"亮色/暗色"按钮
- **THEN** 系统 MUST 调用 `uiStore.setTheme('light' | 'dark')`，同步写入 localStorage('theme', ...)，并设置 `document.documentElement.setAttribute('data-theme', ...)`

#### Scenario: 用户切换 Chat 面板顺序
- **WHEN** 用户在 SettingsTab 中点击"Editor First / Chat First"
- **THEN** 系统 MUST 调用 `uiStore.setChatLayoutReversed(true|false)`，同步写入 localStorage('chat-layout-reversed', ...)

#### Scenario: 用户折叠/展开 Chat Sidebar
- **WHEN** 用户点击 sidebar 折叠按钮
- **THEN** 系统 MUST 调用 `uiStore.setSidebarCollapsed(true|false)`，同步写入 localStorage('chat-sidebar-collapsed', ...)

### Requirement: connectionStore 必须管理浏览器连接全生命周期
系统 MUST 提供 `connectionStore`，持有 `connected`、`wsUrl`、`connectionError`、`profiles`、`selectedProfile`、`connectMode`、`restartDialog`、`restarting`、`highlightMode` 状态；提供 `connect`、`disconnect`、`restart`、`createProfile` action；提供 `connectedRef`（store 外部的模块级布尔变量，用于 `chrome_disconnected` handler 中检测跳变）和 `connectGen`（模块级数字，用于 generation counter 过期检测）。MUST 提供 `handleBrowserDisconnect` action 供 gateway 调用——该 action 内部负责检测 connectedSnapshot 跳变并递增 connectGen，然后将 connected 置为 false、wsUrl 清空。

> **设计说明（E3）：** `restartDialog` 和 `restarting` 进入 connectionStore 的理由：
> - restartDialog 和 restarting 虽然在 App.tsx 内是独立的 useState，但它们共同描述"浏览器重启"这一 connection domain 的子状态
> - ConnectionBar 的模态对话框按钮需要同时读取 restartDialog 和 restarting 来驱动"确认/取消/重启中"三种 UI 状态
> - 如果保留在组件内，每次重启流程（handleRestartConfirm）都需要通过 props 注入多个 callback；现存 ConnectionBar 已有 10 个 props，全部进入 store 更合理
> - 技术上 zustand state 对一个"仅在模态框使用"的布尔值不会带来性能代价；而 restartDialog 的全局可见性为未来跨组件感知重启姿态保留了扩展点

#### Scenario: generation counter 正确递增（E10 原子性）
- **WHEN** 用户点击 connect 按钮
- **THEN** 系统 MUST 在 connect action 入口处执行 `connectGen++` 并保存为 `localGen`，异步操作完成后 MUST 检查 `if (localGen !== connectGen) return;`，确保过期响应被丢弃
- **约束：** `connectGen++` 和 `localGen = connectGen` MUST 在第一个 `await` 之前发生（单线程同步过期检测）；过期检查 MUST 在最后一个 `await` 之后立即执行，中间不能有其他 await 分支

#### Scenario: uiStore localStorage 静默失败（E11）
- **WHEN** uiStore 任何 setter 调用 localStorage.setItem/setAttribute 时
- **THEN** MUST 在 try-catch 中执行，异常 MUST 静默吞掉（不抛出、不记录）；与当前 App.tsx 行为一致（catch { /* ok */ }）

#### Scenario: 用户点击连接按钮
- **WHEN** 前端调用 `connectionStore.connect(mode, profile)`
- **THEN** 系统 MUST 调 `api.connectBrowser(mode, profile, highlightMode)`，成功时 set `connected=true`，失败时 set `connectionError`

#### Scenario: 后端推送 chrome_disconnected 事件
- **WHEN** wsGateway 分发 `chrome_disconnected` 事件
- **THEN** connectionStore MUST 调 `handleBrowserDisconnect()`，将 `connected` 置为 false、`wsUrl` 清空

#### Scenario: handleBrowserDisconnect 检测跳变
- **WHEN** `handleBrowserDisconnect` 被调用时 connectedSnapshot 为 true
- **THEN** 系统 MUST 执行 `connectGen++` 以取消任何进行中的异步 connect 操作；若 connectedSnapshot 为 false 则跳过递增

### Requirement: pipelineStore 必须管理管道数据和执行状态
系统 MUST 提供 `pipelineStore`，持有 `pipelines`、`activePreset`、`pipelineCache`、`pipelineEditor`、`events`、`result`、`resultErrors`、`loading`、`currentRunId`、`currentPipeline`、`cancelling`、`pendingReview`、`reviewMode` 状态。

**必须提供的 action 列表：**
- `run` — 执行管道（内部 MUST 调 `interpolateTemplate` 展开参数，前置插入 review_mode）
- `cancel` — 取消当前运行
- `reviewApprove` / `reviewReject` — 审核 pendingReview
- `refreshPipelines` — 从后端刷新 pipelines 列表
- `deletePipeline` / `savePipeline` — 删除/保存管道
- `setActivePreset` — 设置当前活动管道
- `setReviewMode` — 设置审核模式（'human' | 'llm' | 'none'）
- `setPendingReview` — 设置待审核状态
- `setLoading` / `setCancelling` — 内部 setter
- `setCurrentPipeline` / `setCurrentRunId` — 内部 setter
- `addEvent` — WebSocket fallthrough 路径追加事件到 `events`
- `handleRunEnd` — 处理运行结束语义（重置 loading=false / currentRunId='' / currentPipeline=''）；MUST NOT 触碰 result 和 resultErrors，保留到下一次 pipeline 开始或用户手动重置

### Requirement: pipelineStore 必须从 events 计算 stages/stepNames
pipelineStore 必须在内部维护 derivation 逻辑：从 `events` 数组计算 `stepNames`、`stepStarts`、`stepEnds`、`getStepStatus(name)` 函数，使得 ExecTab/LogTab 不必在 App.tsx 重新实现这个 compute。

#### Scenario: events 变更后 stepNames 自动更新
- **WHEN** addEvent 追加了 step_start 或 preset.stages 字段变化
- **THEN** pipelineStore 暴露 MUST 返回最新 stepNames 数组/computed ref，下游 MUST 通过 `usePipelineStore(s => s.stepNames)` selector 获取

#### Scenario: getStepStatus 语义对齐
- **WHEN** 用户查询某个 stepName 状态
- **THEN** getStepStatus MUST 返回 'pending' | 'current' | 'done' | 'error' | 'review'，判定规则 MUST 与 App.tsx:791-801 行一致：
  - 存在 step_error → 'error'
  - pendingReview 非 null 且已 step_start 未 step_end → 'review'
  - step_start 且 step_end → 'done'
  - step_start 未 step_end → 'current'
  - 默认 → 'pending'

### Requirement: chatStore 必须管理聊天全状态
系统 MUST 提供 `chatStore`，持有 `chatMessages`、`pendingEdits`、`processedEditIds`（模块级 Set）、`currentSessionId`、`chatSessions`、`pipelineSessions`、`expandedNodes`、`loadingSession` 状态和内部可变的 `streamStates`（模块级 Record，不放进 zustand state）；提供 `send`、`cancelChat`、`resetChat`、`newSession`、`archiveSession`、`selectSession`、`setMessages`、`switchPipeline`、`toggleExpand`、`confirmEdit`、`revertEdit` action。

#### Scenario: 用户发送消息
- **WHEN** 前端调用 `chatStore.send(message)`
- **THEN** 系统 MUST 将 user 消息追加到 `chatMessages`，调 `api.chat(message, pipelineName)`，失败时追加 assistant 错误消息

#### Scenario: WebSocket 推送 8 种 chat.* 事件
- **WHEN** wsGateway 分派 chat 事件
- **THEN** chatStore.handleWsEvent MUST 完整处理以下 8 种子类型，每种都 MUST 按照 App.tsx:308-456 行的原语义执行：
  1. `chat.tool_start` — 在 chatMessages 末尾追加 tool 消息；同时向 events 数组追加
  2. `chat.tool_end` — 反向查找匹配 toolCallId 的 tool 消息并更新 toolOk/toolDuration/content；同时向 events 数组追加
  3. `chat.error` — 标记对应 turn_index 的 streamState.complete=true；追加 assistant 错误消息
  4. `chat.stream_start` — 重置对应 turn_index 的 streamState；向前修剪 20 轮以上的过期 state；替换末尾空 assistant 消息或追加新消息
  5. `chat.text_chunk` — 累积到 streamStates[turn_index].accumulating；更新末尾 assistant 消息的 content
  6. `chat.think_chunk` — 追加到 streamStates[turn_index].reasoningParts；更新末尾 assistant 消息的 reasoning
  7. `chat.tool_generated` — 设置 streamStates[turn_index].toolAnnotation；在末尾 assistant 内容后追加"\n\n Calling tool: {toolName}"标注
  8. `chat.stream_end` — 标记 complete=true；强制用最终累积内容更新末尾 assistant 消息

#### Scenario: pipeline.edit 事件
- **WHEN** wsGateway 分派 `pipeline.edit` 事件
- **THEN** gateway MUST 显式分派到 **两个 store**（见 ws-gateway spec）：
  1. `chatStore.handleWsEvent(event)` — 管理 pendingEdits 状态
  2. `pipelineStore.handlePipelineEdit(event)` — 调用 api.listPipelines() 刷新 pipelines 缓存
  
  MUST NOT 让 chatStore 内部回调 pipelineStore；两个 store 的 action MUST 由 gateway 显式顺序调用，保持 store 间解耦。

#### Scenario: setMessages action
- **WHEN** selectSession 从后端加载了历史会话数据
- **THEN** chatStore MUST 暴露 `setMessages(messages: ChatMessage[]) action` 用于将加载到的消息写入 store；selectSession 内部 MUST 调 setMessages(r.session.messages || []) 替换现有消息列表

#### Scenario: treeNodes 派生逻辑
- **WHEN** 下游组件需要 treeNodes 结构
- **THEN** treeNodes MUST 由 chatStore 内部 selector 或组件 useMemo 派生：一个 `__chat__` 节点 + pipelines 映射的 pipeline 节点，每个节点挂 sessions。chatStore 暴露 `selectTreeNodes` selector 返回 `${chatSessions}_${pipelineSessions}_${pipelines}` 的 memoized 结果。

### Requirement: credentialStore 必须管理凭据
系统 MUST 提供 `credentialStore`，持有 `credKeys`、`credKey`、`credValue` 状态，并提供 `setCredKey`、`setCredValue`、`addCredential`、`removeCredential` action。

#### Scenario: 用户新增凭据
- **WHEN** 前端调用 `credentialStore.addCredential()`
- **THEN** 系统 MUST 调 `api.setCredential(key, value)` 并刷新 `credKeys`
