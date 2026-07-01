## 1. 后端清理

- [x] 1.1 删除 `backend/src/yak_browser_use/engine/_lifecycle/guardian.py` 整个文件
- [x] 1.2 修改 `runner_preset.py`：移除 guardian import（`ApprovalResult`）；移除第 272-313 行的审批门控代码块；移除 `run_pipeline` 函数的 `guardian=None` 参数（函数 docstring 同步更新）
- [x] 1.3 修改 `routes.py`：从 `api_run` 中移除 guardian import/调用；从 `api_restart_pipeline` 中移除相同代码；删除 `ReviewStepRequest` 模型类；删除整个 `api_review_step` 端点
- [x] 1.4 **不修改** `test_ops.py` — `test_circuit_breaker_triggers` 和 `test_circuit_breaker_resets_on_success` 测试的是 `ToolContext`（`CircuitBreakerMixin`），与 Guardian 类无关，保持不动
- [x] 1.5 修改 `test_api_routes.py`：删除 `TestPipelineEndpoints.test_review_not_implemented` 测试（测试已删除的 501 端点）

## 2. 前端清理

- [x] 2.1 修改 `pipelineStore.ts` — **reviewMode 移除**：移除 `reviewMode` 字段（第 43 行 interface、第 85 行 init）、移除 `setReviewMode` action（第 56 行 interface、第 249 行 impl）、移除 `run()` 中 `review_mode` YAML 注入逻辑（第 160-163 行）
- [x] 2.2 修改 `pipelineStore.ts` — **pendingReview 彻底移除**：移除 `PendingReviewData` interface 及 import；移除 `pendingReview` 字段；移除 `setPendingReview`、`reviewApprove`、`reviewReject`；移除 `run()` 中 `pending_review` 响应处理分支；`getStepStatus` 签名简化为 `(events, name)`，移除 `'review'` 状态返回值
- [x] 2.3 修改 `SettingsTab.tsx`：移除 reviewMode 相关的整个 set-group（第 51-66 行），包括 `reviewMode` 的 store 读取（第 17 行）
- [x] 2.4 修改 `LogTab.tsx`：移除 pendingReview 审批卡片 UI + DiffView import + review 状态分支；移除 `pendingReview`/`reviewApprove`/`reviewReject`/`useState` 等 store 读取和 react hooks；移除 `step_review_required` 事件相关逻辑
- [x] 2.5 修改 `ExecTab.tsx`：移除 `SuggestionsPanel` import + 组件渲染；移除 `pendingReview`/`reviewApprove`/`reviewReject` 的 store 读取
- [x] 2.6 修改 `App.tsx`：移除 pendingReview 侧边栏指示点
- [x] 2.7 修改 `apiClient.ts`：移除 `reviewPipeline` 函数（第 91-96 行）
- [x] 2.8 修改 `types.ts`：移除 `reviewPipeline` IPC 声明

## 3. i18n 清理

- [x] 3.1 修改 `zh-CN.json`：移除 `reviewMode`、`manual`、`auto`、`none`、`manualDesc`、`autoDesc`、`noneDesc`、`review` 等翻译 key
- [x] 3.2 修改 `en.json`：同上，移除对应英文翻译 key

## 4. 验证

- [x] 4.1 运行后端测试确认无导入错误：1010 passed
- [x] 4.2 运行前端类型检查确认无类型错误：`npx tsc --noEmit` 通过
