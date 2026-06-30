# Backend State Testability

## Requirements

### _EngineState 必须提供测试状态重置方法
`_EngineState` MUST 提供 `reset_for_test()` 方法，将 bridge、running_pipeline、ws_clients、current_state 重置为初始状态（idle）。

#### Scenario: 测试后重置状态
- **WHEN** 测试代码调用 `engine_state.reset_for_test()`
- **THEN** `engine_state.current_state` MUST 变为 `"idle"`
- **AND** `engine_state.bridge` MUST 为 `None`
- **AND** `engine_state.running_pipeline` MUST 为 `None`
- **AND** `engine_state.ws_clients` MUST 为空列表

#### Scenario: 连续两次重置
- **WHEN** 测试代码连续两次调用 `engine_state.reset_for_test()`
- **THEN** 第二次调用 MUST 不抛出异常
- **AND** 状态 MUST 保持为初始状态
