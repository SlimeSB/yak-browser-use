## 背景

当前系统已有 `simplify-dom.js` 用于扫描页面交互元素并生成 `@eN` 编号列表，以及 `cdp/helpers.py` 中的 `js()` 方法可执行 CDP `Runtime.evaluate` 注入任意 JS。但缺少将编号可视化渲染到浏览器页面的能力，用户无法直观看到哪些元素可交互、编号是多少。

browser-use 库的 `add_highlights()` 提供了参考样式（蓝色虚线框 + badge），但其编号体系使用 `backend_node_id`（大数字），不适合用户直接阅读。我们复用其视觉样式，但编号改用已有的 `@eN` 自增体系。

## 目标 / 非目标

**目标：**
- 在浏览器页面上注入可见的交互元素编号标签（蓝色虚线框 + 编号 badge）
- 编号使用 `@e1, @e2, ...` 自增格式，与 `simplify-dom.js` 体系一致
- Agent 可通过 `browser_get_element_by_number` 工具按编号查询元素信息
- 在 goto/click/fill 操作后自动刷新高亮，保持编号与页面同步
- chat 模式启动时异步注入首次高亮，不阻塞对话

**非目标：**
- 不处理 iframe 内元素的高亮
- 不处理 CSS `transform`/`filter`/`perspective` 导致的坐标偏移（极边缘情况）
- 不提供用户手动触发刷新的独立工具（后续按需添加）
- 不修改 `simplify-dom.js` 的扫描逻辑

## 关键决策

### 决策 1：编号体系 — 复用 `@eN`

直接使用 `simplify-dom.js` 的 `@e1, @e2, ...` 自增编号，不引入第二套编号。所有环节（DOM 高亮渲染、`browser_get_element_by_number` 查询、`_resolve_element_ref` 解析）共用同一编号。

**备选方案**：使用 browser-use 的 `backend_node_id`。被否决，因为数字太大（如 `2147483647`），用户难以阅读和输入。

### 决策 2：坐标系统 — `position:absolute` + `scrollX/scrollY` 转换

`simplify-dom.js` 通过 `getBoundingClientRect()` 获取视口相对坐标。高亮覆盖层使用 `position: absolute`（文档相对定位），JS 渲染时用 `rect.left + window.scrollX` / `rect.top + window.scrollY` 转换。

**备选方案**：`position: fixed` 覆盖层。被否决，因为滚动后高亮停留在视口原位而元素已移走。

### 决策 3：映射查询 — Agent 内部工具按需查询

用户说"点 @e3"时，Agent 调用 `browser_get_element_by_number` 工具查询编号对应的元素信息（tag、text、selector），然后调用 `browser_click` 执行操作。映射表存储在 Python 侧 `CDPHelpers._element_map` 缓存中，不走 DOM 查询。

**备选方案**：预查所有元素注入 system message。被否决，因为浪费 token 且与已有 `@eN` 注入重复。

### 决策 4：高亮刷新 — 仅 goto/click/fill 后刷新

只在可能改变页面 DOM 的操作后刷新高亮。snapshot/scroll/source/eval 不改变 DOM，不刷新。

刷新放在上层调用方（`execute_tool_calls_sequential`、`execute_browser_step`），不放在底层 `execute_browser_op` 内部，保持底层函数职责单一。

### 决策 5：首次注入 — conversation_loop 启动时异步注入

chat 模式启动时，在进入消息循环前异步调用 `add_dom_highlights()`，失败静默忽略。确保用户打开已有页面后第一句话就能看到编号。

### 决策 6：`_resolve_element_ref` 改为 async + `cdp_helpers` fallback

chat 模式下 `execute_browser_op` 调用时不传 `element_map`，如果 Agent 直接传 `@e3` 给 click/fill，原 `_resolve_element_ref` 会原样返回导致非法 CSS selector。改为 async 并增加 `cdp_helpers` 参数做 fallback 查询。

### 决策 7：高亮渲染 — 内联 JS，无独立文件

元素数据已在 Python 侧通过 `_inject_simplify_js` 获取，高亮渲染直接用 `self.js()` 内联 JS 完成。不创建独立的 `assets/dom_highlight.js` 文件，减少维护负担。

## 风险 / 权衡

| 风险 | 缓解 |
|:-----|:-----|
| 动态页面（SPA）DOM 变化后编号过时 | 每次 goto/click/fill 后刷新 |
| `pointer-events: none` 在 iframe 中失效 | 首版不处理 iframe |
| 用户手动滚动导致高亮位置偏移 | 每次刷新时重新获取坐标，JS 侧用 `scrollX/scrollY` 转换 |
| 高亮层覆盖用户正常操作 | `pointer-events: none` 确保不拦截交互 |
| `_resolve_element_ref` 改为 async 影响调用方 | 仅 2 处内部调用，加 `await` 即可 |
| `cdp_helpers` 类型为 `object` 无法直接调用新方法 | 使用 `hasattr` 做类型窄化 |

## 迁移计划

1. 新增 `cdp/helpers.py` 中的三个方法（纯新增，无破坏性）
2. 新增 `browser_get_element_by_number` 工具 schema
3. 修改 `_resolve_element_ref` 为 async（内部函数，无外部 API 影响）
4. 在各调用方添加高亮刷新逻辑
5. 部署后用户在浏览器中即可看到编号标签

**回滚**：移除 `BROWSER_TOOLS` 中的新工具 schema，移除各调用方的高亮刷新调用，`_resolve_element_ref` 改回同步（无状态变更，直接回滚代码即可）。

## 待确认问题

- 用户手动触发"显示编号"的交互方式（CLI 命令？chat 命令？）待后续确定
- 是否需要支持高亮样式的自定义（颜色、大小等）待用户反馈后决定
