## Why

Guardian 审批门控 + reviewMode 审查模式是一套从未真正工作过的功能。前端设置页提供了 human/llm/none 三个选项，但 human 和 llm 在后端行为完全一致；审批端点 `api_review_step` 返回 501 Not Implemented；电路断路器（STALE）的 `record_failure` 无任何调用者；内容校验 `validate_output` 同样无人调用。

与此同时，项目的安全模型实际上由以下机制保障：PathGuard 工作区隔离、ParamRef 服务端凭据解析、敏感数据脱敏、工具调用护栏（guardrails）和迭代预算。Guardian 的 step 级审批对真正的安全风险（如 `browser_eval_js` 任意 JS 执行、`browser_goto` 内网访问）毫无帮助，却增加了大量死代码和认知负担。

因此需要彻底移除 Guardian 全家桶及相关前端 UI，清理死代码，降低维护成本。

## What Changes

### 后端

- **删除 `guardian.py` 整个文件** — Guardian 类、ApprovalResult、StepReviewInterrupt、所有辅助函数（`create_guardian_from_frontmatter`、`inject_guardian_config_to_steps`、`llm_review_extra_ops`、`step_guard`、`split_by_guard_result`）
- **修改 `runner_preset.py`** — 移除第 272-313 行的审批门控代码块；移除 `run_pipeline` 函数的 `guardian=None` 参数
- **修改 `routes.py`** — `api_run` 和 `api_restart_pipeline` 中的 guardian import 和调用（`create_guardian_from_frontmatter`、`inject_guardian_config_to_steps`、`guardian=guardian`）；删除 `ReviewStepRequest` 模型类；删除整个 `api_review_step` 端点
- **不删除 `test_ops.py` 中的 `test_circuit_breaker_*` 测试** — 注：这些测试测实为 `ToolContext`/`CircuitBreakerMixin` 的 circuit breaker，与 Guardian 类无关，保持不动
- **修改 `test_api_routes.py`** — 删除 `test_review_not_implemented` 测试（测试被删除的 501 端点）
- **修改 `types.ts`** — 删除 `reviewPipeline` IPC 声明
- **修改 `ExecTab.tsx`** — 移除 `SuggestionsPanel` import + 组件渲染

### 前端

- **修改 `SettingsTab.tsx`** — 移除 reviewMode 相关的整个 set-group（第 51-66 行），包括 `reviewMode` 的 store 读取（第 17 行）
- **修改 `pipelineStore.ts`** — 移除 `reviewMode` 字段（第 43、85 行）、移除 `setReviewMode` action（第 56、249 行）、移除 `run()` 方法中的 `review_mode` YAML 注入逻辑（第 160-163 行）
- **彻底移除 `pendingReview` 相关死代码**：
  - `pipelineStore.ts`：移除 `pendingReview` 字段（第 42、84 行）、`setPendingReview` action（第 57、250 行）、`PendingReviewData` interface（第 23-28 行）、`PendingReviewData` import（第 7 行）、`reviewApprove`/`reviewReject` actions（第 48-49、213-229 行）、`run()` 中对 `resp.data?.pending_review` 的响应处理分支（第 175-185 行）
  - `LogTab.tsx`：移除 pendingReview 审批卡片 UI（第 87-136 行区域）、移除 `pendingReview`、`reviewApprove`、`reviewReject` 的 store 读取（第 16、29-30 行）
  - `ExecTab.tsx`：移除 pendingReview 审批卡片 UI（第 63-69 行区域），移除 `pendingReview`、`reviewApprove`、`reviewReject` 的 store 读取
  - `App.tsx`：移除 pendingReview 侧边栏指示点（第 151 行）

### i18n

- **修改 `zh-CN.json` 和 `en.json`** — 移除 reviewMode 相关翻译 key（`reviewMode`、`manual`、`auto`、`none`、`manualDesc`、`autoDesc`、`noneDesc`、`review` 等）

### 保留

- **`version_manager.py` 的 STALE 逻辑** — 属于独立模块，与 Guardian 无关
- **`test_ops.py` 中的 `test_circuit_breaker_*` 测试** — 测的是 `ToolContext`（`CircuitBreakerMixin`），与 Guardian 无关

## Capabilities

### New Capabilities

无新增能力。

### Modified Capabilities

无既有能力的行为变化。本次只做删除，不改动任何功能逻辑。

## Impact

- **后端**：删除 `backend/src/yak_browser_use/engine/_lifecycle/guardian.py`；修改 `runner_preset.py`（移除审批门控）；修改 `routes.py`（移除 guardian 导入/调用和 review 端点）；修改 `test_api_routes.py`（删除 review 端点测试）
- **前端**：修改 `SettingsTab.tsx`（移除 reviewMode UI）；修改 `pipelineStore.ts`（移除 reviewMode + reviewMode 状态和 YAML 注入 + 彻底移除 pendingReview）；修改 `LogTab.tsx` 和 `ExecTab.tsx`（移除审批卡片 + DiffView/SuggestionsPanel）；修改 `App.tsx`（移除 pendingReview 侧边栏指示点）；修改 `apiClient.ts` + `types.ts`（移除 reviewPipeline）；修改 `LogTab.tsx` 的 `getStepStatus` 移除 `review` 状态分支
- **i18n**：修改 `zh-CN.json` 和 `en.json`（移除 reviewMode 翻译 key）
- **API**：删除 `POST /api/pipeline/{thread_id}/review` 端点
- **测试**：`test_ops.py` 中的 `test_circuit_breaker_*` 测试**不修改**（测的是 `ToolContext`/`CircuitBreakerMixin`，与 Guardian 无关）
