## MODIFIED Requirements

### Requirement: CDPHelpers 构造参数变更

`CDPHelpers.__init__` MUST 从接受 `CDPDaemon` 改为接受 `PlaywrightBridge`，所有方法重写为调用 PlaywrightBridge 的方法。

#### Scenario: 构造参数变更
- **WHEN** 创建 `CDPHelpers(bridge)` 传入 `PlaywrightBridge` 实例
- **THEN** 内部持有 `self._bridge` 引用
- **AND** 不再依赖 `CDPDaemon` 实例

### Requirement: CDPHelpers 已有方法重写

`CDPHelpers` 的所有已有方法 MUST 重写为调用 PlaywrightBridge 的对应方法。

#### Scenario: goto_url 透传
- **WHEN** 调用 `cdp_helpers.goto_url("https://example.com")`
- **THEN** 内部调用 `self._bridge.goto("https://example.com")`

#### Scenario: click_selector 透传
- **WHEN** 调用 `cdp_helpers.click_selector("#btn")`
- **THEN** 内部调用 `self._bridge.click("#btn")`

#### Scenario: fill_input 透传
- **WHEN** 调用 `cdp_helpers.fill_input("#input", "hello")`
- **THEN** 内部调用 `self._bridge.fill("#input", "hello")`

#### Scenario: capture_snapshot 透传
- **WHEN** 调用 `cdp_helpers.capture_snapshot()`
- **THEN** 内部调用 `self._bridge.capture_snapshot()`

#### Scenario: capture_snapshot_interactive 透传
- **WHEN** 调用 `cdp_helpers.capture_snapshot_interactive()`
- **THEN** 内部调用 `self._bridge.simplify_dom()`

#### Scenario: capture_snapshot_simplified 透传
- **WHEN** 调用 `cdp_helpers.capture_snapshot_simplified()`
- **THEN** 内部调用 `self._bridge.evaluate()` 运行 TreeWalker 文本提取 JS

#### Scenario: js 方法透传
- **WHEN** 调用 `cdp_helpers.js("document.title")`
- **THEN** 内部调用 `self._bridge.evaluate("document.title")`

#### Scenario: get_page_html 透传
- **WHEN** 调用 `cdp_helpers.get_page_html()`
- **THEN** 内部调用 `self._bridge.source()`

#### Scenario: add_dom_highlights 透传
- **WHEN** 调用 `cdp_helpers.add_dom_highlights(elements)`
- **THEN** 内部通过 `self._bridge.evaluate()` 注入高亮 JS

#### Scenario: remove_dom_highlights 透传
- **WHEN** 调用 `cdp_helpers.remove_dom_highlights()`
- **THEN** 内部通过 `self._bridge.evaluate()` 清除高亮

#### Scenario: wait_for_network_idle 透传
- **WHEN** 调用 `cdp_helpers.wait_for_network_idle()`
- **THEN** 内部调用 `self._bridge.wait_for_network_idle()`

#### Scenario: wait_for_page_load 透传
- **WHEN** 调用 `cdp_helpers.wait_for_page_load()`
- **THEN** 内部调用 `self._bridge.wait_for_page_load()`

### Requirement: CDPHelpers 新增方法

`CDPHelpers` MUST 新增 hover、unhover、focus_selector、select_option、clear_input、keyboard_key、keyboard_text、navigate、wait、tab_new、tab_switch、tab_close、tab_list、copy_to_clipboard、paste_from_clipboard 方法，全部透传 PlaywrightBridge。

#### Scenario: hover 透传
- **WHEN** 调用 `cdp_helpers.hover("#menu")`
- **THEN** 内部调用 `self._bridge.hover("#menu")`

#### Scenario: select_option 透传
- **WHEN** 调用 `cdp_helpers.select_option("#country", "CN", "value")`
- **THEN** 内部调用 `self._bridge.select("#country", "CN", "value")`

#### Scenario: tab_new 透传
- **WHEN** 调用 `cdp_helpers.tab_new("https://example.com")`
- **THEN** 内部调用 `self._bridge.tab_new("https://example.com")`

#### Scenario: unhover 透传
- **WHEN** 调用 `cdp_helpers.unhover("#menu")`
- **THEN** 内部调用 `self._bridge.unhover("#menu")`

#### Scenario: focus_selector 透传
- **WHEN** 调用 `cdp_helpers.focus_selector("#input")`
- **THEN** 内部调用 `self._bridge.focus("#input")`

#### Scenario: clear_input 透传
- **WHEN** 调用 `cdp_helpers.clear_input("#search")`
- **THEN** 内部调用 `self._bridge.clear("#search")`

