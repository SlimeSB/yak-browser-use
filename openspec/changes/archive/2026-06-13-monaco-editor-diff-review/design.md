## 背景

### 当前状态

ChatTab 右侧 pipeline 编辑器使用裸 `<textarea>`（`ChatTab.tsx:234-240`），无语法高亮、代码折叠、缩进引导。

pipeline 格式已在 `43ba3c0` 完成 agent.md → pipeline.yaml 迁移：纯 YAML，由 Pydantic `PipelineYaml` / `StepYaml` 建模（`compiler/schema.py`），解析简化为 `yaml.safe_load()` + `PipelineYaml.model_validate()`（`compiler/parser.py:66-74`）。

Chat 流程为 IPC → `POST /api/chat`，同步返回响应，无 diff 预览。旧的 `chatEdit` API（`POST /api/chat/edit`）和 `chatPendingDiffs` / `DiffView` / Confirm/Revert 流程已移除。WebSocket 仍有 `chat.message`、`chat.tool_start` 等事件流转，但无 pipeline 编辑相关事件。

### 约束

- Electron + React + Vite 前端，不可引入 CRA 工具链
- Python FastAPI 后端，WebSocket 用于实时事件
- Monaco Editor 需通过 vite-plugin 处理 Web Workers
- 现有 IPC 通道（`api:chatEdit`）保留但未使用，可移除或复用

## 目标 / 非目标

**目标：**
- 用 Monaco Editor (YAML mode) 替换 ChatTab 裸 textarea，提供语法高亮、折叠、缩进
- 恢复 AI pipeline 修改的 diff 预览（Monaco inline diff，`renderSideBySide: false`）
- 恢复 Confirm/Revert 交互流程，用户在确认前可以预览并决定是否接受修改

**非目标：**
- 不在其他 Tab（Exec/Log 等）引入 Monaco
- 不改变现有 pipeline 执行流程
- 不引入实时协作编辑
- 不修改 Pydantic schema 结构

## 关键决策

### 1. Monaco YAML mode vs 自定义语言模式

**选择**：Monaco 内建 YAML mode。

**原因**：pipeline.yaml 是标准 YAML，Monaco 的 YAML mode 提供语法高亮、折叠、缩进、括号匹配，开箱即用。自定义语言（Monarch tokenizer）仅在需要给 `browser_ops` / `tool_name` 等字段染色时考虑，现阶段 YAML mode 已覆盖 90% 需求。

### 2. 内联 diff 实现方式

**选择**：`monaco.editor.createDiffEditor()` + `renderSideBySide: false`。

**原因**：Monaco 原生支持 unified diff 视图（类似 GitHub PR），修改行保留 YAML 语法着色，视觉效果远优于自绘 `DiffView` 的纯文本行。需后端提供两版完整文本（original + modified），而非仅 diff 行。

**备选方案**：自绘 diff 组件 + 单独 Monaco 编辑器展示语法高亮。复杂度高，不取。

### 3. Diff 数据传递方式

**选择**：WebSocket 推送 `pipeline.edit` 事件，携带 `{edit_id, original, modified, diff_lines, explanation}`。

**原因**：Chat 已通过 WebSocket 推送 `chat.message` / `chat.tool_start` / `chat.tool_end` 等事件，基础设施现成。SSE 已移除不再可用。同步 IPC 不适合可能需要异步生成 diff 的情况。

**备选方案**：IPC 同步调用 `chatEdit` 返回 diff。问题是 chat 已在 WebSocket 通道中，同步调用会阻塞主进程，且与现有 chat 消息流不一致。

### 4. Confirm/Revert API 设计

**选择**：检查点文件 + session 持久化。首次 `edit_pipeline` 调用时后端保存检查点文件（`pipeline.yaml.{edit_id}.orig`），记录在 session 中。后续每次修改落盘后，读取检查点 + 当前文件构造 WS 事件。后端重启后检查点文件仍在，session 恢复后可继续处理。

- Confirm：`POST /api/chat/confirm {edit_id}` → 删除检查点文件，标记确认，更新 session
- Revert：`POST /api/chat/revert {edit_id}` → 检查点覆盖回 pipeline.yaml，删除检查点，标记已回退，更新 session

### 5. Monaco 打包方案

**选择**：`vite-plugin-monaco-editor`。

**原因**：自动处理 Monaco 的 Web Workers、语言文件打包，与 Vite 兼容良好。直接使用 CDN 不适合 Electron（离线需求），手配 worker 复杂易错。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| Monaco 打包体积 ~5-8MB | Electron 应用体积增大 | Electron 本地打包，非网络加载，影响可接受；仅加载 YAML 语言包减小体积 |
| Vite + Electron 下 Monaco Workers 配置 | 启动报错或编辑器空白 | 使用 `vite-plugin-monaco-editor` 已验证的配置；开发环境先行验证 |
| 后端重启时检查点存在但 session 丢失 | Confirm/Revert 无法关联 edit_id 到 session | session 持久化（JSON 文件），启动时恢复；检查点文件含 pipeline_name 可扫描恢复 |
| Revert 并发写入 | 两个 Revert 同时覆盖 pipeline 文件 | 文件写入是原子的（先写临时文件再 rename）；Revert 幂等（同一 original，多次回滚无害） |

## 迁移计划

1. **Phase 1 — 依赖安装**：`npm install monaco-editor vite-plugin-monaco-editor`，配置 `vite.config.ts`
2. **Phase 2 — 编辑器组件**：创建 `MonacoYamlEditor.tsx`，基于单 diff editor 实例，先在 ChatTab 替换 textarea（仅普通编辑，暂不接 diff）
3. **Phase 3 — Diff 预览 UI**：在 ChatTab 新增 diff 提示条 + Confirm/Revert 按钮；App.tsx 处理 `pipeline.edit` WS 事件
4. **Phase 4 — 后端配合**：新增 WS 事件推送 `pipeline.edit`；新增 `POST /api/chat/confirm` / `POST /api/chat/revert`
5. **Phase 5 — 清理**：移除旧 `chatEdit` IPC handler；CSS 适配

回滚方案：每个 Phase 独立可回滚，Monaco 编辑器降级为 textarea 只需一行组件替换。

## 待确认问题

- `edit_pipeline` 工具的具体实现方案待用户查阅其他设计后确定（LLM 生成完整 modified YAML vs 生成指令让后端应用）。

## 已确认决策

- **多个 diff 合并**：同一轮 chat 中 LLM 多次调用 `edit_pipeline` 工具时累积合并，每次合并后推送更新的 `pipeline.edit`。`original` 始终保持为首次修改前的检查点快照，`modified` 每次从磁盘读取最新内容。
- **检查点文件 + session 持久化**：检查点存磁盘（`pipeline.yaml.{edit_id}.orig`），session 存 JSON 文件。后端重启后可恢复，无数据丢失。
- **单 diff editor 策略**：使用 `monaco.editor.createDiffEditor()` + `renderSideBySide: false` 作为唯一编辑器。正常模式时两侧 model 设为相同内容（无 diff 标记），diff 模式时两侧分别设为 original 和 modified。正常编辑时必须监听 `modifiedModel` 变更并同步更新 `originalModel`，防止用户打字导致两侧漂移产生伪 diff 标记。
