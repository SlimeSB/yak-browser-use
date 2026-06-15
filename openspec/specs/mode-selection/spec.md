## ADDED Requirements

### Requirement: CLI 和 API 支持执行引擎选择

系统 MUST 支持通过 `--engine` 参数选择 pipeline 执行引擎：programmatic（三层 fallback）或 agent（全程 LLM 驱动）。注意：现有 `--mode` 参数（auto/static/learn/replay）未被使用，保留不动，新参数使用 `--engine` 避免命名冲突。

#### Scenario: 默认使用 programmatic 引擎

- **WHEN** 用户执行 `ybu run pipeline.yaml` 且未指定 --engine
- **THEN** 系统 MUST 使用 programmatic 引擎执行
- **AND** 执行路径 MUST 包含 Tier 1 retry + Tier 2 Local Planner + Tier 3 Agent Swimlane

#### Scenario: 显式指定 agent 引擎

- **WHEN** 用户执行 `ybu run pipeline.yaml --engine agent`
- **THEN** 系统 MUST 直接调用 run_preset_loop()
- **AND** 执行路径 MUST 全程由 LLM 驱动，不经过程序化 fallback

#### Scenario: API 接受 engine 字段

- **WHEN** API 收到 pipeline 执行请求且 body 中包含 engine 字段
- **THEN** 系统 MUST 根据 engine 值选择执行路径（"programmatic" 或 "agent"）
- **AND** 无效的 engine 值 MUST 返回 400 错误
