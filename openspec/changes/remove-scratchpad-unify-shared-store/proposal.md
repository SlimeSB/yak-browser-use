## Why

当前项目存在两套数据缓存/传递机制：`scratchpad`（模块级全局 dict，缓存 HTML、elements、summary）和 `shared_store`（框架级 data bus，通过 bind/`${path}` 模板在 tool 间传递数据）。两者功能重叠但职责模糊：

- `scratchpad` 的写入只在 `_apply_heavy_data_filter` 中（browser_snapshot / browser_source 返回后剥离重数据），读取只在 `_try_scratchpad_source_read` 中（browser_source cached 路径）。但 browser_source 的 cached 路径已有 bridge 自带的 `_element_map` 缓存，scratchpad 是纯粹的冗余层。
- `scratchpad` 的 store/clear 均无外部调用者，`clear_all` 也从未被调用，存在内存泄漏风险。
- `shared_store` 已经是框架级的通用 data bus，贯穿 runner → executor → tool 全链路，完全能替代 scratchpad 的所有功能。

移除 scratchpad 可以消除不必要的抽象层，统一数据传递机制，减少维护负担。

## What Changes

- **删除** `engine/scratchpad.py` 整个模块（`ScratchpadRecord`、`get`、`store`、`store_raw_html`、`clear`、`clear_all`、`_build_summary`）
- **删除** `_try_scratchpad_source_read()` 函数（`tool_executor.py:529`）及其调用点
- **重构** `_apply_heavy_data_filter()` — browser_snapshot 分支当场构建 summary 返回，不再持久化到 scratchpad；browser_source 分支直接依赖 bridge 自带缓存
- **清理** 所有 `from yak_browser_use.engine.scratchpad import ...` 引用
- **更新** 相关测试文件中的 scratchpad import

## Capabilities

### Modified Capabilities

- `heavy-data-filter`: browser_snapshot 和 browser_source 的重数据剥离逻辑从"写入 scratchpad + 替换为 summary"改为"当场构建 summary 返回"，不再依赖外部持久化存储。
- `browser-source-cache`: browser_source 的 cached 路径从"先查 scratchpad 再查 bridge"简化为"只查 bridge 内部缓存"。

## Impact

- 受影响的文件：`engine/scratchpad.py`（删除）、`engine/_harness/tool_executor.py`（删除 `_try_scratchpad_source_read`、重构 `_apply_heavy_data_filter`）
- 受影响的测试：`tests/test_scratchpad.py`、`tests/test_integration_agent_reform.py`、`tests/test_orchestration_filter.py`
- 不影响 API、不影响 preset 模式、不影响 shared_store 行为
