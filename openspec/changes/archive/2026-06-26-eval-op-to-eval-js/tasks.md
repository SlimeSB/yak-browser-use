## 1. eval_js — 独立 tool

- [x] 1.1 在 `tools/registry.py` 的 `_build_registry_impl()` 中注册 `eval_js` 工具：handler 通过 `ctx.cdp_helpers` 获取 bridge 调用 `evaluate(code)`，结果直接返回；schema 含 `code`（必填）和 `source_key`（可选）两个参数
- [x] 1.2 从 `_BROWSER_OPS` 列表中移除 `"eval"`
- [x] 1.3 从 `_BROWSER_SCHEMAS` 字典中删除 `"eval"` 条目
- [x] 1.4 从 `execute_browser_op()` 中删除 `op_type == "eval"` 分支
- [x] 1.5 从 `execute_browser_step()` 的白名单列表中删除 `"eval"`
- [x] 1.6 从 `execute_browser_step()` 中删除 `elif op_type == "eval"` 分支

## 2. expand_branch 合并进 snapshot

- [x] 2.1 从 `_BROWSER_OPS` 列表中移除 `"expand_branch"`
- [x] 2.2 从 `execute_browser_op()` 中删除 `op_type == "expand_branch"` 分支
- [x] 2.3 从 `execute_browser_step()` 的白名单中删除 `"expand_branch"`
- [x] 2.4 从 `execute_browser_step()` 中删除 `elif op_type == "expand_branch"` 分支
- [x] 2.5 在 `execute_browser_op()` 的 snapshot 分支中加 `expand_key` 参数处理：当 `expand_key` 提供时，调用 `bridge.expand_branch(key=expand_key)` 将结果合并到 snapshot 返回中
- [x] 2.6 在 `execute_browser_step()` 的 snapshot 分支中将 `expand_key` 透传到 `core_params`
- [x] 2.7 在 `_BROWSER_SCHEMAS["snapshot"]` 中添加 `expand_key` 可选参数（type: string）
- [x] 2.8 从 `_BROWSER_SCHEMAS` 字典中删除 `"expand_branch"` 条目
- [x] 2.9 更新 `_BROWSER_SCHEMAS["snapshot"]` 描述文字：将 "可用 expand_branch 展开" 改为 "可用 expand_key 参数展开"
- [x] 2.10 更新 `playwright_bridge.py` `expand_hint` 文本：`expand_branch(key='...')` → `snapshot(expand_key='...')`
- [x] 2.11 更新 `playwright_bridge.py` `folded_note` 文本：`expand_branch(key='c_N', ...)` → `snapshot(expand_key='c_N')`
- [x] 2.12 删除 `compensation.py` `UNDO_MAP` 中的 `"eval": None` 条目

## 3. get_element_by_number → lookup_selector

- [x] 3.1 在 `_BROWSER_OPS` 列表中将 `"get_element_by_number"` 改为 `"lookup_selector"`
- [x] 3.2 在 `_BROWSER_SCHEMAS` 中将键名改为 `"lookup_selector"`，描述改为 `"查找页面上指定元素的 CSS selector。每次调用刷新页面缓存确保最新。"`
- [x] 3.3 在 `execute_browser_op()` 中将 `elif op_type == "get_element_by_number"` 改为 `elif op_type == "lookup_selector"`，添加 `await bridge.ensure_highlights()` 调用刷新缓存
- [x] 3.4 在 `execute_browser_step()` 中同步改名（白名单列表和分支）
- [x] 3.5 删除 `tool_executor.py` 中 `browser_get_element_by_number` 的 scratchpad 快捷路径，让请求走到 op handler 调 `ensure_highlights()`
- [x] 3.6 删除 `tool_executor.py` 中 `_try_scratchpad_element_lookup` 函数和 `_normalize_ref` 函数，已无调用方

## 4. eval_agent 更新

- [x] 4.1 在 `eval_agent.py` 的 `get_restricted_tools()` 中将 `"browser_eval"` 改为 `"eval_js"`
- [x] 4.2 从 `get_restricted_tools()` 的 allowed set 中删除 `"browser_expand_branch"`
- [x] 4.3 更新 `eval_agent.py` 的 docstring 中的 `browser_eval` 引用

## 5. Prompts 更新

- [x] 5.1 搜索 `prompts/` 目录中所有引用 `browser_eval` 的文件，替换为 `eval_js`
- [x] 5.2 搜索 `prompts/` 目录中所有引用 `browser_get_element_by_number` 的文件，替换为 `browser_lookup_selector`
- [x] 5.3 搜索 `prompts/` 目录中所有引用 `browser_expand_branch` 的文件，移除或替换
- [x] 5.4 更新 `tools/record_step.py` docstring 中的有效 op_type 列表（移除 `eval`）
- [x] 5.5 更新 `registry.py` 中 `eval_agent` 工具描述：`browser_eval` → `eval_js`
- [x] 5.6 更新 `registry.py` 中 `record_step` schema 描述：移除 `eval`

## 6. 测试更新

- [x] 6.1 更新 `test_harness_tools.py`：`browser_get_element_by_number` → `browser_lookup_selector`
- [x] 6.2 更新 `test_harness_tools.py`：删除 `assert "browser_eval" in names`
- [x] 6.3 更新 `test_harness_tools.py`：删除 `assert "browser_expand_branch" in names`
- [x] 6.4 更新 `test_harness_tools.py`：`browser_get_element_by_number` → `browser_lookup_selector`

## 7. 验证

- [x] 7.1 运行 `pytest backend/tests/ -x -q` 确认所有测试通过
- [x] 7.2 运行 `grep "browser_eval" backend/src/ -r` 确认无遗漏
- [x] 7.3 运行 `grep "browser_get_element_by_number" backend/src/ -r` 确认无遗漏
- [x] 7.4 运行 `grep "browser_expand_branch" backend/src/ -r` 确认无遗漏
- [ ] 7.5 手动：`eval_js(code="document.title")` 调用正常返回
- [ ] 7.6 手动：`browser_lookup_selector(ref="0-2-175")` 调用正常返回
- [ ] 7.7 手动：`browser_snapshot(mode="progressive", expand_key="c_0")` 调用正常返回
