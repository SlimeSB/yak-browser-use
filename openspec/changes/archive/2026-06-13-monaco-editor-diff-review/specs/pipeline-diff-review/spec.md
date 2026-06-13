## ADDED Requirements

### Requirement: Diff 事件接收

系统 MUST 在 AI 聊天修改 pipeline 后，通过 WebSocket 推送 `pipeline.edit` 事件给前端。修改 MUST 已在推送前写入磁盘（事件携带 `original` 仅用于回滚参考）。事件 MUST 包含 `edit_id`（唯一标识）、`original`（修改前 YAML 快照）、`modified`（修改后 YAML，即当前磁盘内容）、`diff_lines`（差异行列表）、`explanation`（AI 修改说明）。

#### Scenario: AI 完成 pipeline 修改
- **WHEN** AI agent 在聊天会话中调用工具修改了 pipeline 文件
- **THEN** 后端 MUST 先将 modified YAML 写入磁盘
- **AND** 后端 MUST 通过 WebSocket 推送 `pipeline.edit` 事件
- **AND** 事件 MUST 包含完整的 original（回滚用）和 modified（当前磁盘内容）
- **AND** diff 预览期间，用户编辑器 MUST 切换到只读 diff 模式

#### Scenario: 累积合并 diff 增量更新
- **WHEN** AI 在同一轮对话中多次调用工具修改 pipeline（累积合并）
- **THEN** 每次累积合并后 MUST 推送一次更新的 `pipeline.edit` 事件
- **AND** `original` MUST 保持为首次修改前的快照不变
- **AND** `modified` MUST 更新为最新的累积合并结果
- **AND** 前端 diff 预览 MUST 实时刷新为最新累积 diff

#### Scenario: 重复 edit_id 被忽略
- **WHEN** 前端收到与已处理 edit_id 相同的事件
- **THEN** 前端 MUST NOT 重复展示 diff 预览

### Requirement: 内联 Diff 预览

当前端收到 `pipeline.edit` 事件时，系统 MUST 在 ChatTab 右侧面板切换 Monaco 为 inline diff 模式（`renderSideBySide: false`），展示原始版（左侧模型）和修改版（右侧模型），修改行 MUST 保留 YAML 语法着色。

#### Scenario: 展示内联 diff
- **WHEN** 前端收到 `pipeline.edit` 事件
- **THEN** Monaco Editor MUST 从普通编辑模式切换到只读 diff 模式
- **AND** 删除行 MUST 标红（背景 + 删除线）
- **AND** 新增行 MUST 标绿（背景高亮）
- **AND** 修改行 MAY 显示字符级变化（删除部分红色、新增部分绿色）
- **AND** 与修改无关的上下文行 MUST 正常渲染

#### Scenario: YAML 语法着色在 diff 中保持
- **WHEN** diff 模式显示修改后的 YAML 内容
- **THEN** 关键字（`name`、`steps`、`browser_ops`、`tool_name` 等）MUST 保留语法着色
- **AND** 字符串、列表、缩进 MUST 正确高亮

### Requirement: 修改说明展示

Diff 预览区域上方 MUST 显示 AI 的修改说明（`explanation` 字段），帮助用户理解修改意图。

#### Scenario: 展示修改说明
- **WHEN** diff 预览渲染时
- **THEN** diff 区域顶部 MUST 显示说明文本
- **AND** 说明 MUST 以不同背景色（信息提示风格）区分于 diff 内容

### Requirement: 确认修改

用户点击 Confirm 按钮后，系统 MUST 通过 IPC 调用 `POST /api/chat/confirm` 传入 `edit_id`，后端标记该 edit_id 为已确认。完成后前端从磁盘刷新 pipeline 内容，恢复到正常编辑模式，移除 diff 预览。

> 注意：修改已在 `pipeline.edit` 事件推送前写入磁盘。Confirm 仅做确认标记 + 刷新编辑器。

#### Scenario: 用户确认修改
- **WHEN** 用户点击 Confirm 按钮
- **THEN** 前端 MUST 通过 IPC 调用后端 Confirm 端点
- **AND** 后端 MUST 标记该 edit_id 为已确认
- **AND** 前端 MUST 从磁盘刷新 pipeline 最新内容
- **AND** 前端 MUST 将编辑器切换回普通编辑模式

#### Scenario: Confirm 成功后 UI 反馈
- **WHEN** Confirm API 返回成功
- **THEN** diff 预览提示条 MUST 消失
- **AND** Monaco Editor MUST 回到可编辑状态，展示刷新后的最新内容

#### Scenario: Confirm 失败回退
- **WHEN** Confirm API 返回错误（网络异常）
- **THEN** 前端 MUST 显示错误提示
- **AND** diff 预览 MUST 保持可见，允许用户重试

### Requirement: 撤销修改

用户点击 Revert 按钮后，系统 MUST 通过 IPC 调用 `POST /api/chat/revert` 传入 `edit_id`，后端将磁盘上的 pipeline 文件**回滚**到 original 版本。编辑器恢复到普通编辑模式，内容为回滚后的最新版本。

> 注意：Revert 会执行实际的文件回滚操作。

#### Scenario: 用户撤销修改
- **WHEN** 用户点击 Revert 按钮
- **THEN** 前端 MUST 通过 IPC 调用后端 Revert 端点
- **AND** 后端 MUST 将磁盘上的 pipeline 文件回滚到 original 版本
- **AND** 后端 MUST 标记该 edit_id 为已回退
- **AND** 前端 MUST 将编辑器切换回普通编辑模式
- **AND** 编辑器 MUST 展示回滚后的最新内容

#### Scenario: Revert 后状态清理
- **WHEN** Revert API 返回成功
- **THEN** diff 预览 MUST 移除
- **AND** Monaco Editor 回到可编辑状态，展示回滚后的内容

### Requirement: 确认/撤销命令幂等性

后端 MUST 保证同一 `edit_id` 的 Confirm 或 Revert 操作幂等：重复调用返回已处理状态，不产生副作用。

#### Scenario: 重复 Confirm
- **WHEN** 同一个 edit_id 被 Confirm 两次
- **THEN** 第二次调用 MUST 返回 `{status: "already_confirmed"}`
- **AND** 不做任何文件操作

#### Scenario: 重复 Revert
- **WHEN** 同一个 edit_id 被 Revert 两次
- **THEN** 第二次调用 MUST 返回 `{status: "already_reverted"}`
- **AND** 文件 MUST NOT 被重复回滚

#### Scenario: Confirm 后 Revert
- **WHEN** 一个已 Confirm 的 edit_id 被 Revert
- **THEN** Revert MUST 返回 `{status: "already_confirmed"}` 错误
- **AND** 文件 MUST NOT 被回滚
