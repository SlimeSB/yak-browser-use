## 背景

shared_store 是框架级 dict，贯穿 `runner → conversation_loop → tool_executor → executor` 全链路。`ToolContext` 已有 `shared_store` 字段，handler 可通过 `ctx.shared_store` 访问。但当前没有工具让 LLM 内省 shared_store 的内容。

## 目标 / 非目标

**目标：**
- 提供 `data_keys` 工具，列出 shared_store 中所有 key 及其元信息
- 提供 `data_browse` 工具，分页浏览 shared_store 中指定 key 的值

**非目标：**
- 不修改 shared_store 的写入/读取机制
- 不修改 preset 模式
- 不提供 shared_store 的删除/清空工具（LLM 不需要管理生命周期）

## 关键决策

**决策 1：两个独立工具而非一个**

`data_keys` 和 `data_browse` 分开。keys 是轻量操作（只返回 key 名和元信息），browse 可能返回大量数据需要分页。合并成一个工具会增加 schema 复杂度。

**决策 2：通过 ToolContext.shared_store 访问**

两个 handler 直接读 `ctx.shared_store`，不引入新的参数传递路径。shared_store 已在 ToolContext 中可用。

**决策 3：data_browse 复用 `_build_snapshot_summary` 格式**

当浏览的值是元素列表（每个元素有 ref/tag/text/selector 字段）时，用已有的 `_build_snapshot_summary` 格式输出。其他类型用 `repr` 截断。

**决策 4：limit 默认 20，offset 默认 0**

与 progressive snapshot 保持一致的分页习惯。

## 风险 / 权衡

- **风险**：shared_store 中的值可能很大，data_browse 输出可能撑爆 LLM 上下文。**缓解**：limit 上限硬编码为 100，超过截断并提示。
- **风险**：data_keys 暴露所有 key 名，如果 LLM 不小心暴露了敏感 key 名。**缓解**：key 名由 LLM 自己通过 bind 设定，不存在服务端注入的敏感 key。

## 迁移计划

纯新增功能，无破坏性变更。上线后 LLM 可在任意对话中使用 `data_keys` 和 `data_browse`。

回滚：删除 registry 中的两个注册即可。

## 待确认问题

- 无
