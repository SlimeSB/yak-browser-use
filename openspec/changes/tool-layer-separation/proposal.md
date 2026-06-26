## Why

当前工具系统边界模糊：`file_write` 可以覆盖 `pipeline.yaml` 等 Agent 结构化文件，绕过 checkpoint / diff / WebSocket push 安全网。`file_read` 直接暴露文件全文，LLM 可绕过 `read_data` 的渐进式披露保护。`eval_agent` 子 Agent 机制主 Agent 使用率低、效果差，增加架构复杂度而无实际收益。`record_step` 与 `pipeline_add_step` 功能重叠，`pipeline_load` 与 `pipeline_list` 语义接近，增加 LLM 选择负担。

本次变更将工具分为三层：Agent 工具（管理 pipeline + 数据入口）、Browser ops（需 CDP 浏览器上下文）、底层工具（仅返元信息，不返文件原文）。简化工具清单，提升 main agent 直接操控力。

## What Changes

- **新增** `read_data` 工具 — LLM 唯一文件内容入口，内置 limit / offset / encoding / convert_to / source_key，强制渐进式披露
- **合并** `pipeline_load` + `pipeline_list` → `pipeline_view` — 一个工具两种用法
- **合并** `record_step` → `pipeline_add_step` — 统一 step 添加入口，支持 op_type 参数
- **增强** `pipeline_update_step` — `updates` 支持 `"browser_ops[2].text"` 深路径 patch
- **增强** `pipeline_load` — 返回完整 `browser_ops` 列表而非仅计数
- **搬家** `eval_js` → `browser_eval_js` — 纳入 browser ops 类（**BREAKING**）
- **搬家** `wait_for_download` → `browser_wait_for_download` — 纳入 browser ops 类（**BREAKING**）
- **沙箱** `file_write` — 限定 workspace 子目录，根目录拒绝写入，返回元信息（path/size）
- **语义变更** `file_read` — 仅返回元信息（path/size/encoding），不返文件内容
- **语义变更** `format_convert` — 仅返回元信息（source/target），不返转换后内容
- **下架** `eval_agent` — 移除子 Agent 机制，主 Agent 直接用 `browser_eval_js`

## Capabilities

### New Capabilities
- `tool-layer-separation`: 三层工具架构（Agent 工具 / Browser ops / 底层工具），底层工具仅返元信息，`file_write` workspace 沙箱
- `read-data`: 统一数据读取入口，内置 limit/offset 渐进式截断、编码检测、格式转换、source_key
- `pipeline-view`: pipeline_load + pipeline_list 合并，参数可选
- `pipeline-update-deep-path`: pipeline_update_step 的 updates 支持 `"key[n].field"` 深路径
- `pipeline-load-full-ops`: pipeline_load 返回完整 browser_ops 列表

### Modified Capabilities
- `pipeline-add-step`: 合并 record_step 功能，增加 op_type / op_args 参数
- `browser-eval`: eval_js 移至 browser ops，增加 `browser_` 前缀
- `browser-wait-download`: wait_for_download 移至 browser ops，增加 `browser_` 前缀
- `format-convert`: 语义变更，仅返回元信息
- `file-io`: file_read 语义变更，仅返回元信息；file_write 增加 workspace 沙箱
- `eval-agent`: 移除子 Agent 工具及整套 EvalAgent / eval_agent 模块

## Impact

- **registry.py**: 新增 read_data 注册，调参 file_read/file_write/format_convert 语义，移除 eval_agent，合并 handler
- **_path_utils.py**: validate_path 新增 workspace 子目录限制
- **pipeline_store.py**: update_step 支持深路径 key 解析
- **pipeline_tools.py**: 合并 load/list handler，load 返回完整 ops
- **file_read.py / file_write.py**: 保持不变（语义变更在 handler 层）
- **eval_agent.py**: 移除
- **tool_executor.py**: 移除 _handle_eval_agent 及辅助函数
- **prompts/**: 更新 tool_strategy.md 工具推荐
- **tests/**: 更新覆盖新工具和移除旧工具
