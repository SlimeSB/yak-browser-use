## 背景

当前前端架构：

```
Browser (React SPA) ←IPC→ Electron Main Process (index.ts, 660 行) ←HTTP→ FastAPI Backend
```

Electron 的 `index.ts` 注册了 30+ 个 IPC handler，每个 handler 都在调用 FastAPI 已有的 `/api/*` 端点。Electron 层本质上是纯代理，没有引入不可替代的价值。例外是 `exportCsv`/`exportExcel`（ExcelJS 在 Node.js 侧生成文件后通过 save-dialog 写盘），以及 `dialog:alert`（原生对话框）。

约束条件：
- Electron 目录不动，保留作为可选 native wrapper
- 所有后端 `/api/*` 接口不变
- 前端组件逻辑不改，只改 API 调用路径
- 明天 demo 可用

## 目标 / 非目标

**目标：**
- 前端在标准浏览器中可运行，不依赖 Electron
- `uvx yak-browser-use` 一键启动 web 版
- Electron 模式完全不受影响
- WebSocket 事件流正常连接

**非目标：**
- 不删 `electron/` 目录
- 不做响应式布局适配（先保 desktop 浏览器）
- 不加 Service Worker / PWA
- 不改后端 API 接口

## 关键决策

### 1. Vite 配置拆分（而非环境变量切换）

拆成两个文件：
- `vite.config.ts` — Electron 模式，保持不变
- `vite.web.config.ts` — Web 模式，去掉 `vite-plugin-electron` / `vite-plugin-electron-renderer`，加 dev proxy

理由：讨厌环境变量，两个配置文件各自清晰，互不干扰。

### 2. 相对 URL 替代端口注入 + createWebSocket

Web 模式下前端由 FastAPI 同源 serve（生产）或 Vite proxy 转发（开发），所以不需要知道后端端口号：

```typescript
// apiClient.ts — 所有请求用相对 URL
fetch('/api/run', { method: 'POST', body: JSON.stringify({...}) })

// apiClient.ts — WebSocket 统一入口
export function createWebSocket(path: string): WebSocket {
  if (window.electronAPI?.getPort) {
    // Electron 模式：通过 IPC 获取端口
    const port = await window.electronAPI.getPort()
    return new WebSocket(`ws://127.0.0.1:${port}${path}`)
  }
  // Web 模式：同源，用 location.host
  return new WebSocket(`ws://${window.location.host}${path}`)
}
```

生产环境：`ws://127.0.0.1:8787/ws/events` ✓
开发环境：`ws://127.0.0.1:5173/ws/events` → Vite proxy → 后端 ✓
Electron：走 IPC `getPort()` ✓

不需要后端做 HTML 模板注入，不需要 `__YBU_PORT__` 全局变量。

### 3. 未使用方法全部清理

`types.ts` 中 44 个方法，renderer 实际只调用 35 个。9 个未使用的方法（`convert`、`openCsvDialog`、`status`、`chromeStatus`、`exportExcel`、`exportCsv`、`getSession`、`listPresets`、`setHighlightConfig`）全部从类型声明中移除。apiClient 也只实现 renderer 实际调用的 35 个方法。

### 4. CSV/Excel 导出暂不实现

当前没有任何 UI 组件触发 `exportCsv` 或 `exportExcel`，这两个方法只在 Electron `index.ts` 中有 IPC handler 注册。Web 模式下不需要实现浏览器端导出，等未来有 UI 需求时再做。

### 5. `showAlert` 改为 `window.alert()`

Electron 的 `dialog.showMessageBox` 替换为浏览器原生 `alert()`，不影响主要功能。

### 6. 构建产物直接输出到 `backend/static/`

`vite.web.config.ts` 的 `build.outDir` 直接指向 `../backend/static/`，不需要 cp 步骤。

### 7. 开发模式用 Vite dev server + proxy

```typescript
server: {
  proxy: {
    '/api': 'http://127.0.0.1:8787',
    '/ws': { target: 'ws://127.0.0.1:8787', ws: true },
  },
}
```

### 7. Monaco editor worker 路径

Web 模式下 `base: '/'`，需要验证 `vite-plugin-monaco-editor` 的 worker URL 解析正确。`vite.web.config.ts` 中保留该插件，与 Electron 配置一致。

## 风险 / 权衡

| 风险 | 概率 | 缓解 |
|------|------|------|
| Monaco worker 加载失败 | 低 | 已有 `vite-plugin-monaco-editor` 处理 worker，验证 base 路径 |
| WebSocket 连接失败 | 低 | dev 模式 proxy 配 `ws: true`，生产模式同源 |
| 某个 `window.electronAPI` 调用遗漏 | 中 | `grep window\\.electronAPI` 全量扫描确认全覆盖 |
| 时间不够明天 demo | 中 | MVP 只做核心流程（connect → chat → run），导出功能已确认无 UI 触发点 |

## 迁移计划

1. **Phase 1**：新建 `apiClient.ts`，替换所有组件中的 `window.electronAPI` 调用
2. **Phase 2**：新建 `vite.web.config.ts`，验证 dev 模式
3. **Phase 3**：修复组件兼容性（TitleBar、showAlert、导出）
4. **Phase 4**：修改 `server.py` 挂载静态文件，修改 `index.html`
5. **Phase 5**：新建 `cli/web.py` + `pyproject.toml` 入口
6. **Phase 6**：构建脚本 + `.gitignore`

回滚方案：删除 `backend/static/`，Electron 模式不受任何影响。

## 待确认问题

- 无（全部已在 explore mode 中讨论确定）
