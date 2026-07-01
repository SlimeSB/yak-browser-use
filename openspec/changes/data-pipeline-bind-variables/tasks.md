## 1. Bug 修复（前置）

- [x] 1.1 **修复 `_format_convert_handler` 不调用 `format_convert()` 的 bug**：当前 handler（registry.py:854-864）只做格式嗅探返回格式信息，从未真正执行文件转换。修改为调用 `format_convert(source, target, source_fmt, target_fmt, pipeline=ctx.pipeline_name)` 并返回其结果

## 2. 核心实现

- [x] 2.1 在 `tools/registry.py` 中为 `browser_eval_js` 增加 `_auto_csv(data: list) -> str` 辅助函数：将 JSON 数组转为 CSV 文本（第一行为所有字段名的并集作为表头，正确处理逗号/引号/换行转义；非 array 输入时降级为 `str(data)`）
- [x] 2.2 修改 `tools/registry.py` 中 `_eval_js_handler` 函数：执行 `bridge.evaluate(code)` 后，若 `args` 含 `output_to`，将原始 `result` 存入 `ctx.shared_store[output_to]`；按 `return_format`（raw/json/csv）格式化返回值
- [x] 2.3 修改 `tools/registry.py` 中 `browser_eval_js` 的 JSON Schema，增加 `output_to`（string，可选）和 `return_format`（enum: raw/json/csv，默认 raw）两个参数
- [x] 2.4 修改 `tools/registry.py` 中 `_file_write_handler`：在执行 `file_write()` 前，使用正则 `re.compile(r'\{(\w+)\}')` 扫描 `content` 参数（与现有 schema description 中的 `{key}` 语法一致），对每个匹配项从 `ctx.shared_store` 中查找并替换为 JSON 序列化字符串；找不到则保留原文并在返回中添加 `_warnings`
- [x] 2.5 修改 `tools/format_convert.py`：在函数签名中增加 `source_json: Any = None` 参数；在 `validate_path(source)` 之前增加 `if source_json is not None:` 分支，直接根据 `target_fmt` 调用 `_write_csv_from_list()` 或 `_write_xlsx_from_list()`
- [x] 2.6 在 `tools/format_convert.py` 中增加 `_write_csv_from_list(data: list, path: Path)` 辅助函数：将 JSON 数组转为 CSV，自动提取所有字段并集作为表头
- [x] 2.7 在 `tools/format_convert.py` 中增加 `_write_xlsx_from_list(data: list, path: Path)` 辅助函数：复用 openpyxl 写入逻辑

## 3. Schema 修正

- [x] 3.1 修改 `tools/registry.py:200-201` 的 snapshot query description，将"支持 CSS selector"改为"仅按文本/tag/type/role 模糊匹配，不支持 CSS selector"
- [x] 3.2 修改 `tools/registry.py:578` 的 file_write description，统一模板语法描述：将"content 支持 {key} 引用"改为"content 支持 {key} 模板替换：{content} 中的 {varname} 会被替换为 shared_store 中对应变量的 JSON 序列化值"

## 4. 测试验证

- [x] 4.1 在 `backend/tests/` 增加 `test_eval_output_to.py`：测试 output_to 正确存入 shared_store；测试 return_format=csv/json/raw 三种格式输出；测试非 array + return_format=csv 的降级处理
- [x] 4.2 在 `backend/tests/` 增加 `test_file_write_template.py`：测试 `{key}` 引用替换；测试无模板语法时行为不变（向后兼容）；测试找不到变量时保留原文并返回 warning
- [x] 4.3 在 `backend/tests/` 增加 `test_format_convert_handler.py`：测试 `_format_convert_handler` 真正执行转换（不再只返回格式信息）
- [x] 4.4 在 `backend/tests/` 增加 `test_format_convert_memory.py`：测试 source_json 为 list 时正确生成 CSV/xlsx；测试 source_json 和 source 同时提供时 source_json 优先

## 5. 回归验证

- [x] 5.1 运行 `python -m pytest backend/tests/test_registry.py` 确认所有现有测试通过
- [x] 5.2 运行 `python -m pytest backend/tests/test_file_io.py` 确认 file_write / file_read 原有行为不受影响
- [x] 5.3 运行 `python -m pytest backend/tests/` 全量测试确认无回归
