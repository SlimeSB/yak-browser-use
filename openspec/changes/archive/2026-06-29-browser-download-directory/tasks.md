## 1. PlaywrightBridge 核心改动

- [x] 1.1 `__init__` 加 `pipeline_name: str = "__chat__"` 参数，导入 `WORKSPACES_ROOT`（from `workspace.manager`），初始化 `_seen_pages: set[Page] = set()`
- [x] 1.2 实现 `_resolve_download_path(pipeline_name=None) -> Path` 方法：基于 `WORKSPACES_ROOT / (name or self._pipeline_name) / "downloads"`，`mkdir(parents=True, exist_ok=True)`
- [x] 1.3 修改 `start()`：拿到 context 后，**遍历 `context.pages` 中所有已有页面**（不只当前 page）调用 CDP `Page.setDownloadBehavior({behavior: "allow", downloadPath: str(path)})`，全部加入 `_seen_pages`
- [x] 1.4 修改 `_on_new_page(page)`：设 CDP download behavior + `_seen_pages.add(page)`。**同时在 `_on_page_closed` 中 `_seen_pages.discard(page)`**
- [x] 1.5 实现 `set_download_pipeline(pipeline_name: str)`：更新 `self._pipeline_name`，遍历 `_seen_pages` 逐个重设 CDP download behavior
- [x] 1.6 实现 `wait_for_download(timeout: int = 60, pipeline_name: str | None = None) -> dict`：临时轮询逻辑（500ms readdir + 1s 间隔两次 stat 大小不变 + >100 字节确认稳定），返回 `{ok: true, path: "downloads/<filename>"}` 或 `{ok: false, error: "timeout"}`。**已知限制：不支持并发多个下载同时进行**
- [x] 1.7 修改 `stop()` 和 `_on_browser_disconnected()`：两处都 `_seen_pages.clear()`
- [x] 1.8 实现 CDP `Page.setDownloadBehavior` 失败兜底：检测命令返回值，失败时退回到 `page.on("download")` + `download.save_as()` 手动写文件

## 2. 路径解析扩展

- [x] 2.1 `tools/_path_utils.py`：`validate_path()` 加 `pipeline: str | None = None` 参数。当 `path.startswith("downloads/")` 且 `pipeline` 不为空时，用 `WORKSPACES_ROOT / pipeline / path` 解析
- [x] 2.2 `engine/executor.py`：`_resolve_path()` 同步支持 `downloads/` 前缀，解析到 `run_dir.parents[2] / ref`（与 `data/` 模式一致）

> `file_read` / `format_convert` 的 pipeline 参数透传已推迟到后续迭代（暂时不传 pipeline → `downloads/` 前缀在这些工具中不触发特殊解析）

## 3. API 层参数透传与运行时切换

- [x] 3.1 `api/state.py`：`connect_chrome()` 加 `pipeline_name: str = "__chat__"` 参数，创建 bridge 时传入
- [x] 3.2 `api/routes.py`：`api_chrome_connect` 从请求中提取 `pipeline_name` 或取 `sessions.active_pipeline`，传给 `connect_chrome`
- [x] 3.3 `api/routes.py`：`api_chrome_restart` 重启时复用当前 `active_pipeline`，传给 `connect_chrome(pipeline_name=...)`
- [x] 3.4 `api/routes.py`：`session_switch` 路由在 `service.switch_session()` 之后调用 `engine_state.bridge.set_download_pipeline(pipeline_name)`，确保运行时切换下载目录

## 4. Prompts 更新

- [x] 4.1 更新 `prompts/` 中的系统提示词：指导 Agent 在触发下载操作后、调用 `file_read` 之前，先调用 `wait_for_download()` 等文件就绪，再使用返回的 `path` 字段引用下载文件

## 5. 验证

- [x] 5.1 运行 `pytest backend/tests/ -x -q` 确认无回归（896 passed）
- [ ] 5.2 手动：启动 Web UI，连接 Chrome，触发下载，确认文件落入对应 `downloads/` 目录
- [ ] 5.3 手动：`switch_session` 后触发下载，确认文件落入新 pipeline 的 `downloads/` 目录
- [ ] 5.4 手动：调用 `wait_for_download()` 确认文件就绪时正确返回路径，超时正确返回 timeout
