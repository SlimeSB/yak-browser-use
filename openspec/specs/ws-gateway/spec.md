# WebSocket Gateway

## Requirements

### gateway 必须在 main.tsx 初始化
系统 MUST 在 main.tsx 的 oot.render(<App />) 之前调用 initGateway()，确保 WebSocket 连接在 React 挂载前建立。gateway 作为模块级 singleton 存在，不参与 React 生命周期。

#### Scenario: 应用启动顺序
- **WHEN** main.tsx 被 Vite 加载
- **THEN** 执行顺序 MUST 为：import { initGateway } from './ws/gateway' → initGateway() → oot.render(<App />)

### gateway 必须管理 WebSocket 连接生命周期
系统 MUST 提供 ws/gateway.ts，封装连接、重连（3s/5s 退避）、关闭逻辑，在组件树外作为 singleton 存在。

#### Scenario: 连接断开（正常 close）
- **WHEN** WebSocket onclose 触发
- **THEN** gateway MUST 在 3 秒后调度重连

#### Scenario: 连接断开（error）
- **WHEN** WebSocket onerror 触发
- **THEN** gateway MUST 在 5 秒后调度重连

### gateway 必须按严格顺序分派事件类型
系统 MUST 在收到 WebSocket message 时按以下 if/else 链顺序判断，匹配一项后立即 return：
1. event.type.startsWith('chat.') → chatStore.handleWsEvent(event)
2. event.type === 'pipeline.edit' → chatStore.handleWsEvent(event) + pipelineStore.handlePipelineEdit(event)
3. event.type === 'chrome_disconnected' → connectionStore.handleBrowserDisconnect()
4. event.type === 'run_end' → pipelineStore.handleRunEnd(event)
5. 默认 fallthrough → pipelineStore.addEvent(event)

### gateway 必须防止 React re-render
系统 MUST 在 React 组件树之外实例化，组件不得直接持有 gateway 引用，只能通过暴露的 getGateway() 访问。
