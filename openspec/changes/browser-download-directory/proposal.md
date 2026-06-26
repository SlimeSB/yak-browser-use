## Why

浏览器下载的文件当前全部落入 Chrome 默认下载目录，无法按 pipeline 隔离。Agent 在 chat 中下载的 CSV、图片、PDF 等文件与其他工作混杂在一起，后续无法通过 `{path}` 引用或程序化读取。

同时 PlaywrightBridge 已提供 `accept_downloads` 能力，但未利用 CDP 的 `Page.setDownloadBehavior` 做运行时动态下载路径管理。当前框架支持 `switch_session` 动态切换 pipeline，下载路径也必须跟随 pipeline 切换，不能钉死在启动时。

## What Changes

- **新增** `PlaywrightBridge.set_download_pipeline(name)` — 运行时切换下载目录，通过 CDP `Page.setDownloadBehavior` 动态设置，不重建 BrowserContext
- **新增** `PlaywrightBridge.wait_for_download(timeout=60)` — 临时轮询检测下载文件完成（500ms readdir + stat 等稳定），非常驻守护
- **修改** `PlaywrightBridge.__init__` — 接受 `pipeline_name` 参数（默认 `"__chat__"`）
- **修改** `PlaywrightBridge.start()` — 对当前页面设 CDP download behavior，绑定 `_on_new_page` 和新页 close 事件到 `_seen_pages` 集合
- **修改** `tools/_path_utils.py` — `validate_path()` 新增 `pipeline` 参数，支持 `downloads/<filename>` 前缀解析到工作区目录
- **修改** `engine/executor.py` — `_resolve_path()` 同步支持 `downloads/` 前缀
- **修改** `api/state.py` — `connect_chrome()` 透传 `pipeline_name`
- **修改** `api/routes.py` — `api_chrome_connect` / `restart` 入口传 `pipeline_name`
- **不修改** `device_query` — 下载功能无交叉

## Capabilities

### New Capabilities
- `download-directory`: 浏览器下载文件按 pipeline 隔离存储，支持运行时动态切换，并提供文件就绪检测

### Modified Capabilities
- `browser-execution`: PlaywrightBridge 启动时设置 CDP download path，运行时随 pipeline 切换
- `file-read`: `validate_path` 支持 `downloads/` 前缀解析到工作区下载目录
- `pipeline-execution`: Preset 模式下下载路径与工作区一致

## Impact

- **代码**：`cdp/playwright_bridge.py` 核心改动（+~80 行）；`tools/_path_utils.py` 和 `engine/executor.py` 路径解析扩展（各 +~10 行）；`api/state.py` 和 `api/routes.py` 参数透传（各 +~5 行）
- **API**：`PlaywrightBridge.__init__` 签名新增 `pipeline_name` 参数；`validate_path` 签名新增 `pipeline` 可选参数；路径 `downloads/<filename>` 成为有效引用方式
- **依赖**：无新增外部依赖
- **数据**：userdata/workspaces/&lt;pipeline&gt;/downloads/ 目录自动创建，已有文件不受影响
