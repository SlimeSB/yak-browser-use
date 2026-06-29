## 背景

### 当前状态

PlaywrightBridge 使用 `self._browser.contexts[0]`（Chrome 默认 context），没有设置任何下载目录。浏览器下载的文件落入 Chrome 默认下载目录，与 pipeline 无关。`switch_session` 可以在运行时切换 pipeline，但下载路径不会跟随。

```
当前通路：
用户点击下载 → Chrome 默认 Download dir → 文件在 Chrome 目录下
→ 无法通过 {path} 引用，无法按 pipeline 隔离
```

### 约束

- PlaywrightBridge 是单例，pipeline 可运行时切换（`switch_session`）
- 不能重建 BrowserContext（丢失页面状态 + 事件绑定）
- 不引入新外部依赖
- Electron 扩展可能通过 `chrome.downloads.download()` 触发下载，不走标准浏览器下载流

### 相关方

- `cdp/playwright_bridge.py` — 核心改动
- `tools/_path_utils.py` — 路径解析扩展
- `engine/executor.py` — 同步路径解析
- `api/state.py` — 参数透传
- `api/routes.py` — API 入口传参
- `workspace/manager.py` — `WORKSPACES_ROOT` 可复用

## 目标 / 非目标

**目标：**
- 浏览器下载文件按 pipeline 隔离存储到 `userdata/workspaces/<pipeline>/downloads/`
- 运行时切换 pipeline 时下载路径自动跟随
- 下载完成后可被后续工具（`file_read`、`format_convert`）通过 `downloads/<file>` 路径引用
- 支持标准浏览器下载和扩展触发下载

**非目标：**
- 不涉及 Electron 前端改动
- 不做 CDP 扩展 Service Worker 拦截（未来优化方向）
- 不引入 watchdog 等文件系统事件依赖
- 不改变已有的 Pipeline YAML 格式或运行流程

## 关键决策

### 决策 1：使用已有 context + CDP setDownloadBehavior，不重建 context

**选择**：继续使用 `self._browser.contexts[0]`，通过 CDP `Page.setDownloadBehavior` 动态设置下载路径。

```
start()
  → self._context = self._browser.contexts[0]  ← 维持现状
  → 当前页 → CDP Page.setDownloadBehavior({behavior: "allow", downloadPath: X})
  → _on_new_page → 同上 + 新页加入 _seen_pages
  → page.on("close") → 从 _seen_pages 移除

set_download_pipeline(name)
  → self._pipeline_name = name
  → 遍历 _seen_pages，逐页重新设 CDP setDownloadBehavior

wait_for_download(timeout=60)
  → 被调用时临时开启 500ms 轮询
  → readdir + stat，等文件稳定 > 100 字节
  → 就绪或超时后自动停止
  → 非全局常驻，每次调用独立
```

**原因**：
- `new_context(downloads_path=...)` 需要重建 context → 丢失页面状态和事件绑定，不可接受
- CDP `Page.setDownloadBehavior` 是浏览器级设置，不依赖任何 Playwright 资源
- 切换路径只需再次调用 CDP，不需要任何资源重建
- Chrome 写盘由浏览器进程完成，不经过 Playwright 桥，不丢事件

**备选方案**：
- `new_context(downloads_path=...)` + 重建页面 → 被拒绝，复杂度高（事件重绑、页面恢复）
- `page.on("download")` + `save_as` → 被拒绝，扩展下载收不到，且需要额外文件复制
- watchdog → 被拒绝，轮询的"等稳"本质无法替代，引入外部依赖不值得

### 决策 2：等待下载完成使用临时轮询，非常驻守护

**选择**：`wait_for_download()` 工具被调用时启动一轮轮询，完成后自动清理。

```
wait_for_download(timeout=60, pipeline_name=None)
  → target_dir = _resolve_download_path(pipeline_name)
  → 初次取 dir 快照 (known_files)
  → 循环 500ms:
      → readdir(target_dir)
      → 发现不在 known_files 中的新文件
      → stat → 记下 size
      → 等 1s → stat → size 不变且 > 100 → 就绪
      → 返回 {ok: true, path: "downloads/<filename>"}
  → 超时 → 返回 {ok: false, error: "timeout"}
  → 清理 interim state
```

**原因**：
- "发现新文件"有多种方式，但"等文件写完"必须通过多次 stat 确认稳定，这是轮询的本质
- 既然"等稳"一定是轮询，那"发现"也通过轮询一起做，不需要额外引入事件机制
- 临时轮询不常驻，不浪费资源；走工具调用前不会启动
- 500ms 空 readdir 开销可忽略（readdir 是纯内核调用）

### 决策 3：`validate_path` 加 `pipeline` 参数支持 `downloads/` 前缀

**选择**：`validate_path("downloads/report.csv", pipeline="my-project")` 解析为 `WORKSPACES_ROOT / pipeline / downloads / report.csv`。

**原因**：
- Agent 不需要知道完整 workspace 路径，只用 `downloads/<file>` 即可引用
- `pipeline` 参数可选，不传时回退当前行为（兼容已有调用）
- 与现有 `data/` 前缀模式一致（`executor.py:_resolve_path` 已有 `data/` 处理）

### 决策 4：`_seen_pages` 集合维护所有活跃页面

`_on_new_page` 中：
```
page.on("download", ...) — 不绑，CDP 接管
page.on("close", lambda: self._seen_pages.discard(page))
self._seen_pages.add(page)
CDP Page.setDownloadBehavior on this page
```

`set_download_pipeline` 遍历 `_seen_pages`，逐个发 CDP 命令。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| `Page.setDownloadBehavior` 在旧版 Chromium 不支持 | 高 | 检测 `start()` 时的 CDP 命令返回值，失败退回到 `page.on("download")` + `save_as` 兜底 |
| 文件名冲突（同 pipeline 同名文件多次下载） | 低 | Chrome 会自动添加 `(1)`, `(2)` 后缀，轮询检测时返回实际文件名 |
| 读大文件时 stat 过早认为稳定 | 低 | 100 字节阈值 + `size` 不变两次确认已覆盖绝大多数场景；大文件可加超时重试 |
| `downloads/` 路径在非 project-root cwd 下失效 | 低 | `validate_path` 通过 `pipeline` 参数 + `WORKSPACES_ROOT` 绝对路径解析，不依赖 cwd |
| 扩展通过 chrome.downloads.download() 触发 | 中 | CDP setDownloadBehavior 接管浏览器下载管理器，扩展发起的下载同样被拦截并写入指定目录 |

## 迁移计划

1. `cdp/playwright_bridge.py` — 核心改动（`__init__` 加参数、`start` 设 CDP、`_seen_pages` 维护、`set_download_pipeline`、`wait_for_download`）
2. `tools/_path_utils.py` — `validate_path` 加 `pipeline` 参数 + `downloads/` 前缀解析
3. `engine/executor.py` — `_resolve_path` 同步支持 `downloads/`
4. `api/state.py` — `connect_chrome` 透传 `pipeline_name`
5. `api/routes.py` — `api_chrome_connect` / `restart` 传 `pipeline_name`
6. 验证：代码检查 + 单元测试（mock CDP）+ 手动测试下载

回滚方案：`git revert`。不涉及数据迁移，下载目录只在需要时创建。

## 待确认问题

无。全部已在 explore mode 中讨论确认。
