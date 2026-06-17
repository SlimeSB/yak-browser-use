## 1. 准备与基础改造

- [ ] 1.1 新增 `backend/cdp/playwright_bridge.py`：实现 `PlaywrightBridge` 核心类，包含 `start()`/`stop()` 生命周期、所有交互操作（goto/click/fill/scroll/source/evaluate/hover/unhover/focus/select/clear/keyboard_press/keyboard_type/navigate/wait/tab_new/tab_switch/tab_close/tab_list/copy_to_clipboard/paste_from_clipboard）、快照方法（screenshot/simplify_dom/capture_snapshot）、元素映射（reset_ref_map/get_element_by_index）、新标签页高亮自动注入（`context.on("page")` 事件回调）
- [ ] 1.2 重构 `backend/cdp/helpers.py`：`CDPHelpers.__init__` 参数从 `CDPDaemon` 改为 `PlaywrightBridge`；所有已有方法（goto_url/click_selector/fill_input/capture_snapshot/capture_snapshot_interactive/capture_snapshot_simplified/js/get_page_html/add_dom_highlights/remove_dom_highlights/wait_for_network_idle/wait_for_page_load）重写为调用 bridge 方法；新增方法（hover/unhover/focus_selector/select_option/clear_input/keyboard_key/keyboard_text/navigate/wait/tab_new/tab_switch/tab_close/tab_list/copy_to_clipboard/paste_from_clipboard）透传 bridge；移除 `_cdp()`、`click_at_xy()`、`target_session` 方法；保留 `reset_ref_map()` 和 `get_element_by_index()` 辅助方法
- [ ] 1.3 修改 `backend/cdp/__init__.py`：导出 `PlaywrightBridge`，`CDPDaemon` 标 deprecated
- [ ] 1.4 修改 `backend/cdp/daemon.py`：`CDPDaemon` 类标 `@deprecated`，docstring 加废弃说明

## 2. Executor 与工具层改造

- [ ] 2.1 重写 `backend/engine/executor.py` 中 `execute_browser_op()`：参数从 `cdp_helpers` 改为 `bridge: PlaywrightBridge`；所有已有 op_type（goto/click/fill/snapshot/scroll/source/eval/get_element_by_number）改为调 bridge 方法；新增 12 个 op_type 分支（hover/unhover/focus/select/clear/keyboard/navigate/wait/tab/copy/paste）；`_resolve_element_ref()` 第三参数从 `cdp_helpers` 改为 `bridge`，fallback 走 `bridge.get_element_by_index()`
- [ ] 2.2 修改 `backend/engine/executor.py` 中 `execute_browser_step()`：`cdp_helpers.wait_for_network_idle()` → `bridge.wait_for_network_idle()`；`cdp_helpers.get_page_html()` → `bridge.get_page_html()`；`cdp_helpers.add_dom_highlights()` → `bridge.evaluate(highlight_js)`
- [ ] 2.3 修改 `backend/engine/executor.py` 中 `run_check()`：签名从 `run_check(check_def, cdp_helpers)` 改为 `run_check(check_def, bridge)`；`cdp_helpers.js()` → `bridge.evaluate()`；`document.body.innerText` → `document.body.textContent`；URL 获取改为 `bridge.page.url`
- [ ] 2.4 修改 `backend/engine/_harness/tools.py`：追加 12 个新 tool schema（browser_hover/browser_unhover/browser_focus/browser_press_key/browser_type_text/browser_select/browser_clear/browser_copy/browser_paste/browser_navigate/browser_wait/browser_tab）；click schema 新增 `clickCount` 参数；fill schema description 注明自动清空行为

## 3. ToolCDPHelpers 与工具层适配

- [ ] 3.1 修改 `backend/utils/tool_cdp.py`：`ToolCDPHelpers.__init__` 参数从 `CDPHelpers` 改为 `PlaywrightBridge`；所有方法改为调 bridge 方法；新增 `evaluate(js)` 方法透传 `bridge.evaluate()`；保留 circuit breaker 逻辑
- [ ] 3.2 修改 `backend/tools/extract.py`：`ToolCDPHelpers` 构造参数从 `CDPHelpers` 改为 `PlaywrightBridge`
- [ ] 3.3 确认 `backend/tools/schemas.py`：`ToolContext.cdp_helpers: Any = None` 标注不变（运行期兼容）

## 4. 入口层改造

