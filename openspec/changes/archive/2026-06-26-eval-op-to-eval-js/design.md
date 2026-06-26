## 背景

当前 `browser_eval` 是 `execute_browser_op()` 中 22 个 elif 分支之一。执行 JS 后结果直接返回给 LLM，没有进入 shared_store / `{path}` 数据管道。而 `file_read`、`captcha`、`file_write` 等 tool 已经通过 `source_key` + shared_store 打通了数据流，`browser_eval` 是链路上唯一的断层。

```
file_read ──→ shared_store ──→ file_write     ✅
captcha   ──→ shared_store ──→ format_convert  ✅
browser_eval ──→ LLM 上下文，不进 shared_store ❌
```

同时 `expand_branch` 本质是 `snapshot` 的子查询（展开折叠容器），不应是独立 op。`get_element_by_number` 名字不准确，它查的是 CSS selector，且当前走 scratchpad 缓存不刷新页面状态。

## 目标 / 非目标

**目标：**
- `browser_eval` 从 op 提为独立 tool `eval_js`，结果走 registry dispatch → shared_store
- `expand_branch` 合并进 `browser_snapshot(expand_key=)`，精简 ops 面
- `get_element_by_number` 更名为 `lookup_selector`，语义更清晰，且每次调用刷新缓存
- 更新 prompts 中所有过时引用

**非目标：**
- 不改 `cdp/playwright_bridge.py` 的 bridge 方法（`expand_branch` 保留给 snapshot 内部调用）
- 不改 `eval_agent` 子 agent 机制（仅替换其 tool 名）
- 不改 `ToolContext.eval()` 内部方法（仅测试用）
- 不改其他 browser ops（评价过，都是纯副作用或已有 bypass）
- 不迁移旧 pipeline YAML（无存量 pipeline 使用受影响 op）

## 关键决策

### 1. eval_js 暴露 code + source_key 两个参数

`eval-op-to-tool.md` 旧设计方案列出了 8 个参数，但 `js_file`、`params`、`poll_seconds`、`output_file`、`silent`、`timeout` 这 6 个从未有实际使用场景。暴露 `code`（必填）和 `source_key`（可选）两个参数：

- `code` — 要执行的 JS 代码，和原 `browser_eval(code)` 一致
- `source_key` — 可选，指定结果写入 shared_store 的 key。设置后结果可通过 `{key}` 被其他 tool 引用，实现数据互通

`source_key` 的写入逻辑由 `tool_executor.py` 的 dispatch 层统一处理（L246-248），handler 无需感知。

### 2. expand_branch 合并进 snapshot 而非独立 tool

`expand_branch` 是 "对已有 progressive snapshot 展开一个容器"——如果抽成独立 tool，每一步都是先 snapshot → 看折叠列表 → expand_branch → 再 snapshot。变成两步并不合理。不如直接在 `browser_snapshot` 上加 `expand_key` 参数一步完成。

### 3. lookup_selector 每次刷新缓存

之前 `get_element_by_number` 走 `_try_scratchpad_element_lookup` 纯缓存查询。网页动态变化后缓存可能失效。改成：

```
lookup_selector(ref)
  → ensure_highlights() 重新扫描
  → 从最新 element_map 查 ref
  → 返回 {selector, tag, text}
```

代价 ~200-500ms 重扫，但对一次点击操作来说可忽略（点击本身也要 ~100ms）。

**注意：** `tool_executor.py:207` 有一个预分发优化，在 `fn_name == "browser_get_element_by_number"` 时直接从 scratchpad 缓存返回，绕过了 op handler。改名后这个检查必须删除，否则 `ensure_highlights()` 永远不会被调用。

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| 旧 pipeline YAML 含 `{type: eval}` 步骤会崩 | 当前无存量使用，fallback 已返回清晰错误 |
| LLM 习惯变化：`browser_eval(code)` 改为 `eval_js(code)` | schema 保持相同参数结构，name 变化在 tool list 中直接体现 |
| 测试覆盖：`execute_browser_step` 无单独测试 | eval 分支删除后现有测试通过即可 |
| expand_branch 合并后 schema 变复杂 | snapshot 原有 3 参数 +1 可选 `expand_key`，复杂度可控 |

## 迁移计划

1. `tools/registry.py` — 注册 `eval_js` handler + schema（含 `source_key` 参数），从 `_BROWSER_OPS` 移除 `eval` 和 `expand_branch`，清理 `_BROWSER_SCHEMAS` 死条目，snapshot schema 加 `expand_key`
2. `engine/executor.py` — `execute_browser_op()` 删 eval/expand_branch 分支，snapshot 加 expand_key
3. `engine/executor.py` — `execute_browser_step()` 同步删除 + 改名 + 刷新逻辑
4. `engine/eval_agent.py` — `get_restricted_tools()` 中 `browser_eval` → `eval_js`，删除 `browser_expand_branch`，更新 docstring
5. `engine/_harness/tool_executor.py` — 删除 `browser_get_element_by_number` 的 scratchpad 快捷路径及 `_try_scratchpad_element_lookup`/`_normalize_ref` 函数
6. `cdp/playwright_bridge.py` — 更新 LLM 提示文本中的 `expand_branch(key=...)` → `snapshot(expand_key=...)`
7. `engine/_lifecycle/compensation.py` — 删除 `UNDO_MAP` 中的 `"eval"` 条目
8. `prompts/` — 更新所有引用
9. `backend/tests/test_harness_tools.py` — 更新断言
10. 验证：`pytest` + manual `eval_js("document.title")` 确认结果可被 `{source_key}` 引用

回滚方案：恢复 `_BROWSER_OPS` + 两个执行器分支 + prompts，git revert 即可。

## 待确认问题

无（全部已在 explore mode 中讨论确定）
