## Why

`browser_source` 单次调用就可能返回 100KB–2MB 的原始 HTML，这些 HTML 文本直接进入 LLM context window，导致：
- context 快速膨胀，后续推理质量下降
- 浪费 token budget（一次调用可能消耗数万个 token）
- LLM 难以从海量 HTML 中提取有效信息

现有防护不足：
1. 工具 schema 描述只是平淡地说"Get the HTML source"，没有强调体量和替代方案
2. `_apply_heavy_data_filter` 是事后守卫——HTML 已经进入 context 后才被替换成 size 摘要
3. Guardrail warning 只在循环 3-6 次后才触发，单次大返回零提醒
4. 除 chat 模式外，pipeline 回放（preset mode）完全不经过 registry handler

本次变更的核心：**从源头阻止 HTML 原文进入 context**，强制通过 shared_store `output_to` 写入，LLM 只拿到元信息和操作指导。同时将 schema 描述改得更强硬，引导 LLM 优先选择轻量工具。

## What Changes

- **browser_source 必须提供 `output_to` 参数**：registry handler 不再返回 HTML 原文到 context，强制写入 shared_store（使用 `output_to` 而非 `bind`，避免与通用 bind 弹出机制冲突）
- **Schema 描述强化**：在工具 description 中明确标注为"HEAVY"、说明必须 `output_to`、提示替代工具（browser_snapshot / browser_eval_js / data_browse）
- **默认 strip_styles=True**：减少 HTML 体积（包括 pipeline 回放路径）
- **删除 `_apply_heavy_data_filter` 中的 `browser_source` 分支**：该后处理已无意义（源头已拦截）
- **更新 prompt 文件**：`tool_strategy.md` 和 `system.md` 中与 `browser_source` 相关的描述同步更新
- **删除相关测试**：`test_orchestration_filter.py` 和 `test_integration_agent_reform.py` 中针对已删除分支的测试

## Capabilities

### New Capabilities
- `browser-source-bind`: browser_source 结果自动写入 shared_store（通过 `output_to` 参数指定 key），context 只返回元信息和下一步操作指导

### Modified Capabilities
- `browser-source`: 从"返回 HTML 原文"变为"必须提供 `output_to` + 只返回 size 元信息"
- `heavy-data-filter`: 移除 browser_source 分支

## Impact

- **backend/src/yak_browser_use/tools/registry.py**: 新增 `_source_handler`（使用 `output_to` 参数），从 `_BROWSER_OPS` 中移除 `source`
- **backend/src/yak_browser_use/engine/executor.py**: `strip_styles` 默认值从 `False` → `True`
- **backend/src/yak_browser_use/engine/_harness/tool_executor.py**: 删除 `_apply_heavy_data_filter` 中 `browser_source` 分支（line 470-483）
- **backend/src/yak_browser_use/prompts/guidance/tool_strategy.md**: 更新 `browser_source` 行描述
- **backend/src/yak_browser_use/prompts/chat/system.md**: 更新第 76 行描述
- **backend/tests/test_orchestration_filter.py**: 删除 `browser_source` filter 测试
- **backend/tests/test_integration_agent_reform.py**: 删除 `browser_source` filter 测试
