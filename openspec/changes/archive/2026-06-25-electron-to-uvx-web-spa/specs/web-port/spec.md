## ADDED Requirements

### Requirement: API 客户端层
系统 MUST 提供浏览器端 API 客户端模块，封装所有后端 `/api/*` 端点调用，每个方法的签名与现有 `window.electronAPI` 保持一致。

#### Scenario: 正常调用返回数据
- **WHEN** 前端组件调用 apiClient 的任意方法（如 `listPipelines()`）
- **THEN** 方法通过 `fetch` 发送 HTTP 请求到对应 `/api/*` 端点，并返回解析后的 JSON 数据

#### Scenario: 网络错误处理
- **WHEN** 后端不可用或返回非 2xx 状态码
- **THEN** 方法抛出包含 HTTP 状态码和错误信息的异常，调用方按现有逻辑处理

### Requirement: WebSocket 连接
系统 MUST 在 apiClient 中提供 `createWebSocket(path: string): WebSocket` 方法，自动处理 Electron 和 Web 模式的 URL 构造差异。

#### Scenario: Web 模式连接
- **WHEN** 前端运行在浏览器中，调用 `createWebSocket('/ws/events')`
- **THEN** 方法使用 `window.location.host` 构造 URL：`ws://{host}/ws/events`

#### Scenario: Electron 模式连接
- **WHEN** 前端运行在 Electron 中，调用 `createWebSocket('/ws/events')`
- **THEN** 方法通过 `window.electronAPI.getPort()` 获取端口，构造 URL：`ws://127.0.0.1:{port}/ws/events`

#### Scenario: 开发环境连接
- **WHEN** 前端运行在 Vite dev server（`http://127.0.0.1:5173`）且 proxy 已配置
- **THEN** WebSocket 连接到 `ws://127.0.0.1:5173/ws/events`，由 Vite proxy 转发到后端

### Requirement: Vite Web 配置
系统 MUST 提供独立的 `vite.web.config.ts` 配置文件，支持 Web 模式的开发和构建。

#### Scenario: 开发模式热更新
- **WHEN** 开发者运行 `npx vite --config vite.web.config.ts`
- **THEN** Vite dev server 启动，提供 React HMR，并将 `/api/*` 和 `/ws/*` 请求代理到后端

#### Scenario: 生产构建
- **WHEN** 开发者运行 `npx vite build --config vite.web.config.ts`
- **THEN** 构建产物输出到 `backend/static/` 目录，包含 index.html、JS bundle、CSS 和 Monaco worker

### Requirement: 静态文件服务
后端 FastAPI 实例 MUST 挂载 `backend/static/` 目录，在 Web 模式下 serve 前端静态文件。

#### Scenario: 访问根路径返回前端
- **WHEN** 用户访问 `http://127.0.0.1:8787/`
- **THEN** 返回 `backend/static/index.html`，浏览器加载对应的 JS/CSS 资源

#### Scenario: 静态资源正确加载
- **WHEN** 浏览器请求 `/assets/index-xxx.js` 等静态资源
- **THEN** FastAPI 从 `backend/static/assets/` 返回对应文件

### Requirement: CLI 一键启动
系统 MUST 提供 `uvx yak-browser-use` CLI 入口，启动 FastAPI 后端 + 打开浏览器。

#### Scenario: 一键启动
- **WHEN** 用户在终端运行 `uvx yak-browser-use`
- **THEN** 系统启动 uvicorn 服务在 8787 端口，自动打开浏览器访问 `http://127.0.0.1:8787`

#### Scenario: Python 子命令入口
- **WHEN** 用户运行 `python -m ybu web`
- **THEN** 行为与 `uvx yak-browser-use` 一致

### Requirement: CSV/Excel 导出浏览器端实现
系统 MUST 在浏览器端使用 Blob + `<a download>`（CSV）和 ExcelJS browser build（Excel）实现导出功能，不依赖 Electron save-dialog。

#### Scenario: CSV 导出
- **WHEN** 用户点击导出 CSV
- **THEN** 前端生成 CSV 内容为 Blob，创建 `<a download>` 元素触发浏览器下载

#### Scenario: Excel 导出
- **WHEN** 用户点击导出 Excel
- **THEN** 前端使用 ExcelJS 在浏览器端生成 `.xlsx` 文件并触发下载

### Requirement: 窗口控制按钮隐藏
Web 模式下 TitleBar 的窗口控制按钮（最小化/最大化/关闭）MUST 不显示。

#### Scenario: Web 模式不显示窗口按钮
- **WHEN** 前端运行在浏览器中
- **THEN** TitleBar 不渲染 min/max/close 按钮

#### Scenario: Electron 模式保留窗口按钮
- **WHEN** 前端运行在 Electron 中
- **THEN** TitleBar 继续渲染窗口控制按钮

### Requirement: 对话框替换
Web 模式下 `showAlert` MUST 使用 `window.alert()` 替代 Electron 的 `dialog.showMessageBox`。

#### Scenario: 提示信息显示
- **WHEN** 前端调用 `showAlert(message)`
- **THEN** 浏览器弹出原生 `alert()` 对话框显示消息

### Requirement: 死代码清理
系统 MUST 移除 `types.ts` 中未使用的 9 个类型声明（`convert`、`openCsvDialog`、`status`、`chromeStatus`、`exportExcel`、`exportCsv`、`getSession`、`listPresets`、`setHighlightConfig`）。

#### Scenario: 类型声明清理
- **WHEN** 检查 `types.ts`
- **THEN** 上述 9 个方法不再存在于 `Window.electronAPI` 接口定义中
