## 1. 测试编写（TDD 绿测试）

- [x] 1.1 创建 `backend/tests/test_api_state.py`，编写 `test_reset_for_test` 测试：构造 `_EngineState` 实例，设置非初始状态后调用 `reset_for_test()`，断言所有字段回到初始值（`current_state == "idle"`、`bridge is None`、`running_pipeline is None`、`ws_clients == []`），以及连续两次调用不抛异常
- [x] 1.2 创建 `backend/tests/test_api_run_snapshot.py`，编写 `test_snapshot_preserved_on_error` 测试：模拟 pipeline 执行异常场景，验证 snapshot 文件被移动到 `_errors/` 子目录而非被删除
- [x] 1.3 运行新增测试，确认全部失败（红灯）—— 因为 `reset_for_test()` 尚未实现，`api_run` 的 `finally` 块仍在删除快照

## 2. 核心实现

- [x] 2.1 在 `state.py` 的 `_EngineState` 中添加 `reset_for_test()` 方法：将 `bridge` 置为 `None`，`_running_pipeline` 置为 `None`，`ws_clients` 清空，`current_state` 置为 `"idle"`
- [x] 2.2 修改 `routes.py` 的 `api_run`：将 `finally` 块中的 `snapshot_path.unlink()` 替换为将文件移动到 `versions/_errors/` 子目录（先创建目录，再 `shutil.move`）

## 3. 验证与收尾

- [x] 3.1 运行 `pytest tests/test_api_state.py tests/test_api_run_snapshot.py -v`，确认所有新增测试通过（绿灯）
- [x] 3.2 运行全量 `pytest`，确认无回归
