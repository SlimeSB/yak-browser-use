## Requirements

### Requirement: browser_* 工具统一注册表

系统 MUST 通过 `build_registry()` 中的 `_BROWSER_OPS` 列表和 `_BROWSER_SCHEMAS` 字典统一注册所有 `browser_*` 工具。每个工具通过 `_make_browser_handler(op_type)` 生成 handler，内部委托给 `execute_browser_op(op, args, bridge)`。

#### Scenario: 工具列表包含的 browser_* 工具
- **WHEN** 调用 `registry.get_schemas()`
- **THEN** 返回列表 MUST 包含 `browser_goto`、`browser_click`、`browser_fill`、`browser_snapshot`、`browser_scroll`、`browser_source`、`browser_hover`、`browser_unhover`、`browser_focus`、`browser_select`、`browser_clear`、`browser_keyboard`、`browser_press_key`、`browser_type_text`、`browser_navigate`、`browser_wait`、`browser_tab`、`browser_copy`、`browser_paste`、`browser_lookup_selector`、`browser_eval_js`
- **AND** 每个工具的 handler 在 `ctx.cdp_helpers` 为 None 时 MUST 返回 `{"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}`

#### Scenario: browser_source 独立注册
- **WHEN** 检查 `build_registry()` 的注册逻辑
- **THEN** `browser_source` MUST 独立注册（不在 `_BROWSER_OPS` 循环中），因为其 handler 需要特殊处理 `output_to` 参数和 shared_store 写入

#### Scenario: browser_eval_js 独立注册
- **WHEN** 检查 `build_registry()` 的注册逻辑
- **THEN** `browser_eval_js` MUST 独立注册（不在 `_BROWSER_OPS` 循环中），因为其 handler 需要 `script_file` 参数读取和 `output_to`/`return_format` 处理

### Requirement: browser_goto

`browser_goto` MUST 通过 `page.goto(url, wait_until="domcontentloaded")` 导航到指定 URL。导航成功后 MUST 调用 `bridge.reset_ref_map()` 清空元素映射。

#### Scenario: 导航到 URL
- **WHEN** LLM 调用 `browser_goto(url="https://example.com")`
- **THEN** executor 调用 `bridge.goto("https://example.com")` 并通过 Playwright `page.goto()` 导航
- **AND** 导航后自动调用 `bridge.reset_ref_map()` 清空元素映射
- **AND** 返回 `{"ok": True, "result": {"url": "https://example.com"}}`

### Requirement: browser_click

`browser_click` MUST 使用 Playwright `locator.click()` 点击元素，支持 `clickCount` 参数（默认 1）执行双击。支持通过 `_resolve_element_ref()` 解析 `@eN` 或 `@e_XXXXX` 格式的元素引用。

#### Scenario: 点击指定选择器
- **WHEN** LLM 调用 `browser_click(selector="#btn")`
- **THEN** executor 调用 `bridge.click("#btn", click_count=1)` — Playwright 自动等待元素可见、滚动到视口

#### Scenario: 双击
- **WHEN** LLM 调用 `browser_click(selector="#btn", clickCount=2)`
- **THEN** executor 调用 `bridge.click("#btn", click_count=2)`

### Requirement: browser_fill

`browser_fill` MUST 使用 Playwright `locator.fill()` 填充输入框。MUST 自动清空已有内容再填入。`text` 参数支持纯字符串或 `{"param_key": "key-name"}` 格式（服务端解析凭据）。

#### Scenario: 填充输入框
- **WHEN** LLM 调用 `browser_fill(selector="#search", text="hello")`
- **THEN** executor 调用 `bridge.fill("#search", "hello")` — Playwright 自动聚焦、清空已有内容、逐字输入

#### Scenario: 使用存储的凭据
- **WHEN** LLM 调用 `browser_fill(selector="#pwd", text={"param_key": "my-password"})`
- **THEN** 服务端从参数存储中解析真实值，LLM 永远看不到明文密码

### Requirement: browser_snapshot

`browser_snapshot` MUST 提供四种模式：`aria`（默认）、`a11y`、`progressive`、`full`。支持 `query` 参数过滤元素（a11y/progressive 模式），支持 `expand_key` 展开折叠容器（progressive 模式）。

#### Scenario: aria 模式（默认）
- **WHEN** LLM 调用 `browser_snapshot()` 或 `browser_snapshot(mode="aria")`
- **THEN** 调用 `bridge.aria_snapshot()` 获取 YAML 语义树

#### Scenario: a11y 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="a11y")`
- **THEN** 调用 `bridge.a11y_snapshot()` 获取结构化元素列表

