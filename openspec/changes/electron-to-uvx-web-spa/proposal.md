## Why

当前 yak-browser-use 的前端必须依赖 Electron 桌面壳才能运行，用户无法直接在浏览器中使用。Electron 的 `index.ts`（660 行）本质上是一个 HTTP 代理层——所有 44 个 IPC handler 都在转发 FastAPI 已有的端点。这意味着 Electron 层没有带来不可替代的价值，反而增加了分发和使用的复杂度。

目标：让前端能直接在浏览器中运行，通过 `uvx yak-browser-use` 一键启动。Electron 保留作为可选 native wrapper，不加不删，出错了切回 Electron 就行。

优先级：高。明天 demo 需要能在浏览器中展示，降低观众的使用门槛。

## What Changes

- **新建** `electron/src/renderer/apiClient.ts`：封装所有后端 API 调用，替代 `window.electronAPI`
- **新建** `backend/cli/web.py`：CLI 入口，启动 FastAPI + 打开浏览器
- **新建** `vite.web.config.ts`：Web 模式专用 Vite 配置（去掉 Electron 插件，加 dev proxy）
- **修改** 7 个前端组件：`App.tsx`、`TitleBar.tsx`、`ChatTab.tsx`、`SettingsTab.tsx`、`PipelinesTab.tsx`、`SuggestionsPanel.tsx`、`VersionPanel.tsx`——将 `window.electronAPI.xxx()` 替换为 apiClient 调用
- **修改** `App.tsx`：WebSocket 连接从 `window.electronAPI.getPort()` 改为 `window.location.host`
- **修改** `backend/api/server.py`：挂载 `backend/static/` 目录提供前端静态文件
- **修改** `backend/pyproject.toml`：添加 `[project.scripts]` 入口
- **修改** `electron/package.json`：添加 `build:web` / `dev:web` 脚本
- **清理** `types.ts`：移除所有未使用的类型声明（`convert`、`openCsvDialog`、`status`、`chromeStatus`、`exportExcel`、`exportCsv`、`getSession`、`listPresets`、`setHighlightConfig` 共 9 个）
- **添加** `.gitignore`：忽略 `backend/static/` 构建产物

## Capabilities

### New Capabilities
- `web-port`: 将前端从 Electron 壳中解耦，支持在标准浏览器中运行，通过 `uvx yak-browser-use` 一键启动

### Modified Capabilities
- 无（所有后端 API 接口不变，前端组件逻辑不变，只改 import 路径）

## Impact

- **代码**：新增 ~230 行，修改 ~7 个前端组件，不删任何现有文件
- **API**：后端 `/api/*` 接口完全不变，100% 兼容
- **依赖**：无新增依赖。ExcelJS 在浏览器端也可运行
- **Electron**：完全不受影响，`vite.config.ts` 保留不动，`vite.web.config.ts` 独立
- **构建流程**：CI 中新增 `npm run build:web` 步骤，产物进入 wheel 包
- **开发流程**：Web 模式用 `npx vite --config vite.web.config.ts` 热更新，Electron 模式不变
