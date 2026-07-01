## 1. 后端清理

- [ ] 1.1 删除 `backend/src/yak_browser_use/engine/_lifecycle/guardian.py` 整个文件
- [ ] 1.2 修改 `runner_preset.py`：移除 guardian import（`ApprovalResult`）；移除第 272-313 行的审批门控代码块；移除 `run_pipeline` 函数的 `guardian=None` 参数（函数 docstring 同步更新）
- [ ] 1.3 修改 `routes.py`：从 `api_run`（第 249-254、272 行）中移除 guardian import/调用（`create_guardian_from_frontmatter`、`inject_guardian_config_to_steps`、`guardian=guardian`）；从 `api_restart_pipeline`（第 775-780、803 行）中移除相同代码；删除 `ReviewStepRequest` 模型类（第 83-85 行）；删除整个 `api_review_step` 端点（第 866-875 行）
- [ ] 1.4 **不修改** `test_ops.py` — `test_circuit_breaker_triggers` 和 `test_circuit_breaker_resets_on_success` 测试的是 `ToolContext`（`CircuitBreakerMixin`），与 Guardian 类无关，保持不动

## 2. 前端清理

- [ ] 2.1 修改 `pipelineStore.ts` — **reviewMode 移除**：移除 `reviewMode` 字段（第 43 行 interface、第 85 行 init）、移除 `setReviewMode` action（第 56 行 interface、第 249 行 impl）、移除 `run()` 中 `review_mode` YAML 注入逻辑（第 160-163 行）
- [ ] 2.2 修改 `pipelineStore.ts` — **pendingReview 彻底移除**：移除 `PendingReviewData` interface（第 23-28 行）及 import（第 7 行）；移除 `pendingReview` 字段（第 42 行 interface、第 84 行 init）；移除 `setPendingReview`、`reviewApprove`、`reviewReject`（interface 第 48-49、57 行，impl 第 213-229、250 行）；移除 `run()` 中 `resp.status === 'interrupted' && resp.data?.pending_review` 分支（第 175-185 行）
- [ ] 2.3 修改 `SettingsTab.tsx`：移除 reviewMode 相关的整个 set-group（第 51-66 行），包括 `reviewMode` 的 store 读取（第 17 行）
- [ ] 2.4 修改 `LogTab.tsx`：移除 pendingReview 审批卡片 UI（第 87-136 行区域）；移除 `pendingReview`、`reviewApprove`、`reviewReject` 的 store 读取（第 16、29-30 行）
- [ ] 2.5 修改 `ExecTab.tsx`：移除 pendingReview 审批卡片 UI（第 63-69 行区域）；移除 `pendingReview`、`reviewApprove`、`reviewReject` 的 store 读取
- [ ] 2.6 修改 `App.tsx`：移除 pendingReview 侧边栏指示点（第 151 行）

## 3. i18n 清理

- [ ] 3.1 修改 `zh-CN.json`：移除 `reviewMode`、`manual`、`auto`、`none`、`manualDesc`、`autoDesc`、`noneDesc`、`review` 等翻译 key
- [ ] 3.2 修改 `en.json`：同上，移除对应英文翻译 key

## 4. 验证

- [ ] 4.1 运行后端测试确认无导入错误：`cd backend && pytest tests/ -x --timeout=60`
- [ ] 4.2 运行前端类型检查确认无类型错误：`cd electron && npx tsc --noEmit`
