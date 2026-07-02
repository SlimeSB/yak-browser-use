## ADDED Requirements

### Requirement: ignore 显式跳过
系统 SHALL 支持 `{ignore: true}` 作为显式声明跳过验收的方式，运行时不执行任何验证。

#### Scenario: ignore 返回 ok
- **WHEN** check 为 `{ignore: true}`
- **THEN** run_check 返回 `{ok: true, result: "ignore: 显式跳过验收"}`

#### Scenario: ignore 在 schema 校验时合法
- **WHEN** StepYaml 的 check 字段为 `{"ignore": true}`
- **THEN** Pydantic 校验通过

#### Scenario: ignore 在运行时不需要 step_dir/shared_store
- **WHEN** check 为 `{ignore: true}` 但 step_dir=None 且 shared_store=None
- **THEN** run_check 仍返回 `{ok: true}`（ignore 不需要任何资源）

#### Scenario: ignore 不与其他 key 并存
- **WHEN** check 为 `{ignore: true, url_contains: "x"}`（与其他 key 组合）
- **THEN** schema validator 仍通过（Prompt 引导 LLM 不要混用），运行时 `ignore: true` 始终优先——跳过全部检查，返回 `{ok: true}`
