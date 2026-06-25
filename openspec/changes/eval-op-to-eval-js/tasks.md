## 1. eval_js — 独立 tool

- [ ] 1.1 在 `tools/registry.py` 的 `_build_registry_impl()` 中注册 `eval_js` 工具：handler 通过 `ctx.cdp_helpers` 获取 bridge 调用 `evaluate(code)`，结果直接返回
- [ ] 1.2 从 `_BROWSER_OPS` 列表中移除 `"eval"`
- [ ] 1.3 从 `_BROWSER_SCHEMAS` 字典中删除 `"eval"` 条目
- [ ] 1.4 从 `execute_browser_op()` 中删除 `op_type == "eval"` 分支 (L210-213)
- [ ] 1.5 从 `execute_browser_step()` 的白名单列表中删除 `"eval"` (L645)
- [ ] 1.6 从 `execute_browser_step()` 中删除 `elif op_type == "eval"` 分支 (L668-670)

## 2. expand_branch 合并进 snapshot

- [ ] 2.1 从 `_BROWSER_OPS` 列表中移除 `"expand_branch"`
- [ ] 2.2 从 `execute_browser_op()` 中删除 `op_type == "expand_branch"` 分支 (L215-224)
- [ ] 2.3 从 `execute_browser_step()` 的白名单中删除 `"expand_branch"` (L648)
- [ ] 2.4 从 `execute_browser_step()` 中删除 `elif op_type == "expand_branch"` 分支 (L707-712)
- [ ] 2.5 在 `execute_browser_op()` 的 snapshot 分支中加 `expand_key` 参数处理：当 `expand_key` 提供时，调用 `bridge.expand_branch(key=expand_key)` 将结果合并到 snapshot 返回中
- [ ] 2.6 在 `execute_browser_step()` 的 snapshot 分支中将 `expand_key` 透传到 `core_params`

## 3. get_element_by_number → lookup_selector

- [ ] 3.1 在 `_BROWSER_OPS` 列表中将 `"get_element_by_number"` 改为 `"lookup_selector"`
- [ ] 3.2 在 `_BROWSER_SCHEMAS` 中将键名改为 `"lookup_selector"`，描述改为 `"查找页面上指定元素的 CSS selector。每次调用刷新页面缓存确保最新。"`
- [ ] 3.3 在 `execute_browser_op()` 中将 `elif op_type == "get_element_by_number"` 改为 `elif op_type == "lookup_selector"`，添加 `await bridge.ensure_highlights()` 调用刷新缓存
- [ ] 3.4 在 `execute_browser_step()` 中同步改名（白名单列表和分支）

## 4. Prompts 更新

- [ ] 4.1 搜索 `prompts/` 目录中所有引用 `browser_eval` 的文件，替换为 `eval_js`
- [ ] 4.2 搜索 `prompts/` 目录中所有引用 `browser_get_element_by_number` 的文件，替换为 `browser_lookup_selector`
- [ ] 4.3 搜索 `prompts/` 目录中所有引用 `browser_expand_branch` 的文件，移除或替换
- [ ] 4.4 更新 `tools/record_step.py` docstring 中的有效 op_type 列表

## 5. 验证

- [ ] 5.1 运行 `pytest backend/tests/ -x -q` 确认所有测试通过
- [ ] 5.2 运行 `grep "browser_eval" backend/src/ -r` 确认无遗漏
- [ ] 5.3 运行 `grep "browser_get_element_by_number" backend/src/ -r` 确认无遗漏
- [ ] 5.4 运行 `grep "browser_expand_branch" backend/src/ -r` 确认无遗漏
- [ ] 5.5 手动：`eval_js(code="document.title")` 调用正常返回
- [ ] 5.6 手动：`browser_lookup_selector(ref="0-2-175")` 调用正常返回
- [ ] 5.7 手动：`browser_snapshot(mode="progressive", expand_key="c_0")` 调用正常返回
