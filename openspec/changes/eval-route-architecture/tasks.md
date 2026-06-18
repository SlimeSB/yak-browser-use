## 1. 准备：合入 ToolContext（ops.py）

- [ ] 1.1 从 toolgen-test 分支 cherry-pick `backend/engine/ops.py`（320 行），保留 ToolContext + build_tool_kwargs
- [ ] 1.2 精简 ops.py：删除 `ctx.save_json`、`ctx.load_json`、`ctx.save_csv`、`ctx.load_csv`、`ctx.load_all_records`、`ctx.save_bytes`、`ctx.cdp()`、`CDP_BLOCKED_COMMANDS`、`DANGEROUS_MODULES`
- [ ] 1.3 精简 ops.py：`ToolContext.__init__` 简化为 `(self, bridge, allowed_domains=None)`，移除 `input_files`/`output_dir`/`params` 参数和实例属性
- [ ] 1.4 精简 ops.py：方法名统一为 `eval` / `type`（不叫 `evaluate` / `fill`），内部仍委托 bridge 的 `evaluate` / `fill`
- [ ] 1.5 精简 ops.py：`build_tool_kwargs` 移除 `input_files`/`output_dir`/`params` 的注入逻辑；bridge 提取兼容 `cdp_helpers.bridge` 和 `cdp_helpers._bridge` 两种路径；对含 `ctx` 的 tool 构造 `ToolContext(bridge=bridge)`，对含 `cdp_helpers` 的旧 tool 构造 `ToolCDPHelpers(bridge)`
- [ ] 1.6 从 toolgen-test 分支 cherry-pick `backend/tests/test_ops.py`（193 行）
- [ ] 1.7 修改 test_ops.py：fixture 改为 `ToolContext(bridge=bridge)`；方法名 `evaluate`→`eval`、`fill`→`type`；删除 data ops 测试（test_save_json/test_load_json/test_save_csv/test_load_csv/test_save_bytes）；删除 cdp 测试（test_cdp/test_cdp_page_none）；删除 DANGEROUS_MODULES 测试
- [ ] 1.8 运行 `pytest backend/tests/test_ops.py -v` 确认所有测试通过

## 2. 清理 main 分支 _PH- 残留

- [ ] 2.1 修改 `backend/engine/runner_preset.py`：删除 `_execute_tool_step_with_guardian` 中的 `if tool_name.startswith("_PH-"):` 分支（~40 行），保留常规 tool 执行路径
- [ ] 2.2 修改 `backend/engine/runner_preset.py`：从 `_execute_tool_step_with_guardian` 签名和 `run_pipeline` 调用处删除 `pipeline_path` 参数（仅被 `_PH-` 分支引用）
- [ ] 2.3 修改 `backend/engine/_lifecycle/tool_runner.py`：删除 `_PH_PREFIX`、`is_ph_tool`、`strip_ph_prefix`、`rename_ph_file`、`update_pipeline_refs`、`_replace_ph_refs`（~80 行），保留 `load_and_call`
- [ ] 2.4 修改 `backend/engine/_lifecycle/tool_runner.py`：删除 `import shutil`、`import yaml`；删除 `ToolRunner.__init__` 的 `guardian` 参数；更新类 docstring 移除 `_PH- lifecycle` 描述
- [ ] 2.5 修改 `load_and_call`：kwargs 构造改为调用 `build_tool_kwargs(func, cdp_helpers=..., input_files=..., output_dir=..., **params)`，不再手动拼接 `input_files`/`output_dir`/`cdp_helpers`
- [ ] 2.6 修改 `backend/engine/executor.py` 的 `execute_tool()`：kwargs 构造改为调用 `build_tool_kwargs(func, cdp_helpers=..., **params)`，不再手动从 `params` 提取 `input_files`/`output_dir` 注入；删除 `ToolCDPHelpers` 包装逻辑（移到 `build_tool_kwargs` 内部）
- [ ] 2.7 确认 `runner_preset.py` 和 `tool_runner.py` 中不再有 `_PH-` 字符串引用
- [ ] 2.8 运行现有测试套件确认无回归：`pytest backend/tests/ -v --timeout=60`

## 3. 新增 file_read / file_write 预设 tool

- [ ] 3.1 创建 `backend/tools/file_read.py`：实现 `file_read(path, head=20, max_chars=3000, encoding="")`，UTF-8 → GBK 自动 fallback，二进制文件返回提示
- [ ] 3.2 创建 `backend/tools/file_write.py`：实现 `file_write(path, content, encoding="utf-8")`，自动创建父目录
- [ ] 3.3 在 `backend/engine/_harness/tool_executor.py` 的 `_execute_single_tool_call()` 中新增 `file_read` 和 `file_write` handler（`from tools.file_read import file_read` 直接导入调用，不走 `else → execute_tool()`）
> **注意**：3.3、4.7、5.4 都修改 `_execute_single_tool_call` 的 `elif` 链，请严格按 3→4→5 顺序逐个添加 handler，避免合并冲突。
- [ ] 3.4 在 `backend/engine/_harness/tools.py` 中定义 `FILE_READ_TOOL` 和 `FILE_WRITE_TOOL` schema，注册到 `get_all_tools()`
- [ ] 3.5 更新 `backend/tests/test_harness_tools.py`：`test_get_all_tools_with_goal` 的 `len(tools) == 36` → `len(tools) == 40`；`test_get_all_tools_without_goal` 的 `len(tools) == 35` → `len(tools) == 39`
- [ ] 3.6 编写 `backend/tests/test_file_io.py`：覆盖文本读取、编码 fallback、显式编码、二进制提示、文件不存在、写入、覆盖、自动创建目录

