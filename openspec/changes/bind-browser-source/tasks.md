## 1. 准备与基础改造

- [ ] 1.1 从 `_BROWSER_OPS` 列表中移除 `"source"`，确保循环不会为 source 注册通用 handler
- [ ] 1.2 在 executor.py `execute_browser_op` source 分支中，将 `strip_styles` 默认值从 `False` 改为 `True`（line 208）

## 2. 核心实现

- [ ] 2.1 在 registry.py 的 `_build_registry_impl` 中，循环结束后单独注册 `browser_source` 的 schema（更新 description + 添加 `output_to` 为 required parameter，注意使用 `output_to` 而非 `bind`，因为通用 bind 机制会在 dispatch 前弹出 bind）
- [ ] 2.2 编写 `_source_handler` 函数：a) 验证 `output_to` 存在且非空（不存在返回错误）b) 调用 `execute_browser_op("source", args, bridge)` c) 从 result 中 pop `html` d) 将 html 写入 `ctx.shared_store[output_to]` e) 返回只含元信息和 guidance 的 result dict（包含 output_to key、size、note 字段）
- [ ] 2.3 在 tool_executor.py `_apply_heavy_data_filter` 中删除 `if fn_name == "browser_source":` 分支（lines 470-483）
- [ ] 2.4 更新 `tool_strategy.md` 第 10 行 `browser_source` 描述，明确标注 HEAVY + 必须 output_to + 下一步用 data_browse
- [ ] 2.5 更新 `system.md` 第 76 行提及 browser_source 的提示文本

## 3. 验证与收尾

- [ ] 3.1 删除 `test_orchestration_filter.py` 中针对 `_apply_heavy_data_filter` browser_source 分支的测试
- [ ] 3.2 删除 `test_integration_agent_reform.py` 中 `browser_source integration` 测试段（lines 188-210）
- [ ] 3.3 运行 `pytest backend/tests/` 确认全部通过
- [ ] 3.4 手动验证：连接浏览器后执行"获取页面源代码"任务，确认 HTML 不进入 context、返回值含 size 和 data_browse 指导
