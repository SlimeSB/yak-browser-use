## Why

当前 pipeline 步骤的 `check` 验收机制存在"可完全绕过"的问题：LLM 生成 pipeline 时可以**不写 check**（`check: None`）、写空字典 `check: {}`，或使用不支持的 key（静默忽略）。这导致大量步骤在运行时没有任何验收验证，step 即使实际未成功也会被标记为 `completed`。本次变更将 `check` 从可选字段改为**必填字段**——每步必须显式声明验收方式（实际验收 或 `{ignore: true}`），不允许省略、不允许空字典。

现有 `run_check` 仅支持 4 种浏览器导向的验证（URL/元素/文本），无法验证工具步骤的输出产物（如 CSV 是否生成、shared_store 数据是否写入）。同时，工具 schema 描述暗示"可以 `{}` 跳过"，prompt 中也未强调 check 的必要性——LLM 没有动力主动写有意义的验收条件。

本次变更要让 check 从"可选装饰"变为"显式声明"——每步必须写 check（要么实际验收，要么显式 `ignore`），并扩展 run_check 支持输出文件类验收，覆盖工具步骤场景。

## What Changes

- **BREAKING**: `check` 字段从可选改为必填。每步必须显式声明——要么实际验收，要么 `{ignore: true}`。不允许省略、不允许空字典。Pydantic validator 会拒绝空 dict 和缺失字段。
- **BREAKING**: run_check 遇到不认识的 key 时，schema 校验阶段直接报 ValidationError，而非运行时被静默忽略。
- **新增**: `run_check` 支持 5 种新 check 类型：`output_exists`、`file_contains`、`js_expression`、`json_field_exists`、`ignore`。
- **修改**: `run_check` 签名增加可选参数 `step_dir: Path | None` 和 `shared_store: dict | None`，支持不依赖浏览器的文件/数据验收。
- **修改**: runner_preset.py 调用 run_check 时传入 `step_dir` 和 `shared_store`。
- **修改**: tool schema description（registry.py）强调每步必须写 check，列出支持的类型。
- **修改**: pipeline_compile hint 和 system.md prompt 引导 LLM 生成有意义的 check。
- **修改**: 现有 `bilibili-home-videos` pipeline.yaml 补上缺失的 check 字段。
- **修改**: 修复 run_check 通用"无效参数"循环对 dict/bool 值的误杀（file_contains/json_field_exists/ignore 的值不是 string）。

## Capabilities

### New Capabilities

- `check-output-validation`: 支持 output_exists / file_contains 文件类验收
- `check-data-validation`: 支持 json_field_exists shared_store 数据路径验收
- `check-js-expression`: 支持 js_expression 自定义浏览器 JS 验收
- `check-ignore-explicit`: 支持 {ignore: true} 显式声明跳过验收

### Modified Capabilities

- `step-check`: 从"可选+可静默忽略"改为"必须显式声明"；key 合法性在 schema 层校验
- `run-check`: 签名扩展，新增 4 种非浏览器导向 check + 1 种 ignore

## Impact

**代码影响**:
- `backend/src/yak_browser_use/engine/executor.py` — run_check 函数体大幅增加
- `backend/src/yak_browser_use/engine/runner_preset.py` — 1 行调用改动
- `backend/src/yak_browser_use/compiler/schema.py` — 新增 validator
- `backend/src/yak_browser_use/tools/registry.py` — tool schema description 文本更新
- `backend/src/yak_browser_use/engine/_harness/pipeline_tools.py` — compile hint 文本
- `backend/src/yak_browser_use/prompts/chat/system.md` — prompt 新增段落
- `userdata/workspaces/bilibili-home-videos/pipeline.yaml` — 补 check

**测试影响**:
- `backend/tests/test_run_check.py` — 新增测试覆盖所有新类型和边界
- `backend/tests/test_schema.py` — 新增 validator 测试
- `backend/tests/test_runner_preset.py` — 新增集成测试

**行为影响**:
- **向后不兼容**：已存在的 pipeline.yaml 如果没有 `check` 字段（`None`），或写了 `check: {}`，在下次 `pipeline_update_step` / `pipeline_create` 时报错——必须补上有效 check（实际验收 或 `{ignore: true}`）
- 运行时 `run_check` 收到 `{}` 或 `None` 直接报错，不做防御性兜底（schema 是唯一防线）
- 已有的 4 种浏览器 check 行为完全不变

**不影响的**:
- chat 模式（不经过 pipeline yaml）
- edit_pipeline（直接编辑文本，不经过 validator）
- goal 步骤（check 逻辑与步骤类型无关）
