## 1. 基础设施搭建

- [x] 1.1 在 `electron/package.json` 添加 `zustand` 依赖并执行 `npm install`
- [x] 1.2 创建目录 `electron/src/renderer/stores/`、`electron/src/renderer/ws/`、`electron/src/renderer/utils/`
- [x] 1.3 把 App.tsx 中的 `interpolateTemplate` 函数移到 `utils/interpolate.ts`（纯字符串工具，不耦合 store）
- [x] 1.4 实现 `ws/gateway.ts`：封装 WebSocket 连接、重连（3s/5s 退避）、关闭生命周期；暴露 `initGateway()` 和 `getGateway()` 入口；dispatch 时严格按 if/else 链顺序判断：chat.* + pipeline.edit → chatStore / chrome_disconnected → connectionStore / run_end → pipelineStore / 默认 fallthrough → pipelineStore.addEvent
- [x] 1.5 修改 `main.tsx`：在 `root.render(<App />)` 之前加一行 `initGateway()`
- [x] 1.6 实现 `stores/uiStore.ts`：activeTab（默认 'exec'）、theme（localStorage）、chatLayoutReversed（localStorage）、sidebarCollapsed（localStorage）；每个 setX 同步 localStorage 写入；setTheme 同时 set `document.documentElement.setAttribute('data-theme', ...)`；**store 顶层 MUST 立即执行** `document.documentElement.setAttribute('data-theme', initialTheme)` 确保初始化时 DOM 同步
- [x] 1.7 实现 `stores/credentialStore.ts`：credKeys、credKey、credValue、setCredKey、setCredValue、addCredential、removeCredential action（调对应 api）

## 2. Connection Store + Browser 领域迁移

- [x] 2.1 实现 `stores/connectionStore.ts`：持有 connected、wsUrl、connectionError、profiles、selectedProfile、connectMode、highlightMode（初始化从 localStorage('highlight-mode') 读取）、restartDialog、restarting（均作为 zustand state）；模块级 `let connectGen = 0` 和 `let connectedSnapshot = false`（不放进 state，供 handler 内部 mutation）；提供 connect（入口处 `connectGen++`，异步返回时检查过期）/ disconnect / restartConfirm / restartCancel / createProfile / handleBrowserDisconnect action（内部调对应 api）
- [x] 2.2 在 `ws/gateway.ts` 接入 browser 事件分发：`chrome_disconnected` → `connectionStore.handleBrowserDisconnect()`
- [x] 2.2b connectionStore.setHighlightMode MUST 内部自动同步 localStorage('highlight-mode', mode)；ConnectionBar 不再手动 setItem
- [x] 2.3 App.tsx 删除所有浏览器连接相关的 useState/useRef，改为用 `useConnectionStore` selector 读取；保留 ConnectionBar JSX 但删除其 props，ConnectionBar 内部 subscribe store
- [x] 2.4 `npm run build` 通过，手动验证：连接/断开/重启流程工作正常

## 3. Pipeline Store + 执行领域迁移

- [x] 3.1 实现 `stores/pipelineStore.ts`：持有 pipelines、activePreset、pipelineCache、pipelineEditor、events、result、resultErrors、loading、currentRunId、currentPipeline、cancelling、pendingReview、reviewMode；其中 run action 内部 MUST 调用 `interpolateTemplate`（从 `utils/interpolate.ts` import）对 pipeline 内容做参数展开，review_mode 前置插入逻辑；提供 run / cancel / reviewApprove / reviewReject / addEvent / handleRunEnd / handlePipelineEdit / refreshPipelines / deletePipeline / savePipeline / setActivePreset / setReviewMode / setPendingReview / setLoading / setCancelling / setPipelineEditor / setCurrentPipeline / setCurrentRunId / setResult / setResultErrors / clearEvents action；handleRunEnd MUST 明确不触碰 result/resultErrors（保留到下次 run 或用户手动重置）
- [x] 3.2 gateway.ts 的 dispatch 路径 MUST 确保 run_end 在 fallthrough 之前被 if/else 命中
- [x] 3.3 App.tsx 删除所有管道相关的 useState/useCallback（handleRun/handleCancel/handleReview 等），改为从 `usePipelineStore` selector 读取
- [x] 3.4 ExecTab、LogTab、StatusBar、PipelinesTab 删除 props，改为内部 `usePipelineStore` selector；PipelinesTab 同时需要 `useUiStore` 提供 setActiveTab 能力
- [x] 3.5 `npm run build` 通过，手动验证：运行管道、查看日志、approve/reject review 工作正常

## 4. Chat Store + 聊天领域迁移

- [x] 4.1 实现 `stores/chatStore.ts`：持有 chatMessages、pendingEdits、activePendingEdit（selector: pendingEdits[0] ?? null）、processedEditIds（模块级 Set）、streamStates（模块级 Record 不放进 state）、currentSessionId、chatSessions、pipelineSessions、expandedNodes、loadingSession、selectTreeNodes（memoized selector）；提供 send / cancelChat / resetChat / setMessages / newSession / archiveSession / selectSession / switchPipeline / toggleExpand / confirmEdit / revertEdit / handleWsEvent action
- [x] 4.2 chatStore.handleWsEvent 实现完整 8 种 chat.* 子类型 + pipeline.edit 类型处理：chat.tool_start/end/error/stream_start/text_chunk/think_chunk/tool_generated/stream_end，gateway 分派 pipeline.edit 到 chatStore.handleWsEvent + pipelineStore.handlePipelineEdit；每种 MUST 完全复制 App.tsx:309-452 行的语义；追加消息时必须调用 nextMsgId() 生成 ID
- [x] 4.3 App.tsx 删除所有 chat 相关 useState/useRef/useCallback；删除内联 200 行 ws.onmessage handler
- [x] 4.4 ChatTab 删除所有 props，改为内部 chatStore + connectionStore + pipelineStore selector；treeNodes 计算从 store 数据 useMemo 得到
- [x] 4.5 `npm run build` 通过，手动验证：发送消息、流式响应、session 切换、pipeline edit confirm/review 流程工作正常

## 5. App.tsx 收尾

- [x] 5.1 App.tsx 最终形态确认：只包含 TitleBar、ConnectionBar、TabBar、五个 Tab JSX（Exec/Chat/Log/Pipelines/Params/Settings）、StatusBar；无业务 state、无 useWebSocket/handleRun/handleConnect 等回调
- [x] 5.2 ChatTab 删除所有 props（改为内部 chatStore + connectionStore + pipelineStore selector）；treeNodes 在 ChatTab 内部通过 `useMemo` 从 chatStore + pipelineStore 数据组装
- [x] 5.3 ParamsTab 删除 props，改为内部 `useCredentialStore` selector
- [x] 5.4 SettingsTab 删除 props，改为内部 `useConnectionStore` + `useUiStore` selector
- [x] 5.5 `npm run build` 通过，App.tsx 127 行（目标 <100，含 2 个 init useEffect 共 ~40 行）

## 6. 全面验证

- [ ] 6.1 手动 E2E：启动应用 → 连接浏览器 → 运行管道 → 完成；切换到 ChatTab → 发送消息 → 流式响应 → 完成；切换到 LogTab → 查看日志 + 审核 approve
- [ ] 6.2 zustand DevTools 可选接入（仅在开发模式），验证 store 更新时序
- [ ] 6.3 检查 re-render 性能：React DevTools Profiler 录制聊天流式更新，对比迁移前后渲染次数无显著退化
- [ ] 6.4 清理临时 debug 代码（如 `console.log('[chatMessages] ...')`、`streamStatesRef` 相关 console.log）


