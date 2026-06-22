## 1. 准备与基础改造

- [x] 1.1 新建 `electron/src/renderer/apiClient.ts`，封装所有 35 个后端 API 调用方法，使用相对 URL（`/api/*`）
- [x] 1.2 修改 `electron/src/renderer/App.tsx`：将 `window.electronAPI.xxx()` 调用替换为 apiClient 导入（含 `getSessionData`、`listSessions`、`switchSession`、`newSession`、`archiveSession` 等所有在 App.tsx 中直接调用的方法）；WebSocket 连接从 `window.electronAPI.getPort()` + `new WebSocket(...)` 替换为 `apiClient.createWebSocket('/ws/events')`
- [x] 1.3 修改 `electron/src/renderer/components/TitleBar.tsx`：去掉 min/max/close 按钮（通过检测 `window.electronAPI` 是否存在做条件渲染）
- [x] 1.4 修改 `electron/src/renderer/components/tabs/ChatTab.tsx`：替换 `window.electronAPI.chat`、`chatReset`、`chatCancel` 为 apiClient（session 方法通过 props 从 App.tsx 传入，不在本组件中直接调用）
- [x] 1.5 修改 `electron/src/renderer/components/tabs/SettingsTab.tsx`：替换 `getProviderConfig`、`setProviderConfig`、`testProvider`、`getProviderPresets` 为 apiClient
- [x] 1.6 修改 `electron/src/renderer/components/tabs/PipelinesTab.tsx`：替换 `getPipeline` 为 apiClient
- [x] 1.7 修改 `electron/src/renderer/components/SuggestionsPanel.tsx`：替换 `showAlert` 为 `window.alert()`
- [x] 1.8 修改 `electron/src/renderer/components/VersionPanel.tsx`：替换 `listVersions`、`getVersion`、`relearn` 为 apiClient
- [x] 1.9 清理 `electron/src/renderer/types.ts`：移除所有未使用的类型声明（`convert`、`openCsvDialog`、`status`、`chromeStatus`、`exportExcel`、`exportCsv`、`getSession`、`listPresets`、`setHighlightConfig` 共 9 个）

## 2. Vite Web 配置

- [x] 2.1 新建 `electron/vite.web.config.ts`：去掉 `vite-plugin-electron` 和 `vite-plugin-electron-renderer`，保留 `@vitejs/plugin-react` 和 `vite-plugin-monaco-editor`，设置 `base: '/'`，`root: 'src/renderer'`，`build.outDir` 指向 `../backend/static/`
- [x] 2.2 在 `vite.web.config.ts` 中添加 dev server proxy：`/api/*` → `http://127.0.0.1:8787`，`/ws/*` → `ws://127.0.0.1:8787`（带 `ws: true`）
- [x] 2.3 修改 `electron/package.json`：添加 `"build:web": "vite build --config vite.web.config.ts"` 和 `"dev:web": "vite --config vite.web.config.ts"` 脚本

## 3. 后端服务与 CLI

- [x] 3.1 修改 `backend/api/server.py`：挂载 `backend/static/` 目录提供前端静态文件（`StaticFiles` + `app.mount("/", ...)`）
- [x] 3.2 新建 `backend/cli/web.py`：`main()` 函数启动 uvicorn（端口 8787）+ 打开浏览器
- [x] 3.3 修改 `backend/__main__.py`：添加 `web` 子命令入口
- [x] 3.4 修改 `backend/pyproject.toml`：添加 `[project.scripts]` → `yak-browser-use = "backend.cli.web:main"`

## 4. 构建与配置收尾

- [x] 5.1 添加 `.gitignore` 条目：`backend/static/`
- [x] 5.2 验证：`grep window\\.electronAPI` 全量扫描确认无遗漏
- [x] 5.3 验证：`npx vite --config vite.web.config.ts` 启动 dev 模式，确认 core flow（connect → chat → run）正常
- [x] 5.4 验证：`npx vite build --config vite.web.config.ts` 确认构建产物完整
