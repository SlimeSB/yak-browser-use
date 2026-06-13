## Why

当前用户通过 chat 与 Agent 交互时，Agent 执行浏览器操作对用户不可见。用户不知道页面上有哪些可交互元素，也无法直接告诉 Agent "点第 3 个按钮"。这导致用户必须用自然语言描述目标元素（如"点那个蓝色的登录按钮"），沟通效率低且容易出错。

本变更利用已有的 `simplify-dom.js` 元素扫描能力，在浏览器页面上注入可见的交互元素编号标签。用户看到编号后可以直接说"点 @e3"，Agent 通过编号映射查到对应 DOM 元素并执行操作。这显著提升了人机协作的交互效率。

## What Changes

- **新增** `cdp/helpers.py` 中 `add_dom_highlights()`、`remove_dom_highlights()`、`get_element_by_index()` 三个方法，实现 DOM 高亮编号的注入、移除和查询
- **新增** `browser_get_element_by_number` 工具，Agent 可通过该工具按编号查询元素信息
- **修改** `engine/executor.py` 中 `execute_browser_op()` 新增 `get_element_by_number` 操作分支；`_resolve_element_ref()` 改为异步并增加 `cdp_helpers` fallback 以支持 chat 模式下的 `@eN` 解析
- **修改** `engine/_harness/tool_executor.py` 中 `execute_tool_calls_sequential()`，在 goto/click/fill 成功后自动刷新高亮
- **修改** `engine/_harness/conversation_loop.py` 中 `run_conversation_loop()`，对话启动时异步注入首次高亮
- **修改** `engine/agent.py` 中 `run_goal_step()` 在 Agent 启动前注入高亮；`_cleanup_agent_highlights()` 同时清理 BU 和 LBU 的高亮元素
- **修改** `engine/executor.py` 中 `execute_browser_step()`，在 goto/click/fill 成功后自动刷新高亮

## Capabilities

### New Capabilities
- `dom-highlight-numbering`: 在浏览器页面上注入交互元素编号标签，支持按编号查询元素信息，Agent 可通过编号映射执行点击/填充操作

### Modified Capabilities
<!-- 本次无既有能力的需求变更 -->

## Impact

- **代码影响**：`cdp/helpers.py`、`engine/executor.py`、`engine/_harness/tools.py`、`engine/_harness/tool_executor.py`、`engine/_harness/conversation_loop.py`、`engine/agent.py`
- **新增测试**：`tests/test_element_highlight.py`
- **依赖**：复用已有的 `simplify-dom.js` 和 `_inject_simplify_js()`，无新增外部依赖
- **破坏性变更**：无。`_resolve_element_ref()` 改为 async 但仅内部调用，对外接口不变
- **用户体验**：用户在浏览器中看到蓝色编号标签，可直接用编号指挥 Agent 操作
