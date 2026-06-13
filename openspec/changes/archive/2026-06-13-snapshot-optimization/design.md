## 背景

当前快照系统只有一种 full 模式：`cdp/helpers.py:CDPHelpers.capture_snapshot()` 截图(PNG) + outerHTML，单次消耗约 3000-5000 tokens。`engine/executor.py:execute_browser_op()` 中 op_type == "snapshot" 时直调 `capture_snapshot()`，CLI `chrome snapshot` 无 mode 参数。

现有 CDP 调用链路成熟：`CDPHelpers._cdp()` 封装 `CDPDaemon._send()`，`CDPHelpers.js()` 通过 `Runtime.evaluate` 注入 JS。`engine/agent.py:run_goal_step()` 创建 browser-use Agent 时支持 `extend_system_message` 参数注入额外上下文。

项目用 YAML pipeline 定义（PipelineYaml/StepYaml），browser_ops 中 `snapshot: true` 触发 full 快照。

## 目标 / 非目标

**目标：**
- 实现三级快照模式：interactive (~200 tokens) / simplified (~500-1000 tokens) / full (~3000-5000 tokens)
- 浏览器端 JS DOM 化简脚本，通过 CDP `Runtime.evaluate` 注入执行
- JS → full 两级降级链（AXTree 路径作为后续优化选项，不在本 change 中实现）
- goal 步骤默认使用 interactive 模式，通过 `extend_system_message` 注入 @eN 元素
- 完全向后兼容 `snapshot: true`

**非目标：**
- 不修改 `capture_snapshot()` 的现有行为
- 不引入新的 Python/Node 依赖
- 不改变 `CDPDaemon` 或 CDP 底层通信机制
- 不涉及前端 UI 变更

## 关键决策

### 1. 简化逻辑在浏览器端 JS

`assets/simplify-dom.js` 纯 JS 通过 CDP 注入，不引入 Python/Node 依赖。已有 `cdp/helpers.js()` 方法支持此途径。

备选方案：Python 端解析 outerHTML。放弃原因：Python 解析 DOM 需要引入 BeautifulSoup/lxml 依赖，且无法准确判断元素可见性（需要浏览器运行时信息）。

### 2. 三级模式设计

| 模式 | Token | 方法 | 产出 |
|------|-------|------|------|
| full | ~3000-5000 | `capture_snapshot()`（不变） | `{"screenshot_base64": "...", "html": "..."}` |
| interactive | ~200 | `capture_snapshot_interactive()`（新增） | `{"elements": [...], "mode": "interactive"}` |
| simplified | ~500-1000 | `capture_snapshot_simplified()`（新增） | `{"summary": "...", "lists": [...], "tables": [...], "mode": "simplified"}` |

### 3. 降级链

```
simplify-dom.js DOM 遍历
  → 失败/空 → capture_snapshot() full 模式兜底
```

JS DOM 遍历优先；full 模式作为最终兜底。AXTree 路径作为后续优化选项，不在本 change 中实现。

### 4. pipeline YAML 语法

向后兼容：`snapshot: true` → full 模式
新模式：`snapshot: { mode: "interactive" }` 或 `snapshot:\n  mode: simplified`

在 `execute_browser_op()` 中通过 `isinstance(params, dict)` 判断：dict → 读取 mode 字段分发；非 dict → 默认 full。

execute_browser_op() 的 snapshot handler 检测 `params.get("mode")`：
- `"full"` 或无 mode → `capture_snapshot()`
- `"interactive"` → `capture_snapshot_interactive()`
- `"simplified"` → `capture_snapshot_simplified()`

所有 capture 方法返回数据 dict，不写文件。文件 I/O 统一在 `execute_browser_step()` 中处理：
- full → `screenshot_<ts>.png` + `page.html`
- interactive → `interactive_elements.json`
- simplified → `page_summary.txt` + `detected_lists.json` + `detected_tables.json`

### 5. goal 步骤注入

通过 `extend_system_message` 注入 @eN 交互元素列表到 Agent 的 system message。`engine/agent.py:run_goal_step()` 中已有 `extend_system_message` 参数，在创建 Agent 前调用 interactive snapshot 并将结果拼接进去。@eN 解析通过映射表实现：`capture_snapshot_interactive()` 返回 `elements` 数组（每个元素含 `ref` 和 `selector`），`execute_browser_op()` 的 click/fill handler 中检测 value 是否以 `@e` 开头，从映射表中解析为 CSS selector。映射表在每次新 interactive snapshot 时重建，生命周期为当前 goal step。

### 6. interactive 元素提取规则

- 元素类型：button、input（非 hidden）、select、textarea、a[href]、[role="button"]、[onclick]
- 可见性判断：offsetParent !== null + getBoundingClientRect 在视口内 + getComputedStyle display/visibility 非隐藏
- 密码字段脱敏：type="password" 的 input 不输出 value
- 上限 50 个元素，超出时在末尾标注截断信息
- 每个元素分配 @eN 引用（@e1, @e2, ...）

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| simplify-dom.js 在不同页面表现不一致 | 提供 test.html 覆盖常见场景，自动化测试验证 |
| JS 执行在某些页面不可用 | 两级降级链确保始终有 full 模式兜底 |
| interactive 模式可能遗漏关键元素 | 上限 50 个覆盖绝大多数页面；Agent 仍可通过 full 模式获取完整信息 |
| goal 步骤注入增加 system message 长度 | interactive 模式仅 ~200 tokens，对上下文预算影响极小 |
| 密码字段可能被意外捕获 | simplify-dom.js 中 type="password" 字段脱敏处理 |

## 迁移计划

1. 新建 `assets/simplify-dom.js` 和测试资源
2. 修改 `cdp/helpers.py` 新增方法
3. 修改 `engine/executor.py` 模式分发
4. 修改 CLI 支持 `--mode` 参数
5. 修改 `engine/agent.py` goal 步骤注入
6. 运行全部测试确保回归

回滚：删除新增文件，恢复 `cdp/helpers.py`、`engine/executor.py`、`cli/chrome.py`、`__main__.py`、`engine/agent.py` 的旧版本。

## 待确认问题

- 无
