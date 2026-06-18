## 背景

当前 yak-browser-use 的浏览器操作层架构：

```
Chrome (--remote-debugging-port=9222)
    └── CDPDaemon (raw websocket) ──→ CDPHelpers ──→ executor
        自建 WS 连接管理、session 追踪、重连逻辑        每个 op 手动拼 CDP 命令
```

`CDPDaemon` 自建 WebSocket 连接到 Chrome DevTools Protocol，`CDPHelpers` 通过 `_send("DOM.*")` 手拼 CDP 命令完成 click/fill/scroll 等操作。这套方案在 Agent 模式下可工作（LLM 失败后能换方式重试），但在 Preset 模式（YAML pipeline，无 LLM 回环）下缺乏鲁棒性——裸 CDP 命令不提供 auto-wait/auto-scroll，元素未渲染或被遮挡时静默失败。

项目已有两种执行模式，对底层鲁棒性要求不同：

| 模式 | 决策者 | 失败后 | 对底层的要求 |
|:----:|:------:|:------|:------------|
| Agent 模式 | LLM | LLM 看到错误，换个方式重试 | 中等 |
| Preset 模式 | YAML pipeline | 没有 LLM 回环 | **高** |

Playwright 已在项目中用于 isolated Chrome 启动（`launcher.py`），但未用于浏览器操作。`playwright.chromium.connect_over_cdp()` 可以连接到已有 Chrome 调试端口，利用 Playwright 的 auto-wait/auto-scroll/auto-retry 特性。

## 目标 / 非目标

**目标：**

1. 通过 `playwright.chromium.connect_over_cdp()` 统一接管所有浏览器操作
2. 为 Preset 模式提供 Playwright 的 auto-wait/auto-scroll 鲁棒性兜底
3. 废弃 `CDPDaemon` 自建 WebSocket 路径，消除双通道维护成本
4. 新增 hover/select/clear/wait/navigate/tab/keyboard/copy/paste 共 12 个操作
5. 保持 Agent 模式的 tool schema 和 @eN refs 不变，LLM 无感知

**非目标：**

- 不引入 `DOMSnapshot.captureSnapshot`（保持 simplify-dom.js 路线）
- 不改为 PIL 画截图的高亮方案（保持 JS 注入路线）
- 不新增 drag_and_drop / right_click / file_upload
- 不涉及 Tag 机制和 `_comment` 支持
- 不涉及验证码自动处理

## 关键决策

### 决策 1：通过 `connect_over_cdp()` 而非 `launch()` 连接

**选择**：`playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")`

**原因**：Chrome 已由 `launcher.py` 以 `--remote-debugging-port=9222` 启动，用户可能已有打开的标签页和登录状态。`connect_over_cdp()` 连接已有实例，不创建新浏览器进程，保持用户会话。

**备选方案**：`playwright.chromium.launch()` 启动新浏览器。被否决——会丢失用户已有标签页和登录状态。

### 决策 2：CDPHelpers 保留但重构，不直接删除

**选择**：`CDPHelpers` 改为接受 `PlaywrightBridge`，所有方法透传或重写为 Playwright 调用。

**原因**：`CDPHelpers` 被 15+ 个调用方引用（executor、conversation_loop、routes、agent、runner、service、tool_executor、tool_runner、chrome CLI 等）。直接删除需要改动所有调用方，风险大。保留 `CDPHelpers` 作为适配层，内部切换到 PlaywrightBridge，调用方改动最小。

**备选方案**：删除 CDPHelpers，所有调用方直接使用 PlaywrightBridge。被否决——改动面太大，且 CDPHelpers 的 `capture_snapshot_interactive()`、`capture_snapshot_simplified()` 等方法封装了 snapshot 逻辑，直接删除需要把这些逻辑搬回调用方。

### 决策 3：conversation_loop 保持 `cdp_helpers` 参数不变

**选择**：`run_conversation_loop(cdp_helpers=helpers)` 签名不变，各调用方自己创建 `PlaywrightBridge` + `CDPHelpers(bridge)`。

**原因**：conversation_loop 是核心回环，被 agent.py / runner.py / service.py 三个入口调用。改签名需要同时改三个调用方 + 所有测试。保持参数名不变，只改参数类型（`CDPHelpers` 内部由 PlaywrightBridge 驱动），调用方改动集中在初始化阶段。

### 决策 4：Snapshot 保持 simplify-dom.js，不走 DOMSnapshot

