## 1. 基础架构：统一 runs/ 目录

- [ ] 1.1 修改 `WorkspaceManager.create_run()`：新增 `exec_type` 参数。preset 类型生成 `YYYYMMDD_HHMMSS`，agent 类型生成 `recovery_YYYYMMDD_HHMMSS_hex`；preset 创建 `final/` 目录，agent 不创建；统一创建 `downloads/` 目录；`_run.json` 写入 `type` 字段
- [ ] 1.2 修改 `_looks_like_run_id()` 正则：同时匹配 `^\d{8}_\d{6}(_\d+)?$` 和 `^recovery_\d{8}_\d{6}_[0-9a-f]{6}$`
- [ ] 1.3 修改 `WorkspaceManager.detect_crashed_runs()`：读取 `_run.json`，只处理 `meta.get("type") == "preset"` 的 run
- [ ] 1.4 修改 `SessionStore.new_session()`：调用 `WorkspaceManager.create_run("agent")` 确保 `runs/{id}/downloads/` 目录创建
- [ ] 1.5 修改 `PlaywrightBridge`：
  - 新增 `_run_id: str | None` 字段
  - 新增 `set_download_dir(pipeline_name, run_id)` 方法（替代旧 `set_download_pipeline`）
  - 修改 `_resolve_download_path()`：有 `_run_id` 时返回 `WORKSPACES_ROOT / pipeline_name / "runs" / run_id / "downloads"`，否则返回 None
  - 更新 `_set_page_download_behavior` 和 `_bind_download_fallback` 使用新逻辑（None 时跳过 CDP download behavior 设置）

## 2. Preset pipeline 清理 snapshot + 路径解析

- [ ] 2.1 修改 `engine_state.connect_chrome()`：不再在连接时绑定 browser 下载路径
- [ ] 2.2 修改 `run_pipeline()`：
  - 删除 `pipeline_path` 参数签名
  - 删除 L198-211 的 snapshot 拷贝逻辑（不再拷贝到 versions_dir 和 wm.root）
  - 删除 L437-459 的 VersionManager.create_version 调用
  - 新增开头调用 `bridge.set_download_dir(name, run_dir.name)`
- [ ] 2.3 修改 `_resolve_path()` 中 `downloads/` 前缀：直接返回 `run_dir / ref`，去掉旧 fallback
- [ ] 2.4 修改 `api_run`：
  - 删除 `snapshot_path` 生成和 `snapshot_path.write_text()`
  - 删除 `_snapshot_cleaned` 标志和 finally 里的错误清理逻辑
  - `_prepare_steps(pipeline_text, snapshot_path)` → 直接 parse pipeline_text
  - 不再传 `pipeline_path=snapshot_path` 给 run_pipeline
- [ ] 2.5 确认 `parse_pipeline()` 签名无 `pipeline_path` 参数（当前已是最简，无需改动）

## 3. Preset recovery 实现

- [ ] 3.1 修改 `engine/state.py` RunContext：新增 `failure_context: dict | None = None` 字段
- [ ] 3.2 修改 `runner_preset.py` terminal failure 路径：
  - 收集 failure_context（step_index、step_name、step_def、error_code、error_message、step_result 截断 10K、execution_tree、completed_steps），设 final_status="needs_recovery"
  - 不 set_status("failed")，break 退出 while
- [ ] 3.3 修改 `runner_preset.py` finalize 逻辑：final_status=="needs_recovery" 时跳过 set_status("failed")、fill_final
- [ ] 3.4 新增 `api/routes.py` `_truncate_step_result(result, max_chars=10000)` 辅助函数：JSON 序列化后截断
- [ ] 3.5 新增 `api/routes.py` `_build_recovery_prompt(failure_context, attempt)` 函数：按 spec 格式格式化
- [ ] 3.6 新增 `api/routes.py` 常量 `MAX_RECOVERY_ATTEMPTS = 3`
- [ ] 3.7 修改 `api_run` recovery 循环：
  1. 从 `WORKSPACES_ROOT / pipeline_name / "pipeline.yaml"` 重新读取+parse yaml
  2. 调用 `service.new_session()` 创建独立 session（带 recovery_ 前缀 run_id）
  3. 调用 `bridge.set_download_dir(name, new_session_run_id)` 绑定 agent session 下载路径
  4. 调用 `process_chat_message(prompt)` 发送 recovery prompt
  5. 等待 agent 完成（pipeline_finish → budget.exhaust）
  6. 检查 agent 最后一次 tool_call 是否为 `pipeline_finish` 且 status="failed" → 是则 break（不 re-run）
  7. 从 pipeline.yaml 重新 parse → 调用 `run_pipeline()` 新建 run_dir 重跑
  8. 成功则清除 failure_context 并 break
- [ ] 3.8 处理 recovery 耗尽：循环结束后 if `ctx.failure_context is not None` → set_status("failed") + return status="failed"

## 4. 验证与测试

- [ ] 4.1 手动测试：运行一个预设会因选择器错误失败的 preset pipeline，验证 recovery session 被自动创建（带 `recovery_` 前缀）、agent 能访问 failure_context
- [ ] 4.2 手动测试：验证 agent 调 edit_pipeline 后 re-run 从 step 0 重跑（从 pipeline.yaml 读取修改后的 yaml）
- [ ] 4.3 手动测试：验证 downloads/ 文件被写入 `runs/{run_id}/downloads/`（preset）和 `runs/{recovery_...}/downloads/`（agent）
- [ ] 4.4 手动测试：验证 MAX_RECOVERY_ATTEMPTS 耗尽后最终 status="failed"
- [ ] 4.5 手动测试：验证 recovery session 独立出现在 session 列表（带 recovery_ 前缀）
- [ ] 4.6 手动测试：验证 step_result > 10K 字符时自动截断
- [ ] 4.7 手动测试：验证 agent 调 pipeline_finish(status="failed") 时 recovery loop 立即终止
- [ ] 4.8 手动测试：验证 cleanup_old_runs 能正确清理 preset + agent（recovery_ 前缀）两种 run
- [ ] 4.9 手动测试：验证 detect_crashed_runs 只标记 preset run，跳过 agent run
- [ ] 4.10 验证：`versions/` 目录不再有新的快照写入
- [ ] 4.11 验证：`api_restart_pipeline` 从 pipeline.yaml 读取成功，不依赖 VersionManager

## 5. 前端适配（可选 / 后续）

- [ ] 5.1 pipelineStore 适配 `_run.json` 中 `type` 字段：前端可据此区分 preset run 和 agent session（低优先级，currentRunId/runId 仍用 preset run_id）
- [ ] 5.2 如有需要，session 列表 UI 显示 recovery session 前缀标识
