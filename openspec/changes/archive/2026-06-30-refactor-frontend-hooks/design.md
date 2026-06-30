## 背景

前端当前只有 `App.tsx` 一个文件承载全部 state（30 个 useState/useRef）和 12 种 WebSocket 事件处理逻辑。
所有子组件（ChatTab、ExecTab、LogTab、PipelinesTab、SettingsTab、ParamsTab、ConnectionBar、StatusBar）都通过 props 接收数据，
最深 drilling 达 22 个 prop（ChatTab）。

约束：
- 后端 API 不变， WebSocket 事件类型/字段不变， apiClient.ts 接口不变
- runtime 行为必须一致（消息顺序、re-render 时机、流式展示）
- streamStatesRef 是不触发 re-render 的 mutable ref，迁徙时需特殊处理

## 目标 / 非目标

**目标：**
- App.tsx < 100 行，只负责布局
- 所有业务状态集中到 5 个 zustand store（uiStore / connectionStore / pipelineStore / chatStore / credentialStore）
- 所有 WebSocket 事件处理集中到 1 个 gateway 文件
- 所有子组件 props 接口归零（8 个组件全部改为内部 store selector）

**非目标：**
- 不重构后端 API 层
- 不引入 Redux/MobX 等其他范式
- 不做 SSR/同期渲染改造
- 不改变任何运行时用户可见行为

## 关键决策

### D1：选择 zustand 而非 Context API

**原因：**
- zustand 原生支持 selector，能精准订阅 store 的某个字段，避免 Context 一变所有 consumers 都 re-render
- zustand 不需要 Provider 包裹，代码迁移路径 App.tsx 内部改动更少
- zustand 1KB gzip，MIT，已验证于大量中型项目

**备选方案 Context + useReducer 缺点：**
- 每个 store 都要加 Provider，App.tsx 变 Provider 嵌套 hell
- 缺 selector 支持，re-render 粒度粗

### D2：拆分 5 个独立 store 而非 1 个大 store

**原因：**
- 5 个领域（ui / connection / pipeline / chat / credential）各有独立的生命周期和变更频率
- selector 细粒度访问不会导致跨域 re-render（如 chatStore 更新不会触发 SettingsTab rerender）
- 未来如需 code splitting 可独立加载

### D3：gateway 作为模块级 singleton

**原因：**
- WebSocket 连接和 React 渲染周期解耦——组件卸载不应关闭连接
- 由 gateway 统一持有 reconnectTimer / stopped flag，避免 hook 内 useEffect 依赖项爆炸
- 测试时容易 mock

### D4：streamStatesRef 处理策略

zustand 中用 `getState()` 获得 store 内部的 mutable 对象引用，不放进 React state。
具体做法：chatStore 内声明 `const streamStates: Record<...> = {}`，action 中直接读写，
这样更新时只触发 selector 订阅者（通过 set({messages}) 同步消息数组），但 streamStates 本身变化不额外 re-render。

### D7：connectGenRef / connectedRef 模块级变量

**原因：**
- 当前 App.tsx 用 `connectGenRef.current++` 做 generation counter 来丢弃过期的异步响应
- `connectedRef` 是"当前是否已连接"的快照，用于 `chrome_disconnected` handler 判断跳变
- zustand state 不可变，不能直接 .current++

**做法：**
- 在 `stores/connectionStore.ts` 模块内声明 `let connectGen = 0` 和 `let connectedSnapshot = false`
- store 中以 `getState()` 暴露只读引用供 handler 使用
- action 内直接使用 `connectGen++` 检测过期

### D9：clearEvents action 归入 pipelineStore

**原因：** LogTab 点击"清空日志"需要把 events=[] 重置。这个操作本质是写入 pipeline 事件状态，不能散落在组件里 setEvents([])，MUST 封装为 pipelineStore.clearEvents action。

### D10：stepNames / stepStarts / stepEnds / getStepStatus 归入 pipelineStore

