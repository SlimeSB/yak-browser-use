## 1. 准备与基础改造

- [ ] 1.1 在 `CDPHelpers.__init__` 中初始化 `self._element_map: dict[str, dict] = {}`

## 2. cdp/helpers.py — 高亮核心方法

- [ ] 2.1 实现 `add_dom_highlights(self, elements=None)`：接收可选元素列表，未传时通过 `_inject_simplify_js("interactive")` 获取并提取 `result["elements"]`；构建 `self._element_map` 缓存；内联 JS 渲染高亮（先 remove 旧高亮，创建 `#ybu-highlights` 容器，每个元素画 absolute 定位虚线框 + 蓝色 badge，JS 中用 `scrollX/scrollY` 转换坐标）
- [ ] 2.2 实现 `remove_dom_highlights(self)`：通过 `self.js()` 执行 `document.getElementById('ybu-highlights')?.remove()`，同时清空 `self._element_map = {}`
- [ ] 2.3 实现 `get_element_by_index(self, ref)`：从 `self._element_map` 缓存查询，支持 `"@e3"`/`"e3"`/`"3"` 格式归一化；返回 `{ref, tag, text, selector, bounds}`

## 3. engine/_harness/tools.py — 新增 Agent 工具

- [ ] 3.1 在 `BROWSER_TOOLS` 列表末尾追加 `browser_get_element_by_number` 工具 schema（参数 `ref: string`，required）

## 4. engine/executor.py — 操作分发与引用解析

- [ ] 4.1 在 `execute_browser_op()` 中新增 `get_element_by_number` 分支：从 `params` 取 `ref`，调用 `cdp_helpers.get_element_by_index(ref)` 返回结果
- [ ] 4.2 将 `_resolve_element_ref()` 改为 `async def`，增加 `cdp_helpers=None` 参数：当 `element_map` 为 None 且 selector 以 `@e` 开头时，通过 `hasattr(cdp_helpers, 'get_element_by_index')` 做 fallback 查询
- [ ] 4.3 在 `execute_browser_op()` 的 click/fill 分支中，将 `_resolve_element_ref()` 调用改为 `await`，并传入 `cdp_helpers` 参数
- [ ] 4.4 在 `execute_browser_step()` 中，goto/click/fill 操作成功后调用 `cdp_helpers.add_dom_highlights()`（需 `hasattr` 检查）

## 5. engine/_harness/tool_executor.py — Chat 模式刷新

- [ ] 5.1 在 `execute_tool_calls_sequential()` 中，`_append_tool_result()` 之后，对 goto/click/fill 三种 op 调用 `cdp_helpers.add_dom_highlights()`（需 `hasattr` 检查）

## 6. engine/_harness/conversation_loop.py — 首次注入

- [ ] 6.1 在 `run_conversation_loop()` 中，进入消息循环前异步调用 `cdp_helpers.add_dom_highlights()`，失败静默忽略，不阻塞对话

## 7. engine/agent.py — Agent 生命周期集成

- [ ] 7.1 在 `run_goal_step()` 中，`elements = interactive.get("elements", [])` 之后、`if elements:` 之前，调用 `await cdp_helpers.add_dom_highlights(elements=elements)`
- [ ] 7.2 修改 `_cleanup_agent_highlights()` 的 JS 表达式，追加 `#ybu-highlights` 的移除逻辑

## 8. 验证与收尾

- [ ] 8.1 手动验证：启动 chat 模式，打开页面，确认浏览器中出现蓝色编号标签
- [ ] 8.2 手动验证：执行 goto/click/fill 后确认编号自动刷新
- [ ] 8.3 手动验证：Agent 通过 `browser_get_element_by_number` 查询编号，再用 `browser_click` 执行点击，端到端链路可用
- [ ] 8.4 运行现有测试确保无回归：`uv run pytest tests/ -v`
