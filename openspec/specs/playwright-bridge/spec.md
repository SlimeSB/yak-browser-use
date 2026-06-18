## ADDED Requirements

### Requirement: PlaywrightBridge 统一浏览器驱动
系统 MUST 提供 `PlaywrightBridge` 类，通过 `playwright.chromium.connect_over_cdp()` 统一管理浏览器连接、标签页和所有交互操作。

#### Scenario: 连接已有 Chrome 实例
- **WHEN** `PlaywrightBridge(cdp_url="http://127.0.0.1:9222")` 创建并调用 `start()`
- **THEN** 通过 `connect_over_cdp()` 连接到已有 Chrome 调试端口
- **AND** 获取当前活跃 Page 和 BrowserContext
- **AND** 不创建新浏览器进程，保持用户已有标签页和登录状态

#### Scenario: 停止连接但不关闭 Chrome
- **WHEN** `bridge.stop()` 被调用
- **THEN** 调用 `playwright.stop()` 释放 Playwright 资源
- **AND** 不关闭 Chrome 浏览器进程

#### Scenario: 新标签页高亮自动注入
- **WHEN** 用户在浏览器中打开新标签页
- **THEN** `context.on("page")` 事件回调自动触发
- **AND** 等待页面 `domcontentloaded` 后注入高亮 JS
- **AND** 注入失败时静默失败，不影响用户操作

### Requirement: PlaywrightBridge 交互操作
`PlaywrightBridge` MUST 提供完整的浏览器交互操作方法，所有方法利用 Playwright 的 auto-wait/auto-scroll 特性。

#### Scenario: 页面导航
- **WHEN** `bridge.goto("https://example.com")` 被调用
- **THEN** 通过 `page.goto(url, wait_until="domcontentloaded")` 导航
- **AND** 自动等待 DOM 内容加载完成

#### Scenario: 元素点击
- **WHEN** `bridge.click("#btn", click_count=1)` 被调用
- **THEN** 通过 `page.locator("#btn").click()` 执行点击
- **AND** Playwright 自动等待元素可见、滚动到视口、dispatch 真实事件
- **AND** `click_count=2` 时执行双击

#### Scenario: 输入框填充
- **WHEN** `bridge.fill("#input", "hello")` 被调用
- **THEN** 通过 `page.locator("#input").fill("hello")` 执行填充
- **AND** 自动聚焦、清空已有内容、逐字输入

#### Scenario: 页面滚动
- **WHEN** `bridge.scroll("down", amount=300)` 被调用
- **THEN** 通过 `page.evaluate()` 执行 `window.scrollBy(0, 300)`
- **AND** 支持 up/down/left/right 四个方向
- **AND** 注意：executor 层不直接调用 `bridge.scroll()`，而是构建 JS 后通过 `bridge.evaluate()` 执行

#### Scenario: 获取页面源码
- **WHEN** `bridge.source()` 被调用
- **THEN** 通过 `page.content()` 返回完整 HTML

#### Scenario: 执行 JavaScript
- **WHEN** `bridge.evaluate("document.title")` 被调用
- **THEN** 通过 `page.evaluate()` 在浏览器中执行 JS
- **AND** 返回 JS 执行结果

### Requirement: PlaywrightBridge 新增操作
`PlaywrightBridge` MUST 支持 hover、focus、select、clear、keyboard、navigate、wait、tab、copy、paste 等新增操作。

#### Scenario: 鼠标悬停
- **WHEN** `bridge.hover("#menu")` 被调用
- **THEN** 通过 `page.locator("#menu").hover()` 执行悬停
- **AND** Playwright 自动等待元素可见并滚动到视口

#### Scenario: 取消悬停
- **WHEN** `bridge.unhover("#menu")` 被调用
- **THEN** 通过 `page.mouse.move(0, 0)` 将鼠标移开

#### Scenario: 元素聚焦
- **WHEN** `bridge.focus("#input")` 被调用
- **THEN** 通过 `page.locator("#input").focus()` 聚焦元素

