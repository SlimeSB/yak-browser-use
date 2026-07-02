## 背景

当前 `run_check` 位于 `backend/src/yak_browser_use/engine/executor.py:487`，签名 `(check_def, bridge)`，仅支持 4 种浏览器导向的验证类型。check 字段在 Pydantic schema 中定义为 `dict | None`，无 key 校验，空 dict `{}` 视为合法且默认通过。

`runner_preset.py:305-321` 在步骤执行完成后调用 `run_check`，但只传 `check_def` 和 `bridge`，无 `step_dir` 和 `shared_store`。

pipeline 的 LLM 生成引导（system.md + registry.py tool schema + pipeline_compile hint）均未强调 check 必要性，schema description 甚至暗示"可以 `{}` 跳过"。

## 目标 / 非目标

**目标：**
- `check` 字段改为必填（像 `name` 一样），不可省略
- 每步必须显式声明验收方式——要么实际验收，要么 `{ignore: true}`，不允许空 dict
- 扩展 run_check 支持文件类、数据类、JS 表达式类验收
- 在 schema 层拒绝不支持的 key，而非运行时静默忽略
- 修复通用 string 校验循环对非 string 值的误杀
- LLM 生成 pipeline 时主动写出有意义的 check

**非目标：**
- 不改变 chat 模式的执行逻辑（pipeline 专属）
- 不改变 `edit_pipeline` 的文本编辑路径
- 不增加新的 CLI 命令或 API 端点
- 不影响现有的 goal 步骤执行流程

## 关键决策

### 1. run_check 签名扩展方案

**选择：** 增加可选参数 `step_dir: Path | None = None` 和 `shared_store: dict | None = None`

**原因：** 最小侵入性。现有浏览器类 check 不需要这些参数，保持向后兼容。新 check 类型通过前置校验确保所需参数存在，否则返回明确的错误。

**备选（未选）：** 改为第三方 context 对象传参。过度设计，且需要改 runner_preset 调用方式。

### 2. 通用 string 校验循环重构

**选择：** 将 `for key in check_def` 校验改为只对已知 string 类型的 key 做非空检查，其他 key 跳过由专属分支校验

**原因：** 精确控制，避免误杀。新类型 `output_exists` 的值是 string 路径、`file_contains` 的值是 dict、`ignore` 的值是 bool、`json_field_exists` 的值是 dict。统一循环无法区分。

### 3. Validator 加在 StepYaml 而非 PipelineYaml

**选择：** Pydantic model_validator 加在 `StepYaml` 类上（`_check_guard`）

**原因：** StepYaml 对应单个步骤，每步独立校验 check 字段。validator 在 `pipeline_create` / `pipeline_update_step` 的 `StepYaml.model_validate()` 调用时自动生效。

**执行顺序：** 加在 `_normalize_browser_ops` 之后，`_check_mutual_exclusion` 之前（按 validator 定义顺序执行）。

### 4. 不支持的 key 在 schema 层拦还是运行时拦

**选择：** 双重防御——schema 层 validator 拒绝写入；`run_check` 运行时遇到未知 key 也返回 ok=False

**原因：** schema 校验是主要卡口（pipeline_update_step/create 都会触发）；运行时防御是兜底（防止旧文件/绕过 schema 的场景）。

### 5. 关于 `check` 必填的 Breaking 处理

**选择：** `check` 改为必填字段（`dict` 而非 `dict | None`），schema validator 拒绝空 dict 和缺失字段，运行时 `run_check` 收到 `{}`/`None` 直接报错不兜底

**原因：** 移除所有灰色地带——schema 是唯一防线，不存在"防御性返回 ok"的退路。`check` 像 `name` 一样必须存在且有意义的值。旧文件加载时如缺少 check，必须通过迁移补上 `{ignore: true}` 或实际验收条件。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| 现有 pipeline 用 `check: {}` 或缺失 check | 加载时 Pydantic 报错 | 自动迁移：扫描现有文件将 `{}`/缺失 替换为 `{ignore: true}` |
| 文件检查路径安全 | output_exists 可能用 `..` 越出 step_dir | 用 `Path` 拼接 + resolve + 验证前缀在 step_dir 内 |
| ignore 被滥用 | LLM 全用 ignore 逃避验收 | prompt + schema 描述强调"必须有实际验收或明确声明忽略" |

## 迁移计划

**Phase 1 — 代码实现（本次变更单元）：**
1. `executor.py`: run_check 重构 + 新类型
2. `runner_preset.py`: 调用处传 step_dir/shared_store
3. `schema.py`: validator
4. `registry.py`: tool schema 文本
5. `pipeline_tools.py`: compile hint
6. `system.md`: prompt 段落
7. 现有 `bilibili-home-videos` 补 check

**Phase 2 — 验证（本次变更单元）：**
- test_run_check 新测试全部通过
- test_schema validator 测试通过
- test_pipeline_store round-trip 不受影响
- test_runner_preset 新增集成测试

**需要迁移** —— `check` 改为必填后，旧文件 `check: None` / `{}` 在加载 `StepYaml` 时直接 Pydantic 报错（不是 write 时才触发）。必须先将现有文件的 `{}`/缺失 迁移为 `{ignore: true}`，之后才能正常加载。

## 待确认问题

1. **result_msg 展示**：新类型（如 output_exists）成功时是否需要在 result 中展示完整路径？当前计划展示 type 缩写（`output_exists: 通过`），不做路径展示，避免成功消息过长。
2. **json_field_exists 是否支持数组索引**：如 `data.ops[0].name`？当前设计只支持点号分隔的 dict key 导航。如需数组索引可后续扩展。
3. **ignore 是否需要 reason 字段**：如 `{ignore: true, reason: "幂等步骤无需验收"}`？当前不做——reason 是可选增强，不阻碍实施。
