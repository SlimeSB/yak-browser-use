## Why

`App.tsx` 当前有 1041 行代码，承载了 30 个 useState/useRef 和 200 行内联 WebSocket 事件处理。
所有前端状态（聊天、管道执行、浏览器连接、Pipeline 编辑器、凭据、设置）集中在这一处，
再通过 props 向下分发给各个 Tab 组件。典型的 "God Component" + "prop drilling" 反模式。

后果：
- ChatTab 接收 22 个 prop，本身也接近 God Object
- 修改任一领域的状态都可能意外触发其他组件 re-render
- 新人理解成本极高：任何功能都要先看 App.tsx 才能动手
- 无法单独复用或测试任一领域的逻辑

目标：引入 zustand 全局 store 替代 App.tsx 的状态中枢地位，让每个组件
直接 subscribe 自己需要的数据，App.tsx 瘦身为纯布局编排层。

## What Changes

**新增：**
- `electron/src/renderer/stores/` 目录，包含 5 个 zustand store：
  - `uiStore` — activeTab, theme, chatLayoutReversed, sidebarCollapsed（全部 localStorage 持久化）
  - `connectionStore` — connected, wsUrl, connectionError, profiles, restartDialog, highlightMode, connectMode, selectedProfile；模块级 connectGen + connectedSnapshot 可变变量
  - `pipelineStore` — pipelines, activePreset, pipelineCache, pipelineEditor, events, result, resultErrors, loading, currentRunId, pendingReview, reviewMode
  - `chatStore` — chatMessages, streamStatesRef, pendingEdits, currentSessionId, chatSessions, pipelineSessions, expandedNodes；模块级 streamStates + processedEditIds 可变变量
  - `credentialStore` — credKeys, credKey, credValue
- `electron/src/renderer/ws/gateway.ts` — 单一 WebSocket 网关，根据 event.type 按严格 if/else 顺序分发到各 store action
- `electron/src/renderer/utils/interpolate.ts` — 从 App.tsx 抽出的纯字符串模板函数

**修改：**
- `App.tsx` 从 1041 行压缩到 <100 行（只剩布局编排 + 零业务 state）
- `ChatTab.tsx` — 删除全部 23 个 props（详见 ChatTab-render spec），内部直接 subscribe 对应 store；treeNodes 内部 useMemo 组装
- `ExecTab.tsx` — 删除所有 props（20→0），内部 subscribe pipelineStore
- `LogTab.tsx` — 删除所有 props（14→0），内部 subscribe pipelineStore
- `PipelinesTab.tsx` — 删除所有 props（5→0），内部 subscribe pipelineStore + uiStore
- `ParamsTab.tsx` — 删除所有 props（7→0），内部 subscribe credentialStore
- `SettingsTab.tsx` — 删除所有 props（8→0），内部 subscribe connectionStore + uiStore
- `ConnectionBar.tsx` — 删除所有 props（10→0），内部 subscribe connectionStore
- `StatusBar.tsx` — 删除所有 props（2→0），内部 subscribe pipelineStore + connectionStore
- `main.tsx` — 在 `root.render()` 前调用 `initGateway()`

**删除：**
- App.tsx 中所有 12 种 chat.* 事件的内联处理逻辑 → 移入 chatStore
- App.tsx 中 WebSocket 连接/重连逻辑 → 移入 gateway.ts
- App.tsx 中 handleRun/handleCancel/handleReview/handleConnect 等回调 → 移入各 store
- `package.json` 中不存在的理论依赖不新增——只加 zustand

**BREAKING：** 无运行时行为变化。API 层不变，后端不变。只是前端组件获取状态的方式从 props 变成 store selector。

## Capabilities

### New Capabilities

- `frontend-store`: 前端全局状态管理基础设施。用 zustand 提供 connectionStore / pipelineStore / chatStore / credentialStore / uiStore 五个独立 store，各组件通过 selector 自主订阅。uiStore 归纳了所有需要 localStorage 持久化的 UI 偏好（activeTab / theme / chatLayoutReversed / sidebarCollapsed）。
- `ws-gateway`: 单一 WebSocket 网关，负责连接/重连/关闭生命周期；必须在 main.tsx 的 root.render() 之前初始化；根据 event.type 按严格 if/else chain 顺序分发到对应的 store action。dispatch 时 gateway MUST 调用 store spec 中已定义的 action 名（chatStore.handleWsEvent / connectionStore.handleBrowserDisconnect / pipelineStore.handleRunEnd / pipelineStore.addEvent）。

### Modified Capabilities

- `App.tsx-layout`: App 组件职责变化——从状态持有者变为纯布局渲染器，不再持有业务 state、不再传递 prop drill、不再内联 WebSocket handler。
- `ChatTab-render`: ChatTab 从 props-driven（23 props）改为 store-driven，内部自主订阅 chatStore / connectionStore / pipelineStore；treeNodes 在 ChatTab 内部 useMemo 组装。
- `ExecTab-render`: ExecTab 从 props-driven 改为内部 subscribe pipelineStore。
- `LogTab-render`: LogTab 从 props-driven 改为内部 subscribe pipelineStore。
- `PipelinesTab-render`: PipelinesTab 从 props-driven（5 props）改为内部 subscribe pipelineStore + uiStore。
- `SettingsTab-render`: SettingsTab 从 props-driven 改为内部 subscribe connectionStore + uiStore + credentialStore。
- `ConnectionBar-render`: ConnectionBar 从 props-driven 改为内部 subscribe connectionStore。
- `ParamsTab-render`: ParamsTab 从 props-driven 改为内部 subscribe credentialStore。
- `StatusBar-render`: StatusBar 从 props-driven（2 props → 0）改为内部 subscribe pipelineStore + connectionStore。

## Impact

**文件改动范围：**
- 新增目录 + 文件：`stores/`（5 个 store + 1 selectors helper）+ `ws/gateway.ts` + `utils/interpolate.ts` ≈ 8 个新文件
- 修改文件：10 个（App.tsx + 5 tabs + ConnectionBar + StatusBar + main.tsx[可选加 Provider] + package.json）
- 删除文件：无

**依赖影响：**
- 新增运行时依赖：`zustand`（~1KB gzip，MIT）
- 无 peer dependency 冲突

**团队影响：**
- 新增文件遵循 "一个 store 一个领域" 原则，未来改功能先找对应 store
- 不再需要读懂 App.tsx 才能开发单一功能

**风险：**
- streamStatesRef 是不触发 re-render 的 useRef 状态，迁入 chatStore 时需要特殊处理（zustand 的 getState() 外部可变引用）
- WebSocket 事件分发时的时序行为需保持与原来一致（JS 单线程保证）
