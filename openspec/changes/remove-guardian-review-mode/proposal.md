## Why

Guardian 审批门控 + reviewMode 审查模式是一套从未真正工作过的功能。前端设置页提供了 human/llm/none 三个选项，但 human 和 llm 在后端行为完全一致；审批端点 `api_review_step` 返回 501 Not Implemented；电路断路器（STALE）的 `record_failure` 无任何调用者；内容校验 `validate_output` 同样无人调用。

与此同时，项目的安全模型实际上由以下机制保障：PathGuard 工作区隔离、ParamRef 服务端凭据解析、敏感数据脱敏、工具调用护栏（guardrails）和迭代预算。Guardian 的 step 级审批对真正的安全风险（如 `browser_eval_js` 任意 JS 执行、`browser_goto` 内网访问）毫无帮助，却增加了大量死代码和认知负担。

因此需要彻底移除 Guardian 全家桶及相关前端 UI，清理死代码，降低维护成本。

## What Changes

- **移除 `guardian.py` 整个文件** — Guardian 类、ApprovalResult、StepReviewInterrupt、所有辅助函数（`create_guardian_from_frontmatter`、`inject_guardian_config_to_steps`、`llm_review_extra_ops`、`step_guard`、`split_by_guard_result`）
- **移除 `runner_preset.py` 中的 Guardian approval gate** — 第 272-313 行的审批门控代码块
- **移除 `routes.py` 中的 Guardian 相关代码** — `api_run` 和 `api_restart_pipeline` 中的 guardian import 和调用，以及整个 `api_review_step` 端点
- **移除前端 reviewMode 设置** — `SettingsTab.tsx` 中的 reviewMode 三选一 UI
- **移除前端 pipelineStore 中的 reviewMode 状态** — `reviewMode` 字段、`setReviewMode` action、以及运行时的 `review_mode` YAML 注入逻辑
- **移除前端审批 UI** — `LogTab.tsx` 和 `ExecTab.tsx` 中的 pendingReview 审批卡片
- **移除 i18n 翻译 key** — reviewMode 相关的翻译条目
- **保留 `version_manager.py` 的 STALE 逻辑** — 属于独立模块，与 Guardian 无关

## Capabilities

### New Capabilities

无新增能力。

### Modified Capabilities

无既有能力的行为变化。本次只做删除，不改动任何功能逻辑。

## Impact

- **后端**：删除 `backend/src/yak_browser_use/engine/_lifecycle/guardian.py`；修改 `runner_preset.py`（移除审批门控）；修改 `routes.py`（移除 guardian 导入/调用和 review 端点）
- **前端**：修改 `SettingsTab.tsx`（移除 reviewMode UI）；修改 `pipelineStore.ts`（移除 reviewMode 状态和 YAML 注入）；修改 `LogTab.tsx` 和 `ExecTab.tsx`（移除审批卡片）；修改 `App.tsx`（移除 pendingReview 侧边栏指示点）
- **i18n**：修改 `zh-CN.json` 和 `en.json`（移除 reviewMode 翻译 key）
- **API**：删除 `POST /api/pipeline/{thread_id}/review` 端点
- **测试**：`test_ops.py` 中的 circuit_breaker 测试需要清理
