## ADDED Requirements

### Requirement: browser_press_key 工具
系统 MUST 提供 `browser_press_key` 工具，通过 Playwright `keyboard.press()` 实现键盘按键操作。executor 层 `browser_press_key` 和 `browser_type_text` 共享 `op_type="keyboard"` 分支，通过 `mode` 参数（`"key"` / `"text"`）路由到不同 bridge 方法。

#### Scenario: 按下单个键
- **WHEN** LLM 调用 `browser_press_key(key="Enter")`
- **THEN** executor 以 `op_type="keyboard"`、`mode="key"` 路由到 `bridge.keyboard_press("Enter")`
- **AND** Playwright 模拟按键按下和释放
- **AND** 返回 `{"result": {"mode": "key"}}`

#### Scenario: 按下组合键
- **WHEN** LLM 调用 `browser_press_key(key="Control+A")`
- **THEN** executor 调用 `bridge.keyboard_press("Control+A")`
- **AND** Playwright 模拟组合键

### Requirement: browser_type_text 工具
系统 MUST 提供 `browser_type_text` 工具，通过 Playwright `keyboard.type()` 实现文本逐字输入。

#### Scenario: 输入文本
- **WHEN** LLM 调用 `browser_type_text(text="hello world")`
- **THEN** executor 以 `op_type="keyboard"`、`mode="text"` 路由到 `bridge.keyboard_type("hello world")`
- **AND** Playwright 逐字输入，触发完整事件链（keydown/keypress/keyup）
- **AND** 返回 `{"result": {"mode": "text"}}`

#### Scenario: 配合 focus 追加输入
- **WHEN** LLM 先调用 `browser_focus(selector="#input")` 再调用 `browser_type_text(text=" suffix")`
- **THEN** 文本追加到已有内容末尾，不清空
