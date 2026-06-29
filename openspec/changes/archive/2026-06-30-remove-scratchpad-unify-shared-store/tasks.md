## 1. 准备与基础改造

- [x] 1.1 在 `tool_executor.py` 中创建 `_build_snapshot_summary(elements, url, title)` 函数，将 `scratchpad._build_summary()` 的逻辑内联迁移，输入从 `ScratchpadRecord` 改为独立参数
- [x] 1.2 重构 `_apply_heavy_data_filter` 中 browser_snapshot 的 a11y / progressive / full 分支，用 `_build_snapshot_summary` 替代 `store_scratchpad` + `get_scratchpad().summary`

## 2. 删除 scratchpad 耦合

- [x] 2.1 重构 `_apply_heavy_data_filter` 中 browser_source 分支，移除 `scratchpad_store_raw_html(html)` 调用和 `get_scratchpad()` 引用
- [x] 2.2 删除 `_try_scratchpad_source_read()` 函数（`tool_executor.py:529`）
- [x] 2.3 在 `_execute_single_tool_call` 中删除 `_try_scratchpad_source_read()` 的调用（`tool_executor.py:205-208`）
- [x] 2.4 清理 `tool_executor.py` 中所有 `from yak_browser_use.engine.scratchpad import ...` 语句（`_apply_heavy_data_filter` 和 `_try_scratchpad_source_read` 内）
- [x] 2.5 删除 `engine/scratchpad.py` 整个文件

## 3. 测试与验证

- [x] 3.1 删除 `tests/test_scratchpad.py`
- [x] 3.2 更新 `tests/test_integration_agent_reform.py` 中 scratchpad 相关 import 和测试用例（`TestScratchpadLifecycle`）
- [x] 3.3 更新 `tests/test_orchestration_filter.py` 中 scratchpad 相关 import 和测试用例
- [x] 3.4 运行 `python -m pytest backend/tests/ -q --ignore=backend/tests/test_a11y_snapshot.py` — 876 passed
- [x] 3.5 运行 `python -c "from yak_browser_use.tools.registry import build_registry; build_registry()"` — registry 正常初始化