**原因：** 这些字段目前在 App.tsx 的 useMemo 计算，从 events 派生。迁移后 App.tsx 不复存在，这一步推导 MUST 进入 pipelineStore selector 或由订阅组件在 useMemo 消费 store 原始数据计算。本 spec 选择后者——pipelineStore 暴露原始 events，但 Exe/Log/Tab 通过共享的 `@/stores/pipelineStore/selectors.ts` 中导出的 memoized compute helpers 获取 stepNames/getStepStatus。App.tsx 的 `useMemo` pure function MUST 移到该 selectors 文件，语义一行不变。

### D8：interpolateTemplate 归入 src/utils/

**原因：**
- 是纯字符串工具函数（正则模板替换），无副作用，无 store 关联
- 放入 store 文件会让 store 文件职责发散，放 utils 可被 pipelineStore 和其他未来逻辑复用

**路径：** `electron/src/renderer/utils/interpolate.ts`

**函数签名：**
```typescript
export function interpolateTemplate(template: string, ctx: Record<string, string>): string
```

**行为：** 匹配 `{{key}}` 模式（正则 `/{{([\w.-]+)}}/g`），在 ctx 中查找 key：
- 命中 → 替换为 ctx[key]
- 未命中 → 保留原始 `{{key}}`（不删除不报错）

### D11：highlightMode 持久化策略

**原因：** highlightMode 目前在 App.tsx 通过 localStorage.setItem('highlight-mode', ...) 持久化。迁移到 connectionStore 后，MUST 由 `setHighlightMode` action 内部自动同步 localStorage；组件不再手动 setItem。

### D12：SettingsTab providerConfig 不纳入 store

**原因：** LLM provider 表单（model/api_key/api_base）仅在 SettingsTab 内部使用、跨组件共享价值低；presets/activePresetId 是组件挂载时拉取的一次性数据。遵循 D4 "UI-only state 留在组件" 原则，这些 MUST 保留为 SettingsTab 的内部 useState，不引入 store。

### D5：逐步迁移而非 big-bang

on 路径分 4 个阶段，每阶段独立可 build、可验证：

| 阶段 | 做什么 | App.tsx 影响 | gateway 状态 |
|------|--------|-------------|--------------|
| Phase 1 | 建 5 个 store 骨架（空 state + 占位 action），gateway 骨架（空 handler） | 未变 | dispatch 到空函数 |
| Phase 2 | connectionStore 接入完整逻辑；browser 事件接入 gateway | 删除 connected/wsUrl/... useState | chrome_disconnected 路径激活 |
| Phase 3 | pipelineStore 接入完整逻辑；pipeline 事件接入 gateway | 删除 pipelines/events/loading/... useState | 全部分发路径激活 |
| Phase 4 | chatStore 接入完整逻辑；chat 事件接入 gateway；子组件 props 迁移 | 删除 chat 状态和 useCallback，瘦身到 <100 行 | 完整运行 |
| Phase 5 | ChatTab 等 8 个组件内部改用 store selector，删除所有 props | 最终编排层 | 完整运行 |

每步都必须 `npm run build` 通过 + 手动验证行为不变，才进入下一步。

### D6：props 接口不一定立即删除（渐进式）

**主路径：** 先完成 store 迁移，App.tsx 瘦身，最后批量清子组件 props。这样如果中途发现 store 设计有误，回滚成本低。

**替代路径：** 也可以按"子组件自包含 ChatTab"方式走 A 方案——这等价于把 store 包装成 hooks 给组件用，只是换了写法。本 spec 选 D5 主路径。

