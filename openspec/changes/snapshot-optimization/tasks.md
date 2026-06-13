## 1. 新建 DOM 化简脚本与测试资源

- [ ] 1.1 新建 `assets/simplify-dom.js`：实现 `simplifyDom()` 函数，支持 interactive 模式（提取 button/input/select/textarea/a/[role]/onclick 元素，分配 @eN 引用）和 simplified 模式（页面摘要 + ul/ol/table 检测），含可见性判断（offsetParent + getBoundingClientRect + getComputedStyle）、密码字段脱敏、上限 50 个元素
- [ ] 1.2 新建 `assets/simplify-dom.test.html`：手动测试页面，覆盖表单/导航/表格/卡片/ARIA/隐藏元素/超上限等场景
- [ ] 1.3 新建 `tests/test_simplify_dom.py`：自动化测试，验证 interactive/simplified 两种模式的输出正确性

## 2. 修改 CDP 层

- [ ] 2.1 修改 `cdp/helpers.py`：新增 `_inject_simplify_js(mode)` 方法，读取 `assets/simplify-dom.js` 并通过 `self.js()` 注入执行
- [ ] 2.2 新增 `capture_snapshot_interactive()` 方法：调用 `_inject_simplify_js("interactive")`，实现 JS → full 两级降级链，返回数据 dict `{"elements": [...], "mode": "interactive"}`，不写文件。降级时返回 `{"elements": [...], "mode": "interactive", "degraded": true}`（JS 失败回退到 full 模式时）
- [ ] 2.3 新增 `capture_snapshot_simplified()` 方法：调用 `_inject_simplify_js("simplified")`，实现 JS → full 两级降级链，返回数据 dict `{"summary": "...", "lists": [...], "tables": [...], "mode": "simplified"}`，不写文件。降级时返回 `{"summary": "...", "lists": [...], "tables": [...], "mode": "simplified", "degraded": true}`
- [ ] 2.4 修改 `cdp/helpers.py:ToolCDPHelpers.snapshot()`：增加 `mode` 参数支持，根据 mode 分发到对应的 capture 方法（full → `capture_snapshot()`，interactive → `capture_snapshot_interactive()`，simplified → `capture_snapshot_simplified()`）

## 3. 修改执行器

- [ ] 3.1 修改 `engine/executor.py:execute_browser_op()`：snapshot handler 按 value 类型分发，dict → 读取 mode 字段调用对应方法，非 dict → 默认 full。具体分发逻辑：`params.get("mode")` 为 "interactive" → `capture_snapshot_interactive()`，"simplified" → `capture_snapshot_simplified()`，"full" 或无 mode → `capture_snapshot()`。所有方法返回数据 dict，不写文件。click/fill handler 中检测 value 是否以 `@e` 开头，从映射表中解析为 CSS selector
- [ ] 3.2 修改 `engine/executor.py:execute_browser_step()`：snapshot 文件 I/O 部分根据 mode 写不同文件：
  - full → `screenshot_<ts>.png` + `page.html`
  - interactive → `interactive_elements.json`
  - simplified → `page_summary.txt` + `detected_lists.json` + `detected_tables.json`
  - core_params 中需包含 mode 字段以传递给 execute_browser_op()
- [ ] 3.3 新增 `engine/executor.py` 中 `@eN` 映射表：维护 `{ref: selector}` dict，每次新 interactive snapshot 时重建。在 execute_browser_op() 的 click/fill handler 中，检测 value 是否以 `@e` 开头，从映射表中解析为 CSS selector。映射表生命周期为当前 goal step
- [ ] 3.4 确认 `_convert_browser_op()` 正确处理 dict value：`snapshot: true` → `value=True`，`snapshot: {mode: "interactive"}` → `value={"mode": "interactive"}`

## 4. 修改 CLI

- [ ] 4.1 修改 `__main__.py`：`chrome snapshot` 子命令增加 `--mode {full,interactive,simplified}` 参数，默认 full
- [ ] 4.2 修改 `cli/chrome.py:_cmd_chrome_snapshot()`：支持 `mode` 参数，根据 mode 调用对应的 capture 方法获取数据 dict，然后写入对应产出文件

## 5. 修改 Agent goal 步骤注入

- [ ] 5.1 修改 `engine/agent.py:run_goal_step()`：在创建 browser-use Agent 之前调用 `cdp_helpers.capture_snapshot_interactive()`，将 @eN 元素列表追加到 `extend_system_message` 参数中
- [ ] 5.2 处理降级场景：interactive snapshot 失败时不影响 goal 步骤正常执行

## 6. 验证与收尾

- [ ] 6.1 运行 `uv run pytest tests/ -v` 确保全部测试通过（含新增 test_simplify_dom.py 和现有测试回归）
- [ ] 6.2 手动验证 `lbu chrome snapshot --mode interactive` 和 `lbu chrome snapshot --mode simplified` 产出正确
- [ ] 6.3 确认 `snapshot: true` 向后兼容，现有 pipeline 行为不变
