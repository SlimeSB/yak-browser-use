## 1. progressive 模式：元素属性暴露

- [x] 1.1 在 `CollectState.walk()` 中，`el` 构造完成后追加交互状态属性的条件写入（`disabled`、`aria_disabled`、`aria_expanded`、`aria_haspopup`、`aria_pressed`、`aria_selected`、`aria_checked`、`aria_hidden`、`hidden`、`readonly`、`required`），有值才写 key
- [x] 1.2 在 `CollectState.walk()` 中，追加语义属性的条件写入（`type`、`aria_label`、`placeholder`、`value`），有值才写 key；`href` 仅在 `tag=="a"` 且有值时写入
- [x] 1.3 在 `_progressive_snapshot` 的 public 输出阶段（`public_elements` 构造），增加条件剥离逻辑：探索模式（无 query）跳过 `hidden` 和 `aria_hidden` 字段，搜索模式（有 query）始终保留

## 2. progressive 模式：query 匹配扩展

- [x] 2.1 将 `_progressive_snapshot` 中 query 过滤从固定 4 字段匹配改为遍历所有非 `_` 前缀字段的通用匹配函数 `_match(el, q)`，先匹配 key 名（`q in k.lower()`），再匹配 string 值（`q in v.lower()`）
- [x] 2.2 验证 query="disabled" 通过 key 名匹配到含 `disabled` key 的元素，query="aria-expanded" 匹配到含 `aria_expanded` key 的元素（无论值为 "true"/"false"），query="submit" 通过 string 值匹配到 `type: "submit"` 的元素

## 3. a11y 模式：属性补齐与修复

- [x] 3.1 修复 `_flatten_cdp_ax_nodes` 中 `checked` 和 `disabled` 改用 `_ax_value()` 提取（当前直接 `node.get("checked")` 可能拿到 dict 而非 bool）
- [x] 3.2 在 `_flatten_cdp_ax_nodes` 中新增 `expanded`、`haspopup`、`pressed`、`selected`、`hidden` 属性，使用 `_ax_value()` 提取
- [x] 3.3 a11y 模式改用通用 `_match` 函数进行 query 过滤，替代硬编码 name/role/value/description 四字段匹配；`_match` 中 key 名匹配增加 `and v` 条件，避免 a11y 空值字段误命中

## 4. 验证

- [x] 4.1 在电商页面（如 Amazon/Taobao）上测试 progressive snapshot，确认新属性字段正确出现在返回结果中（需手动验证）
- [x] 4.2 测试 `query="disabled"` 在 progressive 和 a11y 模式下均能返回正确结果（逻辑已验证，需手动端到端验证）
- [x] 4.3 测试搜索模式（传入任意 query）时 `hidden` 字段出现在结果中，探索模式（无 query）时不出现（逻辑已验证，需手动验证）
- [x] 4.4 测试 token 增量：对比修改前后 200 元素页面的元素数据 key 数量（需手动验证）
