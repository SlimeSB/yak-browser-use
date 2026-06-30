# App.tsx Layout

## Requirements

### App.tsx 必须瘦身为布局编排器
App.tsx MUST 不再持有任何业务 state（所有 useState 必须迁移到对应 store），MUST 只保留 JSX 结构：TitleBar、ConnectionBar、TabBar、TabContent、StatusBar。

#### Scenario: App 渲染
- **WHEN** 首次渲染
- **THEN** App MUST 渲染各 Tab 组件且 MUST 不传递任何业务 props

### App.tsx 不再内联 WebSocket handler
App.tsx MUST 不包含任何 ws.onmessage 或 setChatMessages/setEvents/setConnected/setLoading 等内联状态操作。

#### Scenario: 检查代码
- **WHEN** 审阅 App.tsx
- **THEN** 文件 MUST 不包含 useEffect(() => { let ws: WebSocket 或 setChatMessages 调用
