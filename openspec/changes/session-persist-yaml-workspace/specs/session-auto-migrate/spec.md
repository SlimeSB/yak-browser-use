## ADDED Requirements

### Requirement: `__chat__` 工作区概念
系统 MUST 维护一个特殊的 `__chat__` 工作区，用于存放无 Pipeline 绑定时的纯聊会话。

#### Scenario: 首次纯聊自动创建
- **WHEN** 用户首次在无 Pipeline 选中时发送聊天消息
- **THEN** 系统 MUST 在 `workspaces/__chat__/` 下创建 session/ 目录
- **THEN** 系统 MUST 将当前会话的 `pipeline_name` 设为 `__chat__`

#### Scenario: `__chat__` 会话持久化
- **WHEN** 用户在纯聊模式下完成对话回合
- **THEN** 系统 MUST 将会话持久化到 `workspaces/__chat__/session/{session_id}.json`

### Requirement: 自动迁移到新 Pipeline
当 `_active_pipeline == "__chat__"` 且通过聊天创建了新的 `pipeline.yaml` 时，系统 MUST 自动将 `workspaces/__chat__/session/` 目录迁移到新 Pipeline 工作区。

#### Scenario: Chat 创建 Pipeline 后迁移
- **WHEN** Agent 在 `__chat__` 模式下调用 `pipeline_edit` 工具创建了一个新的 Pipeline YAML 文件
- **THEN** 系统 MUST 检测 `_active_pipeline == "__chat__"`
- **THEN** 系统 MUST 将 `workspaces/__chat__/session/` 目录整体移动到 `workspaces/{new_pipeline_name}/session/`
- **THEN** 系统 MUST 更新 `Service._sessions` 字典中的 key 从 `__chat__` 为 `{new_pipeline_name}`
- **THEN** 前端 MUST 自动更新为新的 Pipeline 名称

#### Scenario: 迁移后 `__chat__` 回退为空
- **WHEN** session 目录从 `__chat__` 迁移到新 Pipeline 后
- **THEN** 如果用户继续在 `__chat__` 下聊天
- **THEN** 系统 MUST 在 `workspaces/__chat__/session/` 重新创建空的 session 目录
- **THEN** 后续对话使用新的 session

#### Scenario: 迁移目标目录已存在
- **WHEN** `workspaces/{new_pipeline_name}/session/` 已存在（如复现同名 Pipeline）
- **THEN** 系统 MUST 跳过目录移动，仅将会话数据合并到目标目录
- **THEN** 系统 MUST 记录警告日志
