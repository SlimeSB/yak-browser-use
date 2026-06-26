## MODIFIED Requirements

### Requirement: browser_snapshot 支持 expand_key 参数
`browser_snapshot` 工具 MUST 新增可选参数 `expand_key`，在 `mode="progressive"` 时指定要展开的折叠容器 key，替代独立的 `browser_expand_branch` op。

#### Scenario: snapshot 同时展开容器
- **WHEN** LLM 调用 `browser_snapshot(mode="progressive", expand_key="c_0")`
- **THEN** executor 先执行 progressive snapshot，然后展开 `c_0` 容器
- **AND** 返回结果中包含展开后的元素

### Requirement: browser_expand_branch op 移除
系统 MUST 从 `_BROWSER_OPS`、`execute_browser_op()`、`execute_browser_step()` 中移除 `expand_branch` op。

#### Scenario: 旧 pipeline 使用 expand_branch 会报错
- **WHEN** preser 模式执行到 `{type: expand_branch, key: "c_0"}` 步骤
- **THEN** `execute_browser_op()` 返回 `Unknown browser op type: expand_branch`
