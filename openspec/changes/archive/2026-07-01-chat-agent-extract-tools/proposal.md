## Why

当前 `browser_extract_list`、`browser_extract_table`、`browser_extract_details` 三个数据提取工具只在 pipeline 模式下可用（通过 `extract.py` 注册为 pipeline step），chat agent 无法直接在对话中调用它们。

这导致 Agent 需要写自定义 JavaScript（通过 `browser_eval_js`）来完成同样的列表/表格/详情提取工作——既浪费 token 又容易出错。

同时，`format_convert` 已有 `source_json` 参数支持从内存 JSON 转换，但缺少 `output_to` 参数将转换后的文件路径存入 `shared_store`，Agent 无法在后续步骤中引用转换结果。

## What Changes

- **注册 browser_extract_list 到 chat registry**：暴露 `selector`、`output_to`、`fields` 参数，支持自定义字段映射提取
- **注册 browser_extract_table 到 chat registry**：暴露 `output_to`、`selector` 参数
- **注册 browser_extract_details 到 chat registry**：暴露 `output_to`、`selector` 参数
- **format_convert 增加 output_to 参数**：转换完成后将目标文件路径存入 `shared_store`

## Capabilities

### New Capabilities

- `browser-extract-list-chat`: Agent 可在对话中直接调用结构化列表提取，结果存入 shared_store
- `browser-extract-table-chat`: Agent 可在对话中直接调用表格提取
- `browser-extract-details-chat`: Agent 可在对话中直接调用详情键值对提取
- `format-convert-output-to`: format_convert 转换完成后将结果存入 shared_store

### Modified Capabilities

- `format_convert`: 增加可选的 `output_to` 参数

## Impact

- **后端文件**：`tools/registry.py`（新增 3 个 extract handler + schema）、`tools/extract.py`（无需修改，复用 EXTRACT_*_JS 常量和 evaluate 逻辑）
- **行为影响**：完全向后兼容，新增注册不影响现有 pipeline 模式
- **测试**：需新增覆盖 extract handler（含 fields 映射、output_to 存入）和 format_convert output_to 的用例
- **Prompt/Agent 体验**：Agent 可直接用结构化提取替代手写 JS eval，减少 token 消耗和出错概率
