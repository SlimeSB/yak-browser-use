## ADDED Requirements

### Requirement: DOM 化简脚本注入
系统 MUST 提供 `assets/simplify-dom.js` 脚本，通过 CDP `Runtime.evaluate` 注入浏览器执行，支持 interactive 和 simplified 两种模式。

#### Scenario: interactive 模式执行
- **WHEN** 调用 `simplifyDom({ mode: "interactive" })`
- **THEN** 返回 JSON 对象包含 `mode: "interactive"` 和 `elements` 数组
- **AND** 每个元素包含 `ref`、`tag`、`type`、`text`、`selector` 字段

#### Scenario: simplified 模式执行
- **WHEN** 调用 `simplifyDom({ mode: "simplified" })`
- **THEN** 返回 JSON 对象包含 `mode: "simplified"`、`summary`、`lists`、`tables` 字段

#### Scenario: 可见性判断
- **WHEN** 元素 `offsetParent === null` 或 `getBoundingClientRect()` 返回的宽/高为 0
- **THEN** 该元素被视为不可见，不被包含在结果中

#### Scenario: 视口内判断
- **WHEN** 元素 `getBoundingClientRect()` 返回的位置完全在视口外
- **THEN** 该元素不被包含在 interactive 结果中

#### Scenario: 脚本不存在时的降级
- **WHEN** `assets/simplify-dom.js` 文件不存在或无法读取
- **THEN** `_inject_simplify_js()` 返回 None
- **AND** 调用方进入降级链的下一级（JS → full 两级降级链，AXTree 路径不在本 change 中实现）

#### Scenario: JS 执行异常时的降级
- **WHEN** `Runtime.evaluate` 执行 simplify-dom.js 时抛出异常
- **THEN** 捕获异常并返回 None
- **AND** 调用方进入降级链的下一级

### Requirement: CDP 注入方法
系统 MUST 在 `cdp/helpers.py` 中提供 `_inject_simplify_js(mode)` 方法，负责读取脚本文件并通过 CDP 注入执行。

#### Scenario: 成功注入并执行
- **WHEN** `_inject_simplify_js("interactive")` 被调用
- **THEN** 读取 `assets/simplify-dom.js` 内容
- **AND** 通过 `self.js()` 注入并执行
- **AND** 返回解析后的 JSON 结果

#### Scenario: 注入 simplified 模式
- **WHEN** `_inject_simplify_js("simplified")` 被调用
- **THEN** 注入的 JS 代码以 `simplifyDom({ mode: "simplified" })` 结尾
