## 1. 基础设施

- [ ] 1.1 新建 `tools/extract_fields.py`：实现以下函数：
  - `_safe_selector(sel: str) -> str`：转义单引号（`'` → `\'`），防 JS 注入
  - `_build_selector_js(selector: str) -> str`：生成通用 selector 提取 JS（复用 extract.py:262-276 的逻辑），每个元素返回 `{text, href}`
  - `_build_field_extraction_js(selector: str, fields: dict) -> str`：将字段映射转为客户端 JS。规则：`"key": "h3"` → `el.querySelector('h3')?.textContent?.trim() || ''`；`"key": "@attr"` → `el.getAttribute('attr') || ''`
  - `_build_table_selector_js(selector: str) -> str`：包装表格提取逻辑，限制 root 为 `document.querySelector(selector)`，在该子树内执行 headers + rows 提取
  - `_build_details_selector_js(selector: str) -> str`：生成 key-value 提取 JS（复用 extract.py:308-324 逻辑），限制容器为 `document.querySelector(selector)`，提取 tr>th/td 或 li 的 label:value 对

## 2. 注册 extract 工具

- [ ] 2.1 在 registry.py `_build_registry_impl()` 末尾注册 `browser_extract_list`：schema 含 `selector`（可选）、`output_to`（可选）、`fields`（可选 object）；handler 逻辑：先用 `_safe_selector` 转义 selector；fields 非空时调 `_build_field_extraction_js` 生成 JS 执行；selector 非空时调 `_build_selector_js`；否则用 `EXTRACT_LIST_JS`。shared_store 存**完整**数据，返回给 LLM 的 items 截断为前 50 项 + `_truncated` 标记
- [ ] 2.2 在 registry.py 注册 `browser_extract_table`：schema 含 `output_to`（可选）、`selector`（可选）；handler 调 `bridge.evaluate(EXTRACT_TABLE_JS)` 或用 `_safe_selector` + selector 版本。shared_store 存完整数据，返回 rows 截断前 100 行
- [ ] 2.3 在 registry.py 注册 `browser_extract_details`：schema 含 `output_to`（可选）、`selector`（可选）；handler 调 `bridge.evaluate(EXTRACT_DETAILS_JS)` 或用 `_safe_selector` + selector 版本

## 3. format_convert output_to

- [ ] 3.1 修改 `_format_convert_handler`：增加 `output_to` 参数。转换成功后由 handler 自己调用 `validate_path(target, pipeline=ctx.pipeline_name or None)` 获取绝对路径，将绝对路径字符串存入 `ctx.shared_store[output_to]`（方案 A：handler 自行 validate，不依赖 format_convert 的返回值解析）

## 4. 测试

- [ ] 4.1 新建 `test_extract_chat_tools.py`：覆盖以下场景：
  - 通用列表提取返回正确结构
  - 自定义 selector 提取
  - fields 映射提取
  - output_to 存入完整 shared_store 且返回截断数据
  - 截断 + 无 output_to
  - selector 含单引号被正确转义
  - table 通用提取 + selector + output_to + 截断
  - details 通用 + selector + output_to
- [ ] 4.2 新建 `test_format_convert_output_to.py`：
  - 转换成功后 shared_store 存绝对路径
  - source_json 路径同样存绝对路径
  - 转换失败时不修改 shared_store
  - 无 output_to 时行为不变

## 5. 回归验证

- [ ] 5.1 运行 `python -m pytest backend/tests/` 确认全部通过
