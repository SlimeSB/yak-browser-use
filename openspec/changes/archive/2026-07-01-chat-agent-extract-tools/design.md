## 背景

`tools/extract.py` 已定义了三个提取函数（`extract_table`、`extract_list`、`extract_details`），它们：
1. 接受 `input_files`、`output_dir`、`cdp_helpers`、`**params` 参数
2. 内部调用 `cdp_helpers.evaluate()` 执行客户端 JS 提取数据
3. 通过 `_save_output()` 将结果写入 `output_dir/name.json`

在 pipeline 模式下，这三个函数由 pipeline step 调用，结果写入文件系统。

但 chat agent 的 tool handler 签名是 `(args: dict, ctx: ToolContext) -> dict`，与 extract 函数签名不同。需要新建 handler 桥接。

## 目标 / 非目标

**目标：**
- Agent 在对话中可直接调用 `browser_extract_list/table/details`
- 提取结果直接返回 JSON（不写文件），可选存入 `shared_store`
- `browser_extract_list` 支持 `fields` 参数做自定义字段映射提取
- `format_convert` 支持 `output_to` 将转换后文件的绝对路径存入 `shared_store`

**非目标：**
- 不修改 `extract.py` 的实现（纯复用）
- 不新增 pipeline 能力
- 不做跨 turn 持久化

## 关键决策

### 决策 1：新建 handler 而非修改 extract 函数

extract 函数的签名 `(input_files, output_dir, cdp_helpers, **params)` 与 chat handler 签名不兼容。且 extract 函数内部调用 `_save_output()` 写文件，chat 模式不需要文件系统操作。

**方案**：在 registry.py 中新建 handler，直接 `import` EXTRACT_*_JS 常量（已是模块级变量），通过 `bridge.evaluate(js)` 执行，结果返回给 LLM。

**复用现有 JS 生成逻辑**：`extract_list` 在 pipeline 模式已有自定义 selector JS（`extract.py:262-276`），抽取为 `extract_fields.py` 的 `_build_selector_js(selector)` 函数复用于 chat handler，避免重复逻辑。

### 决策 2：fields 参数生成自定义 JS

当 Agent 提供 `fields` 参数（如 `{"title": "h3", "href": "@href"}`）时，动态生成 JS：
- `"title": "h3"` → `el.querySelector('h3')?.textContent?.trim() || ''`
- `"href": "@href"` → `el.getAttribute('href') || ''`

JS 生成器放在 `tools/extract_fields.py`（新文件），包含 `_build_field_extraction_js(selector, fields)` 和复用的 `_safe_selector(selector)` 转义函数。

### 决策 3：返回截断策略

为避免 token 溢出，默认返回截断结果：
- `browser_extract_list`：截断前 50 项
- `browser_extract_table`：截断前 100 行
- `browser_extract_details`：不截断（details 通常不大）

**关键：shared_store 始终存完整数据，只有返回给 LLM 的被截断。** Agent 可通过 `data_browse` 查看 shared_store 完整内容。

### 决策 4：format_convert output_to 语义

`output_to` 存入 `shared_store` 的值为目标文件的**绝对路径**字符串（经 `validate_path()` 解析后）。理由是：
- 大文件内容不适合放入 shared_store（内存压力）
- Agent 需要绝对路径才能在后续步骤中准确操作文件
- multipipeline 场景下相对路径可能歧义

### 决策 5：JS 注入防护

对 `selector` 参数做基本字符转义（`'` → `\'`），参考 `_captcha_handler` 的 `safe_sel` 模式（`registry.py:817`）。具体实现：`extract_fields.py` 提供 `_safe_selector(sel)` 函数。

## 风险 / 权衡

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| selector 含特殊字符导致 JS 错误 | 提取失败 | `_safe_selector()` 转义单引号 |
| 大列表导致 token 溢出 | 返回结果过大 | 默认截断，shared_store 存完整 |
| 与 pipeline extract step 混淆 | Agent 可能同时看到两个同名工具 | chat registry 用 `browser_extract_list`（带 browser_ 前缀），pipeline 用 `extract_list`，不冲突 |
| format_convert 存绝对路径 vs 相对路径 | Agent 后续步骤找不到文件 | 存 validate_path 后的绝对路径 |

## 迁移计划

1. 新建 `tools/extract_fields.py` 放 JS 生成器（含 `_safe_selector`）
2. 在 registry.py 的 `_build_registry_impl()` 末尾追加注册
3. 修改 `_format_convert_handler` 增加 `output_to` 支持（存绝对路径）
4. 添加测试用例
