## Why

当前聊天会话完全在内存中运行（`Service._active_session` 是全局单例），切换 Pipeline 或重启应用后聊天记录全部丢失。`_save_session_history()` 虽然写入磁盘但仅在 reset 时触发，且存储位置（`userdata/sessions/{id}.json`）与 Pipeline 工作区解耦，无法实现"切换工作区保留各自对话"。

已有的 Pipeline 工作区（`workspaces/{name}/`）下有完善的 runs/、versions/、tools/ 目录结构，但缺少 session/ 目录。引入会话持久化能实现：切换 Pipeline 不丢对话、重启恢复上下文、支持多会话历史回溯。

现在做是因为 Chat 模式已在实际使用，用户切换 Pipeline 后对话丢失影响体验；且当前 tool-data-flow 变更正添加 shared_store 等基础设施，趁架构变动期一起引入会话层改动，投入产出比高。

## What Changes

- **新增** `SessionStore` 类（`backend/workspace/session_store.py`）：按 Pipeline 工作区维度管理会话，读写 `workspaces/{pipeline_name}/session/` 目录
- **新增** `sessions.json` 索引文件：以 `{session_id: metadata}` dict 形式存储每个 Pipeline 下的会话元数据列表
- **修改** `Service`：`_active_session` 从单例改为 `_sessions: dict[str, SessionState]` 池，key 为 pipeline_name
- **修改** `Service.process_chat_message()`：每个对话回合结束后异步持久化当前 session
- **修改** `Service`：新增 `switch_session(pipeline_name)` 方法，切换时保存旧会话、切换到目标工作区的活跃会话
- **修改** `conversation_loop.py`：`run_conversation_loop()` 新增可选 `on_turn_complete` 回调，每回合完成后通知 Service 保存
- **新增** API 端点：`POST /api/session/new`、`POST /api/session/switch`、`GET /api/session/{pipeline_name}/list`、`GET /api/session/{pipeline_name}/{session_id}`
- **修改** Chat 模式中 `pipeline_edit` 工具：当 `_active_pipeline == "__chat__"` 且创建了 `pipeline.yaml` 时，自动将 session/ 目录迁移至新 Pipeline 工作区
- **新增** 默认 `__chat__` 工作区概念：无 Pipeline 绑定时的纯聊会话，存储在 `workspaces/__chat__/session/`
- **修改** 前端 `App.tsx`：切换 `activePreset` 时同步加载/清空会话；启动时按首个 Pipeline 或 `__chat__` 恢复
- **修改** 前端 `ChatTab.tsx`：新增会话列表面板（侧栏显示历史 session、创建新会话按钮）
- **修改** Preset 模式回退到 Chat 时：新建一个独立 session，不污染当前活跃会话

## Capabilities

### New Capabilities
- `session-persist`: 按 Pipeline 工作区维度的会话持久化，支持切换不丢、重启恢复、多会话历史管理
- `session-multi`: 每个 Pipeline 下可创建多个独立会话，支持切换和列表展示
- `session-auto-migrate`: `__chat__` 工作区中通过聊天创建 Pipeline YAML 后，自动将会话迁移到新工作区

### Modified Capabilities
- `preset-run`: Preset 模式执行异常回退到 Chat 时，新建独立 session 而非复用当前会话

## Impact

- **代码**：新增 `backend/workspace/session_store.py`（~60 行），修改 `backend/api/service.py`（~40 行）、`backend/api/routes.py`（~25 行）、`backend/engine/_harness/conversation_loop.py`（~10 行）、`electron/src/renderer/App.tsx`（~20 行）、`electron/src/renderer/components/tabs/ChatTab.tsx`（~50 行）
- **接口**：`Service.create_session()` 改为接受 `pipeline_name` 参数；`Service.get_session()` 改为 `get_session(pipeline_name)`；`run_conversation_loop()` 新增可选 `on_turn_complete` 参数；新增 3 个 API 端点
- **依赖**：无新增外部依赖
- **数据**：新增 `workspaces/{name}/session/` 目录结构；旧 `userdata/sessions/` 目录迁移期共存但不再写入新数据
- **流程**：切换 Pipeline 时自动保存/加载会话；重启后按最后活跃的 Pipeline 恢复会话上下文
- **风险**：异步写盘失败不应阻塞对话（catch 异常 + 日志警告）；会话 ID 使用时间戳+hex 保证唯一性和可排序性。
