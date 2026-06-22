## 背景

### 当前状态

- `Service._active_session` 是内存全局单例（`SessionState | None`），不支持多工作区
- `_save_session_history()` 仅在 `reset_session()` 时触发，写入 `userdata/sessions/{id}.json`
- 消息在 `conversation_loop` 内部追加到 `session.messages`，对话完成后不自动持久化
- 前端 `chatMessages` 初始化为 `[]`，启动时不从后端恢复
- Pipeline 工作区（`workspaces/{name}/`）已有 runs/、versions/、tools/，但无 session/

### 已有基础设施

- `WorkspaceManager`（`backend/workspace/manager.py`）处理工作区目录生命周期
- `SessionState` dataclass 包含 session_id、pipeline_name、status、messages
- WebSocket 事件系统（`_push_event`）可扩展新事件类型
- Electron IPC 桥已注册 `api:session`（GET）、`api:chat`、`api:chat-reset`、`api:chat-cancel`

## 目标 / 非目标

**目标：**
- 每次对话回合结束后自动持久化，不丢未完成会话
- 切换 Pipeline 时保存旧会话、清空界面，加载目标工作区的会话列表
- 每个 Pipeline 下支持创建多个独立会话，可切换和列表浏览
- `__chat__` 纯聊工作区作为默认兜底，创建 Pipeline YAML 后自动迁移会话
- 重启后恢复最后活跃工作区的会话上下文
- Preset 模式回退到 Chat 时创建新 session，不污染当前活跃会话

**非目标：**
- 不支持实时协同（多用户同时操作同一 session）
- 不实现会话归档 UI（`history/` 目录）
- 不动旧 `userdata/sessions/` 数据（共存但不写入）
- 不做 session 软删除或回收站

## 关键决策

### 决策 1：存储格式 — 全量 JSON，不用 JSONL

| 方案 | 评价 |
|------|------|
| JSONL（append-only） | tool 消息需要更新（start→end 改 content），JSONL 无法原地修改 |
| **全量 JSON**（最终决定） | 每次回合结束后全量覆盖 `{session_id}.json`，简单可靠 |

`messages` 列表在 `conversation_loop` 中被持续追加和修改，全量写符合数据流模式。

### 决策 2：索引结构 — dict 而非数组

```json
// sessions.json
{
  "20260622_140208_a1b2c3": {
    "session_id": "20260622_140208_a1b2c3",
    "display_name": null,
    "created_at": "2026-06-22T14:02:08",
    "updated_at": "2026-06-22T15:30:00",
    "message_count": 12,
    "status": "idle"
  }
}
```

`{session_id: metadata}` dict 比数组查找更快（O(1)），且天然防止重复。

### 决策 3：Session ID 格式 — 时间戳+hex

```
YYYYMMDD_HHMMSS_<uuid4 hex[:6]>
```

例：`20260622_140208_a1b2c3`

- 按文件名自然排序
- 全局唯一无需中心化服务
- 从 ID 即可读知创建时间

### 决策 4：持久化触发时机 — 回合结束，异步写

```
conversation_loop 每回合完成后
  └─ 调用 on_turn_complete(session) 回调
       └─ Service._async_save_session(pipeline_name)
            ├─ 写 {session_id}.json（全量覆盖）
            └─ 更新 sessions.json（元数据刷新）
```

异步写不阻塞对话，写失败仅打日志警告。

### 决策 5：并发锁 — 全局锁

保持当前 `Service._chat_lock` 为全局 `asyncio.Lock`，一次只聊一个 session。多 session 并发在当前阶段（单用户桌面应用）无实际需求，引入 per-session 锁增加复杂度。

### 决策 6：__chat__ → Pipeline 迁移时机

`pipeline_edit` 工具 execute 时同步检查 `_active_pipeline == "__chat__"`，如果目标 `pipeline.yaml` 是新创建的，将 `workspaces/__chat__/session/` 目录整体 mv 到新工作区。

### 决策 7：最后活跃 Pipeline 追踪

通过 `workspaces/.last_active` 文件记录。每次 `switch_session()` 时写入当前 `_active_pipeline`，应用启动时读取。文件内容为纯文本，仅一行 Pipeline 名称。

### 决策 8：sessions.json 原子写

`read → modify → write` 存在并发覆盖风险。写入策略：先写 `sessions.json.tmp`，再 `os.replace()` 重命名，保证文件不损坏。

### 决策 9：旧 userdata/sessions/ 处理

