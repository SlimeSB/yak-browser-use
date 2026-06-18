## 1. 准备与基础改造

- [ ] 1.1 创建 `backend/engine/ops.py`：实现 `ToolContext` 类，包含浏览器 ops（wait/evaluate/click/fill/snapshot/screenshot/source）、数据 ops（save_json/load_json/save_csv/load_csv/save_bytes）、CDP 逃逸口（cdp）、域名白名单（allowed_domains）、连续失败熔断器（MAX_FAILS=3）、危险模块列表（DANGEROUS_MODULES）
- [ ] 1.2 创建 `backend/prompts/tool_gen/generate.md`：LLM 生成 prompt 模板，含函数签名约束（`async def {func_name}(ctx: ToolContext, params: dict) -> dict`）、ToolContext API 完整文档、few-shot 示例（提取表格、验证码识别）、错误反馈格式、危险模块禁止声明
- [ ] 1.3 删除废弃文件：`backend/tools/base.py`、`backend/tools/registry.py`、`backend/tools/schemas.py`，验证无 import 断裂

## 2. Inline 生成核心流程

- [ ] 2.1 修改 `backend/engine/runner_preset.py`：`_execute_tool_step_with_guardian` 新增 `llm_call` 参数；`run_pipeline` 调用处传入 `llm_call=llm_call`
- [ ] 2.2 在 `runner_preset.py` 中实现 `_inline_generate_and_execute()` 函数：确保 `tools_dir` 存在（`mkdir(parents=True, exist_ok=True)`）→ 捕获页面状态（`cdp_helpers.capture_snapshot_simplified()` + `cdp_helpers.js("window.location.href")`）→ 构建 prompt → 调 `llm_call` → 正则提取代码块 → AST 安全检查 → `py_compile` 语法检查 → 注入外壳写入 `userdata/workspaces/{pipeline}/tools/_PH-{name}.py` → 创建 ToolContext 执行 → 成功则 rename + schema 注册 → 失败则重试（≤3 次）
- [ ] 2.3 实现 `_check_safe_imports(code: str) -> str | None`：AST 遍历检查危险模块导入，危险模块列表从 `ToolContext.DANGEROUS_MODULES` 读取
- [ ] 2.4 实现 `_extract_code_from_response(completion: str) -> str`：正则提取 ` ```python ... ``` ` 代码块，fallback 为整段 completion
- [ ] 2.5 修改 `backend/engine/_lifecycle/tool_runner.py`：`load_and_call` 改为注入 `ToolContext` 实例作为 `ctx` 参数（替代旧的 `cdp_helpers`），并透传工具函数的返回值（`dict`）而非丢弃后返回 `{"ok": True}`。已有 `_PH-` 工具若仍接收 `cdp_helpers` 参数，通过检测函数签名兼容注入（`ctx` 优先，`cdp_helpers` 作为 fallback）

## 3. Chat 模式支持

- [ ] 3.1 修改 `backend/engine/_harness/tool_executor.py`：`_execute_single_tool_call` 的 `else` 分支检测 `fn_name.startswith("_PH-")`，触发 `_inline_generate_and_execute`（共用同一函数）
- [ ] 3.2 修改 `conversation_loop.py`：将 `llm_call` 沿 `execute_tool_calls_sequential` → `_execute_single_tool_call` → `execute_tool` 传递链下传，使 chat 模式下 inline 生成流程可调用 LLM。涉及 4 处签名变更：`execute_tool_calls_sequential` 新增 `llm_call` 参数、`_execute_single_tool_call` 新增 `llm_call` 参数、`execute_tool` 新增 `llm_call` 参数、`conversation_loop` 调用处传入 `llm_call`

## 4. Schema 自动注册

- [ ] 4.1 修改 `backend/engine/_lifecycle/tool_runner.py`：rename 后自动解析生成的 `.py` 文件函数签名和 docstring，构建 OpenAI function schema，加入动态注册表（内存 dict，keyed by `{pipeline_name}/{tool_name}`）
- [ ] 4.2 修改 `backend/engine/_harness/tools.py`：`get_all_tools()` 新增 `pipeline_name: str | None = None` 可选参数，返回时合并静态工具列表 + 动态注册表（按 pipeline_name 过滤）；更新 `test_harness_tools.py` 中受影响的断言

## 5. 旧工具迁移至 ToolContext

- [ ] 5.1 修改 `backend/tools/extract.py`：`extract_table`/`extract_list`/`extract_details` 改为接收 `ctx: ToolContext` 参数，内部调 `ctx.evaluate` + `ctx.save_json`，删除 `_save_output` 和 `CAPABILITIES`
- [ ] 5.2 修改 `backend/tools/data.py`：`filter_data`/`sort_data`/`deduplicate`/`map_fields` 改为接收 `ctx: ToolContext` 参数，内部调 `ctx.load_json` + `ctx.save_json`，删除 `_resolve_input_files`、`_load_records`、`_save_records`
- [ ] 5.3 修改 `backend/tools/adapters.py`：`csv_to_json`/`json_to_csv`/`apply_field_mapping` 改为接收 `ctx: ToolContext` 参数，内部调 `ctx.load_json` + `ctx.save_csv`，删除 `_resolve_input_files`、`_load_json_records`、`_output_name`、`_flatten_dict`

## 6. 兼容性标注

- [ ] 6.1 修改 `backend/utils/tool_cdp.py`：文件头部和类 docstring 添加 deprecated 标注，说明 allowed_domains + circuit breaker 已迁移到 ToolContext
- [ ] 6.2 确认 `backend/engine/executor.py` 中 `execute_tool` 的 `CAPABILITIES` 检查保留兼容，旧工具仍可通过旧路径调用

## 7. 测试

- [ ] 7.1 创建 `tests/test_ops.py`：ToolContext 各方法的单元测试（mock PlaywrightBridge），覆盖浏览器 ops、数据 ops、CDP 逃逸口（`ctx.cdp()`）、熔断器触发、域名白名单
- [ ] 7.2 创建 `tests/test_ops_safety.py`：`_check_safe_imports` 单元测试，覆盖所有 10 类危险模块、合法 import、语法错误代码
- [ ] 7.3 创建 `tests/test_ph_generation.py`：`_inline_generate_and_execute` 集成测试（mock llm_call 和 cdp_helpers），覆盖首次生成成功、生成失败重试、重试 3 次后终端失败、代码块提取、函数名约定（`_PH-crack-captcha` → `crack_captcha`，连字符→下划线）
- [ ] 7.4 运行现有测试套件 `pytest -x -q`，确保所有已有测试通过
