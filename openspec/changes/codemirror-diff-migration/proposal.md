## Why

当前 `MonacoYamlEditor` 组件使用 Monaco DiffEditor 实现 diff 模式。Monaco DiffEditor 的 original 面板无法通过 API 或 CSS 干净地隐藏——JS 内联样式每帧重写 CSS `!important`，导致任何 hack 方案（ResizeObserver / MutationObserver）都失败且脆弱。

本次变更将替换为 CodeMirror 6，并使用 `@codemirror/merge` 的 `unifiedMergeView` extension 实现**单栏 inline diff 视图**，彻底消除"关不掉的 origin"问题。

## What Changes

- **删除** `MonacoYamlEditor.tsx`，替换为新的 `CodeMirrorYamlEditor.tsx`
- **新增** CodeMirror 6 依赖：`@uiw/react-codemirror`、`@codemirror/lang-yaml`、`@codemirror/merge`
- **移除** Monaco 依赖：`monaco-editor`、`vite-plugin-monaco-editor`
- **删除** `global.css` 中所有 Monaco diff hack CSS 规则（~30 行）
- **清理** `vite.config.ts` 和 `vite.web.config.ts` 中 Monaco 相关构建配置
- diff 模式下使用 `unifiedMergeView({ original })` 实现单栏 inline diff 高亮，不再有 origin 面板

## Capabilities

### New Capabilities
- `unified-diff-view`: 在 CodeMirror 编辑器中，通过 `unifiedMergeView` extension 实现单栏 inline diff 视图，用背景色高亮增删行，无需额外面板

### Modified Capabilities
- `yaml-editor`: 编辑器组件从 Monaco 替换为 CodeMirror 6，外部 props 接口（`value`/`original`/`modified`/`onChange`/`theme`）保持完全兼容

## Impact

- **文件变更**：8 个文件（1 新建、1 删除、6 修改）
- **包依赖**：移除 2 个 monaco 包，新增 3 个 codemirror 包
- **bundle 大小**：预计减少 ~5MB（Monaco worker chunk）
- **构建配置**：`vite.config.ts` 和 `vite.web.config.ts` 需要移除 monaco plugin 调用
- **无任何破坏性 API 变更**：组件对外接口保持不变
