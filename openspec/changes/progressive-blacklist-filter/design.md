## 背景

渐进快照（progressive snapshot）是 yak-browser-use 三种快照策略之一，通过 CDP DOM 深度遍历 + 密度自适应折叠为 LLM 提供页面结构视图。当前实现中，`_is_interactive_progressive` 函数采用白名单机制决定哪些 DOM 元素被收集：

```
_is_interactive_progressive(tag, attrs):
    if tag in _ALWAYS_FULL_TAGS (15 tags) → True
    if role in _ALWAYS_FULL_ROLES (17 roles) → True
    if onclick/tabindex/contenteditable → True
    if div/span/li with data-v-/data-react- → True
    else → False
```

白名单导致纯结构元素（`<p>`、`<h1>`-`<h6>`、`<img>`、`<section>`、`<article>`、`<form>` 等）被排除，LLM 无法感知页面完整结构。

与此同时，`build_llm_view` 已实现密度折叠（density folding）和 `MAX_LLM_ELEMENTS=200` 上限，可以有效控制输出规模。白名单过滤在已有安全网的情况下变得多余。

## 目标 / 非目标

**目标：**
- 将 `_is_interactive_progressive` 从白名单反转为黑名单，扩大 LLM 可见元素范围
- 删除冗余的启发式规则（onclick/tabindex/contenteditable、data-v-/data-react-）
- 新增 `_SKIP_CHILDREN_TAGS` 机制，对 svg/canvas 等元素跳过子节点遍历

**非目标：**
- 不改变 `build_llm_view` 的密度折叠逻辑
- 不改变 `MAX_LLM_ELEMENTS=200` 上限
- 不改变 `_ALWAYS_FULL_TAGS` / `_ALWAYS_FULL_ROLES`（仍用于 `_whitelist` 标志位）
- 不改变高亮系统
- 不改变 aria 快照或 a11y 快照

## 关键决策

### 决策 1：黑名单而非扩白名单

**方案 A（扩展白名单）**：在 `_ALWAYS_FULL_TAGS` 中追加 p、h1-h6、img、section、article、form 等标签。

**方案 B（黑名单）**：默认收集所有元素，仅排除明确非交互的标签。

**选择方案 B**。理由：
- 白名单永远无法穷尽所有有意义的标签（自定义元素、未来 HTML 标签等）
- 黑名单是有限闭集——需要排除的标签极少
- 密度折叠机制已提供足够的安全网
- 代码更简洁，语义更清晰

### 决策 2：黑名单标签选择

```
_NON_INTERACTIVE_TAGS = frozenset({
    "script", "style", "meta", "link", "br", "hr", "noscript",
    "head", "title", "base", "template",
    "html", "body",
})
```

- `script`/`style`：纯代码，无视觉呈现
- `meta`/`link`/`base`/`title`：head 内元数据
- `br`/`hr`：纯排版元素，无交互
- `noscript`/`template`：不渲染的内容
- `head`：容器，本身无交互
- `html`/`body`：根元素，LLM 无需作为交互目标；body 已被容器机制捕获

### 决策 3：`_SKIP_CHILDREN_TAGS` 机制

```
_SKIP_CHILDREN_TAGS = frozenset({"svg", "canvas"})
```

在 `CollectState.walk()` 中，如果当前节点的 tag 在 `_SKIP_CHILDREN_TAGS` 中，则不递归遍历其子节点。节点本身仍被收集为元素（LLM 知道它存在），但内部图形原语（path、circle、rect 等）被跳过。

**备选方案**：将 path/circle/rect/g/defs 等加入 `_NON_INTERACTIVE_TAGS`。不选择此方案，因为需要维护 20+ 个 SVG 子标签，且仍需遍历子节点再判断。

### 决策 4：保留 input[type=hidden] 排除

`_is_interactive_progressive` 中保留 `input[type=hidden]` 的排除逻辑，因为隐藏输入字段对 LLM 无意义。

### 决策 5：`_whitelist` 标志位不变

`_ALWAYS_FULL_TAGS` 和 `_ALWAYS_FULL_ROLES` 保持不变，继续用于设置 `_whitelist` 标志位，影响密度折叠时的优先级排序。这实现了关注点分离：
- `_is_interactive_progressive`：决定"是否收集"（几乎全收）
- `_whitelist`：决定"是否优先"（仅交互元素优先）

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| `elements_all` 膨胀 | 遍历阶段内存增加数 MB | 普通页面数 MB 级别，可接受 |
| 密度折叠更频繁触发 | LLM 视图结构变化 | 这正是预期行为，折叠机制本身设计就是为此 |
| 容器统计值变大 | `total_descendants` 包含非交互元素 | 密度阈值 `DENSITY_THRESHOLD=50` 仍然适用 |
| LLM 提示词中提到"interactive elements" | 语义不一致 | 函数名保留（内部实现细节），LLM 提示词如需调整可在后续 change 中处理 |

## 迁移计划

1. 修改 `_is_interactive_progressive` 函数
2. 新增 `_NON_INTERACTIVE_TAGS` 和 `_SKIP_CHILDREN_TAGS` 常量
3. 修改 `CollectState.walk()` 添加子节点跳过逻辑
4. 更新 `test_progressive.py` 中的受影响测试
5. 运行完整测试套件验证
6. 回滚方案：git revert，无数据迁移需求

## 待确认问题

- 无。方案已在探索阶段充分讨论。
