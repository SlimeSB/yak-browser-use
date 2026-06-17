## Why

当前 yak-browser-use 的浏览器操作层通过 `CDPDaemon` 自建 WebSocket 连接，手拼 CDP 命令（`Input.dispatchMouseEvent`、`DOM.getBoxModel` 等）完成 click/fill/scroll 等操作。这套方案有两个核心问题：

1. **Preset 模式缺乏鲁棒性兜底**：Preset 模式（YAML pipeline）没有 LLM 回环，一次失败就结束。裸 CDP 命令不提供 auto-wait/auto-scroll/auto-retry，元素未渲染、被遮挡、未滚动到视口内时静默失败，导致 Preset 执行不稳定。
2. **维护成本高**：`CDPDaemon` 自建了 WS 连接管理、session 追踪、重连逻辑，这些 Playwright 已内置。维护两套代码不如统一到 Playwright 一条通道。

通过 `playwright.chromium.connect_over_cdp()` 统一接管所有浏览器操作，Playwright 的 auto-wait/auto-scroll 特性为 Preset 模式提供鲁棒性兜底，同时大幅简化代码。

## What Changes

- **新增** `PlaywrightBridge` 核心类（`backend/cdp/playwright_bridge.py`），通过 `connect_over_cdp()` 统一驱动浏览器，封装所有交互/导航/标签页/剪贴板操作
- **重写** `CDPHelpers`（`backend/cdp/helpers.py`），从接受 `CDPDaemon` 改为接受 `PlaywrightBridge`，所有方法透传或重写为 Playwright 调用
- **重写** `execute_browser_op()`（`backend/engine/executor.py`），参数从 `cdp_helpers` 改为 `bridge: PlaywrightBridge`，新增 hover/unhover/focus/select/clear/keyboard/navigate/wait/tab/copy/paste 共 11 个 op_type 分支
- **修改** tool schema（`backend/engine/_harness/tools.py`），追加 12 个新 tool schema，click 增加 `clickCount` 参数
- **修改** `ToolCDPHelpers`（`backend/utils/tool_cdp.py`），改为接受 `PlaywrightBridge`，新增 `evaluate()` 方法
- **废弃** `CDPDaemon`（`backend/cdp/daemon.py`），标记 `@deprecated`
- **修改** 所有初始化入口（`state.py`、`routes.py`、`agent.py`、`conversation_loop.py`、`runner.py`、`service.py`），从 `CDPDaemon` 切换到 `PlaywrightBridge`
- **移除** `_highlight_guard_task`，改用 Playwright 的 `context.on("page")` 事件自动注入高亮 JS
- **修改** CLI 层（`chrome.py`、`run.py`），CDP 命令改为调 bridge 方法
- **修改** Preset 引擎层（`runner_preset.py`、`tool_executor.py`、`tool_runner.py`），cdp_helpers 参数类型更新
- **修改** `run_check()` 签名从 `(check_def, cdp_helpers)` 改为 `(check_def, bridge)`，`innerText` 改为 `textContent`
- **BREAKING**：`CDPHelpers.__init__` 参数从 `CDPDaemon` 变为 `PlaywrightBridge`；`execute_browser_op` 参数从 `cdp_helpers` 变为 `bridge`；`_resolve_element_ref` 第三参数从 `cdp_helpers` 变为 `bridge`

## Capabilities

### New Capabilities

- `playwright-bridge`: PlaywrightBridge 核心类，通过 `connect_over_cdp()` 统一管理浏览器连接、标签页、交互操作，内置 auto-wait/auto-scroll/auto-retry
- `browser-hover`: 鼠标悬停操作，通过 Playwright `locator.hover()` 实现，自动等待元素可见并滚动到视口
- `browser-focus`: 元素聚焦操作，通过 Playwright `locator.focus()` 实现
- `browser-select`: 下拉选择操作，通过 Playwright `selectOption()` 实现
- `browser-clear`: 输入框清空操作，通过 Playwright `locator.clear()` 实现
- `browser-keyboard`: 键盘操作（按键/输入文本），通过 Playwright `keyboard.press()` / `keyboard.type()` 实现
- `browser-navigate`: 页面导航操作（前进/后退/刷新），通过 Playwright `page.goBack()` / `goForward()` / `reload()` 实现
- `browser-wait`: 等待操作（时间/元素/加载状态），通过 Playwright `waitForSelector()` / `waitForLoadState()` 实现
- `browser-tab`: 标签页管理（新建/切换/关闭/列表），通过 Playwright `context.newPage()` / `bringToFront()` 实现
- `browser-copy-paste`: 剪贴板操作（复制/粘贴），通过 Playwright `page.evaluate()` 实现

### Modified Capabilities

- `browser-click`: 底层从 CDP `Input.dispatchMouseEvent` 改为 Playwright `locator.click()`，新增 `clickCount` 参数支持双击
- `browser-fill`: 底层从 CDP `Input.insertText` 改为 Playwright `locator.fill()`，行为变化：自动清空已有内容再填入
- `browser-goto`: 底层从 CDP `Page.navigate` 改为 Playwright `page.goto()`，自动等待 `domcontentloaded`
- `browser-snapshot`: 底层从 CDP `Runtime.evaluate` 改为 Playwright `page.evaluate()`，行为等价
- `browser-scroll`: 底层从 CDP `Runtime.evaluate` 改为 Playwright `page.evaluate()`，行为等价
- `browser-source`: 底层从 CDP 方法改为 Playwright `page.content()`，支持 `cached` 参数从 scratchpad 读取缓存
- `browser-get-element`: 底层从 `cdp_helpers.get_element_by_index()` 改为 `bridge.get_element_by_index()`
- `browser-eval`: 底层从 CDP `Runtime.evaluate` 改为 Playwright `page.evaluate()`，行为等价
- `browser-unhover`: 新增取消悬停工具，通过 Playwright `page.mouse.move(0, 0)` 实现
- `cdp-helpers`: `CDPHelpers` 构造参数从 `CDPDaemon` 改为 `PlaywrightBridge`，所有方法透传或重写
- `tool-cdp-helpers`: `ToolCDPHelpers` 构造参数从 `CDPHelpers` 改为 `PlaywrightBridge`，新增 `evaluate()` 方法

## Impact

- **涉及 21 个文件**：5 核心改动 + 2 CDP 退役 + 4 入口 + 2 CLI + 3 Preset + 2 Service + 2 工具 + 1 兼容确认
- **测试文件需更新**：`test_executor_helpers.py`、`test_harness_tools.py`、`test_conversation_loop.py`、`test_run_check.py`
- **依赖**：`playwright>=1.48.0`
- **运行环境**：Chrome 需以 `--remote-debugging-port=9222` 启动（已有 launcher.py 支持）
- **Agent 模式**：tool schema 不变，LLM 无感知，底层更稳定
- **Preset 模式**：Playwright auto-wait/auto-scroll 提供鲁棒性兜底，减少静默失败
- **风险**：`page.fill()` 清空行为变化需在 tool description 中注明；`locator.click()` 超时行为可能与原 CDP 坐标点击不同
