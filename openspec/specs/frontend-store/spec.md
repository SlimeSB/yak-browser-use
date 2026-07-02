## ADDED Requirements

### Requirement: frontend components MUST use stores instead of props
All frontend tab components and App.tsx MUST 不再通过 props 接收业务状态，全部改为从对应 store 内部 selector 读取。App.tsx MUST 瘦身为纯布局编排器：TitleBar、ConnectionBar、TabBar、TabContent、StatusBar。

#### Scenario: App.tsx 渲染
- **WHEN** 首次渲染
- **THEN** App MUST 渲染各 Tab 组件且 MUST 不传递任何业务 props
- **AND** App.tsx MUST 不包含任何 useState/setChatMessages/setEvents/setConnected/setLoading 等内联状态操作

#### Scenario: ChatTab 从 store 获取数据
- **WHEN** ChatTab 被激活
- **THEN** ChatTab MUST 从 chatStore / connectionStore / pipelineStore 内部 selector 读取
- **AND** MUST NOT 接收 23+ 个 props
- **AND** 内部 api.chat 调用 MUST 改为调 chatStore.send(text)

#### Scenario: ExecTab 从 pipelineStore 获取状态
- **WHEN** 用户点击运行
- **THEN** ExecTab MUST 调 pipelineStore.run(params)
- **AND** MUST NOT 通过 props.onRun

#### Scenario: LogTab 从 pipelineStore 获取状态
- **WHEN** 用户清空 events
- **THEN** LogTab MUST 调 pipelineStore.clearEvents()

#### Scenario: PipelinesTab 从 store 获取数据
- **WHEN** 渲染 pipelines 列表
- **THEN** MUST 展示来自 `usePipelineStore(s => s.pipelines)` 的卡片列表
- **AND** 点击 Run 按钮 MUST 调 `pipelineStore.setActivePreset(name)` + `uiStore.setActiveTab('exec')`

#### Scenario: SettingsTab 从 store 获取状态
- **WHEN** 用户切换 reviewMode/theme/highlightMode
- **THEN** MUST 调对应 store 的 action，不通过 props

#### Scenario: ParamsTab 从 credentialStore 获取状态
- **WHEN** 渲染凭据列表
- **THEN** MUST 通过 `useCredentialStore(s => s.credKeys)` 获取凭据列表

#### Scenario: StatusBar 从 store 获取状态
- **WHEN** 渲染 StatusBar
- **THEN** MUST 展示 conn-dot 指示器（useConnectionStore）+ 步骤进度（pipelineStore.events）

#### Scenario: ConnectionBar 从 connectionStore 获取状态
- **WHEN** 用户点击连接/断开按钮
- **THEN** MUST 调 connectionStore.connect()/disconnect()，不通过 props.onConnect/onDisconnect
- **AND** highlightMode MUST 存入 connectionStore
