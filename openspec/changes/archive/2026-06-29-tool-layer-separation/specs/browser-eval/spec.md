## MODIFIED Requirements

### Requirement: eval_js 重命名为 browser_eval_js
原 `eval_js` 工具 MUST 重命名为 `browser_eval_js`，纳入 browser ops 类。工具功能保持不变（在页面执行 JavaScript、结果写入 shared_store），仅改变名称和分类。

#### Scenario: browser_eval_js 出现在 browser ops 中
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中 MUST 包含 `browser_eval_js` 而非 `eval_js`
- **AND** tool description MUST 包含 `browser_` 前缀与其他 browser ops 一致

#### Scenario: browser_eval_js 功能不变
- **WHEN** LLM 调用 `browser_eval_js(code="document.title")`
- **THEN** 系统 MUST 通过 ctx.cdp_helpers 执行 `bridge.evaluate("document.title")`
- **AND** 返回当前页面 title 字符串
- **AND** 结果通过 `source_key` 写入 shared_store

#### Scenario: browser_eval_js 参数不变
- **WHEN** LLM 查看 `browser_eval_js` 的 tool schema
- **THEN** schema MUST 包含参数 `code`（string, required）
- **AND** schema MUST 包含参数 `source_key`（string, optional）

## REMOVED Requirements

### Requirement: 移除 eval_js 工具注册
原 `eval_js` 工具名 SHALL 从 registry 移除。**Reason:** 重命名为 `browser_eval_js` 以纳入 browser ops 分类体系。**Migration:** 已有 pipeline 中引用 `eval_js` 的步骤需要更新 tool_name 为 `browser_eval_js`。**BREAKING**。
