## 背景

当前 `browser_snapshot(mode="interactive")` 返回的元素编号 `@e1` ~ `@e50` 由 `simplify-dom.js` 在 JS 侧按视口可见顺序自增分配。每次调用 `simplifyDom()` 都会重新扫描 DOM、重新编号，因此：

- 滚动后同一元素的编号必然改变
- 页面 DOM 变化后编号可能改变
- `@eN` 本身无语义，LLM 无法跨 turn 记忆

现有 `_element_map` 设计为临时缓存，每次 `add_dom_highlights()` 都会清空重建（`helpers.py:210`）。`remove_dom_highlights()` 也会清空（`helpers.py:303`）。

**约束**：
- `simplify-dom.js` 运行在浏览器沙箱中，无法直接访问 CDP 的 `backendNodeId`
- 所有 CDP 调用通过 `_cdp()` 方法走 WebSocket 往返
- `CDPHelpers` 被多个调用方使用：chat 模式（`tool_executor`）、preset 模式（`executor`）、CLI（`chrome.py`）、工具（`tool_cdp.py`）

## 目标 / 非目标

**目标：**
- 提供基于 CDP `backendNodeId` 的持久化元素编号方案（`@e_XXXXX`）
- 通过 `use_stable_refs` 开关控制新旧模式，默认关闭保证零行为变化
- 滚动后同一元素编号不变，LLM 可跨 turn 引用
- 页面导航（`browser_goto`）后自动清空映射
- 修复新模式下的所有边界问题（MutationObserver、ref 归一化、simplified snapshot 污染等）

**非目标：**
- 不修改 `simplify-dom.js`
- 不优化 CDP 调用批量性能（v1 串行即可）
- 不实现 SPA 路由变化的自动检测
- 不改变 `browser_get_element_by_number` 的工具名

## 关键决策

### 决策 1：使用 CDP `DOM.querySelector` + `DOM.describeNode` 获取 backendNodeId

**方案**：对每个 JS scan 返回的元素，用其 `selector` 字段调 `DOM.querySelector` 获取 `nodeId`，再调 `DOM.describeNode` 获取 `backendNodeId`。

**备选方案**：
- 在 JS 侧通过 `Runtime.evaluate` 获取 backendNodeId：不可行，JS 沙箱无法访问 CDP 内部 ID
- 用 `DOM.querySelectorAll` 按 tag 批量获取：v2 优化，v1 串行即可

**取舍**：50 个元素 × 2 次 CDP 调用 ≈ 100 次 WebSocket 往返，localhost 下约 500ms-1s。可接受。

### 决策 2：`_ref_map` 持久化策略

**旧模式**：`_element_map` 每次 `add_dom_highlights()` 清空重建。

**新模式**：`_ref_map` 页面内持久。`add_dom_highlights()` 时：
- 已存在的 key（`@e_XXXXX`）保留，仅更新位置信息
- 新进入视口的元素新增 key
- 不再出现在视口的元素不移除（LLM 可能仍持有引用）

`reset_ref_map()` 仅在 `browser_goto` 时调用。

### 决策 3：MutationObserver 处理

`add_dom_highlights()` 注入的 JS 中包含 MutationObserver，DOM 变化时调用 `simplifyDom()` 重绘高亮。但 `simplifyDom()` 生成的是 `@e1..@eN` 顺序 ref，与 `_ref_map` 中的 `@e_XXXXX` 不匹配。

**方案**：新模式禁用 MutationObserver 和 ResizeObserver。高亮仅在显式调用 `add_dom_highlights()` 时刷新（goto/click/fill/scroll 后自动触发）。

### 决策 4：ref 归一化兼容

**旧格式**：`@e3`、`e3`、`3` → 归一化为 `@e3`

**新格式**：`@e_12345`、`e_12345`、`12345` → 归一化为 `@e_12345`

修改 `get_element_by_index()` 和 `_normalize_ref()` 的归一化逻辑：优先尝试 `@e_XXXXX` 格式匹配，回退到旧 `@eN` 格式。

### 决策 5：`capture_snapshot_simplified` 不触发 highlight

当前 `capture_snapshot_simplified()` 调用 `add_dom_highlights()` 不传 elements，会触发 JS scan 拿到 `@e1..@eN` 顺序 ref，污染持久化映射。

**方案**：新模式跳过此调用。simplified 模式不需要元素编号。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| CDP selector 匹配失败 | 元素无法获取 backendNodeId，降级为 `@e_unknown` | `buildSelector()` 优先用 id，大部分场景够用；v2 可加位置匹配回退 |
| CDP 调用耗时 | 每次 snapshot 增加 ~500ms-1s | 可接受；v2 按 tag 分组批量查询 |
| SPA 路由切换不重置映射 | 旧 ref 指向已销毁的 DOM 节点 | LLM 引用时 `get_element_by_index` 返回 not found，自然失效 |
| 旧模式 `_element_map` 与新 `_ref_map` 命名混淆 | 代码可读性 | 用 `use_stable_refs` 分支隔离，旧路径完全不动 |

## 迁移计划

1. **上线**：`use_stable_refs` 默认 `False`，用户无感知
2. **启用**：通过构造函数参数传入 `use_stable_refs=True`
3. **回滚**：将参数改回 `False` 即可，零数据迁移
4. **后续**：确认稳定后可改为默认 `True`，移除旧代码路径

## 待确认问题

- 无。所有技术决策已在 review 中确认。
