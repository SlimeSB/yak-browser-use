## 背景

当前 `main` 分支上浏览器交互通过 `browser_*` 系列 tool（`browser_click`、`browser_fill`、`browser_snapshot` 等）完成，每个 tool 直接操作 PlaywrightBridge。`toolgen-test` 分支探索了 ToolContext 统一 SDK + `_PH-` 动态代码生成路线，但代码生成部分经实践验证是过度设计。

本次设计将 ToolContext 从 toolgen-test 分支合入 main 并精简为纯浏览器操作 SDK，同时引入 eval agent 处理复杂 DOM 场景、file_read/file_write 处理文件读写、format_convert 处理格式转换。

**约束：**
- ToolContext 依赖现有 `PlaywrightBridge`，不引入新的浏览器抽象层
- eval agent 调用 `run_conversation_loop()`（非 `run_preset_loop()`），传入自定义 system prompt + 受限 tool 集合
- `file_read`/`file_write`/`format_convert`/`eval_agent` 在 `_execute_single_tool_call` 中有专用 handler，不依赖 `execute_tool()` 的文件路径查找
- format_convert 复用现有 `tools/adapters.py` 的 csv↔json 实现
- `toolgen-test` 分支保留不动，不合入 main

## 目标 / 非目标

**目标：**
- 合入精简版 ToolContext（ops.py），提供 ctx.eval / ctx.type / ctx.click / ctx.snapshot / ctx.wait / ctx.screenshot / ctx.source 七个方法
- 实现 eval agent subagent，处理复杂 DOM 操作和验证码识别
- 实现 file_read / file_write 预设 tool，纯文本文件读写
- 实现 format_convert 预设 tool，xlsx/csv/json any-to-any 格式转换
- 清理 main 分支上残留的 `_PH-` 工具执行路径

**非目标：**
- 不实现 tool gen（`_inline_generate_and_execute` 等），留在 toolgen-test 分支
- 不实现 AST 安全检查
- 不实现 ToolContext 的 data ops（save_json/load_json/save_csv/load_csv 等）
- 不实现 ToolContext 的 cdp() escape hatch
- 不修改 PlaywrightBridge 接口

## 关键决策

### 决策 1：ToolContext 方法名用 eval / type，而非 evaluate / fill

**选择：** `ctx.eval(js)` 和 `ctx.type(selector, text)`

**原因：** eval 和 type 是用户直觉词汇（"在浏览器里 eval 一段 JS"、"往输入框 type 文字"），虽然与 Python 内置函数同名，但 ToolContext 是实例方法，调用时写 `ctx.eval(...)` 不会与内置 `eval()` 混淆。PlaywrightBridge 内部仍用 `evaluate` / `fill`，ToolContext 做一层命名适配。

**备选：** 用 `evaluate` / `fill` 避免与内置函数冲突。否决原因：eval/type 更短、更符合用户心智模型。

### 决策 2：eval agent 共享主流程 CDP 连接

**选择：** eval agent 通过 `cdp_helpers` 参数拿到主流程的 PlaywrightBridge，不创建独立 CDP 连接。

**原因：**
- 页面状态必须一致（eval agent 操作的页面就是主流程当前页面）
- conversation_loop 是串行的——eval agent 执行期间主流程不操作页面，无竞态
- 复用 `_run_swimlane_agent` 模式（已在 runner_preset.py 中验证可行）

**备选：** 独立 CDP 连接。否决原因：页面状态不同步，需要额外的页面同步逻辑。

### 决策 3：eval agent 通过 run_conversation_loop 实现

**选择：** eval agent 内部调用 `run_conversation_loop()`，传入 eval agent 专用的 system prompt + 受限 tool 集合 + 用户上下文。

**原因：**
- `run_preset_loop` 内部依赖 `PipelineTaskAdapter` 将 `step_defs` 转为 `TaskDescriptor`，eval agent 没有 pipeline 步骤结构
- `run_conversation_loop` 直接接受 `system_prompt` + `tools` + `messages`，更灵活
- eval agent 使用受限 tool 集合（browser_eval、browser_snapshot、browser_click、browser_fill、browser_wait、browser_source、browser_scroll），不暴露 goal_run 和 pipeline_* 工具