#### Scenario: 下拉选择
- **WHEN** `bridge.select("#country", "CN", mode="value")` 被调用
- **THEN** 通过 `page.locator("#country").selectOption("CN")` 选择选项
- **AND** 支持 value/label/index 三种选择模式

#### Scenario: 输入框清空
- **WHEN** `bridge.clear("#input")` 被调用（默认 `mode="js"`）
- **THEN** 通过 `page.evaluate()` 设置 `element.value = ""`
- **AND** `mode="pw"` 时通过 `page.locator("#input").clear()` 清空内容

#### Scenario: 键盘按键
- **WHEN** `bridge.keyboard_press("Enter")` 被调用
- **THEN** 通过 `page.keyboard.press("Enter")` 模拟按键

#### Scenario: 键盘输入文本
- **WHEN** `bridge.keyboard_type("hello world")` 被调用
- **THEN** 通过 `page.keyboard.type("hello world")` 逐字输入

#### Scenario: 页面导航操作
- **WHEN** `bridge.navigate("back")` 被调用
- **THEN** 通过 `page.goBack()` 返回上一页
- **AND** `navigate("forward")` 调用 `page.goForward()`
- **AND** `navigate("reload")` 调用 `page.reload()`

#### Scenario: 等待操作
- **WHEN** `bridge.wait(mode="time", duration=2000)` 被调用
- **THEN** 等待指定毫秒数
- **AND** `mode="selector"` 时通过 `page.waitForSelector()` 等待元素出现
- **AND** `mode="load"` 时通过 `page.waitForLoadState()` 等待页面加载

#### Scenario: 等待网络空闲
- **WHEN** `bridge.wait_for_network_idle()` 被调用
- **THEN** 通过 `page.wait_for_load_state("networkidle")` 等待网络空闲

#### Scenario: 等待页面加载
- **WHEN** `bridge.wait_for_page_load()` 被调用
- **THEN** 通过 `page.wait_for_load_state("load")` 等待页面完全加载

#### Scenario: 标签页管理
- **WHEN** `bridge.tab_new("https://example.com")` 被调用
- **THEN** 通过 `context.newPage()` 创建新标签页并导航
- **AND** `bridge.tab_switch(target_id)` 通过 `page.bringToFront()` 切换
- **AND** `bridge.tab_close(target_id)` 通过 `page.close()` 关闭
- **AND** `bridge.tab_list()` 返回所有标签页列表

#### Scenario: 剪贴板操作
- **WHEN** `bridge.copy_to_clipboard("#src")` 被调用
- **THEN** 通过 `page.evaluate()` 读取元素文本内容并写入剪贴板
- **AND** `bridge.paste_from_clipboard("#dst")` 通过 `page.evaluate()` 模拟粘贴

### Requirement: PlaywrightBridge 快照与高亮
`PlaywrightBridge` MUST 支持通过 `page.evaluate()` 运行 simplify-dom.js 和注入高亮 JS。

#### Scenario: 交互元素快照
- **WHEN** `bridge.simplify_dom(query="", in_viewport=False)` 被调用
- **THEN** 通过 `page.evaluate()` 运行 simplify-dom.js
- **AND** 返回交互元素列表

#### Scenario: 页面截图
- **WHEN** `bridge.screenshot()` 被调用
- **THEN** 通过 `page.screenshot()` 返回 base64 编码的截图

#### Scenario: 组合快照
- **WHEN** `bridge.capture_snapshot()` 被调用
- **THEN** 组合截图、HTML、页面标题返回

### Requirement: PlaywrightBridge 元素映射
`PlaywrightBridge` MUST 维护 @eN 元素引用映射，支持按索引查找。

#### Scenario: 重置映射
- **WHEN** `bridge.reset_ref_map()` 被调用
- **THEN** 清空内部元素映射缓存

#### Scenario: 按索引查找
- **WHEN** `bridge.get_element_by_index("@e5")` 被调用
- **THEN** 从映射缓存中查找对应元素信息
- **AND** 未找到时返回 None
