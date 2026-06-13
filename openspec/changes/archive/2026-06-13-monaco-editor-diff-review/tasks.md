## 1. 准备与基础改造

- [x] 1.1 安装 npm 依赖：`monaco-editor`、`vite-plugin-monaco-editor`
- [x] 1.2 配置 `vite.config.ts`：注册 `vite-plugin-monaco-editor` 插件，仅加载 YAML 语言 worker
- [x] 1.3 创建 `MonacoYamlEditor` 组件（`electron/src/renderer/components/editor/MonacoYamlEditor.tsx`），使用 `monaco.editor.createDiffEditor()` + `renderSideBySide: false` 作为唯一编辑器实例；实现 onChange 回调（含 300ms debounce）同步父组件状态；正常编辑时监听 modifiedModel 变更并同步更新 originalModel，避免打字时出现伪 diff 标记
- [x] 1.4 将 ChatTab 中裸 `<textarea>` 替换为 `MonacoYamlEditor` 组件（普通编辑模式）

## 2. 核心实现

- [x] 2.1 在 `MonacoYamlEditor` 中实现 diff 切换：接收 `original` / `modified` props，当两者不同时 diff editor 自动显示内联 diff 并设为只读模式；两者相同时取消只读，恢复普通编辑模式
- [x] 2.2 在 `ChatTab.tsx` 中新增 diff 预览 UI：AI 提示条（显示 `explanation`）+ [Confirm] [Revert] 按钮
- [x] 2.3 在 `App.tsx` 中处理 WebSocket `pipeline.edit` 事件：存储 `pendingEdit` 状态（`edit_id`、`original`、`modified`、`explanation`），传入 ChatTab；维护已处理 edit_id 列表，忽略重复事件
- [x] 2.4 新增 IPC 通道 `api:chatConfirm` / `api:chatRevert`：前端调用后端 Confirm/Revert API
- [x] 2.5 前端实现 Confirm 流程：调用 Confirm API → 处理响应（成功则刷新编辑器、清除 diff；失败则显示错误、保留 diff；`already_confirmed` 则静默清除 diff）
- [x] 2.6 前端实现 Revert 流程：调用 Revert API → 处理响应（成功则后端回滚文件、刷新编辑器、清除 diff；失败则显示错误、保留 diff；`already_reverted` 则静默清除 diff）

## 3. 后端实现

- [x] 3.1 后端实现 `edit_pipeline` 工具 handler：首次调用时保存检查点文件（`pipeline.yaml.{edit_id}.orig`），记录到 session；每次修改落盘后，读检查点 + 当前文件，通过 WS 推送 `pipeline.edit` 事件（含 `edit_id`、`original`、`modified`、`diff_lines`、`explanation`）。（注意：`edit_pipeline` 工具的具体交互方式待确定，此任务侧重 WS 推送和检查点逻辑）
- [x] 3.2 新增 `POST /api/chat/confirm` 端点：接收 `{edit_id}`，删除检查点文件，更新 session 状态为已确认（幂等）
- [x] 3.3 新增 `POST /api/chat/revert` 端点：接收 `{edit_id}`，检查点覆盖回 pipeline.yaml，删除检查点，更新 session 状态为已回退（幂等）

## 4. 验证与收尾

- [x] 4.1 添加 `MonacoYamlEditor` 的 CSS 样式：容器充满高度、背景色与 `.chat-pipeline-editor` 融合
- [x] 4.2 添加 diff 预览提示条的 CSS 样式
- [x] 4.3 移除旧的 `chatEdit` IPC handler（`api:chatEdit`，已被 Confirm/Revert 取代）；DiffView 组件保留（LogTab 仍在使用）
- [ ] 4.4 验证 Monaco YAML 编辑器加载、语法高亮、折叠功能正常
- [ ] 4.5 端到端验证：发送聊天指令 → 触发 pipeline.edit 事件 → 展示内联 diff → Confirm 后文件更新 → Revert 后恢复原版
