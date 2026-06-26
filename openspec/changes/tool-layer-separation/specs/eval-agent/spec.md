## REMOVED Requirements

### Requirement: 移除 eval_agent 工具及子 Agent 机制
`eval_agent` 工具及其关联的 `EvalAgent` 类、`_handle_eval_agent` handler、`eval_agent` 模块 SHALL 全部移除。eval_agent 的 tool schema 注册 MUST 从 registry 中移除。

**Reason:** eval_agent 子 Agent 机制增加架构复杂度但实际使用率低。主 Agent 已有 `browser_eval_js` + `browser_snapshot` 可自行迭代试错。数据流通走 `shared_store` 无需子 Agent 作为中转。YAGNI。

**Migration:**
- 原 `eval_agent(purpose="提取表格", snapshot="...", source_key="data")` 的用法 → 主 Agent 直接使用 `browser_eval_js(code="...")` + `browser_snapshot()` 迭代
- 数据流通 → 任何工具的结果可通过 `source_key` 写入 `shared_store`，不依赖子 Agent