忽略。新方案只读写 `workspaces/{name}/session/`。旧文件不会被删除，但也不再写入新数据。测试阶段不处理兼容迁移。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| 异步写盘失败 | 丢最后一回合消息 | catch 异常仅打警告，不阻塞对话 |
| sessions.json 写并发 | 两个异步写同时修改索引导致数据损坏 | 写 `.tmp` 再 `os.replace()` 原子重命名，保证文件完整性 |
| __chat__ 迁移后读空目录 | 前端访问旧 session | 迁移后检查目标目录是否存在；回退为空状态 |
| session 文件无限累积 | 磁盘占用 | 后续引入清理策略（YAGNI，现在不做） |

## 架构图

```
┌───────────────────────────────────────────────────────────────┐
│  userdata/workspaces/{pipeline_name}/                          │
│                                                                │
│  pipeline.yaml ← 工作区标识                                     │
│  session/                                                      │
│  ├── sessions.json        ← {session_id: metadata} 索引        │
│  ├── 20260622_140208_abc  ← session 完整消息                    │
│  ├── 20260622_151030_def  ← session 完整消息                    │
│  └── ...                                                       │
│  runs/                                                         │
│  versions/                                                     │
│  tools/                                                        │
└───────────────────────────────────────────────────────────────┘
        │
        │ SessionStore (backend/workspace/session_store.py)
        │   - save_session(pipeline_name, session)
        │   - load_session(pipeline_name, session_id)
        │   - switch_session(pipeline_name)
        │   - list_sessions(pipeline_name)
        │   - new_session(pipeline_name)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│  Service (backend/api/service.py)                              │
│                                                                │
│  _sessions: dict[str, SessionState]  ← pipeline_name → session │
│  _active_pipeline: str                ← 当前活跃工作区         │
│  _chat_lock: asyncio.Lock             ← 全局并发锁             │
│                                                                │
│  get_session(pipeline_name) → SessionState | None              │
│  switch_session(pipeline_name) → void (保存旧/加载新/清空前    │
│  new_session(pipeline_name) → SessionState                     │
│  process_chat_message() ... 每回合后调 _async_save_session()   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│  前端 (Electron Renderer)                                      │
│                                                                │
│  App.tsx:                                                      │
│    - init: GET /api/session/__chat__/list → 恢复上下文         │
│    - on activePreset change:                                   │
│        POST /api/session/switch {pipeline_name}                │
│        → 清空 chatMessages → 显示空会话 + session 列表         │
│                                                                │
│  ChatTab.tsx:                                                  │
│    - 侧栏: session 列表（当前高亮 + 历史）                     │
│    - 按钮: [+ 新会话] → POST /api/session/new                 │
│    - 点击历史 session → GET /api/session/{name}/{sid} → 加载   │
└───────────────────────────────────────────────────────────────┘
```

## 数据流

```
对话回合完成
  │
  ▼
conversation_loop.Agent._step()
  │ 消息追加到 session.messages 完毕
  │
  ▼
on_turn_complete(session)  ← 新回调
  │
  ▼
Service._async_save_session(pipeline_name)
  │
  ├─ write: workspaces/{name}/session/{session_id}.json
  │   └─ 全量 messages + 元数据
  │
  └─ write: workspaces/{name}/session/sessions.json
      └─ 更新 session 元数据（message_count, updated_at）

切换 Pipeline
  │
  ▼
POST /api/session/switch {pipeline_name}
  │
  ├─ 保存当前 _active_pipeline 的 session（若 dirty）
  ├─ 更新 _active_pipeline = pipeline_name
  ├─ 清空前端 chatMessages
  └─ 返回该 workspace 的 session 列表
```

## 迁移计划

1. 先实现 `SessionStore` 类 + 新存储格式
2. 改造 `Service` 为多 session 池，保持向后兼容（`get_session()` 无参时返回 `_active_pipeline` 的 session）
3. 新增 API 端点，前端按功能逐项对接
4. `__chat__` 工作区在首次需要时自动创建（`ensure_workspace`）
5. 旧 `userdata/sessions/` 数据不动，不迁移

回滚：切换回旧版代码即可，新数据格式与旧版本无冲突（新文件写新路径）。

## 待确认问题

- session 在新版前端如何命名显示？就用 `{session_id}` 时间戳前缀（如 `06/22 14:02`）还是需要额外标题？
- 切换 Pipeline 时是否需要后端 `sessions.json` 当前活跃标记？还是前端维护当前 session ID？
