## ADDED Requirements

### Requirement: 每个 Pipeline 下支持多 Session
每个 Pipeline 工作区下 MUST 支持创建和管理多个独立 Session，每个 Session 拥有独立的 `messages` 列表和生命周期。

#### Scenario: 创建新 Session
- **WHEN** 用户点击前端「+ 新会话」按钮
- **THEN** 前端调用 `POST /api/session/new?pipeline={name}`
- **THEN** 后端生成 `YYYYMMDD_HHMMSS_hex` 格式的 session_id
- **THEN** 后端返回新 Session 元数据
- **THEN** 前端清空 `chatMessages`，进入空输入状态

#### Scenario: 切换历史 Session
- **WHEN** 用户点击前端 session 列表中的历史会话项
- **THEN** 前端调用 `GET /api/session/{pipeline_name}/{session_id}`
- **THEN** 后端从磁盘读取 `{session_id}.json` 的完整 `messages`
- **THEN** 前端将 `chatMessages` 替换为该历史会话的消息列表

#### Scenario: 当前活跃 Session 高亮
- **WHEN** session 列表渲染时
- **THEN** 当前正在对话的 session 在列表中 MUST 有高亮标记

### Requirement: Session ID 格式
Session ID MUST 采用 `YYYYMMDD_HHMMSS_<uuid4 hex[:6]>` 格式，确保按创建时间自然排序且全局唯一。

#### Scenario: Session ID 可排序
- **WHEN** 系统列出 `workspaces/{name}/session/` 下的 `{session_id}.json` 文件
- **THEN** 文件名按字典序排列后等同于按创建时间排序

### Requirement: Session 元数据索引
每个 Pipeline 工作区的 `sessions.json` 文件 MUST 以 `{session_id: metadata}` dict 存储所有 session 的元数据。

#### Scenario: 索引更新
- **WHEN** 新 Session 被创建
- **THEN** `sessions.json` 中增加一条 `{session_id: {created_at, message_count: 0, status: "idle"}}` 记录

#### Scenario: 索引读取
- **WHEN** 前端请求某个 Pipeline 的 session 列表
- **THEN** 后端读取该工作区的 `sessions.json` 并返回所有 session 元数据
- **THEN** 前端渲染 session 列表供用户选择
