## Why

当前 yak-browser-use 的快照系统只有一种 full 模式：`cdp/helpers.py:CDPHelpers.capture_snapshot()` 截图(PNG) + outerHTML，单次消耗约 3000-5000 tokens。goal 步骤的 Agent 每次探索都消耗这些 token，多次探索后上下文预算很快用完。

此外，当前快照不提供交互元素列表（button/input/select/textarea 等），Agent 无法通过 `@eN` ref 精确引用元素；也没有列表/表格自动检测，Agent 难以高效理解页面数据结构。

本次变更为快照系统引入三级模式（interactive/simplified/full），通过浏览器端 JS DOM 化简脚本大幅降低 LLM token 消耗，同时提升 Agent 对页面结构的理解能力。

## What Changes

- **新增** `assets/simplify-dom.js`：浏览器端 DOM 化简脚本，支持 interactive 和 simplified 两种模式，通过 CDP `Runtime.evaluate` 注入执行
- **新增** `assets/simplify-dom.test.html`：手动测试页面，覆盖表单/导航/表格/卡片/ARIA/隐藏元素/超上限等场景
- **新增** `tests/test_simplify_dom.py`：自动化测试
- **修改** `cdp/helpers.py`：新增 `_inject_simplify_js(mode)`、`capture_snapshot_interactive()`、`capture_snapshot_simplified()` 三个方法，实现 JS → full 两级降级链。修改 `ToolCDPHelpers.snapshot()` 增加 `mode` 参数支持
- **修改** `engine/executor.py`：snapshot handler 按 value 类型分发：dict → mode 判断；非 dict → 默认 full。`execute_browser_op()` 和 `execute_browser_step()` 均需适配
- **修改** `cli/chrome.py`：`_cmd_chrome_snapshot()` 增加 `--mode` 参数支持
- **修改** `__main__.py`：`chrome snapshot` 子命令增加 `--mode {full,interactive,simplified}` 参数，默认 full
- **修改** `engine/agent.py`：goal 步骤启动前调用 interactive snapshot，通过 `extend_system_message` 注入 `@eN` 交互元素列表到 Agent 的 system message

## Capabilities

### New Capabilities
- `snapshot-interactive`: 交互元素快照模式，提取 button/input/select/textarea/a/[role]/onclick 元素，分配 @eN 引用，约 200 tokens
- `snapshot-simplified`: 简化页面摘要快照模式，输出页面摘要 + 检测到的列表/表格，约 500-1000 tokens
- `dom-simplify-js`: 浏览器端 DOM 化简脚本，支持 interactive/simplified 两种模式，含可见性判断、密码脱敏、上限控制
- `goal-interactive-injection`: goal 步骤启动前自动获取 interactive snapshot 并通过 extend_system_message 注入 @eN 元素列表

### Modified Capabilities
- `snapshot-full`: 现有 full 模式保持不变，但 pipeline YAML 语法扩展为支持 `snapshot: { mode: "full" }` 显式指定模式，`snapshot: true` 向后兼容

## Impact

- **代码**：`cdp/helpers.py`（新增 3 个方法 + ToolCDPHelpers.snapshot() mode 参数，约 80 行）、`engine/executor.py`（snapshot handler 模式分发 + @eN 映射表 + click/fill @eN 解析，约 40 行）、`cli/chrome.py`（--mode 参数）、`__main__.py`（CLI 参数）、`engine/agent.py`（goal 步骤注入）
- **新建文件**：`assets/simplify-dom.js`（约 500 行）、`assets/simplify-dom.test.html`、`tests/test_simplify_dom.py`
- **接口**：`capture_snapshot()` 签名不变，完全向后兼容；新增 `capture_snapshot_interactive()` 和 `capture_snapshot_simplified()` 方法
- **依赖**：不引入新 Python/Node 依赖，纯 JS 通过 CDP 注入
- **向后兼容**：`snapshot: true` 行为不变，仍为 full 模式；所有现有 pipeline 无需修改