- [ ] 4.1 修改 `backend/api/state.py`：`_EngineState.chrome_daemon: CDPDaemon` → `_EngineState.bridge: PlaywrightBridge`；`connect_chrome()` 改为 `PlaywrightBridge.start()`；移除 `_highlight_guard_task`（新标签页高亮由 PlaywrightBridge 的 `context.on("page")` 事件自动处理）
- [ ] 4.2 修改 `backend/api/routes.py`：5 处 `CDPHelpers(engine_state.chrome_daemon)` → `CDPHelpers(engine_state.bridge)`；移除 `_highlight_guard()` 函数；`add_dom_highlights()` 调用改为调 `bridge.evaluate()`
- [ ] 4.3 修改 `backend/engine/agent.py`：`start_chat_agent()` 中初始化从 `CDPDaemon` + `CDPHelpers(daemon)` 改为 `PlaywrightBridge` + `CDPHelpers(bridge)`；传 `cdp_helpers` 给 `run_conversation_loop()`（参数名不变）
- [ ] 4.4 修改 `backend/engine/_harness/conversation_loop.py`：`run_conversation_loop()` 保持 `cdp_helpers` 参数不变（内部不创建 bridge，由调用方传入）；`run_preset_loop()` 同样保持 `cdp_helpers` 参数不变
- [ ] 4.5 修改 `backend/engine/runner.py`：`run_chat_loop()` 中初始化从 `ensure_daemon()` + `CDPHelpers(daemon)` 改为 `PlaywrightBridge` + `CDPHelpers(bridge)`
- [ ] 4.6 修改 `backend/api/service.py`：`process_chat_message()` 中从 `engine_state` 拿 `bridge` 而非 `CDPDaemon`，创建 `CDPHelpers(bridge)` 传入 `run_conversation_loop()`

## 5. CLI 与 Preset 引擎层改造

- [ ] 5.1 修改 `backend/cli/run.py`：`CDPDaemon(ws_url)` → `PlaywrightBridge(http_url)`；传 `bridge` 给 `run_pipeline()` / `run_preset_loop()`
- [ ] 5.2 修改 `backend/cli/chrome.py`：`_with_cdp()` 工厂函数改为 `_with_bridge()`；所有直接 CDP 命令改为调 bridge 方法；tab 命令（list/switch/close/new）改为 `bridge.tab_list()` / `bridge.tab_switch()` / `bridge.tab_close()` / `bridge.tab_new()`
- [ ] 5.3 修改 `backend/engine/runner_preset.py`：`cdp_helpers` 参数类型更新（接口兼容）；`run_check()` 调用改为传 `bridge`
- [ ] 5.4 修改 `backend/engine/_harness/tool_executor.py`：`cdp_helpers` 参数类型更新；`_auto_refresh_highlights()` 调 `bridge.evaluate(add_highlights_js)`；移除 CDP 重连逻辑（Playwright 内置）
- [ ] 5.5 修改 `backend/engine/_lifecycle/tool_runner.py`：`load_and_call()` 中 `cdp_helpers` 参数类型更新
- [ ] 5.6 确认 `backend/engine/scratchpad.py`：`sync_element_map()` 的调用方 `_auto_refresh_highlights` 改为 `bridge.evaluate()`，确认 map 格式兼容

## 6. 测试更新

- [ ] 6.1 更新 `tests/test_executor_helpers.py`：mock `CDPDaemon` → mock `PlaywrightBridge`
- [ ] 6.2 更新 `tests/test_harness_tools.py`：验证新增 12 个 tool schema 和 click `clickCount` 参数
- [ ] 6.3 更新 `tests/test_conversation_loop.py`：验证初始化路径从 CDPDaemon 切换到 PlaywrightBridge
- [ ] 6.4 更新 `tests/test_run_check.py`：验证 `run_check()` 参数从 `cdp_helpers` 改为 `bridge`，`textContent` 行为正确

## 7. 验证与收尾

- [ ] 7.1 运行现有测试套件，确保无回归
- [ ] 7.2 手动验证 Agent 模式：确认 LLM 能正确调用新增 tool（browser_hover 等）
- [ ] 7.3 手动验证 Preset 模式：确认 YAML pipeline 在 Playwright 驱动下执行稳定
- [ ] 7.4 验证 `simplify-dom.js` 通过 `page.evaluate()` 运行结果与 CDP `Runtime.evaluate` 一致
- [ ] 7.5 验证新标签页高亮自动注入（`context.on("page")` 事件）正常工作
- [ ] 7.6 确认 `CDPDaemon` 标记 deprecated 后不影响现有功能