#### Scenario: progressive 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive")`
- **THEN** 调用 `bridge._progressive_snapshot()` 执行 DOM 深度扫描 + 密度自适应折叠，最多 200 元素

#### Scenario: full 模式
- **WHEN** LLM 调用 `browser_snapshot(mode="full")`
- **THEN** 调用 `bridge.capture_snapshot()` 获取 screenshot + HTML

#### Scenario: a11y 不可用降级
- **WHEN** a11y snapshot 因浏览器环境不可用而失败
- **THEN** 自动降级为 progressive 模式，返回结果中标记 `degraded: true`

#### Scenario: query 过滤
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", query="disabled")`
- **THEN** `_progressive_snapshot` 遍历元素所有非 `_` 前缀字段进行模糊匹配

#### Scenario: expand_key 展开容器
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", expand_key="c_0")`
- **THEN** 先执行 progressive snapshot，然后展开 `c_0` 容器，返回结果中包含展开后的元素

### Requirement: browser_scroll

`browser_scroll` MUST 构建 `window.scrollBy()` JS 代码并通过 `bridge.evaluate()` 执行。

#### Scenario: 向下滚动
- **WHEN** LLM 调用 `browser_scroll(direction="down", amount=300)`
- **THEN** executor 构建 `window.scrollBy(0, 300)` 并通过 `bridge.evaluate()` 执行

#### Scenario: 默认参数
- **WHEN** LLM 调用 `browser_scroll()`
- **THEN** 默认 `direction="down"`、`amount=300`

### Requirement: browser_source

`browser_source` MUST 获取页面完整 HTML 并通过 `output_to` 参数将 HTML 写入 shared_store，返回结果仅含元信息（size/output_to/note）。支持 `selector` 参数获取指定元素的 outerHTML，支持 `cached` 参数读取缓存。

#### Scenario: 必须提供 output_to
- **WHEN** LLM 调用 `browser_source(output_to="page_html")`
- **THEN** HTML 写入 `shared_store["page_html"]`
- **AND** 返回仅含元信息（size/output_to/note），不含 HTML 原文
- **AND** 如果未提供 `output_to`，返回错误提示

#### Scenario: 获取指定元素的 outerHTML
- **WHEN** LLM 调用 `browser_source(output_to="element_html", selector="#main")`
- **THEN** 通过 JS `document.querySelector` 获取该元素的 outerHTML 并写入 shared_store

#### Scenario: HTML 较大时的建议
- **WHEN** HTML 大小超过 100,000 字节
- **THEN** 返回 note 中建议优先使用 `browser_snapshot` 或 `browser_eval_js`

### Requirement: browser_hover / browser_unhover

`browser_hover` MUST 使用 Playwright `locator.hover()` 悬停元素。`browser_unhover` MUST 通过 `page.mouse.move(0, 0)` 将鼠标移到页面左上角。

### Requirement: browser_focus

`browser_focus` MUST 使用 Playwright `locator.focus()` 聚焦元素。典型用法是配合 `browser_type_text` 追加输入（不清空已有内容）。

### Requirement: browser_select

`browser_select` MUST 支持三种模式：`value`（按 option value 属性）、`label`（按显示文本）、`index`（按 0-based 位置）。

#### Scenario: 按值选择
- **WHEN** LLM 调用 `browser_select(selector="#country", value="CN", mode="value")`
- **THEN** 调用 `bridge.select("#country", "CN", "value")`

#### Scenario: 按索引选择
- **WHEN** LLM 调用 `browser_select(selector="#country", value="2", mode="index")`
- **THEN** executor 将字符串 `"2"` 转为整数后调用 `bridge.select("#country", 2, "index")`

### Requirement: browser_clear

`browser_clear` MUST 支持两种模式：`js`（默认，通过 `page.evaluate()` 设置 `value=""`）和 `pw`（Playwright 原生 `locator.clear()`）。

### Requirement: browser_keyboard / browser_press_key / browser_type_text

`browser_keyboard` MUST 通过 `mode` 参数路由：`"key"` 对应 `bridge.keyboard_press()`（单键/组合键），`"text"` 对应 `bridge.keyboard_type()`（逐字输入）。`browser_press_key` 和 `browser_type_text` 是这两个模式的便捷别名。`text` 参数支持 `{"param_key": "key-name"}` 格式。

#### Scenario: 按下单个键
- **WHEN** LLM 调用 `browser_press_key(key="Enter")`
- **THEN** 调用 `bridge.keyboard_press("Enter")`

#### Scenario: 输入文本
- **WHEN** LLM 调用 `browser_type_text(text="hello world")`
- **THEN** 调用 `bridge.keyboard_type("hello world")`