## 4. 新增 format_convert 预设 tool

> **注意**：format_convert 依赖 openpyxl，已在 pyproject.toml 中添加。实施前运行 `uv sync` 安装。

- [ ] 4.0 运行 `uv sync` 安装 openpyxl 依赖
- [ ] 4.1 创建 `backend/tools/format_convert.py`：实现 `format_convert(source, target, source_fmt="", target_fmt="")`
- [ ] 4.2 实现 xlsx→csv 路由（openpyxl 读取 → csv.writer 写入）
- [ ] 4.3 实现 csv→xlsx 路由（csv 读取 → openpyxl 写入）
- [ ] 4.4 实现 csv↔json 路由：构造 `input_files` dict + `output_dir` 适配参数，委托 `await adapters.csv_to_json(...)` / `await adapters.json_to_csv(...)`
- [ ] 4.5 实现 xlsx↔json 两步转换：中间 csv 写入 `tempfile.gettempdir()`，转换完成后删除临时文件
- [ ] 4.6 实现格式嗅探逻辑（从文件扩展名推断 source_fmt / target_fmt）
- [ ] 4.7 在 `backend/engine/_harness/tool_executor.py` 的 `_execute_single_tool_call()` 中新增 `format_convert` handler（`from tools.format_convert import format_convert` 直接导入调用）
- [ ] 4.8 在 `backend/engine/_harness/tools.py` 中定义 `FORMAT_CONVERT_TOOL` schema，注册到 `get_all_tools()`
- [ ] 4.9 编写 `backend/tests/test_format_convert.py`：覆盖 6 种转换方向 + 嗅探 + 不支持格式 + 临时文件清理

## 5. 新增 eval agent

- [ ] 5.1 创建 `backend/engine/eval_agent.py`：实现 `EvalAgent` 类，支持 prompt 模板注入、JS 函数库注入、max_attempts
- [ ] 5.2 在 `execute_tool_calls_sequential` 签名中新增 `llm_call` 参数，传递给 `_execute_single_tool_call`；同步更新 `conversation_loop.py:189` 调用处传入 `llm_call=llm_call`
- [ ] 5.3 在 `_execute_single_tool_call` 签名中新增 `llm_call` 参数
- [ ] 5.4 在 `_execute_single_tool_call()` 中新增 `eval_agent` 专用 handler（类似 `goal_run`/`pipeline_finish`），不走 `else → execute_tool()` 分支
- [ ] 5.5 实现 handler：接收 `purpose` + `snapshot`，构造 EvalAgent 实例，调用 `run_conversation_loop()`（非 `run_preset_loop()`），传入 eval agent 专用 system_prompt + 受限 tool 集合
- [ ] 5.6 实现 handler 的阻塞语义：`asyncio.wait_for` 超时（默认 120s），`interrupt_check` 回调传播主流程取消信号，独立 `IterationBudget`（max_total=10）
- [ ] 5.7 创建 `backend/prompts/eval_agent/system.md`：默认 system prompt 模板，指导 LLM 观察 browser_snapshot → browser_eval JS → 判断完成
- [ ] 5.8 创建 `backend/prompts/eval_agent/js_lib.js`：内置 JS 原子函数（`isVisible(selector)`、`retryUntil(fn, maxAttempts)`、`waitForElement(selector, timeout)`）
- [ ] 5.9 在 `backend/engine/_harness/tools.py` 中定义 `EVAL_AGENT_TOOL` schema（description 含"会额外消耗 LLM token"提示），注册到 `get_all_tools()`
- [ ] 5.10 实现 eval agent 的 CSV 落盘逻辑：仅在 `output_dir` 可用时写入 `{output_dir}/eval_result.csv`（chat 模式下不可用则跳过）
- [ ] 5.11 实现 eval agent 的 pipeline yaml 写入逻辑：仅在 `pipeline_path` 可用时追加步骤记录（chat 模式下不可用则跳过）

## 6. 调整 planner prompt

- [ ] 6.1 修改 planner prompt（`backend/prompts/` 中相关模板），添加 eval agent 启动条件指导：ops 搞不定 / 需要批量收集信息时启动 eval_agent
- [ ] 6.2 确保 prompt 中明确 eval_agent 的入参格式（purpose + snapshot）

## 7. 集成验证

- [ ] 7.1 运行完整测试套件：`pytest backend/tests/ -v --timeout=120`
- [ ] 7.2 手动测试：启动应用，在 chat 模式中验证 `file_read`、`file_write`、`format_convert` 三个 tool 可被 LLM 正常调用
- [ ] 7.3 手动测试：验证 `ctx.eval` / `ctx.type` / `ctx.click` 通过 ToolContext 正常工作
- [ ] 7.4 确认 toolgen-test 分支未被修改，所有 tool gen 代码完整保留
