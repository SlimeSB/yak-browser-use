## 1. run_check 核心重构

- [ ] 1.1 修改 `executor.py`：将 `run_check` 签名扩展为 `(check_def, bridge, step_dir=None, shared_store=None)`；移除防御性兜底——`check_def` 为 `{}` 或 `None` 时直接返回 `{ok: false, error: "..."}` 报错
- [ ] 1.2 修改 `executor.py`：在 `run_check` 函数入口添加 `ignore` 前置处理 — 如果 `check_def` 含 `{ignore: true}`，立即返回 `ok: true`
- [ ] 1.3 修改 `executor.py`：添加前置资源校验 — output_exists/file_contains 需要 step_dir；json_field_exists 需要 shared_store；js_expression 需要 bridge；缺失则返回明确错误
- [ ] 1.4 修改 `executor.py`：重构通用"无效参数"循环 — 只对已知 string-only 的 key（url_contains/element_exists/text_contains/element_visible/output_exists）做 isinstance(value, str) 校验，其他 key 跳过
- [ ] 1.5 修改 `executor.py`：新增运行时未知 key 拦截 — 遍历 check_def 的 key，发现不在 `_VALID_CHECK_KEYS` 中的 key 立即返回 `{ok: false, error: "不支持的 check key: '{key}'"}`
- [ ] 1.6 修改 `executor.py`：新增 `file_contains` 分支 — 读取文件内容并检查是否包含 `text` 字段
- [ ] 1.7 修改 `executor.py`：新增 `output_exists` 分支 — 检查 `step_dir / path` 是否存在
- [ ] 1.8 修改 `executor.py`：新增 `js_expression` 分支 — 通过 bridge.evaluate 执行 JS 并检查 truthy
- [ ] 1.9 修改 `executor.py`：新增 `json_field_exists` 分支 — 按 `.` 分隔的 field 路径逐层遍历 shared_store[step].data
- [ ] 1.10 修改 `executor.py`：优化 result_msg — 新类型使用简称（`output_exists: 通过` 而非展示完整文件路径）

## 2. 调用链更新

- [ ] 2.1 修改 `runner_preset.py`：调用 `run_check` 时传入 `step_dir=step_dir` 和 `shared_store=shared_store`
- [ ] 2.2 修改 `runner_preset.py`：去掉 bridge-None 短路逻辑 — 不再因 bridge 为 None 就直接报 CHECK_FAILED，始终调用 run_check，让 run_check 自行判断所需资源
- [ ] 2.3 确认 import 不变（run_check 已在 runner_preset 的 import 列表中）

## 3. Schema 校验层

- [ ] 3.1 修改 `schema.py`：将 `check` 字段从 `dict | None` 改为 `dict`（必填，无 default）
- [ ] 3.2 修改 `schema.py`：定义模块级常量 `_VALID_CHECK_KEYS` frozenset（包含全部 9 种合法 key）
- [ ] 3.3 修改 `schema.py`：在 `StepYaml` 上新增 `_check_guard` model_validator（mode="after"）— 空 dict 拒绝 + key 合法性校验
- [ ] 3.4 确认 `_check_guard` validator 代码物理位置插在 `_normalize_browser_ops` 与 `_check_mutual_exclusion` 之间（Pydantic mode="after" 按类体定义顺序执行）

## 4. LLM 引导更新

- [ ] 4.1 修改 `registry.py`：更新 `pipeline_create` tool schema description — 将原先"check (dict, use {} to skip)"改为强调必须显式声明 + 列出支持的类型
- [ ] 4.2 修改 `registry.py`：更新 `pipeline_compile` tool schema description — 在 hint 中强调每步必须有 check
- [ ] 4.3 修改 `pipeline_tools.py`：更新 `pipeline_compile` 返回的 hint 文本 — 引导 LLM 写有意义的 check
- [ ] 4.4 修改 `system.md`：在 Recording Rules 末尾新增 "Step Check (验收) — REQUIRED" 段落，按步骤类型列出推荐 check

## 5. 现有数据迁移

- [ ] 5.1 修改 `userdata/workspaces/bilibili-home-videos/pipeline.yaml`：为 step_2 和 step_3 补上有意义的 check（step_2 用 `json_field_exists: {step: step_2, field: bili_videos_data}` 验证 shared_store 写入；step_3 用 `output_exists: downloads/bilibili_home_videos.csv` 验证 CSV 生成）

## 6. 测试覆盖

- [ ] 6.0 修改 `test_run_check.py`：更新 `test_empty_check_def` — 期望从 `ok: true` 改为 `ok: false`（因为 `check` 必填且 `{}` 不合法）
- [ ] 6.1 修改 `test_run_check.py`：新增 `TestRunCheckIgnore` 类（ignore:true 返回 ok）
- [ ] 6.2 修改 `test_run_check.py`：新增 `TestRunCheckOutputExists` 类（pass/fail/缺少 step_dir）
- [ ] 6.3 修改 `test_run_check.py`：新增 `TestRunCheckFileContains` 类（pass/fail/文件缺失）
- [ ] 6.4 修改 `test_run_check.py`：新增 `TestRunCheckJsonFieldExists` 类（pass/fail/字段缺失/嵌套路径/缺少 shared_store）
- [ ] 6.5 修改 `test_run_check.py`：新增 `TestRunCheckJsExpression` 类（pass/fail/缺少 bridge）
- [ ] 6.6 修改 `test_run_check.py`：新增 `TestRunCheckNonStringValues` 类（file_contains dict 值不被通用循环误杀）
- [ ] 6.7 修改 `test_schema.py`：新增 `TestCheckValidator` 类（valid keys/empty dict/invalid key/缺失必填字段）
- [ ] 6.8 修改 `test_runner_preset.py`：新增集成测试 — tool step 使用 output_exists check 在 bridge 存在时通过
- [ ] 6.9 运行全部相关测试确认通过：`python -m pytest tests/test_run_check.py tests/test_schema.py tests/test_pipeline_store.py tests/test_runner_preset.py -x -q`
