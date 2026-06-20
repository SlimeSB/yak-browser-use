## ADDED Requirements

### Requirement: ToolContext 构造函数
ToolContext MUST 仅接受 `bridge` 和 `allowed_domains` 两个参数。

**Reason:** data ops 已移除（save_json/load_json/save_csv/load_csv/load_all_records/save_bytes），`input_files`/`output_dir`/`params` 不再需要。`CDP_BLOCKED_COMMANDS` 和 `DANGEROUS_MODULES` 仅被 `cdp()` 和 tool gen 使用，一并移除。

#### Scenario: ToolContext 构造
- **WHEN** 创建 `ToolContext(bridge=bridge, allowed_domains=["example.com"])`
- **THEN** `__init__` MUST 仅接受 `bridge` 和 `allowed_domains` 参数
- **AND** `CDP_BLOCKED_COMMANDS` 类属性 MUST NOT 存在
- **AND** `DANGEROUS_MODULES` 类属性 MUST NOT 存在
- **AND** `input_files`/`output_dir`/`params` 实例属性 MUST NOT 存在

### Requirement: ToolContext 浏览器操作方法
ToolContext MUST 提供七个浏览器操作方法，内部委托给 PlaywrightBridge 的实际方法。

#### Scenario: ctx.eval 执行 JavaScript
- **WHEN** 调用 `ctx.eval(js)`
- **THEN** 系统 MUST 先执行 domain whitelist 检查
- **AND** 系统 MUST 先执行 circuit breaker 检查
- **AND** 系统 MUST 调用 `bridge.evaluate(js)` 并返回结果
- **AND** 成功时 MUST 重置 fail_count 为 0
- **AND** 失败时 MUST 递增 fail_count 并抛出异常

#### Scenario: ctx.type 输入文本
- **WHEN** 调用 `ctx.type(selector, text)`
- **THEN** 系统 MUST 先执行 domain whitelist 检查
- **AND** 系统 MUST 先执行 circuit breaker 检查
- **AND** 系统 MUST 调用 `bridge.fill(selector, text)` 并返回结果

#### Scenario: ctx.click 点击元素
- **WHEN** 调用 `ctx.click(selector, click_count=1)`
- **THEN** 系统 MUST 先执行 domain whitelist 检查
- **AND** 系统 MUST 先执行 circuit breaker 检查
- **AND** 系统 MUST 调用 `bridge.click(selector, click_count=click_count)` 并返回结果

#### Scenario: ctx.snapshot 获取页面快照
- **WHEN** 调用 `ctx.snapshot(mode="simplified")`
- **THEN** 系统 MUST 根据 mode 参数路由到 bridge 的不同方法
- **AND** mode="simplified" 时 MUST 调用 `bridge.simplified_snapshot()`
- **AND** mode="interactive" 时 MUST 调用 `bridge.simplify_dom()`
- **AND** mode="full" 时 MUST 调用 `bridge.capture_snapshot()`

#### Scenario: ctx.wait 等待
- **WHEN** 调用 `ctx.wait(seconds)`
- **THEN** 系统 MUST 执行 `asyncio.sleep(seconds)`
- **AND** 该操作 MUST NOT 受 circuit breaker 影响

#### Scenario: ctx.screenshot 截图
- **WHEN** 调用 `ctx.screenshot()`
- **THEN** 系统 MUST 调用 `bridge.screenshot()` 并返回 base64 PNG 字符串

#### Scenario: ctx.source 获取 HTML
- **WHEN** 调用 `ctx.source()`
- **THEN** 系统 MUST 调用 `bridge.source()` 并返回完整 HTML 字符串

### Requirement: ToolContext 安全机制
ToolContext MUST 提供 domain whitelist 和 circuit breaker 两种安全机制。

#### Scenario: domain whitelist 检查通过
- **WHEN** `_allowed_domains` 不为空且当前页面 hostname 在列表中
- **THEN** 操作 MUST 正常执行

#### Scenario: domain whitelist 检查拒绝
- **WHEN** `_allowed_domains` 不为空且当前页面 hostname 不在列表中
- **THEN** 系统 MUST 抛出 SafetyViolation 异常

#### Scenario: domain whitelist 为空时放行
- **WHEN** `_allowed_domains` 为空或 None
- **THEN** 系统 MUST 跳过 domain 检查，允许所有域名

#### Scenario: circuit breaker 触发
- **WHEN** `_fail_count` 达到 `_MAX_CONSECUTIVE_FAILURES`（3）
- **THEN** 系统 MUST 抛出 SafetyViolation 异常
- **AND** 后续所有受保护操作 MUST 继续抛出异常

#### Scenario: circuit breaker 重置
- **WHEN** 受保护操作执行成功
- **THEN** 系统 MUST 将 `_fail_count` 重置为 0

### Requirement: build_tool_kwargs 自动注入
`build_tool_kwargs()` MUST 根据目标函数的参数签名自动注入 ToolContext 实例。

#### Scenario: 函数签名包含 ctx 参数
- **WHEN** 目标函数签名包含 `ctx` 参数且 cdp_helpers 可用
- **THEN** 系统 MUST 构造 `ToolContext(bridge=bridge, allowed_domains=allowed_domains)` 并注入为 `ctx` 参数
- **AND** bridge MUST 通过 `getattr(cdp_helpers, "bridge", None) or getattr(cdp_helpers, "_bridge", cdp_helpers)` 提取

#### Scenario: 函数签名包含 cdp_helpers 参数但不含 ctx
- **WHEN** 目标函数签名包含 `cdp_helpers` 但不含 `ctx`
- **THEN** 系统 MUST 构造 `ToolCDPHelpers(bridge)` 注入为 `cdp_helpers`（兼容旧工具）

### Requirement: test_ops.py 适配
从 toolgen-test 分支 cherry-pick 的 `test_ops.py` MUST 适配精简后的 ToolContext API。

#### Scenario: fixture 更新
- **WHEN** 测试创建 ToolContext 实例
- **THEN** fixture MUST 使用 `ToolContext(bridge=bridge)` 而非 `ToolContext(bridge, input_files, output_dir, params)`

#### Scenario: 方法名更新
- **WHEN** 测试调用 ToolContext 方法
- **THEN** `ctx.evaluate(js)` MUST 改为 `ctx.eval(js)`
- **AND** `ctx.fill(selector, text)` MUST 改为 `ctx.type(selector, text)`

#### Scenario: 删除 data ops 测试
- **WHEN** 检查 `test_ops.py` 的测试列表
- **THEN** `test_save_json`、`test_load_json`、`test_load_json_missing`、`test_save_csv`、`test_load_csv`、`test_save_bytes` MUST NOT 存在

#### Scenario: 删除 cdp escape hatch 测试
- **WHEN** 检查 `test_ops.py` 的测试列表
- **THEN** `test_cdp`、`test_cdp_page_none` MUST NOT 存在

#### Scenario: 删除 DANGEROUS_MODULES 测试
- **WHEN** 检查 `test_ops.py` 的测试列表
- **THEN** `test_dangerous_modules_is_frozenset`、`test_dangerous_modules_contains_expected` MUST NOT 存在
