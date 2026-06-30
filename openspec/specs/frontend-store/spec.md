# Frontend Store

## Requirements

### uiStore 必须提供所有全局 UI 偏好状态
系统 MUST 提供 uiStore，暴露 ctiveTab、	heme、chatLayoutReversed、sidebarCollapsed 字段以及对应的 setter action。所有 UI 偏好 MUST 在变更时同步写入 localStorage 以保持持久化。

#### Scenario: 用户切换 Tab
- **WHEN** 用户点击某个 Tab 按钮
- **THEN** 系统 MUST 调用 uiStore.setActiveTab(tabName)，且所有订阅该字段的组件 MUST 收到新值

#### Scenario: 用户切换主题
- **WHEN** 用户在设置中点击"亮色/暗色"按钮
- **THEN** 系统 MUST 调用 uiStore.setTheme('light' | 'dark')，同步写入 localStorage('theme', ...)，并设置 document.documentElement.setAttribute('data-theme', ...)

#### Scenario: 用户切换 Chat 面板顺序
- **WHEN** 用户在 SettingsTab 中点击"Editor First / Chat First"
- **THEN** 系统 MUST 调用 uiStore.setChatLayoutReversed(true|false)，同步写入 localStorage('chat-layout-reversed', ...)

#### Scenario: 用户折叠/展开 Chat Sidebar
- **WHEN** 用户点击 sidebar 折叠按钮
- **THEN** 系统 MUST 调用 uiStore.setSidebarCollapsed(true|false)，同步写入 localStorage('chat-sidebar-collapsed', ...)

### connectionStore 必须管理浏览器连接全生命周期
系统 MUST 提供 connectionStore，持有 connected、wsUrl、connectionError、profiles、selectedProfile、connectMode、estartDialog、estarting、highlightMode 状态；提供 connect、disconnect、estart、createProfile action；提供 connectedRef（store 外部的模块级布尔变量，用于 chrome_disconnected handler 中检测跳变）和 connectGen（模块级数字，用于 generation counter 过期检测）。MUST 提供 handleBrowserDisconnect action 供 gateway 调用。

#### Scenario: generation counter 正确递增
- **WHEN** 用户点击 connect 按钮
- **THEN** 系统 MUST 在 connect action 入口处执行 connectGen++ 并保存为 localGen，异步操作完成后 MUST 检查 if (localGen !== connectGen) return;，确保过期响应被丢弃

#### Scenario: uiStore localStorage 静默失败
- **WHEN** uiStore 任何 setter 调用 localStorage.setItem/setAttribute 时
- **THEN** MUST 在 try-catch 中执行，异常 MUST 静默吞掉

#### Scenario: 用户点击连接按钮
- **WHEN** 前端调用 connectionStore.connect(mode, profile)
- **THEN** 系统 MUST 调 pi.connectBrowser(mode, profile, highlightMode)，成功时 set connected=true，失败时 set connectionError

#### Scenario: 后端推送 chrome_disconnected 事件
- **WHEN** wsGateway 分发 chrome_disconnected 事件
- **THEN** connectionStore MUST 调 handleBrowserDisconnect()，将 connected 置为 false、wsUrl 清空

### pipelineStore 必须管理管道数据和执行状态
系统 MUST 提供 pipelineStore，持有 pipelines、ctivePreset、pipelineCache、pipelineEditor、events、esult、esultErrors、loading、currentRunId、currentPipeline、cancelling、pendingReview、eviewMode 状态。

### pipelineStore 必须从 events 计算 stages/stepNames
pipelineStore 必须在内部维护 derivation 逻辑：从 events 数组计算 stepNames、stepStarts、stepEnds、getStepStatus(name) 函数。

### chatStore 必须管理聊天全状态
系统 MUST 提供 chatStore，持有 chatMessages、pendingEdits、processedEditIds（模块级 Set）、currentSessionId、chatSessions、pipelineSessions、expandedNodes、loadingSession 状态和内部可变的 streamStates。

### credentialStore 必须管理凭据
系统 MUST 提供 credentialStore，持有 credKeys、credKey、credValue 状态，并提供 setCredKey、setCredValue、ddCredential、emoveCredential action。