## 风险 / 权衡

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| streamStatesRef 异步更新导致 text_chunk 丢失 | 高 | 严格保持 zustand action 内的同步更新顺序，不引入 async |
| 大量 re-render 影响聊天流式体验 | 中 | zustand selector 确保只有订阅特定字段的组件 re-render；messages 数组不可变拷贝保持原语义 |
| 迁移期间两个 state 源并存导致不一致 | 中 | 每个 store 完全替换 App.tsx 同名字段后才移除 App 端的 useState |
| ChatTab selectTreeNodes 跨 store memo 组合（chatStore.sessions + pipelineStore.pipelines）| 低 | chatStore 暴露 selectTreeNodes selector，内部基于 chatSessions/pipelineSessions/pipelines 三字段 useMemo |

## ## 迁移计划

上线为单一 PR，无 runtime schema 变更。灰度策略：重构前后均可通过 `npm run build` 验证编译通过。

回滚：保留一个 git commit 的完整旧 App.tsx，发现问题 `git revert` 1 commit 即可回到 prop drilling 版本，5 分钟完成。

## 待确认问题

- [x] 是否需要为 streamStatesRef 增加单元测试，防止事件顺序未来漂移？**→ 不写，仍用人工测试覆盖**
- [x] ChatTab 内部 `splitRatio` 和 `expandedThinks` 等 UI-only 状态是否保留为组件内 useState？**→ 保留为组件 useState（D4 决策已覆盖）**
- [x] connectGenRef 在 zustand 中的实现方式？**→ D7 决策：模块级 let 变量**
- [x] chatLayoutReversed 和 sidebarCollapsed 放在哪个 store？**→ uiStore（frontend-store spec 已更新）**
- [x] initGateway 在哪调用？**→ main.tsx 的 `root.render()` 之前（ws-gateway spec 已明确）**
- [x] interpolateTemplate 放哪里？**→ D8 决策：src/utils/interpolate.ts**
- [x] chat.* 事件完整覆盖？**→ 8 种子类型全列（chatStore spec 已更新）**
- [x] gateway 的 dispatch 顺序？**→ 严格 if/else 链（ws-gateway spec 已明确）**
- [x] 是否应该在 zustand 接入 middleware？**→ D13 决策：默认不接入；但 store create 调用 MUST 包装在 `_create()` 中，便于未来一行代码启用 devtools；详见 D13**
- [x] 子组件 props 精确数量对齐？**→ proposal 30-37 行已统一：ChatTab=23 / ExecTab=15 / LogTab=14 / PipelinesTab=5 / ParamsTab=7 / SettingsTab=8 / ConnectionBar=10 / StatusBar=2
- [x] Phase 5 任务分散问题？**→ D14 决策：design 表格保持高层视图，tasks.md 按可执行颗粒度展开

### D13：zustand middleware 决策

**结论：** 默认不接入 middleware。但 store 创建必须封装为：

```typescript
// stores/_factory.ts
export const _create = <T>(fn: ...) => create(fn);  // 一行替换即可接入 devtools
```

**理由：** zustand devtools 对调试帮助显著，但 production bundle 应保持最小化。实现者在需要开发调试时可以用 `import { devtools } from 'zustand/middleware'` 包装 `_create`，无需修改各 store 文件。logger middleware 暂不引入。

### D14：design 阶段表 vs tasks.md 颗粒度对齐

**结论：** design.md 的 D5 阶段表是 **高层视图**（5 个 Phase），tasks.md 按 **可执行颗粒度** 展开（编号 1.1-6.4）。Phase 边界对应关系：

| Phase | 对应 tasks |
|-------|-----------|
| Phase 1 骨架 | 1.1-1.7 |
| Phase 2 connectionStore | 2.1-2.4 |
| Phase 3 pipelineStore | 3.1-3.5 |
| Phase 4 chatStore | 4.1-4.5 |
| Phase 5 组件 props + App 收尾 | 2.3 + 3.4 + 4.4 + 5.1-5.5 |

Phase 5 活动时间上跨越多个 task section 是因为 App.tsx props 删除依赖于对应 store 完成；这种"交叉依赖"在单次 PR 内是正常的。
