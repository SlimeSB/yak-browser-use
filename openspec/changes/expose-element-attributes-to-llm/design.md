## 背景

当前 `_progressive_snapshot` 返回给 LLM 的元素数据只包含 `tag`、`text`、`role`、`selector`、`prog_label` 五个字段。`CollectState.walk()` 在收集元素时通过 `_node_attrs(node)` 拿到了完整的 HTML 属性，但只用于 `_is_interactive_progressive` 判断和 text 提取，其余信息全部丢弃。

`a11y_snapshot` 虽然暴露了 `disabled` 和 `checked`，但 CDP `Accessibility.getFullAXTree` 在电商等复杂页面性能极差（需要序列化整棵 AX 树），实际使用中经常超时或不可用。progressive 模式是主力，但缺乏属性信息。

`query` 参数当前在 progressive 模式只匹配 `text`/`tag`/`role`/`ref`，在 a11y 模式只匹配 `name`/`role`，LLM 无法按属性搜索元素。

## 目标 / 非目标

**目标：**
- progressive 模式元素数据暴露交互状态属性（`disabled`、`aria-expanded`、`aria-hidden` 等）和语义属性（`type`、`placeholder`、`href` 等）
- `query` 参数支持按属性值搜索（`query="disabled"` 匹配禁用元素）
- `hidden`/`aria_hidden` 探索模式（无 query）不暴露，搜索模式（有 query）始终暴露
- a11y 模式补齐 `expanded`/`haspopup` 等 CDP AX 属性，修复 `checked`/`disabled` 的 `_ax_value()` 提取问题
- 条件写入：属性不存在时不写 key，控制 token 成本

**非目标：**
- 不引入元素评分/排序系统（独立变更）
- 不预过滤 `hidden`/`disabled` 元素（仅暴露数据，由 LLM 决策）
- 不修改 aria_snapshot 或 capture_snapshot（它们不支持 query）
- 不修改前端或 API 接口

## 关键决策

### 1. 条件写入 vs 总是写入

**决策**：条件写入（有值才写 key）。

**原因**：电商页面 200 个交互元素，总是写入 `disabled: false` 等会给每个元素增加 ~10 个 key。条件写入预计只增加 ~3-4 个 key/元素，token 膨胀约 50%，可接受。

### 2. hidden 探索隐藏、搜索暴露

**决策**：`hidden` 和 `aria_hidden` 在 `CollectState.walk()` 中正常写入，但在 `public_elements` 输出阶段条件剥离——探索模式（无 query）不暴露，搜索模式（有 query）始终暴露，与 query 内容无关。

**原因**：探索时隐藏元素通常不关心，搜索时 LLM 需要看到完整信息做决策。有 query 即表示 LLM 在主动查找，应给予全部数据。

**实现**：
```python
show_hidden = query is not None
# public 输出时跳过 hidden/aria_hidden 当 show_hidden=False
```

### 3. query 匹配改为通用遍历

**决策**：将 progressive 的 query 匹配从固定 4 字段改为遍历所有非 `_` 前缀字段，先匹配 key 名再匹配 string 值。

**原因**：属性字段数量会增长（本次就新增 ~15 个），固定枚举不可维护。key 名匹配覆盖 `query="disabled"`（匹配含 `disabled` key 的元素）和 `query="aria-expanded"`（匹配含 `aria_expanded` key 的元素，无论值是 "true" 还是 "false"）。string 值匹配覆盖 `query="submit"`（匹配 `type: "submit"`）。

**匹配逻辑**：
```python
def _match(el: dict, q: str) -> bool:
    for k, v in el.items():
        if k.startswith("_"):
            continue
        if q in k.lower():       # key 名匹配
            return True
        if isinstance(v, str) and q in v.lower():  # string 值匹配
            return True
    return False
```

**Known tradeoff**：`disabled=False` 不可搜索（因为条件写入不写 False）。对当前需求足够。

### 4. a11y 属性提取用 `_ax_value()`

**决策**：`_flatten_cdp_ax_nodes` 中 `checked`/`disabled` 改用 `_ax_value()` 提取，新增属性也统一使用。

**原因**：CDP AX 树返回的是 `{"type":"boolean","value":true}` 对象，不是原始值。当前代码 `node.get("checked")` 拿到的可能是 dict 而非 bool，存在 bug。

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| Token 膨胀 ~50% | 条件写入 + hidden 默认不暴露；实测后可根据数据调整 |
| `disabled=False` 不可搜索 | Known tradeoff，spec 中明确说明 |
| `value` 与 `text` 字段重叠 | 两者语义不同（text 是可见标签，value 是原始值），spec 中说明 |
| `aria_label` 与 `text` 重叠 | `text` 的 fallback 链包含 `aria-label`，但 `aria_label` 是原始值，两者互补 |

## 迁移计划

1. 修改 `playwright_bridge.py` 中 4 个位置，无需数据迁移
2. 渐进上线：progressive 模式默认启用新字段，a11y 模式补齐属性
3. 回滚：直接 revert commit，无持久化副作用
4. 兼容性：仅新增字段，不修改或删除现有字段，无破坏性变更

## 待确认问题

- 暂无