#### Scenario: keyboard_key 透传
- **WHEN** 调用 `cdp_helpers.keyboard_key("Enter")`
- **THEN** 内部调用 `self._bridge.keyboard_press("Enter")`

#### Scenario: keyboard_text 透传
- **WHEN** 调用 `cdp_helpers.keyboard_text("hello")`
- **THEN** 内部调用 `self._bridge.keyboard_type("hello")`

#### Scenario: navigate 透传
- **WHEN** 调用 `cdp_helpers.navigate("back")`
- **THEN** 内部调用 `self._bridge.navigate("back")`

#### Scenario: wait 透传
- **WHEN** 调用 `cdp_helpers.wait(mode="time", duration=2000)`
- **THEN** 内部调用 `self._bridge.wait(mode="time", duration=2000)`

#### Scenario: tab_switch 透传
- **WHEN** 调用 `cdp_helpers.tab_switch("ABC123")`
- **THEN** 内部调用 `self._bridge.tab_switch("ABC123")`

#### Scenario: tab_close 透传
- **WHEN** 调用 `cdp_helpers.tab_close("ABC123")`
- **THEN** 内部调用 `self._bridge.tab_close("ABC123")`

#### Scenario: tab_list 透传
- **WHEN** 调用 `cdp_helpers.tab_list()`
- **THEN** 内部调用 `self._bridge.tab_list()`

#### Scenario: copy_to_clipboard 透传
- **WHEN** 调用 `cdp_helpers.copy_to_clipboard("#src")`
- **THEN** 内部调用 `self._bridge.copy_to_clipboard("#src")`

#### Scenario: paste_from_clipboard 透传
- **WHEN** 调用 `cdp_helpers.paste_from_clipboard("#dst")`
- **THEN** 内部调用 `self._bridge.paste_from_clipboard("#dst")`

### Requirement: CDPHelpers 移除的方法

`CDPHelpers` MUST 移除 `_cdp()` 私有方法、`click_at_xy()` 方法、`target_session` 方法。

#### Scenario: _cdp 已移除
- **WHEN** 检查 `CDPHelpers` 类的方法列表
- **THEN** 不包含 `_cdp` 方法
- **AND** 不包含 `click_at_xy` 方法
- **AND** 不包含 `target_session` 方法

### Requirement: CDPHelpers 保留辅助方法

`CDPHelpers` MUST 保留 `reset_ref_map()` 和 `get_element_by_index()` 辅助方法，内部透传 PlaywrightBridge。

#### Scenario: reset_ref_map 透传
- **WHEN** 调用 `cdp_helpers.reset_ref_map()`
- **THEN** 内部调用 `self._bridge.reset_ref_map()`

#### Scenario: get_element_by_index 透传
- **WHEN** 调用 `cdp_helpers.get_element_by_index("@e5")`
- **THEN** 内部调用 `self._bridge.get_element_by_index("@e5")`

### Requirement: ToolCDPHelpers（工具层轻量包装）

`ToolCDPHelpers.__init__` MUST 接受 `PlaywrightBridge`，内部持有 `self._bridge`。click/fill 方法透传 bridge。MUST 新增 `evaluate(js)` 方法透传 `bridge.evaluate()`，供 `extract.py` 等工具跑任意 JS。MUST 保留 circuit breaker 逻辑：连续失败 3 次后抛出 `RuntimeError`，成功后重置计数。

#### Scenario: 构造参数变更
- **WHEN** 创建 `ToolCDPHelpers(bridge)` 传入 `PlaywrightBridge` 实例
- **THEN** 内部持有 `self._bridge` 引用
- **AND** 不再依赖 `CDPHelpers` 实例

#### Scenario: click 方法透传
- **WHEN** 工具脚本调用 `tool_cdp.click("#btn")`
- **THEN** `ToolCDPHelpers` 通过 `self._bridge.click("#btn")` 执行
- **AND** circuit breaker 在调用前后检查/重置失败计数

#### Scenario: evaluate 方法
- **WHEN** 工具脚本调用 `tool_cdp.evaluate("document.title")`
- **THEN** `ToolCDPHelpers` 通过 `self._bridge.evaluate("document.title")` 执行
- **AND** circuit breaker 在调用前后检查/重置失败计数
- **AND** 返回 JS 执行结果

#### Scenario: 连续失败触发熔断
- **WHEN** 工具脚本连续 3 次调用均失败
- **THEN** 第 4 次调用时 `_check_failures()` 抛出 `RuntimeError("Circuit breaker: 3 consecutive failures")`

#### Scenario: 成功后重置计数
- **WHEN** 工具脚本在失败后成功调用一次
- **THEN** `_fail_count` 重置为 0
- **AND** 后续调用不受熔断限制
