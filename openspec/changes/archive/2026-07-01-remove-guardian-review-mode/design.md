## 背景

当前代码库中存在一套 Guardian 审批门控系统，包含：

- **后端**：`guardian.py`（Guardian 类、ApprovalResult、辅助函数）、`runner_preset.py` 中的审批门控代码块、`routes.py` 中的 guardian 导入/调用和 `api_review_step` 端点
- **前端**：`SettingsTab.tsx` 中的 reviewMode 三选一 UI、`pipelineStore.ts` 中的 reviewMode 状态和 YAML 注入逻辑、`LogTab.tsx` 和 `ExecTab.tsx` 中的 pendingReview 审批卡片
- **i18n**：zh-CN.json 和 en.json 中的 reviewMode 翻译 key

这套系统从未真正工作过（审批端点返回 501），且对项目的安全模型无实际贡献——真正的安全保障来自 PathGuard、ParamRef、敏感数据脱敏等机制。

## 目标 / 非目标

**目标：**
- 彻底移除 Guardian 审批门控系统及相关代码
- 清理前端 reviewMode 设置 UI 和审批卡片
- 清理 i18n 翻译条目
- 删除 `api_review_step` 端点
- **不修改** `test_ops.py` 中的 `test_circuit_breaker_*` 测试（与 Guardian 无关）

**非目标：**
- 不改动 `version_manager.py` 的 STALE 逻辑（独立模块）
- 不引入新的安全机制
- 不改动项目的实际安全保护措施（PathGuard、ParamRef 等）
- 不改动前端其他设置项

## 关键决策

| 决策 | 方案 | 原因 |
|------|------|------|
| 删除 vs 注释 | 直接删除 | 死代码无保留价值，git history 可回溯 |
| `guardian.py` 整体删除 | 整个文件移除 | 所有函数均无外部调用者 |
| `api_review_step` 端点 | 删除路由注册 | 返回 501 的无用端点 |
| `ReviewStepRequest` 模型 | 删除 | 仅被该端点使用 |
| 前端 pendingReview 相关 | **彻底移除**：store 字段 + 类型 + actions + UI，全部删除 | `pendingReview` 非空的唯一路径是后端返回 `pending_review`，审批门控移除后此数据不可能再产生，保留只会增加无源码债 |
| `run_pipeline` 函数签名 | 同步移除 `guardian=None` 参数 | 审批门控已不传此参数 |
| 测试清理 | **不删除** `test_ops.py` 中的 `test_circuit_breaker_*` 测试；**删除** `test_api_routes.py` 中的 `test_review_not_implemented` | circuit_breaker 测试与 Guardian 无关；review 端点已删除，其测试也应移除 |
| `SuggestionsPanel` | 随 pendingReview 一并移除 | 仅在 ExecTab 的 pendingReview 场景使用 |
| `DiffView` import in LogTab | 随 pendingReview 一并移除 | 仅在 LogTab 的 pendingReview 场景使用 |
| `types.ts` IPC 声明 | 同步移除 `reviewPipeline` | apiClient 中对应函数已删除 |
| `getStepStatus` 签名 | 移除 `pendingReview` 参数和 `'review'` 状态返回值 | pendingReview 已不存在，review 状态不再有意义 |

## 风险 / 权衡

- **低风险**：所有被删除的代码均为死代码或从未生效的功能
- **兼容性**：前端 `pendingReview` 字段、类型、actions 全部彻底移除。由于审批门控移除后后端不再返回 `pending_review` 数据，移除不会导致运行时错误
- **回滚**：如果发现遗漏依赖，git revert 即可恢复

## 迁移计划

1. 删除 `guardian.py` 文件
2. 修改 `runner_preset.py`：移除 guardian import 和审批门控代码块；移除 `run_pipeline` 函数的 `guardian=None` 参数
3. 修改 `routes.py`：移除 guardian import/调用、`ReviewStepRequest`、`api_review_step`（覆盖 `api_run` 和 `api_restart_pipeline`）
4. 修改 `test_api_routes.py`：删除 `test_review_not_implemented` 测试
5. 修改前端 `pipelineStore.ts`：
   - 移除 `reviewMode` 字段 + `setReviewMode` + YAML 注入
   - 移除 `pendingReview` 字段 + `PendingReviewData` 类型 + `setPendingReview` + `reviewApprove` + `reviewReject` + `pending_review` 响应处理分支
   - `getStepStatus` 签名简化：移除 `pendingReview` 参数 + `'review'` 状态
6. 修改前端 `SettingsTab.tsx`：移除 reviewMode UI
7. 修改前端 `LogTab.tsx`：移除 pendingReview 审批卡片 + DiffView import + store 读取 + review 状态分支
8. 修改前端 `ExecTab.tsx`：移除 pendingReview SuggestionsPanel + store 读取
9. 修改前端 `App.tsx`：移除 pendingReview 侧边栏指示点
10. 修改 `apiClient.ts`：移除 `reviewPipeline` 函数
11. 修改 `types.ts`：移除 `reviewPipeline` IPC 声明
12. 修改 i18n 文件（zh-CN.json + en.json）：移除 reviewMode 等翻译 key
13. **不修改** `test_ops.py`（`test_circuit_breaker_*` 测的是 ToolContext，与 Guardian 无关）

无需数据迁移，无需上线步骤，PR 合并即可。

## 待确认问题

无。
