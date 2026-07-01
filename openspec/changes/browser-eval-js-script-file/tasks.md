## 1. 核心实现

- [ ] 1.1 在 `_eval_js_handler` 中新增 `script_file` 参数读取逻辑：当 `script_file` 有值时，使用 `validate_path` 解析路径并读取文件内容，将内容作为 `code` 传给 `bridge.evaluate(code)`
- [ ] 1.2 添加互斥校验：`script_file` 和 `code` 都为空时返回错误；两者都有时优先 `script_file`
- [ ] 1.3 更新 `browser_eval_js` 的 `description`，包含 `return` 语法警告和 `script_file` 用法
- [ ] 1.4 在 `parameters.properties` 中新增 `script_file` 字段的 schema 定义（type: string，非 required）；并将 `required` 从 `["code"]` 改为 `[]`（互斥校验在 handler 中完成）

## 2. 验证与收尾

- [ ] 2.1 运行 `test_registry.py` 确认不破坏现有测试
- [ ] 2.2 手动验证：调用 `browser_eval_js(code="document.title")` 行为不变
