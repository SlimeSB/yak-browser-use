## 背景

`browser_source` 在 registry 中以通用 `_make_browser_handler` 注册（registry.py:423），走 `execute_browser_op("source", ...)`（executor.py:191）。HTML 原文通过 `result["html"]` 一路返回到 `_format_tool_result` 并写入 LLM context。

聊天模式走 registry handler（chat → conversation_loop → tool_executor → registry.dispatch），pipeline/preset 模式直接调 `execute_browser_op` 不经 registry。

当前的 `_apply_heavy_data_filter`（tool_executor.py:470-483）试图在事后把 HTML 抽走替换成 size 摘要，但此时 HTML 已进入 context。

## 目标 / 非目标

**目标：**
- browser_source 调用后 HTML 原文不进入 LLM context
- 强制 LLM 通过 `output_to` 参数提供 shared_store key
- 返回给 LLM 的信息包含：size 元信息 + 下一步操作指导（data_browse key）
- schema 描述足够强硬，让 LLM 优先考虑 browser_snapshot / browser_eval_js
- 默认 strip_styles=True 减少体积
- 删除无用的事后过滤逻辑

**非目标：**
- 不改 pipeline/preset 回放路径的强制行为（只改 strip_styles 默认值）
- 不改变 browser_source 的浏览器底层行为（bridge.source() 逻辑不变）
- 不动 guardrail warning 机制（本次只处理源头）

## 关键决策

### 决策 1：registry handler 单独注册 vs 改 execute_browser_op

选择：**registry handler 单独注册**

原因：
- registry handler 只在 chat 模式命中，pipeline/preset 不经过这里
- 如果改 execute_browser_op，preset 模式也会强制要求 output_to（副作用大）
- registry 层可以写 ctx.shared_store，executor 层没有这个上下文

`_BROWSER_OPS` 列表移除 `"source"`，循环后单独 register `_source_handler`。

### 决策 2：使用 `output_to` 参数（避免与通用 `bind` 冲突）

选择：**使用 `output_to` 参数名，与 `browser_eval_js` 保持一致**

关键发现：`_execute_single_tool_call`（tool_executor.py:211）在 dispatch **之前**会 `fn_args.pop("bind", "")`，将通用 `bind` 弹出。如果 `_source_handler` 试图读取 `bind`，会拿到空 args。

方案：
- 使用 `output_to` 作为参数名（浏览器写入 shared_store 的 key），与 `_eval_js_handler` 的命名一致
- `output_to` 不在通用 `bind` 的弹出范围内，可以安全传递到 handler
- handler 内部：验证 `output_to` 存在且非空 → 调用 `execute_browser_op` → 从 result pop html → 写入 `ctx.shared_store[output_to]` → 返回元信息

通用 `bind` 仍然可同时使用（如果 LLM 同时传了 `bind` 和 `output_to`，`bind` 弹出后指向的会是 handler 返回的 result dict，这是预期行为）。

LLM 调用示例：`browser_source(output_to="page_html")`

### 决策 3：strip_styles 默认值改为 True

选择：**改 executor.py 默认值**

原因：
- 影响所有路径（chat + preset），行为一致
- pipeline YAML 显式传 `strip_styles=false` 可覆盖
- 不是破坏性变更——用户通过 shared_store/data_browse 拿到的数据少了 script/style 标签，体积更小

### 决策 4：删除 `_apply_heavy_data_filter` 分支

选择：**直接删除**

原因：
- handler 源头已拦截，HTML 不再出现在 result 里
- 该分支成为死代码
- 保留只会增加维护负担

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| 已有 pipeline 回放时 browser_source 没写 output_to | preset 模式不走 registry handler，execute_browser_op 仍正常工作（只是默认 strip_styles=True） |
| LLM 不知道 data_browse 是什么 | schema description + 返回值 guidance 都明确提到 data_browse |
| strip_styles=True 默认影响需要样式内容的场景 | 显式传 strip_styles=false 可覆盖（极罕见） |
| 相关测试删除后覆盖率下降 | 被测代码本身已删除，测试无存在意义 |

## 迁移计划

1. 先改 registry.py + executor.py（核心行为变更）
2. 改 prompt 文件（tool_strategy.md + system.md）
3. 删除 tool_executor.py 的 filter 分支
4. 删除/更新相关测试
5. 运行 pytest 验证
6. 手动测试 chat 模式 browser_source 调用

## 待确认问题

- 无
