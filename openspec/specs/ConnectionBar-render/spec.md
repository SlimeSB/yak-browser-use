# ConnectionBar Render

## Requirements

### ConnectionBar 必须从 connectionStore 获取状态
ConnectionBar MUST 删除 11 个 props，全部改为内部 useConnectionStore(selector)。

#### Scenario: 连接状态显示
- **WHEN** 浏览器已连接
- **THEN** ConnectionBar MUST 展示绿色指示灯和 wsUrl，数据来自 useConnectionStore(s => s.connected) 和 useConnectionStore(s => s.wsUrl)

#### Scenario: 用户点击连接按钮
- **WHEN** 用户在 user 模式下点击"连接 Chrome"按钮
- **THEN** ConnectionBar MUST 调 connectionStore.connect('user')，不通过 props.onConnect

#### Scenario: 用户点击断开按钮
- **WHEN** connected === true 且用户点击"断开"按钮
- **THEN** ConnectionBar MUST 调 connectionStore.disconnect()，不通过 props.onDisconnect

#### Scenario: highlightMode 存入 connectionStore
- **WHEN** highlightMode 需要与 connect action 共享显示策略
- **THEN** highlightMode MUST 存入 connectionStore；ConnectionBar MUST 通过 useConnectionStore(s => s.highlightMode) 读取
