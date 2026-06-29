## ADDED Requirements

### Requirement: 浏览器下载按 pipeline 隔离存储
系统 MUST 将浏览器下载的文件存储到 `userdata/workspaces/<pipeline_name>/downloads/` 目录，按 pipeline 隔离。

#### Scenario: Chat 模式下下载文件
- **WHEN** 用户在 chat 模式下触发浏览器下载（点击下载按钮、表单提交等）
- **THEN** 文件写入 `userdata/workspaces/__chat__/downloads/` 目录

#### Scenario: Preset 模式下下载文件
- **WHEN** pipeline 运行过程中触发浏览器下载
- **THEN** 文件写入 `userdata/workspaces/<pipeline_name>/downloads/` 目录

### Requirement: 运行时切换下载目录
系统 MUST 支持在运行时通过 `set_download_pipeline()` 切换下载目录，无需重建 BrowserContext。

#### Scenario: switch_session 后下载路径跟随
- **WHEN** 用户调用 `switch_session("new-pipeline")`
- **THEN** 后续浏览器下载的文件写入 `userdata/workspaces/new-pipeline/downloads/`
- **AND** 已有浏览器页面不受影响，无需刷新

### Requirement: 下载完成检测
系统 MUST 提供 `wait_for_download()` 方法，通过轮询检测下载文件是否就绪。Agent 在触发下载后应先调用 `wait_for_download()`，确认文件就绪后再执行 `file_read` 等后续操作。

#### Scenario: 下载完成后阻塞等待
- **WHEN** Agent 触发浏览器下载后调用 `wait_for_download()`
- **THEN** 轮询检测到文件大小稳定 > 100 字节后返回 `{ok: true, path: "downloads/<filename>"}`

#### Scenario: 下载超时
- **WHEN** 60 秒内没有新文件出现或文件未稳定
- **THEN** `wait_for_download()` 返回 `{ok: false, error: "timeout"}`

### Requirement: 路径引用支持 downloads/ 前缀
系统 MUST 支持使用 `downloads/<filename>` 相对路径引用下载的文件。

#### Scenario: validate_path 识别 downloads/ 前缀
- **WHEN** `validate_path("downloads/report.csv", pipeline="my-project")` 被调用
- **THEN** 返回 `userdata/workspaces/my-project/downloads/report.csv` 的绝对路径

#### Scenario: 无 pipeline 参数时回退普通路径
- **WHEN** `validate_path("downloads/report.csv")` 被调用（无 pipeline）
- **THEN** 按普通相对路径处理，不触发特殊解析

### Requirement: 扩展触发下载兼容
系统 MUST 支持由 Chrome 扩展通过 `chrome.downloads.download()` 触发的下载。

#### Scenario: 扩展触发 CSV 导出
- **WHEN** 用户通过扩展按钮触发 CSV 导出下载
- **THEN** 文件写入当前 pipeline 的 `downloads/` 目录，并由 `wait_for_download()` 检测到

### Requirement: 下载目录自动创建
系统 MUST 在设置下载路径时自动创建目录（`mkdir(parents=True, exist_ok=True)`）。

#### Scenario: 首次设置 download path
- **WHEN** 首次调用 `set_download_pipeline()`
- **THEN** `userdata/workspaces/<pipeline>/downloads/` 目录被自动创建
