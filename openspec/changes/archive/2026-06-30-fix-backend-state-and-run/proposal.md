## Why

`state.py` 中 `engine_state = _EngineState()` 是模块级全局单例，所有路由 handler 直接 `from state import engine_state` 后读写。这导致无法并行运行测试、无法 mock 状态、测试之间有状态泄漏。

`routes.py` 中 `api_run` 在异常路径的 `finally` 块里通过 `snapshot_path.unlink()` 删除 pipeline 快照，导致调试时无法查看出问题的 pipeline 内容。

两个问题都是在 `refactor-frontend-hooks` 审查中确认的，现在修复以提升后端可测试性和可调试性。

## What Changes

**修改：**
- `state.py` — `_EngineState` 新增 `reset_for_test()` 方法，将 bridge / running_pipeline / ws_clients / current_state 重置为初始状态
- `routes.py` — `api_run` 的 `finally` 块改为将异常快照移动到 `_errors/` 目录而不是删除

**新增：**
- `tests/test_state.py` — 验证 `reset_for_test()` 能正确重置所有状态字段
- `tests/test_api_run.py` — 验证 pipeline 执行异常时快照被保留在 `_errors/` 目录

**BREAKING：** 无。`reset_for_test()` 是新增方法，不影响现有调用方。

## Capabilities

### New Capabilities

- `backend-state-testability`: `_EngineState` 提供 `reset_for_test()` 方法，支持测试环境下的状态隔离和重置
- `backend-snapshot-preservation`: `api_run` 在 pipeline 执行异常时保留快照到 `_errors/` 目录而不是删除

### Modified Capabilities

无。

## Impact

**文件改动范围：**
- 修改文件：2 个（`state.py`、`routes.py`）
- 新增文件：2 个（`tests/test_state.py`、`tests/test_api_run.py`）

**依赖影响：** 无新增依赖。

**测试影响：**
- 新增 2 个测试文件，遵循项目现有的 `pytest` 约定
- `reset_for_test()` 方法仅用于测试环境，不影响生产路径