**选择**：通过 `page.evaluate()` 运行 simplify-dom.js。

**原因**：
- simplify-dom.js 在浏览器端预过滤，只返回 ~50 个交互元素，给 LLM 的 token 更少
- 已做了摘要、暗色模式兼容、自定义交互规则，迁移成本高
- `page.evaluate()` 底层就是 CDP `Runtime.evaluate`，行为完全一致

### 决策 5：Highlight 保持 JS 注入，不走 PIL 画截图

**选择**：通过 `page.evaluate()` 注入高亮 JS，新标签页通过 `context.on("page")` 事件自动注入。

**原因**：
- 用户看着浏览器操作，需要看到 @e1, @e2 编号
- JS 注入的 `pointer-events:none` 覆盖层不阻塞用户操作
- `MutationObserver` 自动刷新高亮，SPA 页面也跟得住
- 去掉 `_highlight_guard_task`（CDP event queue 轮询），改用 Playwright 事件回调，更简洁

### 决策 6：不保留 raw_cdp 备用通道

**选择**：所有能力走 Playwright，不保留 `raw_cdp()` 方法。

**原因**：screenshot（`page.screenshot()`）、JS evaluate（`page.evaluate()`）、DOM content（`page.content()`）Playwright 全有，不需要 CDP 备用通道。

### 决策 7：ToolCDPHelpers 新增 evaluate() 方法

**选择**：`ToolCDPHelpers` 新增 `evaluate(js)` 方法，透传给 `bridge.evaluate()`。

**原因**：`extract.py` 等工具需要跑任意 JS，原来通过 `cdp_helpers.js()` 实现。改为接受 PlaywrightBridge 后，需要 `evaluate()` 方法保持能力。不改为直接接收 PlaywrightBridge——ToolCDPHelpers 的 circuit breaker 逻辑仍有价值。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| `locator.click()` 行为变化（auto-wait 可能超时） | Agent 模式下 LLM 需适应微小时序变化 | executor 超时设 30s；Preset 模式下超时更友好 |
| `page.fill()` 自动清空已有内容 | 行为变化，Agent 追加输入需走 focus + type_text | tool description 写明行为 |
| Playwright 版本升级可能 break `connect_over_cdp()` | 阻塞 Playwright 升级 | 锁定 `playwright>=1.48.0`，升级前跑测试 |
| `connect_over_cdp` 连不上 | 全部 ops 不可用 | 启动时 try/except，报错提示检查 Chrome 调试端口 |
| CDP 重连逻辑丢失 | tool_executor.py 有应用层重试 | Playwright 内置 WebSocket 重连；如需应用层重试，在 bridge 外层加简单重试装饰器 |
| `textContent` vs `innerText` 行为差异 | run_check 文本检查结果可能不同 | `textContent` 更可靠（不受 CSS 影响），测试验证 |

## 迁移计划

1. **Phase 1**：新增 `PlaywrightBridge`，不改任何现有代码
2. **Phase 2**：重构 `CDPHelpers` 接受 PlaywrightBridge，方法透传
3. **Phase 3**：改 executor（`execute_browser_op`、`execute_browser_step`、`run_check`）
4. **Phase 4**：改 tools.py（追加 12 个 tool schema）
5. **Phase 5**：改 ToolCDPHelpers（接受 PlaywrightBridge，新增 evaluate）
6. **Phase 6**：改所有初始化入口（state.py、routes.py、agent.py、runner.py、service.py）
7. **Phase 7**：改 CLI 层（chrome.py、run.py）
8. **Phase 8**：改 Preset 引擎层（runner_preset.py、tool_executor.py、tool_runner.py）
9. **Phase 9**：标记 CDPDaemon 为 deprecated
10. **Phase 10**：更新测试

**回滚策略**：CDPDaemon 仅标记 deprecated 不删除，如需回滚，将初始化入口改回 `CDPDaemon` + `CDPHelpers(daemon)` 即可。

## 待确认问题

1. `simplify-dom.js` 通过 `page.evaluate()` 运行的结果是否与 CDP `Runtime.evaluate` 完全一致？需先跑现有 snapshot 测试确认。
2. `textContent` vs `innerText` 的行为差异是否影响现有 Preset 的 check 逻辑？需在测试中验证。
3. Playwright 的 `connect_over_cdp()` 在 Windows 上的稳定性如何？需在目标环境验证。