#### Scenario: 配合 focus 追加输入
- **WHEN** LLM 先调用 `browser_focus(selector="#input")` 再调用 `browser_type_text(text=" suffix")`
- **THEN** 文本追加到已有内容末尾，不清空

### Requirement: browser_navigate

`browser_navigate` MUST 支持 `back`（`page.goBack()`）、`forward`（`page.goForward()`）、`reload`（`page.reload()`）三种操作。

### Requirement: browser_wait

`browser_wait` MUST 支持三种模式：`time`（`asyncio.sleep(duration/1000)`）、`selector`（`page.waitForSelector()`）、`load`（`page.waitForLoadState()`）。默认 `mode="time"`，默认 `duration=1000`。

### Requirement: browser_tab

`browser_tab` MUST 支持四种操作：`new`（新建标签页）、`switch`（切换到指定标签页）、`close`（关闭标签页）、`list`（列出所有标签页）。

### Requirement: browser_copy / browser_paste

`browser_copy` MUST 通过 `page.evaluate()` 读取元素 textContent 并写入系统剪贴板。`browser_paste` MUST 从剪贴板读取内容并写入目标输入框。`paste` 支持 `index` 参数指定插入位置（-1 默认追加到末尾）。

### Requirement: browser_lookup_selector

`browser_lookup_selector` MUST 先执行 `ensure_highlights()` 刷新页面元素映射，再从最新 `element_map` 中查询 ref。支持 `@eN` 和 `@e_XXXXX` 两种格式。

### Requirement: browser_eval_js

`browser_eval_js` MUST 接受 `script_file` 参数（workspace 相对路径），读取文件内容后通过 `bridge.evaluate()` 执行。支持 `output_to` 将结果存入 shared_store。支持 `return_format` 参数：`raw`（默认，原样返回）、`json`（`json.dumps` 序列化）、`csv`（数组结果转为 CSV 文本）。

#### Scenario: 使用 script_file 执行 JS 脚本
- **WHEN** Agent 调用 `browser_eval_js(script_file="scripts/extract.js")`
- **THEN** 系统读取 workspace 下 `scripts/extract.js` 文件内容并执行

#### Scenario: script_file 不存在时返回错误
- **WHEN** Agent 调用 `browser_eval_js(script_file="scripts/nonexistent.js")`
- **THEN** 返回 `{"ok": False, "error": "脚本文件不存在: scripts/nonexistent.js"}`

#### Scenario: script_file 路径越界时返回错误
- **WHEN** Agent 调用 `browser_eval_js(script_file="../../../etc/passwd")`
- **THEN** 系统通过 `validate_path` 拒绝并返回越界错误

#### Scenario: output_to 写入 shared_store
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", output_to="link_count")`
- **THEN** 执行结果存入 `ctx.shared_store["link_count"]`

#### Scenario: return_format=csv
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", return_format="csv")` 且结果为数组
- **THEN** 返回 CSV 格式文本

#### Scenario: return_format=csv 但结果不是数组
- **WHEN** Agent 调用 `browser_eval_js(script_file="extract.js", return_format="csv")` 但结果为字符串
- **THEN** 返回 `"return_format=csv requires array result, got str"`

### Requirement: ToolContext 安全层

`ToolContext` MUST 仅接受 `bridge` 和 `allowed_domains` 两个构造参数。MUST 提供 domain whitelist（`_allowed_domains`）和 circuit breaker（`_fail_count` / `_MAX_CONSECUTIVE_FAILURES=3`）两种安全机制。

#### Scenario: domain whitelist 检查
- **WHEN** `_allowed_domains` 不为空且当前页面 hostname 不在列表中
- **THEN** 操作 MUST 被拒绝

#### Scenario: circuit breaker 触发
- **WHEN** `_fail_count` 达到 3
- **THEN** 系统 MUST 抛出异常，后续所有受保护操作 MUST 继续抛出异常

#### Scenario: circuit breaker 重置
- **WHEN** 受保护操作执行成功
- **THEN** 系统 MUST 将 `_fail_count` 重置为 0

### Requirement: build_tool_kwargs 自动注入

`build_tool_kwargs()` MUST 根据目标函数的参数签名自动注入 `ToolContext` 实例（当签名包含 `ctx` 参数时）或 `ToolCDPHelpers` 实例（当签名包含 `cdp_helpers` 但不含 `ctx` 时）。

#### Scenario: 函数签名包含 ctx 参数
- **WHEN** 目标函数签名包含 `ctx` 参数且 cdp_helpers 可用
- **THEN** 系统 MUST 构造 `ToolContext(bridge=bridge, allowed_domains=allowed_domains)` 并注入为 `ctx` 参数
