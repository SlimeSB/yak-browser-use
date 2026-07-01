## Why

在 Agent 对话场景中，`browser_eval_js` 获取到的数据无法自动传递给下一个工具调用。Agent 拿到 JS 执行结果后，只能手动格式化（如手写 CSV 字符串拼接、处理引号转义），然后通过 `file_write` 保存。这个过程有三个问题：

1. **数据断链**：eval_js 的结果流入 LLM 上下文后，下一步 tool call 无法直接引用原始数据对象，只能依赖 LLM 重新生成文本内容
2. **格式丢失**：LLM 在上下文中看到的 JSON 结果被截断/格式化后，可能在二次转换中出现精度损失
3. **体验退化**：Agent 需要额外的 turn 来做"把结果格式化并保存"这种本应由框架自动完成的事情

根本原因是当前 `shared_store` 变量总线虽然已经存在于 `ToolContext` 中，但没有任何工具 schema 暴露"存入变量"或"消费变量"的能力。工具和变量系统是脱节的。

## What Changes

- **browser_eval_js 增加 `output_to` 参数**：执行 JS 后自动将结果存入 `shared_store` 的指定变量名
- **browser_eval_js 增加 `return_format` 参数**：支持 `raw`/`json`/`csv` 三种返回格式，其中 `csv` 自动把 JSON 数组转为 CSV 文本
- **file_write 支持 `{key}` 模板引用**：content 参数中的 `{key}` 会被替换为 `shared_store` 中对应变量的值（JSON 序列化）。与现有 schema description 统一
- **format_convert handler 修复为真正调用 `format_convert()`**：当前 `_format_convert_handler` 只做了格式嗅探返回信息，从未调用真正的转换函数。修复后支持完整转换功能
- **format_convert 增加 `source_json` 参数**：支持从内存中的 JSON 数据直接转换为目标文件格式，无需先写临时文件再转换
- **snapshot query schema 描述修正**：把"支持 CSS selector"的误导性描述改为准确的"文本/tag/role 模糊匹配"

## Capabilities

### New Capabilities

- `eval-output-to-variable`: browser_eval-js 执行结果自动存入 shared_store，后续工具通过 `{key}` 引用
- `file-write-template-ref`: file_write 的 content 参数支持 `{key}` 模板替换，从 shared_store 取数据写入文件
- `format-convert-from-memory`: format_convert 接受 source_json 参数直接从内存 JSON 转换为目标文件

### Modified Capabilities

- `browser-eval-js`: 增加 output_to 和 return_format 两个可选参数
- `file-write`: content 参数支持 `{key}` 模板语法，与现有 schema description 统一
- `format_convert`: 修复 handler 为真正调用 format_convert()；增加可选的 source_json 入参
- `browser-snapshot`: 修正 query 参数的 description 文本

## Impact

- **后端文件**：`tools/registry.py`（eval_js schema + handler）、`tools/file_write.py`（模板解析）、`tools/format_convert.py`（source_json 分支）
- **行为影响**：完全向后兼容，所有新参数可选且不影响现有默认行为
- **测试**：需要新增覆盖 output_to、return_format、file_write 模板引用、format_convert source_json 的用例
- **Prompt/Agent 体验**：Agent 可以使用更简洁的 pipeline 完成"提取→格式化→保存"全链路
