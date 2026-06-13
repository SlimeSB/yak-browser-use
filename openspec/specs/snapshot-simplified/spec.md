## ADDED Requirements

### Requirement: 简化页面摘要快照
系统 MUST 提供 `capture_snapshot_simplified()` 方法，生成页面摘要和检测到的列表/表格结构。方法不写文件，返回数据 dict。

#### Scenario: 生成页面摘要
- **WHEN** 页面包含 title、h1-h6 标题、meta description
- **THEN** 返回 dict 中 `summary` 字段包含页面标题、主要标题层级、meta 描述信息

#### Scenario: 检测无序列表
- **WHEN** 页面包含 `<ul>` 元素
- **THEN** 返回 dict 中 `lists` 数组包含列表的定位信息（selector、item_count、sample_items）

#### Scenario: 检测有序列表
- **WHEN** 页面包含 `<ol>` 元素
- **THEN** 返回 dict 中 `lists` 数组包含列表的定位信息

#### Scenario: 检测表格
- **WHEN** 页面包含 `<table>` 元素
- **THEN** 返回 dict 中 `tables` 数组包含表格的定位信息（selector、row_count、col_count、headers）

#### Scenario: 无列表或表格
- **WHEN** 页面不包含任何 `<ul>`、`<ol>`、`<table>` 元素
- **THEN** 返回 dict 中 `lists` 和 `tables` 均为空数组

#### Scenario: 返回数据格式
- **WHEN** `capture_snapshot_simplified()` 成功执行
- **THEN** 返回 dict `{"summary": "...", "lists": [...], "tables": [...], "mode": "simplified"}`
- **AND** 不写入任何文件

#### Scenario: 可见性过滤
- **WHEN** 列表或表格元素被隐藏（display: none 等）
- **THEN** 这些元素不被包含在检测结果中

### Requirement: pipeline YAML simplified 模式触发
系统 MUST 支持通过 pipeline YAML 的 `snapshot: { mode: "simplified" }` 语法触发 simplified 快照。

#### Scenario: YAML 显式指定 simplified 模式
- **WHEN** pipeline 步骤中 browser_ops 包含 `snapshot: { mode: "simplified" }`
- **THEN** `_convert_browser_op()` 产出 `{"type": "snapshot", "mode": "simplified"}`
- **AND** `execute_browser_step()` 将 mode 传入 `core_params = {"mode": "simplified"}`
- **AND** `execute_browser_op()` 从 `params["mode"]` 检测到 `"simplified"`，调用 `capture_snapshot_simplified()`
- **AND** `execute_browser_step()` 将返回的 summary/lists/tables 数据分别写入 `page_summary.txt`、`detected_lists.json`、`detected_tables.json`

#### Scenario: execute_browser_step() snapshot handler 传递 mode
- **WHEN** `execute_browser_step()` 处理 snapshot op 且 op 包含 `mode` 字段
- **THEN** `core_params` 包含 `{"mode": op.get("mode", "full")}`
- **AND** 将 `core_params` 传递给 `execute_browser_op()`

### Requirement: simplified 模式降级链
系统 MUST 在 simplified 快照中实现 JS → full 两级降级链。

#### Scenario: JS 执行成功
- **WHEN** `_inject_simplify_js("simplified")` 成功返回结果
- **THEN** 使用 JS 返回的 summary/lists/tables 数据
- **AND** 返回 dict 中不包含 `degraded` 字段或 `degraded: false`

#### Scenario: JS 执行失败回退到 full
- **WHEN** `_inject_simplify_js("simplified")` 执行失败或无结果
- **THEN** 回退到 `capture_snapshot()` full 模式
- **AND** 返回 dict 中标记 `degraded: true`

#### Scenario: AXTree 路径不在本 change 中实现
- **WHEN** 考虑降级链设计
- **THEN** AXTree 路径作为后续优化选项，不在本 change 中实现
- **AND** 当前降级链仅包含 JS → full 两级

### Requirement: execute_browser_op() mode 分发
`execute_browser_op()` 的 snapshot handler MUST 根据 params 中的 mode 字段分发到对应方法。

#### Scenario: mode 为 simplified
- **WHEN** `execute_browser_op()` 收到 op `{"type": "snapshot", "mode": "simplified"}`
- **THEN** 从 `params.get("mode", "full")` 读取 mode 并分发
- **AND** 调用 `capture_snapshot_simplified()`
- **AND** 返回数据 dict 给 `execute_browser_step()` 处理文件 I/O
