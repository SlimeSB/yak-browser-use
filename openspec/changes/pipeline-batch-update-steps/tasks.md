## 1. 核心实现

- [ ] 1.1 修改 `pipeline_tools.py` 中的 `pipeline_update_step` 函数签名：新增 `steps_updates: dict | None = None`、`step_name: str | None = None`、`updates: dict | None = None` 参数
- [ ] 1.2 添加兼容逻辑：当 `step_name` + `updates` 被传入且 `steps_updates` 为空时，自动转换为 `{step_name: updates}` 格式
- [ ] 1.3 批量更新逻辑：遍历 `steps_updates`，逐条调用 `_get_store().update_step()`，收集错误
- [ ] 1.4 错误处理：如果任何 step 更新失败，返回错误汇总，不写盘；全部成功才调 `_write_via_edit_pipeline`
- [ ] 1.5 更新 `registry.py` 中 `_PIPELINE_SCHEMAS["pipeline_update_step"]` 的 description 和 properties，说明 `steps_updates` 字典格式，标注 `step_name` 和 `updates` 为兼容旧接口
- [ ] 1.6 `required` 从 `["pipeline_name", "step_name", "updates"]` 改为 `["pipeline_name"]`

## 2. 验证与收尾

- [ ] 2.1 运行现有 pipeline 相关测试确认不破坏
- [ ] 2.2 手动验证旧接口调用（`step_name` + `updates`）仍正常工作
