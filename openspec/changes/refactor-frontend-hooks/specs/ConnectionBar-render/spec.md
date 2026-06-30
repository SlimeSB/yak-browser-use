## ADDED Requirements

### Requirement: ConnectionBar 必须从 connectionStore 获取状态
ConnectionBar MUST 删除以下 **10 个** props：`connected`、`wsUrl`、`connectionError`、`connectMode`、`selectedProfile`、`profiles`、`onConnect`、`onDisconnect`、`onModeChange`、`onProfileChange`、`onCreateProfile`，全部改为内部 `useConnectionStore(selector)`。

#### Scenario: 连接状态显示
- **WHEN** 浏览器已连接
- **THEN** ConnectionBar MUST 展示绿色指示灯和 wsUrl，数据来自 `useConnectionStore(s => s.connected)` 和 `useConnectionStore(s => s.wsUrl)`

#### Scenario: 未连接状态
- **WHEN** `connected === false`
- **THEN** MUST 展示断开状态文案 + 错误信息（如有）+ 连接模式切换（user/isolated）组件；数据来自 `useConnectionStore(s => s.connectionError)` 和 `useConnectionStore(s => s.connectMode)`

#### Scenario: 用户点击连接按钮（user 模式）
- **WHEN** 用户在 user 模式下点击"连接 Chrome"按钮
- **THEN** ConnectionBar MUST 调 `connectionStore.connect('user')`，不通过 props.onConnect

#### Scenario: 用户点击连接按钮（isolated 模式）
- **WHEN** 用户在 isolated 模式下点击"启动并连接"按钮
- **THEN** ConnectionBar MUST 调 `connectionStore.connect('isolated', selectedProfile)`，selectedProfile 从 store selector 取得

#### Scenario: 用户点击断开按钮
- **WHEN** connected === true 且用户点击"断开"按钮
- **THEN** ConnectionBar MUST 调 `connectionStore.disconnect()`，不通过 props.onDisconnect

#### Scenario: 用户切换连接模式
- **WHEN** 用户点击 mode-switch radio（user↔isolated）
- **THEN** ConnectionBar MUST 调 `connectionStore.setConnectMode(mode)` + `connectionStore.setConnectionError(null)` 清空错误

#### Scenario: 用户切换 profile
- **WHEN** 用户在 profile-select 下拉选择另一个 profile
- **THEN** ConnectionBar MUST 通过 `connectionStore.setSelectedProfile(name)` 更新 store

#### Scenario: 用户创建新 profile
- **WHEN** 用户在 profile 区域点击"新建"按钮并输入名称后确认
- **THEN** ConnectionBar MUST 调 `connectionStore.createProfile(name)`；组件内部 MUST 管理 showNewProfileInput 和 newProfileName 的临时 UI 状态（useState，不属于 store）

#### Scenario: 显示 restartDialog
- **WHEN** connectionStore.restartDialog 非 null（通过 connect action 内部 setRestartDialog 设置）
- **THEN** ConnectionBar MUST 显示重启对话框，提供"关闭并重启"/"使用 isolated"/"取消"三个按钮；点击后 MUST 调对应的 connectionStore action

#### Scenario: highlightMode 存入 connectionStore
- **WHEN** highlightMode 需要与 connect action 共享显示策略
- **THEN** highlightMode MUST 存入 connectionStore（而非 App.tsx 的 useState + localStorage 单独管理）；ConnectionBar MUST 通过 `useConnectionStore(s => s.highlightMode)` 读取
