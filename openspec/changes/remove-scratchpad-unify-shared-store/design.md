## 背景

当前项目中有两个独立的数据缓存层：

1. **scratchpad** (`engine/scratchpad.py`)：模块级 `dict[str, ScratchpadRecord]`，缓存 HTML、elements、summary。仅在 `_apply_heavy_data_filter` 中写入，在 `_try_scratchpad_source_read` 中读取。`clear`/`clear_all` 无调用者。

2. **shared_store** (`dict`)：框架级 data bus，在 `runner` 层创建，贯穿 `conversation_loop` / `runner_preset` → `tool_executor` → `executor` 全链路。通过 `bind` 写入、`${path}` 模板读取，是通用机制。

两者功能重叠但 scratchpad 是硬编码的特殊路径，shared_store 是通用框架。browser_source 的 cached 路径同时存在 bridge 内部缓存和 scratchpad 两层，形成冗余。

## 目标 / 非目标

**目标：**
- 删除 `engine/scratchpad.py` 整个模块
- 删除 `_try_scratchpad_source_read()` 函数
- 重构 `_apply_heavy_data_filter`，browser_snapshot 当场构建 summary，browser_source 依赖 bridge 自带缓存
- 清理所有 scratchpad 的 import 引用和测试代码

**非目标：**
- 不改变 shared_store 的行为或接口
- 不改变 browser_snapshot / browser_source 对外返回的结果格式
- 不修改 preset 模式（本来就不走 scratchpad）

## 关键决策

**决策 1：browser_snapshot 的 summary 当场构建，不持久化**

`_apply_heavy_data_filter` 中 a11y / progressive / full 模式原本是 `store_scratchpad({elements, ...})` 然后 `result = get_scratchpad().summary`。改为直接调用 `_build_summary(elements, url, title)` 当场构建 summary 字符串返回。summary 的生成逻辑从 `scratchpad._build_summary` 迁移到 `tool_executor._build_snapshot_summary`。

备选方案：保留 scratchpad 但只用于 summary 缓存。放弃原因：summary 只在 snapshot 返回时生成一次，后续不会被读取，缓存无意义。

**决策 2：browser_source cached 路径只走 bridge 缓存**

`_try_scratchpad_source_read` 删除后，`browser_source(cached=true)` 直接走 `bridge.get_page_html(cached=True)`，它内部已有 `_element_map["raw_html"]` 缓存。`_apply_heavy_data_filter` 中的 browser_source 分支删除 scratchpad 写入，只保留 html 剥离逻辑。

备选方案：在 shared_store 中缓存 HTML。放弃原因：bridge 已有缓存，再加一层无意义；且 HTML 体积大，不适合放 shared_store。

**决策 3：`_build_summary` 逻辑内联到 `tool_executor.py`**

`scratchpad._build_summary(record)` 的逻辑（遍历 elements 生成中文摘要）迁移为 `tool_executor` 中的独立函数，不依赖 ScratchpadRecord 数据结构。

## 风险 / 权衡

- **风险**：删除 scratchpad 后，如果未来需要跨 session 缓存 snapshot 数据，需要重新设计。**缓解**：当前 scratchpad 的 clear 也从未被调用，说明跨 session 场景不存在。
- **风险**：测试文件 `test_scratchpad.py` 需要删除或重写。**缓解**：确认测试覆盖范围，如果是单元测试则删除，如果是集成测试则适配。
- **性能影响**：无。summary 构建逻辑不变，只是调用位置从 scratchpad 移到 tool_executor。

## 迁移计划

1. 将 `_build_summary` 逻辑从 scratchpad 迁移到 `tool_executor.py`（独立函数）
2. 重构 `_apply_heavy_data_filter`，移除 scratchpad 依赖
3. 删除 `_try_scratchpad_source_read` 及其调用点
4. 删除 `engine/scratchpad.py`
5. 清理所有 import 引用
6. 更新/删除相关测试
7. 回归测试 browser_snapshot / browser_source 功能

回滚：恢复 scratchpad.py 并还原 tool_executor.py 的修改即可，无数据迁移问题。

## 待确认问题

- `test_scratchpad.py`、`test_integration_agent_reform.py`、`test_orchestration_filter.py` 中对 scratchpad 的测试是否需要保留部分逻辑（如 summary 格式验证）？
