## ADDED Requirements

### Requirement: 渐进快照元素收集黑名单
`_is_interactive_progressive` 函数 MUST 采用黑名单策略：默认收集所有 DOM 元素，仅排除 `_NON_INTERACTIVE_TAGS` 中定义的标签。`input[type=hidden]` 仍需单独排除。

#### Scenario: 黑名单标签被排除
- **WHEN** 遍历到 tag 为 `script`、`style`、`meta`、`link`、`br`、`hr`、`noscript`、`head`、`title`、`base`、`template`、`html`、`body` 的元素
- **THEN** `_is_interactive_progressive` 返回 `False`
- **AND** 该元素不被收集到 `elements_all`

#### Scenario: 非黑名单标签默认收集
- **WHEN** 遍历到 tag 不在 `_NON_INTERACTIVE_TAGS` 中的元素（如 `div`、`span`、`p`、`h1`、`section`、`img`、`form`）
- **THEN** `_is_interactive_progressive` 返回 `True`
- **AND** 该元素被收集到 `elements_all`（前提是满足 `nodeType==1`）

#### Scenario: input hidden 排除
- **WHEN** 遍历到 `input` 元素且 `type` 属性为 `hidden`
- **THEN** `_is_interactive_progressive` 返回 `False`
- **AND** 该元素不被收集

#### Scenario: a 标签无 href 仍收集
- **WHEN** 遍历到 `a` 标签且无 `href` 属性
- **THEN** `_is_interactive_progressive` 返回 `True`（不再因缺少 href 而排除）

#### Scenario: 启发式属性不再特殊处理
- **WHEN** 遍历到带有 `onclick`、`tabindex`、`contenteditable` 或 `data-v-`/`data-react-` 前缀属性的元素
- **THEN** 这些属性不产生额外的收集行为
- **AND** 元素是否被收集仅取决于是否在 `_NON_INTERACTIVE_TAGS` 黑名单中
- **AND** `_is_interactive_progressive` 函数不包含对这些属性的检测逻辑

### Requirement: 子节点跳过机制
`CollectState.walk()` MUST 在遍历 `_SKIP_CHILDREN_TAGS` 中定义的标签时，不递归遍历其子节点。节点本身仍正常收集。

#### Scenario: svg 子节点跳过
- **WHEN** 遍历到 `svg` 元素
- **THEN** `svg` 元素本身被收集（包含其属性如 aria-label、role、class）
- **AND** 不遍历 `svg` 内部的 `path`、`circle`、`rect`、`g`、`defs` 等子节点

#### Scenario: canvas 子节点跳过
- **WHEN** 遍历到 `canvas` 元素
- **THEN** `canvas` 元素本身被收集
- **AND** 不遍历 `canvas` 内部的子节点

#### Scenario: 非跳过标签正常递归
- **WHEN** 遍历到 tag 不在 `_SKIP_CHILDREN_TAGS` 中的元素（如 `div`、`ul`、`form`）
- **THEN** 正常递归遍历其所有子节点
- **AND** nth-of-type 计数器正常工作

### Requirement: _whitelist 标志位不变
`_ALWAYS_FULL_TAGS` 和 `_ALWAYS_FULL_ROLES` 常量 MUST 保留不变，继续用于设置元素的 `_whitelist` 标志位，影响密度折叠时的优先级排序。

#### Scenario: 交互标签设置 whitelist
- **WHEN** 收集到 tag 在 `_ALWAYS_FULL_TAGS` 中或 role 在 `_ALWAYS_FULL_ROLES` 中的元素
- **THEN** 该元素的 `_whitelist` 为 `True`
- **AND** 密度折叠时该元素优先保留

#### Scenario: 非交互标签不设置 whitelist
- **WHEN** 收集到 tag 不在 `_ALWAYS_FULL_TAGS` 中且 role 不在 `_ALWAYS_FULL_ROLES` 中的元素（如 `div`、`p`、`h1`）
- **THEN** 该元素的 `_whitelist` 为 `False`
- **AND** 密度折叠时该元素不优先保留
