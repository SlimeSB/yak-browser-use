## Why

当前 progressive snapshot 返回给 LLM 的元素数据只包含 `tag`、`text`、`role`、`selector`、`prog_label` 五个字段。元素的交互状态（`disabled`、`aria-expanded`、`aria-hidden` 等）完全不可见，导致 LLM 无法做出正确决策——例如点击一个 disabled 按钮、忽略一个 aria-expanded 的下拉菜单。同时，`query` 参数只匹配 `text`/`tag`/`role`/`ref` 四个字段，LLM 无法用 `query="disabled"` 搜索禁用的元素。

a11y 模式虽然暴露了 `disabled` 和 `checked`，但在电商等复杂页面性能极差（CDP `getFullAXTree` 序列化整棵 AX 树），实际使用中经常超时或不可用。因此需要以 progressive 模式为主力，补齐属性暴露能力。

## What Changes

- **新增**：`CollectState.walk()` 收集元素时，条件写入交互状态属性（`disabled`、`aria-expanded`、`aria-haspopup`、`aria-hidden`、`hidden`、`readonly`、`required` 等）和语义属性（`type`、`aria_label`、`placeholder`、`value`、`href`），有值才写以控制 token 成本。
- **新增**：`_progressive_snapshot` 的 `query` 参数从固定 4 字段匹配改为遍历所有 string 和 boolean 字段的通用匹配。
- **新增**：`hidden` 和 `aria_hidden` 字段探索模式（无 query）不暴露，搜索模式（有 query）始终暴露，与 query 内容无关。
- **修改**：`_flatten_cdp_ax_nodes` 中 `checked`/`disabled` 改用 `_ax_value()` 统一提取，并新增 `expanded`、`haspopup`、`pressed`、`selected`、`hidden` 属性。
- **修改**：`a11y_snapshot` 的 `query` 匹配改用通用 `_match` 函数（与 progressive 一致），替代原有硬编码字段匹配。

## Capabilities

### New Capabilities
- `element-attribute-exposure`: progressive snapshot 元素数据暴露交互状态属性（disabled、aria-expanded 等），LLM 可据此判断元素是否可交互。
- `snapshot-query-attributes`: `query` 参数支持按属性搜索，例如 `query="disabled"` 匹配所有禁用元素；搜索模式下 hidden 字段自动暴露。

### Modified Capabilities
- `a11y-snapshot`: 元素数据新增 `expanded`/`haspopup`/`pressed`/`selected`/`hidden` 属性；`query` 匹配从 2 字段扩展到 4 字段。

## Impact

- 受影响文件：`backend/src/yak_browser_use/cdp/playwright_bridge.py`（`CollectState.walk`、`_progressive_snapshot`、`_flatten_cdp_ax_nodes`、`a11y_snapshot`）
- 无 API 破坏性变更：元素数据新增字段，不删除或修改现有字段
- Token 成本：200 元素页面预计增加约 700 个 key（膨胀约 50%），可接受
- 不涉及前端、数据库、配置变更
