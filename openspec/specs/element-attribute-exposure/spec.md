### Requirement: progressive 模式元素暴露交互状态属性

`_progressive_snapshot` 返回的元素数据 MUST 包含元素的交互状态属性和语义属性，使 LLM 可以判断元素是否可交互、获取元素附加信息。

#### Scenario: 按钮暴露 disabled 状态

- **WHEN** 页面中存在 `<button disabled>Submit</button>`
- **THEN** 该元素在 progressive snapshot 结果中包含 `"disabled": true`

#### Scenario: 下拉按钮暴露展开状态

- **WHEN** 页面中存在 `<button aria-expanded="false">Menu</button>`
- **THEN** 该元素在 progressive snapshot 结果中包含 `"aria_expanded": "false"`

#### Scenario: 探索模式不暴露隐藏状态

- **WHEN** 页面中存在 `<button hidden>Hidden Button</button>`
- **AND** snapshot 调用时未传 `query` 参数（探索模式）
- **THEN** 该元素在 progressive snapshot 结果中不包含 `hidden` 和 `aria_hidden` 字段

#### Scenario: 搜索模式暴露隐藏状态

- **WHEN** 页面中存在 `<button hidden>Hidden Button</button>`
- **AND** snapshot 调用时传入了 `query` 参数（搜索模式，无论 query 内容是什么）
- **THEN** 该元素在 progressive snapshot 结果中包含 `"hidden": true`

#### Scenario: aria-hidden 在探索模式不暴露

- **WHEN** 页面中存在 `<button aria-hidden="true">Invisible</button>`
- **AND** snapshot 调用时未传 `query` 参数（探索模式）
- **THEN** 该元素在 progressive snapshot 结果中不包含 `hidden` 和 `aria_hidden` 字段

#### Scenario: aria-hidden 在搜索模式暴露

- **WHEN** 页面中存在 `<button aria-hidden="true">Invisible</button>`
- **AND** snapshot 调用时传入了 `query` 参数（搜索模式）
- **THEN** 该元素在 progressive snapshot 结果中包含 `"aria_hidden": "true"`

#### Scenario: 条件写入——无属性时不写 key

- **WHEN** 页面中存在 `<button>Plain Button</button>`（无 disabled、aria-expanded 等属性）
- **THEN** 该元素在 progressive snapshot 结果中不包含 `disabled`、`aria_expanded` 等不存在属性的 key

#### Scenario: 只读和必填输入框暴露状态

- **WHEN** 页面中存在 `<input readonly required placeholder="Name">`
- **THEN** 该元素在 progressive snapshot 结果中包含 `"readonly": true`、`"required": true`、`"placeholder": "Name"`

#### Scenario: 链接暴露 href

- **WHEN** 页面中存在 `<a href="/login">Login</a>`
- **THEN** 该元素在 progressive snapshot 结果中包含 `"href": "/login"`
- **AND** 非 `<a>` 标签不包含 `href` 字段

#### Scenario: 输入框暴露 type 和 value

- **WHEN** 页面中存在 `<input type="email" value="user@test.com">`
- **THEN** 该元素在 progressive snapshot 结果中包含 `"type": "email"`、`"value": "user@test.com"`

#### Scenario: 元素暴露 aria_label

- **WHEN** 页面中存在 `<button aria-label="Close dialog">X</button>`
- **THEN** 该元素在 progressive snapshot 结果中包含 `"aria_label": "Close dialog"`

### Requirement: a11y 模式元素数据补齐 AX 属性

`a11y_snapshot` 返回的元素数据 MUST 包含 `expanded`、`haspopup`、`pressed`、`selected`、`hidden` 属性，且 `checked`、`disabled` 的值 MUST 使用 `_ax_value()` 统一提取。

#### Scenario: a11y 元素暴露 disabled 状态

- **WHEN** 页面中存在 `<button disabled>Submit</button>`
- **THEN** 该元素在 a11y snapshot 结果中包含 `"disabled": "true"`（字符串形式）

#### Scenario: a11y 元素暴露展开和弹出状态

- **WHEN** 页面中存在 `<button aria-expanded="false" aria-haspopup="true">Menu</button>`
- **THEN** 该元素在 a11y snapshot 结果中包含 `"expanded": "false"` 和 `"haspopup": "true"`

#### Scenario: checked 和 disabled 使用 _ax_value 提取

- **WHEN** CDP `Accessibility.getFullAXTree` 返回 `checked: {"type":"boolean","value":true}`
- **THEN** `_flatten_cdp_ax_nodes` 提取出 `"checked": "true"`（字符串形式，非 dict 对象）
