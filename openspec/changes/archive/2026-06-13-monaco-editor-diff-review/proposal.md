## Why

当前 ChatTab 右侧的 pipeline 编辑器是一个裸 `<textarea>`，缺少 YAML 语法高亮、代码折叠、缩进引导等基本 IDE 体验，在编辑结构化 YAML 文件时容易出错且效率低下。同时，AI 聊天修改 pipeline 时直接写入磁盘，用户无法预览变更内容，也缺少撤销手段——一旦 AI 产生不符合预期的修改，用户只能手动回滚。

pipeline 格式已从 agent.md 完成到纯 YAML 的迁移（commit `43ba3c0`），Monaco Editor 内建的 YAML mode 是极佳匹配。此外 Monaco 原生支持 inline diff（`renderSideBySide: false`），可以一并解决 diff 预览问题。

## What Changes

- **新增** Monaco Editor 集成：用 YAML 模式替换 ChatTab 中的裸 textarea，提供语法高亮、代码折叠、自动缩进、格式化
- **新增** 内联 diff 预览：AI 建议修改 pipeline 时，前端展示 Monaco 的 unified diff 视图（单窗口内联模式），保留 YAML 语法着色
- **新增** Confirm/Revert 交互：用户可预览 AI 修改，确认（标记 + 刷新编辑器）或撤销（回滚磁盘 + 刷新编辑器）
- **新增** 后端 `pipeline.edit` WebSocket 事件：AI 修改 pipeline 落盘后，通过 WS 推送原始版快照（检查点文件）、修改版（磁盘）、diff 及说明
- **新增** 后端 `POST /api/chat/confirm` / `POST /api/chat/revert` 端点：Confirm 标记确认，Revert 回滚磁盘到原始版

## Capabilities

### New Capabilities
- `monaco-yaml-editor`: 基于 Monaco Editor 的 YAML pipeline 编辑器，替换 ChatTab 当前裸 textarea，提供语法高亮、代码折叠、缩进引导
- `pipeline-diff-review`: AI 聊天修改 pipeline 时的 diff 预览与确认/撤销流程，含后端 WS 事件推送和前端 Monaco inline diff 渲染

### Modified Capabilities
<!-- 无 -->

## Impact

- **npm 依赖**：新增 `monaco-editor` (~5MB), `vite-plugin-monaco-editor`
- **前端文件**：ChatTab.tsx, App.tsx, types.ts, global.css, vite.config.ts
- **Electron 主进程**：index.ts (IPC handlers), preload.ts (API 通道)
- **后端 API**：api/routes.py (新增 Confirm/Revert 端点 + WS 事件推送)
- **不涉及**：现有 pipeline 执行流程、工具链、CLI 保持不变
