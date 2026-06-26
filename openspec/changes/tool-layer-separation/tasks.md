## 1. 底层工具语义变更

- [ ] 1.1 `registry.py` — `_file_read_handler` 改为仅返回元信息：`{"ok": True, "path": "...", "size": <bytes>, "encoding": "utf-8"}`，不调 `file_read` 获取内容
- [ ] 1.2 `registry.py` — `_file_write_handler` 传递 `ctx.pipeline_name`，增加 workspace 沙箱检查：根目录写入拒绝，子目录放行，返回 `{"ok": True, "path": "...", "size": <bytes>}`
- [ ] 1.3 `registry.py` — `_format_convert_handler` 改为仅返回元信息：`{"ok": True, "source": "...", "target": "...", "source_fmt": "...", "target_fmt": "..."}`
- [ ] 1.4 `_path_utils.py` — `validate_path` 新增 `pipeline` 参数时解析到 `WORKSPACES_ROOT/<pipeline>/<path>`

## 2. read_data 新工具

- [ ] 2.1 `tools/read_data.py` — 新建，实现 `read_data(path, limit=20, offset=0, encoding, convert_to, source_key)`，内部串联 `file_read` → `format_convert`（如需）→ limit/offset 截断 → 返回
- [ ] 2.2 `read_data` 校验：`limit` 禁止 0 或负值，`offset` 越界处理
- [ ] 2.3 `registry.py` — 注册 `read_data` tool schema 含 `path`(required)、`limit`(optional, default=20)、`offset`(optional, default=0)、`encoding`(optional)、`convert_to`(optional)、`source_key`(optional)，handler 传递 `ctx.pipeline_name`

## 3. 工具合并与重命名

- [ ] 3.1 `pipeline_tools.py` — 新建 `pipeline_view` 函数：无参调用 `pipeline_list` 逻辑，有 `name` 参数调用 `pipeline_load` 逻辑并返回完整 `browser_ops` 列表（非计数）
- [ ] 3.2 `pipeline_tools.py` — 修改 `pipeline_load` 返回完整 `browser_ops`（使用 `PipelineStore.ops_to_yaml()` 格式）
- [ ] 3.3 `registry.py` — 注册 `pipeline_view`，移除 `pipeline_load` 和 `pipeline_list` 注册
- [ ] 3.4 `_get_pipeline_dispatch()` — 移除 `pipeline_load`、`pipeline_list`，新增 `pipeline_view`
- [ ] 3.5 `pipeline_tools.py` — `pipeline_add_step` 新增 `op_type`（可选）和 `op_args`（可选）参数：有值时构造 browser_op 写入，无值时保持原有 outline placeholder 行为
- [ ] 3.6 `registry.py` — 移除 `record_step` 的 tool schema 注册及 handler
- [ ] 3.7 `registry.py` — `eval_js` 重命名为 `browser_eval_js`，tool schema description 调整
- [ ] 3.8 `registry.py` — `wait_for_download` 重命名为 `browser_wait_for_download`

## 4. pipeline_update_step 深路径

- [ ] 4.1 `pipeline_store.py` — `update_step` 方法新增 key 解析逻辑：regex `(\w+)\[(\d+)\]\.(.+)` 识别深路径，解析出 list_key / index / field
- [ ] 4.2 `pipeline_store.py` — 对深路径 key 执行字段级更新（仅修改目标元素的指定字段），value 为 list/object 时保持全量替换

## 5. 移除 eval_agent

- [ ] 5.1 `registry.py` — 移除 `eval_agent` 的 tool schema 注册及 `_eval_agent_handler`
- [ ] 5.2 `tool_executor.py` — 移除 `_handle_eval_agent`、`_extract_eval_summary`、`_write_eval_csv`、`_append_eval_to_pipeline`
- [ ] 5.3 移除 `engine/eval_agent.py` 模块
- [ ] 5.4 移除 `prompts/eval_agent/` 目录
- [ ] 5.5 检查移除 `conversation_loop.py` 中仅 `eval_agent` 使用的 `llm_call` 透传参数

## 6. Prompt 与文档更新

- [ ] 6.1 `prompts/guidance/tool_strategy.md` — 更新工具推荐：`eval_js` → `browser_eval_js`、`wait_for_download` → `browser_wait_for_download`、新增 `read_data` 推荐及 limit/offset 渐进式用法、移除 `eval_agent` 引用
- [ ] 6.2 `prompts/chat/system.md` — 更新工具列表分类描述，反映新的三层架构（底层工具 exit-code-only 语义说明）

## 7. 测试更新

- [ ] 7.1 `tests/test_registry.py` — 更新工具数量断言，验证新工具存在、移除工具不存在、底层工具 schema 仍注册
- [ ] 7.2 `tests/test_pipeline_tools.py` — 新增 `pipeline_view` 测试（无参列表、有参详情、不存在行为）、`pipeline_add_step` 合并 op_type 测试、`pipeline_update_step` 深路径测试
- [ ] 7.3 `tests/test_file_io.py` — 新增 `file_write` 沙箱测试（子目录可写、根目录被拒、无 pipeline 降级）；新增 `file_read` exit-code 测试；新增 `read_data` 渐进式披露测试、source_key 测试
- [ ] 7.4 运行全量测试套件确认无回归
