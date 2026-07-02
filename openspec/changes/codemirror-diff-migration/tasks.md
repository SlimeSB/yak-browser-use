## 1. 准备与基础改造

- [x] 1.1 安装 CodeMirror 6 核心依赖：`npm install @uiw/react-codemirror @codemirror/lang-yaml @codemirror/merge`
- [x] 1.2 删除 `electron/src/renderer/components/editor/MonacoYamlEditor.tsx`

## 2. 核心实现

- [x] 2.1 新建 `electron/src/renderer/components/editor/CodeMirrorYamlEditor.tsx`，实现 `Props` 接口（`value`/`original`/`modified`/`onChange`/`theme`），编辑模式用 `<CodeMirror>` + `yaml()` extension，diff 模式用同一个 `<CodeMirror>` 加 `unifiedMergeView({ original })` + `readOnly` extension
- [x] 2.2 在 `electron/src/renderer/components/tabs/ChatTab.tsx` 中替换 `MonacoYamlEditor` import 为 `CodeMirrorYamlEditor`
- [x] 2.3 在 `electron/src/renderer/styles/global.css` 中删除 `.monaco-yaml-editor` 相关的 CSS hack 块（L2699-2726），添加 `.cm-editor { border-radius: var(--radius-sm); overflow: hidden; }`

## 3. 构建配置清理

- [x] 3.1 修改 `electron/vite.config.ts`：删除 `monacoEditorPlugin` import、plugins 中的 `monacoEditorPlugin(...)` 调用、`optimizeDeps.include` 中的 `monaco-editor`、`manualChunks.monaco`
- [x] 3.2 修改 `electron/vite.web.config.ts`：同上，删除所有 Monaco 构建配置
- [x] 3.3 从 `electron/package.json` 中移除 `monaco-editor` 和 `vite-plugin-monaco-editor` 依赖，然后运行 `npm install`

## 4. 验证与收尾

- [x] 4.1 运行 `npm run build` 确认构建成功，无 Monaco 相关 warning/error
- [ ] 4.2 手动测试：编辑模式下 YAML 高亮正常、可编辑、Tab 缩进 2 空格
- [ ] 4.3 手动测试：diff 模式下只显示 modified 单栏、有 inline diff 高亮、readOnly
- [ ] 4.4 手动测试：模式切换（编辑→diff→编辑）不报错不闪烁
- [ ] 4.5 手动测试：light/dark 主题切换正确
