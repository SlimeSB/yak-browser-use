## ADDED Requirements

### Requirement: 每回合自动持久化
系统 MUST 在每次对话回合（即 `conversation_loop` 的每个 `_step()` 完成后）自动持久化当前会话。持久化 MUST 异步执行，不阻塞对话流程。

#### Scenario: 回合完成后自动写盘
- **WHEN** 用户发送一条消息，Agent 完成一轮 LLM 调用 + 工具执行
- **THEN** 系统自动将完整的 `session.messages` 列表写入 `workspaces/{pipeline_name}/session/{session_id}.json`

#### Scenario: 写盘失败不阻塞对话
- **WHEN** 异步写盘过程中发生 IO 异常
- **THEN** 系统 MUST 捕获异常并记录日志警告，对话 MUST 继续不受影响

### Requirement: 切换 Pipeline 时保存当前会话
系统 MUST 响应用户切换 Pipeline 操作，先保存当前活跃会话到磁盘，再清空前端聊天界面。

#### Scenario: 切换 Pipeline 保留旧会话
- **WHEN** 用户从 Pipeline A 切换到 Pipeline B
- **THEN** 系统 MUST 将 Pipeline A 的当前会话写入磁盘
- **THEN** 前端 MUST 清空 `chatMessages`
- **THEN** 前端 MUST 显示 Pipeline B 的会话列表（空状态或历史 session）

### Requirement: 重启恢复最后活跃工作区
系统 MUST 在启动时自动加载最后活跃工作区的会话上下文。

#### Scenario: 重启后恢复 `__chat__` 会话
- **WHEN** 应用重启，且最后活跃工作区是 `__chat__`
- **THEN** 系统 MUST 读取 `workspaces/__chat__/session/` 下的 `sessions.json`
- **THEN** 前端 MUST 显示会话列表，默认展开最近活跃的 session

### Requirement: Preset 回退 Chat 时新建独立 Session
当 Preset 模式执行异常回退到 Chat 模式时，系统 MUST 创建一个全新的 Session，不污染当前活跃会话。

#### Scenario: Pipeline 回退 Chat 创建新会话
- **WHEN** Preset 模式执行中出现不可恢复错误，系统回退到 Chat 交互
- **THEN** 系统 MUST 调用 `new_session(pipeline_name)` 创建新 Session
- **THEN** 该 Session 的 `pipeline_name` MUST 指向当前 Pipeline
- **THEN** 前端 MUST 显示空白的 Chat 输入区，准备接受用户指令

## MODIFIED Requirements

### Requirement: 会话持久化目标路径
当前 `_save_session_history()` 写入 `userdata/sessions/{session_id}.json`。
修改为：写入 `workspaces/{pipeline_name}/session/{session_id}.json`。
sessions/ 目录下同时维护 `sessions.json` 索引文件。

#### Scenario: 新路径写入
- **WHEN** 系统执行会话持久化
- **THEN** 数据写入 `workspaces/{pipeline_name}/session/{session_id}.json`
- **THEN** `sessions.json` 中对应 session 的元数据被更新
