## ADDED Requirements

### Requirement: browser_copy 工具
系统 MUST 提供 `browser_copy` 工具，通过 Playwright `page.evaluate()` 读取元素文本并写入剪贴板。

#### Scenario: 复制元素文本
- **WHEN** LLM 调用 `browser_copy(selector="#result")`
- **THEN** executor 调用 `bridge.copy_to_clipboard("#result")`
- **AND** 通过 `page.evaluate()` 读取 `#result` 的 `textContent`
- **AND** 将文本写入系统剪贴板
- **AND** 返回复制的文本内容

### Requirement: browser_paste 工具
系统 MUST 提供 `browser_paste` 工具，通过 Playwright `page.evaluate()` 模拟粘贴操作。

#### Scenario: 粘贴到输入框
- **WHEN** LLM 调用 `browser_paste(selector="#input")`
- **THEN** executor 调用 `bridge.paste_from_clipboard("#input")`
- **AND** 通过 `page.evaluate()` 读取剪贴板内容
- **AND** 将内容写入目标输入框

#### Scenario: 粘贴到指定位置
- **WHEN** LLM 调用 `browser_paste(selector="#input", index=0)`
- **THEN** executor 调用 `bridge.paste_from_clipboard("#input", 0)`
- **AND** 将剪贴板内容插入到输入框开头
