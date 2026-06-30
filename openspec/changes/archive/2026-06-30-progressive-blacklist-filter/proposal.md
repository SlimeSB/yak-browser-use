## Why

渐进快照（progressive snapshot）的 `_is_interactive_progressive` 函数目前采用白名单机制：只有特定标签（button、input、select 等）、特定 ARIA role、或带有 onclick/tabindex/contenteditable 等属性的元素才会被收集并呈现给 LLM。这导致两个问题：

1. **假阴性**：大量有意义的页面结构元素（段落、标题、图片、表单容器等）被过滤掉，LLM 无法感知页面全貌，影响对页面布局和上下文的理解。
2. **维护负担**：白名单机制需要维护多层启发式规则（`_ALWAYS_FULL_TAGS`、`_ALWAYS_FULL_ROLES`、onclick/tabindex/contenteditable 检测、React/Vue data- 属性检测），逻辑复杂且容易遗漏。

由于渐进快照已有密度折叠（density folding）和 `MAX_LLM_ELEMENTS=200` 上限保护 token 预算，白名单过滤变得多余——应该让密度折叠机制负责控制输出规模，而非在收集阶段就排除元素。

## What Changes

- **修改** `_is_interactive_progressive` 函数：从白名单反转为黑名单，默认收集所有元素，仅排除明确非交互的标签。
- **新增** `_NON_INTERACTIVE_TAGS` frozenset：定义应被排除的标签（script、style、meta、link、br、hr、noscript、head、title、base、template、html、body）。
- **新增** `_SKIP_CHILDREN_TAGS` frozenset：定义应收集自身但不递归子节点的标签（svg、canvas），避免展开大量无意义的内部子元素。
- **删除** onclick/tabindex/contenteditable 启发式检测（黑名单机制下已冗余）。
- **删除** React/Vue data- 属性启发式检测（黑名单机制下已冗余）。
- **修改** 相关单元测试以适配新的收集行为。

## Capabilities

### Modified Capabilities

- `progressive-snapshot`: 渐进快照的元素收集策略从白名单改为黑名单，扩大 LLM 对页面结构的可见范围。

## Impact

- **受影响文件**：`backend/src/yak_browser_use/cdp/playwright_bridge.py`（核心逻辑）、`backend/tests/test_progressive.py`（测试）
- **不影响**：`build_llm_view`、`MAX_LLM_ELEMENTS`、密度折叠逻辑、`_ALWAYS_FULL_TAGS`/`_ALWAYS_FULL_ROLES`（仍用于 `_whitelist` 标志位）、高亮系统
- **行为变化**：`elements_all` 列表显著增大（从数十到数千），密度折叠将更频繁触发；LLM 视图包含更多页面结构信息
- **性能**：遍历阶段内存占用增加（数 MB 级别），`build_llm_view` 处理时间增加