**流程：**
1. 主 LLM 调用 `eval_agent(purpose="提取表格", snapshot="...")`
2. `eval_agent` tool handler 构造 EvalAgent 实例，注入 prompt 模板 + JS 函数库
3. EvalAgent 调用 `run_conversation_loop()`，system_prompt 为 eval agent 专用 prompt，tools 为受限集合
4. eval agent 的 LLM 在循环中：观察 browser_snapshot → browser_eval JS → 看结果 → 调整 → 再 eval
5. tool handler 同步阻塞等待（`asyncio.wait_for`，默认 120s 超时），完成时返回数据摘要
6. 如果 tool handler 传入了 `output_dir`，结果写入 `{output_dir}/eval_result.csv`

### 决策 4：format_convert 用 any-to-any 统一入口

**选择：** 单个 `format_convert(source, target, source_fmt="", target_fmt="", **opts)` 函数，内部路由。

**原因：**
- LLM 只需记一个 tool 名，降低认知负担
- 格式嗅探逻辑集中在一处，避免分散
- 复用现有 `tools/adapters.py` 的 csv↔json 实现

**路由逻辑：**
- xlsx→csv：openpyxl 读取 → csv.writer 写入
- csv→xlsx：csv 读取 → openpyxl 写入
- csv↔json：委托 `tools/adapters.py`
- xlsx↔json：两步转换（xlsx→csv→json 或 json→csv→xlsx）

### 决策 5：file_read 不做任何解析

**选择：** `file_read(path, head=20, max_chars=3000)` 返回原始文件内容，不做 JSON 解析、不做 tab 分隔、不做结构化。

**原因：**
- 避免"万能解析器"陷阱——不同文件格式需要不同解析逻辑
- 结构化解析交给 format_convert
- LLM 拿到原始文本后可以自行判断内容

**二进制文件处理：** 检测到非文本扩展名（.xlsx、.png 等）时返回提示"二进制文件，请使用 format_convert"。

### 决策 6：execute_tool 改用 build_tool_kwargs

**选择：** `backend/engine/executor.py` 的 `execute_tool()` 改用 `build_tool_kwargs()` 构造 kwargs，不再硬编码 `input_files`/`output_dir` 注入。

**原因：**
- 当前 `execute_tool()` 总是注入 `input_files={}` 和 `output_dir=""` 到 kwargs
- 新增的 chat-mode tool（`file_read`、`file_write`、`format_convert`）不接受这两个参数，硬编码注入会导致 `TypeError`
- `build_tool_kwargs` 按函数签名选择性注入，兼容新旧 tool

**Bridge 提取兼容：** `build_tool_kwargs` 从 `cdp_helpers` 提取 bridge 时兼容 `cdp_helpers.bridge`（CDPHelpers）和 `cdp_helpers._bridge`（ToolCDPHelpers）两种路径。对于含 `ctx` 的新 tool 直接构造 `ToolContext(bridge=bridge)`；对于含 `cdp_helpers` 的旧 tool 构造 `ToolCDPHelpers(bridge)`。

### 决策 7：eval_agent 在 _execute_single_tool_call 中需要专用 handler

**选择：** `eval_agent` 在 `_execute_single_tool_call()` 中有自己的 handler（类似 `goal_run`、`pipeline_finish`），不走 `else → execute_tool()` 分支。

**原因：**
- `eval_agent` 需要 `llm_call` 参数来启动 subagent 的 LLM 循环
- `llm_call` 在 `execute_tool_calls_sequential` → `_execute_single_tool_call` 的调用链中不存在，需要新增参数传递
- `execute_tool()` 的职责是加载并调用 tool 函数，不涉及 LLM 调用

**传递链：**
```
execute_tool_calls_sequential(llm_call=...)  ← 新增参数
  → _execute_single_tool_call(llm_call=...)  ← 新增参数
    → elif fn_name == "eval_agent": handler(fn_args, cdp_helpers, llm_call, ...)
```

### 决策 8：file_read / file_write / format_convert 在 _execute_single_tool_call 加 handler

**选择：** `file_read`、`file_write`、`format_convert` 在 `_execute_single_tool_call()` 中有自己的 handler，通过 `from tools.xxx import xxx` 直接导入调用。

