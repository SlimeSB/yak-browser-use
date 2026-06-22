## ADDED Requirements

### Requirement: 工具 rename 后自动注册 schema

当 `_PH-` 工具 rename 为正式名称后，系统 MUST 自动解析生成的 `.py` 文件的函数签名和 docstring，构建 OpenAI function schema，并加入动态注册表。

#### Scenario: 解析函数签名构建 schema
- **WHEN** 工具 `crack-captcha.py` 包含函数 `async def crack_captcha(ctx: ToolContext, params: dict) -> dict` 及 docstring 使用 `Parameters in **params:` 格式（与现有 `extract.py`/`data.py`/`adapters.py` 一致）：`"""识别验证码并返回结果。\n\nParameters in **params:\n    image_selector (str): 图片元素选择器\n    threshold (float): 识别阈值\n    retry (bool): 是否重试\n    max_items (int): 最大条目数\n"""`
- **THEN** 系统从 docstring 的 `Parameters in **params:` 段解析参数描述，构建 OpenAI function schema：`{"type": "function", "function": {"name": "crack_captcha", "description": "识别验证码并返回结果。", "parameters": {"type": "object", "properties": {"image_selector": {"type": "string", "description": "图片元素选择器"}, "threshold": {"type": "number", "description": "识别阈值"}, "retry": {"type": "boolean", "description": "是否重试"}, "max_items": {"type": "integer", "description": "最大条目数"}}, "required": ["image_selector", "threshold", "retry", "max_items"]}}}`

#### Scenario: 无 docstring 时使用默认描述
- **WHEN** 工具函数没有 docstring
- **THEN** 系统使用 `"Auto-generated tool: {name}"` 作为描述

#### Scenario: 无参数类型提示时使用空 properties
- **WHEN** 工具函数的 `params` 参数无类型提示
- **THEN** 系统使用 `{"type": "object", "properties": {}}` 作为 parameters schema

### Requirement: 参数类型映射

系统 MUST 支持以下 docstring 参数类型到 JSON Schema type 的映射：

| docstring 类型 | JSON Schema type |
|---|---|
| `(str)` | `"string"` |
| `(int)` | `"integer"` |
| `(float)` | `"number"` |
| `(bool)` | `"boolean"` |
| `(list)` | `"array"`（items 为 `{"type": "string"}`） |
| 未识别类型 | `"string"`（默认） |

#### Scenario: 混合类型参数解析
- **WHEN** docstring 包含 `poll_seconds (float): 轮询间隔` 和 `exclude (bool): 是否排除`
- **THEN** 系统生成 `{"poll_seconds": {"type": "number", "description": "轮询间隔"}, "exclude": {"type": "boolean", "description": "是否排除"}}`

### Requirement: 动态注册表合并

`get_all_tools(include_goal_run: bool = True, pipeline_name: str | None = None)` MUST 在返回时将静态工具列表与动态注册表中的工具合并。当 `pipeline_name` 为 `None` 时返回所有 pipeline 的动态工具；指定 `pipeline_name` 时仅返回该 pipeline 的动态工具。`include_goal_run` 参数行为不变。

#### Scenario: 静态工具 + 动态工具合并
- **WHEN** 调用 `get_all_tools()` 且动态注册表中有 2 个已注册工具
- **THEN** 返回的工具列表包含所有静态工具（`BROWSER_TOOLS` + `PIPELINE_TOOLS` + skill 工具 + `goal_run`） + 2 个动态工具

#### Scenario: 动态注册表为空
- **WHEN** 调用 `get_all_tools()` 且动态注册表为空
- **THEN** 返回的工具列表仅包含静态工具（行为不变）

#### Scenario: 按 pipeline 过滤动态工具
- **WHEN** 调用 `get_all_tools(pipeline_name="A")` 且动态注册表中有 `A/crack-captcha` 和 `B/crack-captcha`
- **THEN** 返回的工具列表包含所有静态工具 + 1 个 `A/crack-captcha`

#### Scenario: 排除 goal_run
- **WHEN** 调用 `get_all_tools(include_goal_run=False)`
- **THEN** 返回的工具列表包含静态工具（不含 `goal_run`）+ 动态工具（行为不变）

### Requirement: 动态注册表 key 格式

动态注册表 MUST 使用 `{pipeline_name}/{tool_name}` 作为 key，避免不同 pipeline 的同名工具冲突。

#### Scenario: 不同 pipeline 的同名工具
- **WHEN** pipeline `A` 和 pipeline `B` 各自生成了 `crack-captcha` 工具
- **THEN** 动态注册表中存在两个条目：`A/crack-captcha` 和 `B/crack-captcha`，互不冲突
