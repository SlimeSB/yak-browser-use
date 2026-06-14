## ADDED Requirements

### Requirement: Agent 可通过 `todo` 工具读取任务列表

Agent 调用 `todo` 工具时不传参数时，MUST 返回当前会话中所有 todo 条目，返回格式为 JSON 列表，每个条目含 `id`、`content`、`status`。

#### Scenario: 无参数调用返回当前列表
- **WHEN** Agent 调用 `todo()` 不带参数
- **THEN** 系统返回当前任务列表的 JSON 数组

#### Scenario: 空列表返回 `[]`
- **WHEN** Agent 调用 `todo()` 但当前没有任何任务
- **THEN** 系统返回 `[]`

### Requirement: Agent 可通过 `todo` 工具写入任务列表

Agent 传入 `todos` 参数时，MUST 替换或合并当前任务列表，并返回更新后的完整列表。`merge=False`（默认）时替换整个列表；`merge=True` 时按 `id` 更新已有条目、追加新条目。

#### Scenario: `merge=False` 替换全部
- **WHEN** Agent 调用 `todo(todos=[{"id": "1", "content": "搜索咖啡", "status": "in_progress"}])` 且 `merge=False`
- **THEN** 系统用新列表替换全部旧条目，返回 `[{"id": "1", "content": "搜索咖啡", "status": "in_progress"}]`

#### Scenario: `merge=True` 按 id 更新
- **WHEN** 当前列表为 `[{"id": "1", "content": "旧描述", "status": "pending"}]`，Agent 调用 `todo(todos=[{"id": "1", "content": "新描述"}], merge=True)`
- **THEN** 系统更新 id=1 的条目的 content 为"新描述"，status 保持不变

#### Scenario: `merge=True` 追加新条目
- **WHEN** Agent 调用 `todo(todos=[{"id": "2", "content": "发邮件", "status": "pending"}], merge=True)`
- **THEN** 系统追加新条目，列表包含新旧所有条目

### Requirement: 条目 id 为空时自动生成唯一标识

用户或 Agent 传入的条目如果没有 `id`，TodoStore MUST 自动生成一个唯一 id（8 字符 UUID 前缀）。

#### Scenario: 无 id 条目自动分配
- **WHEN** Agent 调用 `todo(todos=[{"content": "无 id 任务"}])`
- **THEN** 返回的条目 `id` 字段为一个非空字符串，且不会与已有 id 冲突

### Requirement: 条目 content 为空时使用默认描述

用户或 Agent 传入的条目如果没有 `content`，MUST 使用 `"(no description)"` 作为默认值。

#### Scenario: 空 content 使用默认值
- **WHEN** Agent 调用 `todo(todos=[{"id": "1", "status": "pending"}])`
- **THEN** 返回的条目 content 为 `"(no description)"`

### Requirement: 列表超出上限时自动截断

当 todo 条目数量超过 `MAX_ITEMS`（256）时，MUST 截断尾部条目并记录警告日志。

#### Scenario: 超出上限截断
- **WHEN** 写入后条目数超过 256
- **THEN** 系统保留前 256 条，丢弃后续条目，并输出 `logger.warning`

### Requirement: `todos` 参数类型校验

当 `todos` 参数传入且不是 list 类型时，系统 MUST 直接忽略该参数（等价于不传），并返回当前列表。

#### Scenario: todos 不是 list
- **WHEN** Agent 调用 `todo(todos="not a list")`
- **THEN** 系统忽略 `todos` 参数，返回当前列表

### Requirement: `merge` 参数类型校验

当 `merge` 参数传入且不是 bool 类型时，MUST 视为 `False`（替换模式）。

#### Scenario: merge 不是 bool
- **WHEN** Agent 调用 `todo(todos=[...], merge="yes")`
- **THEN** 系统将 `merge` 视为 `False`

### Requirement: 条目 content 超长时截断

单个条目的 content 超过 `MAX_CONTENT_CHARS`（4000）时，MUST 截断并追加 `… [truncated]` 标记。

#### Scenario: content 超长截断
- **WHEN** Agent 调用 `todo(todos=[{"id": "1", "content": "x" * 5000}])`
- **THEN** 返回的条目 content 长度为 `MAX_CONTENT_CHARS - 20 + len("… [truncated]")`

### Requirement: 无效 status 降级为 `pending`

传入的 status 不在 `VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}` 中时，MUST 自动降级为 `pending`。

#### Scenario: 无效 status 降级
- **WHEN** Agent 调用 `todo(todos=[{"id": "1", "content": "test", "status": "invalid_status"}])`
- **THEN** 返回的条目 status 为 `"pending"`
