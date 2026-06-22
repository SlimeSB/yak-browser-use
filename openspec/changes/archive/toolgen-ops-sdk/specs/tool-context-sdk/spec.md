## ADDED Requirements

### Requirement: ToolContext 浏览器操作封装

`ToolContext` MUST 提供对 `PlaywrightBridge` 的受控封装，暴露以下浏览器操作方法，每个方法在失败时递增内部熔断计数器：

- `await ctx.wait(seconds: float) -> None` — 等待指定秒数（直接调用 `asyncio.sleep`，不通过 `PlaywrightBridge.wait`；不参与熔断器计数）
- `await ctx.evaluate(js: str) -> Any` — 在页面中执行 JavaScript 并返回结果（封装 `PlaywrightBridge.evaluate`）
- `await ctx.click(selector: str, click_count: int = 1) -> dict` — 点击匹配 CSS 选择器的元素，`click_count=2` 支持双击，返回 `{"selector": selector}`（封装 `PlaywrightBridge.click`，返回值透传）
- `await ctx.fill(selector: str, text: str) -> dict` — 向匹配 CSS 选择器的输入框填入文本，返回 `{"selector": selector}`（封装 `PlaywrightBridge.fill`，返回值透传）
- `await ctx.snapshot(mode: str = "full", query: str = "", in_viewport: bool = False) -> dict` — 获取页面快照，mode 支持 `"interactive"`（可交互元素，调 `simplify_dom`）、`"simplified"`（简化版，调 `simplified_snapshot`）、`"full"`（完整 DOM，调 `capture_snapshot`，默认值）。`query` 和 `in_viewport` 仅在 `mode="interactive"` 时生效。不同 mode 返回不同结构的 dict
- `await ctx.screenshot() -> str` — 截取当前页面视口截图，返回 base64 编码字符串（封装 `PlaywrightBridge.screenshot`）
- `await ctx.source() -> str` — 获取当前页面完整 HTML 源码

#### Scenario: 浏览器操作成功执行
- **WHEN** 调用 `ctx.click("#submit-btn")`
- **THEN** 系统通过 `PlaywrightBridge.click` 执行点击操作，熔断计数器重置为 0

#### Scenario: bridge.page 为 None 时拒绝操作
- **WHEN** 在 `bridge.start()` 调用前创建 `ToolContext` 并调用任何浏览器操作（`evaluate`/`click`/`fill`/`snapshot`/`screenshot`/`source`/`cdp`）
- **THEN** 系统抛出 `RuntimeError("ToolContext: bridge.page is None, call bridge.start() first")`

#### Scenario: 浏览器操作连续失败触发熔断
- **WHEN** 连续 3 次浏览器操作（如 `ctx.click`）抛出异常
- **THEN** 第 4 次调用时系统抛出 `RuntimeError("ToolContext circuit breaker: 3 consecutive failures")`

### Requirement: ToolContext 数据操作封装

`ToolContext` MUST 提供文件 I/O 的数据操作方法，所有路径基于 `output_dir` 解析：

- `await ctx.save_json(data, name: str = "output.json") -> str` — 将数据保存为 JSON 文件，返回文件路径
- `await ctx.load_json(name: str) -> Any` — 从 `input_files` 中加载 JSON 文件
- `await ctx.save_csv(records: list[dict], name: str = "output.csv") -> str` — 将记录列表保存为 CSV 文件，返回文件路径
- `await ctx.load_csv(name: str) -> list[dict]` — 从 `input_files` 中加载 CSV 文件
- `await ctx.save_bytes(data: bytes, name: str = "output.bin") -> str` — 将字节数据保存为文件，返回文件路径

#### Scenario: 保存 JSON 数据
- **WHEN** 调用 `await ctx.save_json({"rows": [...]}, "table.json")`
- **THEN** 系统在 `output_dir/table.json` 创建文件，内容为格式化的 JSON，返回完整路径

#### Scenario: 加载已存在的 JSON 文件
- **WHEN** 调用 `await ctx.load_json("input.json")` 且 `input_files` 中包含该 key
- **THEN** 系统读取对应路径的文件并解析为 Python 对象返回

### Requirement: ToolContext CDP 逃逸口

`ToolContext` MUST 提供 `await ctx.cdp(cmd: str, params: dict = {}) -> dict` 方法，允许在 ops 不够用时直接发送 CDP 命令。该方法通过 `bridge._context.new_cdp_session(bridge.page)` 创建临时 CDP session 发送命令后立即 detach，同样受域名白名单和熔断器约束。

> **实现说明**：`PlaywrightBridge` 当前没有公开的 CDP session 方法（`new_cdp_session` 仅在 `simplify_dom` 内部使用）。`ToolContext.cdp()` 需要通过 `bridge.page`（公开属性）和 `bridge._context`（私有属性）创建临时 CDP session。如果 `bridge.page` 为 `None`（`start()` 未调用），应抛出 `RuntimeError`。

#### Scenario: 通过 CDP 逃逸口执行自定义命令
- **WHEN** 调用 `await ctx.cdp("Page.captureScreenshot", {"format": "png"})`
- **THEN** 系统通过 `PlaywrightBridge` 新建 CDP session 发送命令并返回结果

### Requirement: ToolContext 域名白名单

`ToolContext` MUST 支持通过 `allowed_domains` 参数限制浏览器操作的目标域名。当 `allowed_domains` 为 `None` 或空列表时不限制域名。域名检查通过 `bridge.page.url` 获取当前页面 URL 并解析 hostname 进行比对。

> **实现说明**：现有 `ToolCDPHelpers` 接受 `allowed_domains` 参数但从未实际检查（`tool_cdp.py:31`）。`ToolContext` 需要实现真正的域名校验逻辑。

#### Scenario: 域名白名单限制生效
- **WHEN** 创建 `ToolContext(bridge, ..., allowed_domains=["example.com"])` 后调用 `ctx.evaluate("document.title")` 且当前页面域名为 `other.com`
- **THEN** 系统拒绝操作并抛出异常

#### Scenario: 无域名限制
- **WHEN** 创建 `ToolContext(bridge, ..., allowed_domains=None)` 后调用 `ctx.evaluate("document.title")` 且当前页面域名为 `any.com`
- **THEN** 系统正常执行操作

### Requirement: ToolContext 初始化参数

`ToolContext` 的构造函数 MUST 接受以下参数：
- `bridge`: `PlaywrightBridge` 实例
- `input_files: dict[str, str]`: 输入文件映射（key → 路径）
- `output_dir: str`: 输出目录路径
- `params: dict`: 步骤参数
- `allowed_domains: list[str] | None`: 可选域名白名单，默认 `None`

#### Scenario: ToolContext 正确初始化
- **WHEN** 调用 `ToolContext(bridge, {"input": "/path/to/file.json"}, "/output/dir", {"key": "value"})`
- **THEN** 系统创建 ToolContext 实例，`input_files`、`output_dir`、`params` 属性正确设置