**原因：**
- chat 模式下 `tools_dir = Path("tools")` 在项目根不存在（已确认），`execute_tool()` 的文件路径查找会永远失败
- 通过 Python import 系统导入（`from tools.file_read import file_read`）与 `todo` 工具的模式一致
- 避免修改 `tools_dir` 默认值（那是独立的 bug，不应在本变更中修复）

### 决策 9：ToolContext 构造函数精简为 (bridge, allowed_domains)

**选择：** `ToolContext.__init__` 仅接受 `bridge` 和 `allowed_domains` 两个参数。移除 `input_files`/`output_dir`/`params` 实例属性、`CDP_BLOCKED_COMMANDS` 类属性、`DANGEROUS_MODULES` 类属性。

**原因：** data ops 已移除，`cdp()` escape hatch 已移除，tool gen 不走 main。这些属性和参数都是 dead code。

### 决策 10：_PH- 清理连带删除 guardian/sutil/yaml/docstring

**选择：** 删除 `_PH-` 方法的同时，删除仅被这些方法使用的 import（`shutil`、`yaml`）、`ToolRunner.__init__` 的 `guardian` 参数、类 docstring 中的 `_PH- lifecycle` 描述。

**原因：** `guardian` 仅被 `_PH-` 分支的 `runner.guardian.validate_output()` 使用。`shutil` 仅被 `rename_ph_file` 使用。`yaml` 仅被 `update_pipeline_refs` 使用。保留这些是 dead code。

### 决策 11：_execute_tool_step_with_guardian 移除 pipeline_path 参数

**选择：** 从 `_execute_tool_step_with_guardian` 的函数签名和 `run_pipeline` 的调用处删除 `pipeline_path` 参数。

**原因：** `pipeline_path` 仅被 `_PH-` 分支的 `update_pipeline_refs` 引用。删除 `_PH-` 分支后成为 dead code。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| `ctx.eval` / `ctx.type` 与 Python 内置函数同名 | IDE 警告、代码审查混淆 | 文档说明 + ToolContext 是实例方法，`ctx.eval(...)` 不会与 `eval()` 混淆 |
| eval agent 共享 CDP 连接，eval 可能产生页面副作用 | 主流程后续操作基于被修改的页面状态 | eval agent 的 snapshot 输入让 LLM 了解当前状态；主流程每次操作前也应 snapshot |
| format_convert 的 xlsx↔json 两步转换可能丢失格式 | 复杂 xlsx（多 sheet、公式、样式）信息丢失 | 文档说明限制；复杂场景建议用户手动处理 |
| eval agent 的 LLM 循环可能消耗大量 token | 成本增加 | max_attempts 限制（默认 3）；每次 eval 返回精简结果 |
| eval agent 执行超时阻塞主流程 | 主流程卡死 | `asyncio.wait_for` 超时（默认 120s）；interrupt_check 传播取消信号 |
| 删除 `_PH-` 执行路径可能影响已有 pipeline | 使用 `_PH-` 工具的 pipeline 无法执行 | `_PH-` 工具从未在 main 分支上正式可用，无向后兼容问题 |

## 迁移计划

1. **合入 ops.py + test_ops.py**：从 toolgen-test 分支 cherry-pick 并精简
2. **清理 _PH- 残留**：修改 runner_preset.py 和 tool_runner.py
3. **新增 file_read/file_write**：纯文本读写 tool
4. **新增 format_convert**：格式转换 tool，引入 openpyxl 依赖
5. **新增 eval_agent**：subagent 实现 + prompt 模板 + JS 函数库
6. **调整 planner prompt**：添加 eval agent 启动条件指导

**回滚：** 所有新增文件可独立删除，runner_preset.py 和 tool_runner.py 的修改可通过 git revert 回退。不影响现有 browser_* tool 和 conversation_loop 主流程。

## 待确认问题

- eval agent 的默认 system prompt 模板内容需要实现时编写
- JS 原子函数库（isVisible、retryUntil、waitForElement）的具体实现需要实现时编写
- ~~format_convert 的 openpyxl 依赖是否需要添加到 requirements.txt~~ → 已添加到 pyproject.toml
- eval agent 的 CSV 落盘路径约定（固定 output_dir 还是可配置）
