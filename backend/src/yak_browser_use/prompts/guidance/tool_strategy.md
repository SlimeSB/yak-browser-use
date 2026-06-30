## Tool Selection Strategy

### Priority: Use atomic browser tools first
Prefer these tools for most operations:
- `browser_goto(url)` — navigate to a URL
- `browser_click(selector)` — click an element
- `browser_fill(selector, text)` — fill an input field
- `browser_snapshot(mode?, query?)` — 页面快照。推荐渐进式：aria（概览）→ a11y+query（精准）→ a11y（全量）
- `browser_scroll(direction)` — scroll the page (up/down)
- `browser_source(cached?, strip_styles?, only_body?)` — get the full page HTML source (⚠️ heavy: may return 500KB+ HTML, prefer `browser_snapshot` or `browser_lookup_selector` instead. Only use when you need raw HTML that snapshots can't provide.)
- `browser_eval_js(code)` — execute JavaScript on the page
- `browser_lookup_selector(ref)` — get element details by @e_XXXXX reference

### 页面内容与滚动
- 先用 `browser_snapshot(mode="aria")` 了解页面结构（token 最少）
- 有目标后用 `browser_snapshot(mode="a11y", query="关键词")` 精准找
- query 没找到再扩大搜索范围，最后才用无参数全量
- 如果要操作页面上方/下方的元素，先 `browser_scroll` 滚动到目标区域，再刷新 snapshot
- 同一元素在多次 snapshot 中的 `@e_XXXXX` 编号是**稳定不变的**（只要 DOM 不重建）

### 反幻觉：Selector 必须来自实际页面
- **禁止**使用未经验证的 CSS selector。任何 click/fill 的 selector 必须先通过 `browser_snapshot` 或 `browser_lookup_selector` 确认存在
- Pipeline 中预先填写的 browser_ops 可能包含不准确的 selector —— 执行时以实际页面为准
- 如果 snapshot 中找不到 pipeline 指定的元素，用 `browser_snapshot(mode="a11y", query="关键词")` 重新搜索

### When to use complex goal mode
For complex multi-step goals, use these tools directly (no intermediate tool needed):
- `todo` to break the goal into 3-6 concrete steps
- `browser_*` tools to execute each step
- `pipeline_add_step` to save each successful step (or pipeline_view to review)
- `browser_snapshot(mode="aria")` to verify page state between steps

Typical scenarios:
- Multi-page workflows (search → filter → select → checkout)
- Tasks requiring page content analysis to decide next action
- Complex data extraction across multiple pages

### 读取文件内容：使用 read_data（渐进式披露）
文件内容读取**唯一入口**是 `read_data`，支持渐进式披露：
- `read_data(path)` — 读取前 20 行
- `read_data(path, limit=50, offset=20)` — 读取第 21-70 行（逐段浏览）
- `read_data(path, limit=0)` 非法，limit 必须 > 0

二进制文件可配合 convert_to 参数先转换再读取：
- `read_data(path="data.xlsx", convert_to="csv")`

`file_read` 仍存在于工具列表中（用于 pipeline YAML 引用），但**仅返回元信息**（path/size/encoding），不返回文件内容。

### 浏览器下载文件处理
浏览器下载的文件自动写入 `downloads/` 目录，内容存入 shared_store。触发下载后：
1. 调用 `browser_wait_for_download(timeout)` 等待文件就绪，返回 `{ok, key: "downloads/<filename>", size}`
2. 用 `data_browse(key="downloads/<filename>", limit=500)` 分页浏览内容
3. 如需要转换格式，用 `read_data(path="downloads/<filename>", convert_to="csv")`

**注意：** 不先调用 `browser_wait_for_download` 直接 `read_data` 会导致文件不存在错误。

### 验证码识别
遇到页面出现验证码时使用 `captcha` 工具：
- **文字验证码**：`captcha(type="ocr", dom_selector="img[alt*='验证码']")` — 自动从页面提取图片并识别文字
- **滑块验证码**：`captcha(type="slide", dom_selector="滑块图片选择器", background_bytes="背景图 base64")` — 检测滑块缺口位置，返回 `target_x` / `target_y` 中心点坐标
- **最佳实践**：优先传 `dom_selector`（自动从 CDP 提取图片），避免手动传递大段 base64 数据
- `image_bytes` 支持纯 base64 或 `data:image/...;base64,` 前缀格式

### 工具间数据传递 (shared_store)
工具通过 shared_store 传递数据，避免大数据绕经 LLM 上下文。shared_store 是一个单次会话内的运行时键值总线，支持两种引用语法：

**写入 (Producer)：** 所有工具都支持 `bind` 参数，结果自动存入 shared_store：
- `browser_eval_js(code="...", bind="extracted_data")`
- `read_data(path="data.csv", bind="table_data")`
- 执行结果存入 `shared_store["extracted_data"]`

**读取 (Consumer)：** 任意工具参数中都可以用指针语法引用 shared_store 数据，代替直接传值：
- `{*path}` — **全值指针**（保留原类型）。整个参数必须是 `{*key}` 格式：
  - `file_write(path="output.csv", content="{*extracted_data}")`
  - 适合传递完整数据对象（list、dict 等），类型不变
- `${path}` — **字符串插值**。支持全串替换和部分嵌入：
  - `browser_goto(url="${base_url}/api/v1")`
  - 结果始终是字符串
  - 适合 URL 拼接、模板填充等场景

注意：
- `{*key}` 和 `${key}` 都支持点号链取嵌套字段，如 `{*result.data}`
- 如果引用的 key 不存在，会显示 `__RESOLVE_FAILED__:key` 占位符，可重试或纠正
- 写入端 `bind` 接受 `{*key}` 格式（如 `bind="{*my_data}"`），也能精确表达指针语义
