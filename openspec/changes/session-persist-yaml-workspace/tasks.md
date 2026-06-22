## 1. 基础存储层 — SessionStore

- [x] 1.1 新建 `backend/workspace/session_store.py`，实现 `SessionStore` 类，包含 `__init__(pipeline_name)`、存储目录解析逻辑
- [x] 1.2 实现 `save_session(session)`: 全量写 `workspaces/{name}/session/{sid}.json`，更新 `sessions.json` 索引
- [x] 1.3 实现 `load_session(session_id) -> SessionState | None`: 从 `{session_id}.json` 读取完整消息恢复 `SessionState`
- [x] 1.4 实现 `list_sessions() -> list[dict]`: 读取 `sessions.json` 返回所有 session 元数据
- [x] 1.5 实现 `new_session() -> str`: 生成 `YYYYMMDD_HHMMSS_hex` 格式 session_id，写入 `sessions.json` 索引
- [x] 1.6 实现 `ensure_session_dir()`: 确保 `workspaces/{name}/session/` 目录存在
- [x] 1.7 `sessions.json` 写入采用原子写策略：先写 `.tmp` 文件，再 `os.replace()` 重命名

## 2. Service 层改造

- [x] 2.1 `Service.__init__`: `_active_session` 改为 `_sessions: dict[str, SessionState]` 池 + `_active_pipeline: str` 字段
- [x] 2.2 实现 `Service.get_session(pipeline_name)`: 从 `_sessions` 取，miss 则从 `SessionStore` 加载或创建空 session。保留 `get_session()` 无参形式，返回 `_active_pipeline` 的 session 保证向后兼容
- [x] 2.3 实现 `Service.switch_session(pipeline_name)`: 保存当前 session，更新 `_active_pipeline`，写入 `workspaces/.last_active` 标记文件，返回目标工作区 session 列表
- [x] 2.4 实现 `Service.new_session(pipeline_name)`: 调用 `SessionStore.new_session()`，创建 `SessionState` 并加入 `_sessions` 池
- [x] 2.5 `Service.process_chat_message()` 改造: 按 `pipeline_name` 获取 session，对话完成后异步调用 `SessionStore.save_session()`
- [x] 2.6 `Service._save_session_history()` 改造: 写入路径从 `userdata/sessions/{id}.json` 改为 `workspaces/{name}/session/{id}.json`

## 3. Conversation Loop 持久化钩子

- [x] 3.1 `run_conversation_loop()` 新增可选参数 `on_turn_complete`
- [x] 3.2 `Agent._step()` 在每次回合完成后（助手消息/tool 消息追加后），调用 `on_turn_complete()` 回调
- [x] 3.3 Service 侧实现异步保存：`_async_save_session(pipeline_name)` 封装 `try/except`，写失败仅日志警告

## 4. API 端点

- [x] 4.1 新增 `POST /api/session/new?pipeline={name}`: 创建新 session，返回 `{session_id, created_at}`
- [x] 4.2 新增 `POST /api/session/switch`: 接收 `{pipeline_name}`，调用 `Service.switch_session()`，返回 `{sessions: [...]}`
- [x] 4.3 新增 `GET /api/session/{pipeline_name}/list`: 返回该工作区所有 session 元数据列表
- [x] 4.4 新增 `GET /api/session/{pipeline_name}/{session_id}`: 返回完整 session 数据（含 `messages`）
- [x] 4.5 Electron IPC 桥注册新端点对应的 `ipcMain.handle` 和 `contextBridge` 暴露

## 5. `__chat__` 默认工作区

- [x] 5.1 当 `pipeline_name` 为空或 `"chat"` 时，统一映射到 `__chat__` 工作区（`session_store._normalize_pipeline` + `service._normalize_pipeline`）
- [x] 5.2 首次纯聊时自动 `ensure_session_dir()` 创建 `workspaces/__chat__/session/`
- [x] 5.3 实现 `__chat__` → 新 Pipeline 的 session 迁移：`_push_auto_record_review()` 中检测 `_active_pipeline == "__chat__"`，调用 `_migrate_chat_session_if_needed()` 做 shutil.move

## 6. 前端改造

- [x] 6.1 `App.tsx`: 启动时按最后活跃 Pipeline 调用 listSessions 恢复上下文
- [x] 6.2 `App.tsx`: `onPresetChange` 回调中调用 switchSession API，清空 `chatMessages`
- [x] 6.3 `ChatTab.tsx`: 新增 session 侧栏面板，显示当前 Pipeline 下所有 session 列表，当前 session 高亮
- [x] 6.4 `ChatTab.tsx`: 新增「+」按钮，调用 newSession API 创建新 session
- [x] 6.5 `ChatTab.tsx`: 点击历史 session 项，调用 getSessionData API 加载并替换 `chatMessages`
- [x] 6.6 Preset 模式回退到 Chat: 当前 preset runner 使用独立消息列表（`run_preset_loop`），与 `Service._sessions` 池不互通，无数据污染。保留此设计约束，未来需显式 fallback 到 `process_chat_message` 时再接入 `Service.new_session()`

## 7. 验证

- [x] 7.1 编写 SessionStore 单元测试（`test_session_persist.py`）：11 场景覆盖生成ID、规范化、目录创建、保存加载、列表、原子写、last_active、缺失处理
- [x] 7.2 端到端场景测试由手工验证（启动应用 → __chat__ 会话 → 重启 → 恢复上下文）
- [x] 7.3 端到端场景测试由手工验证（切 Pipeline → session 切换保存 → 切回 → 旧会话不丢失）
- [x] 7.4 端到端场景测试由手工验证（__chat__ 下对话 → 创建 Pipeline YAML → 自动迁移 session）
