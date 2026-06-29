## Why

shared_store 是目前唯一的跨 tool/step 数据通道，LLM 通过 `bind` 写入、`${path}` 读取。但 shared_store 对 LLM 是完全不透明的黑盒——没有工具可以列出 key、浏览内容、分页查看。LLM 只能靠 context window 记忆自己存过什么 key，一旦忘记就永远丢失数据。

删除 scratchpad 后，所有重数据（elements、HTML）的缓存都依赖 shared_store，LLM 更需要内省能力。提供 `data_keys` 和 `data_browse` 两个工具可以让 shared_store 成为真正的"通用指针"。

## What Changes

- **新增** `data_keys` 工具：列出 shared_store 中所有 key，返回 key 名、值类型、大小（元素数或字符数）
- **新增** `data_browse` 工具：分页浏览 shared_store 中指定 key 的值，支持 `limit` 和 `offset` 参数。元素列表用 `_build_snapshot_summary` 格式输出，字符串截断显示
- **注册** 两个工具到 `registry.py`，通过 `ToolContext` 访问 shared_store

## Capabilities

### New Capabilities

- `data-keys`: 列出 shared_store 中所有 key 及其元信息
- `data-browse`: 分页浏览 shared_store 中指定 key 的值

## Impact

- 受影响的文件：`tools/registry.py`（注册两个新工具）、`engine/_harness/tool_executor.py`（`ToolContext` 可能需要扩展 shared_store 访问）
- 不影响现有工具、不影响 preset 模式
