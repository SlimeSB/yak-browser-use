## ADDED Requirements

### Requirement: gateway 必须在 main.tsx 初始化
系统 MUST 在 `main.tsx` 的 `root.render(<App />)` 之前调用 `initGateway()`，确保 WebSocket 连接在 React 挂载前建立。gateway 作为模块级 singleton 存在，不参与 React 生命周期。

#### Scenario: 应用启动顺序
- **WHEN** main.tsx 被 Vite 加载
- **THEN** 执行顺序 MUST 为：`import { initGateway } from './ws/gateway'` → `initGateway()` → `root.render(<App />)`

### Requirement: gateway 必须管理 WebSocket 连接生命周期
系统 MUST 提供 `ws/gateway.ts`，封装连接、重连（3s/5s 退避）、关闭逻辑，在组件树外作为 singleton 存在。

#### Scenario: 首次渲染
- **WHEN** 应用启动
- **THEN** gateway MUST 调用 `api.createWebSocket('/ws/events')` 建立连接

#### Scenario: 连接断开（正常 close）
- **WHEN** WebSocket onclose 触发
- **THEN** gateway MUST 在 3 秒后调度重连；重连 MUST 复用同一个 stopped 标志位

#### Scenario: 连接断开（error）
- **WHEN** WebSocket onerror 触发
- **THEN** gateway MUST 在 5 秒后调度重连

#### Scenario: 应用卸载
- **WHEN** gateway 被显式销毁（如开发模式 HMR）
- **THEN** MUST 设置 stopped=true 并 clearTimeout + ws.close()

### Requirement: gateway 必须按严格顺序分派事件类型
系统 MUST 在收到 WebSocket message 时按以下 if/else 链顺序判断，匹配一项后立即 return，不继续向下匹配：
1. `event.type.startsWith('chat.') || event.type === 'pipeline.edit'` → `chatStore.handleWsEvent(event)`
2. `event.type === 'chrome_disconnected'` → `connectionStore.handleBrowserDisconnect()`
3. `event.type === 'run_end'` → `pipelineStore.handleRunEnd(event)`
4. 默认 fallthrough → `pipelineStore.addEvent(event)`

**MUST NOT** 使用散列查找或并行 if 判断——顺序是正确性的关键，`run_end` 必须优先于默认 fallthrough 被识别。

#### Scenario: 收到 chat.text_chunk
- **WHEN** gateway 收到 `{type:'chat.text_chunk', turn_index:3, content:'foo'}`
- **THEN** 系统 MUST 调 `chatStore.handleWsEvent(event)`（步骤 1 命中）且 MUST NOT 调 pipelineStore

#### Scenario: 收到 chrome_disconnected
- **WHEN** gateway 收到 `{type:'chrome_disconnected'}`
- **THEN** 系统 MUST 调 `connectionStore.handleBrowserDisconnect()`（步骤 2 命中）

#### Scenario: 收到 run_end
- **WHEN** gateway 收到 `{type:'run_end'}`
- **THEN** 系统 MUST 调 `pipelineStore.handleRunEnd(event)`（步骤 3 命中）且 MUST NOT 走 fallthrough

#### Scenario: 收到 step_start
- **WHEN** gateway 收到 `{type:'step_start', step:'goto', ...}`
- **THEN** 系统 MUST 调 `pipelineStore.addEvent(eventData)`（步骤 4 默认命中）

#### Scenario: 收到 chat.stream_start
- **WHEN** gateway 收到 `{type:'chat.stream_start', turn_index:7}`
- **THEN** 系统 MUST 调 `chatStore.handleWsEvent(event)`（步骤 1 命中，startsWith('chat.') 匹配）且 MUST NOT chrome_disconnected / run_end 路径

### Requirement: gateway 必须防止 React re-render
系统 MUST 在 React 组件树之外实例化，组件不得直接持有 gateway 引用，只能通过暴露的 `getGateway()` 访问。

#### Scenario: 多个组件同时监听
- **WHEN** chatStore 和 pipelineStore 各自 selector 订阅同一 event 触发的 cascade 更新
- **THEN** gateway 的一次 dispatch MUST 只触发目标 store update，各自 selector 独立 re-render，不发生级联

### Requirement: gateway 分派 action 名称必须精准对齐 store spec
gateway.ts MUST 按以下固定名称调用 store action，MUST NOT 自行发明 action 名：

| 事件模式 | store | action |
|----------|-------|--------|
| `chat.*` 或 `pipeline.edit` | chatStore | `handleWsEvent(event)` |
| `chrome_disconnected` | connectionStore | `handleBrowserDisconnect()` |
| `run_end` | pipelineStore | `handleRunEnd(event)` |
| 默认 | pipelineStore | `addEvent(event)` |
