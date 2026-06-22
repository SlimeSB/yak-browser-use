# TODO

> 从各活跃 plan 中提取的未完成项。已归档 plan（`archive/`）的内容不再追踪。

---

## 后端

### 1. 多标签页管理
> 源自 `2026-06-13-agent-harness-conversation-loop` 遗留

CDP 层已有基础原语（`Target.createTarget` / `Target.attachToTarget` / `_target_id`），需补齐：

| 步骤 | 位置 | 说明 |
|------|------|------|
| CDP 事件监听 | `cdp/daemon.py` | 监听 `Target.attachedToTarget` / `Target.detachedFromTarget`，暴露当前激活 tab 的 targetId |
| conversation_loop 绑定 | `engine/_harness/conversation_loop.py` | 从 daemon 读取 targetId，传给 tool_executor |
| tool_executor attach | `engine/_harness/tool_executor.py` | 每次 op 执行前调 `Target.attachToTarget` |
| 新会话开标签页 | session 管理 | 调 `Target.createTarget("about:blank")` |

### 2. Snapshot Enhancement — a11y + progressive 收尾
> 源自 `2026-06-22_090000-snapshot-enhancement.md` — P0-P2 代码已完成，尚余验证 + 边缘情况

| 步骤 | 说明 | 工作量 |
|------|------|--------|
| a11y mode 验证 | stamping（DOM resolveNode）与 Playwright get_by_role 匹配率实测 | ~1d |
| a11y 空 name 定位 | 无 label 元素的 `exact=True` 行为确认 | ~0.5d |
| highlight overlay 渲染 | `_wait_for_highlight_render` + `ensure_highlights` 时序验证 | ~0.5d |
| progressive mode 边缘 | 容器策略方案 2/3（软深度限制 / 双层 ckey 统计）留后续 | ~1d |

### 3. 拆 `run_pipeline()` + Pipeline Hooks
> 源自 `2026-06-22_refactor-run-pipeline-and-fallback.md` — 设计已完成，未实施

| 步骤 | 说明 | 工作量 |
|------|------|--------|
| Phase 1: 拆函数 | 从 `runner_preset.py:run_pipeline()` while 循环提取 `_execute_single_step` / `_handle_success` / `_handle_failure` | ~1d |
| Phase 2: PipelineHooks | 新增 `PipelineHooks` dataclass + 调用点 guard | ~0.5d |
| Phase 3: Fallback to chat | 新建 `pipeline_fallback.py` + `ContextVar` 递归防护 | ~1d |

### 4. 统一数据引用层 — `{path}` 替代 `_source_key`
> 源自 `2026-06-22-unified-data-reference-layer.md` — 净删除 ~6 行

| 步骤 | 位置 | 说明 |
|------|------|------|
| 加 `{path}` 分支 | `_param_resolver.py` | fullmatch 模式，直接查 shared_store 裸数据 |
| 删 `_source_key` 分支 | `_param_resolver.py` | ~6 行 |
| `${}` 去 `.data` 约定 | `_param_resolver.py` | 补齐类型检查 + errors 追加 + 优先级 |
| 写路径改为裸数据 | `tool_executor.py:245-250` | `shared_store[key] = result` 不再包装 `{ok, data}` |
| 删 eval 独立写路径 | `tool_executor.py:386-391` | ~6 行 |
| 删 `fill_credential` | `utils/tool_cdp.py:48-51` | 无调用方 |

### 5. Message Compaction
> 源自 `generalization-roadmap.md` Phase 2 — 对话超过上下文窗口时自动压缩

| 步骤 | 说明 | 工作量 |
|------|------|--------|
| 阈值触发 | 消息数 > N 或 token > M 时触发 | ~0.5d |
| 压缩策略 | 保留 system prompt + 最近 k 轮，中间合成摘要 | ~1d |

### 6. 集成测试
> todo.md 原有项

需要真实 CDP/浏览器环境，编写 chat → 浏览器操作 → 导出的端到端测试。

---

## 前端 (TypeScript/Electron)

### 1. WebSocket 客户端 — 实时事件推送
> todo.md 原有项

后端已就绪：`api/routes.py` 提供 `/ws/events` 端点，事件类型包括 `chat.message` / `chat.tool_start` / `chat.tool_end` / `chat.error` / `session.state`。当前前端走 HTTP POST polling，需：
- Electron main process 加 WebSocket client
- 实时事件分发给 renderer（`ChatTab` 可展示 tool_start/tool_end 的流式更新）
- 断线重连
