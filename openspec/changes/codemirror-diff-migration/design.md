## 背景

**当前实现**：`MonacoYamlEditor.tsx` 使用 `monaco.editor.createDiffEditor` 配合 `renderSideBySide: false` 实现 diff 视图。Monaco DiffEditor 内部始终维护两个 EditorView（original + modified），即使 `renderSideBySide: false` 设为 false，original 面板的 DOM 仍存在，只是宽度被计算为 `Math.max(5, decorationsLeft)` 像素。任何 CSS `display: none !important` 都会被 Monaco 每帧重写的内联样式覆盖。

**约束**：
- 组件对外 props 接口不能变（`ChatTab.tsx` 直接引用）
- 必须支持 light/dark 主题切换
- diff 模式下编辑器只读，编辑模式下可写
- 构建系统使用 Vite 6，Electron 34 环境

## 目标 / 非目标

**目标：**
- 用 CodeMirror 6 替换 Monaco DiffEditor，彻底消除 origin 面板
- diff 模式下使用 `unifiedMergeView` 实现单栏 inline diff 高亮
- 保持组件对外 props 接口 100% 兼容
- 移除 Monaco 相关构建配置和 CSS hack

**非目标：**
- 不改变 diff 交互流程（confirm/revert 仍由 `chat-diff-bar` 处理）
- 不引入新的 diff 功能（如三向合并、冲突解决）
- 不改变编辑器在 UI 布局中的位置和尺寸行为

## 关键决策

### 决策 1：diff 模式使用 `unifiedMergeView` 而非 `CodeMirrorMerge` 双栏组件

**选择**：使用 `@codemirror/merge` 的 `unifiedMergeView({ original })` extension，配合 `@uiw/react-codemirror` 的 `CodeMirror` 组件。

**原因**：
- `unifiedMergeView` 是 CodeMirror 官方提供的单栏 inline diff 方案，只渲染一个 EditorView，original 信息通过 diff decorations 呈现
- `react-codemirror-merge` 的 `CodeMirrorMerge` 组件永远是 side-by-side 双栏，没有 API 能隐藏 original 侧
- 单栏方案天然不存在"关不掉的 origin"问题

**备选方案**：
- `CodeMirrorMerge` + CSS 隐藏 original 栏：不可靠，内部仍管理两个 EditorView
- 自己实现 diff 算法 + decorations：重复造轮子，`unifiedMergeView` 已经内置 Myers diff

### 决策 2：编辑模式和 diff 模式使用同一个 `CodeMirror` 组件，通过 extensions 切换

**选择**：不通过条件渲染两个不同组件，而是用同一个 `<CodeMirror>` 组件，根据 `hasDiff` 动态计算 extensions 数组。

**原因**：
- 避免组件 unmount/remount 导致的闪烁和状态丢失
- 更简洁的代码结构
- CodeMirror 6 的 extension 系统是专门为动态配置设计的

**实现**：
```tsx
const extensions = hasDiff
  ? [yaml(), unifiedMergeView({ original }), EditorState.readOf(true), EditorView.editable.of(false)]
  : [yaml(), EditorView.lineWrapping];
```

### 决策 3：主题使用 CodeMirror 内置 `'light'`/`'dark'` 字符串

**选择**：直接传 `theme={theme === 'light' ? 'light' : 'dark'}`，不引入额外主题包。

**原因**：
- `@uiw/react-codemirror` 内置 `light` 和 `dark` 主题，无需安装 `@uiw/codemirror-theme-vscode`
- 减少依赖，降低 bundle 大小
- 如果未来需要更精细的主题，可以无缝切换为 `Extension`

## 风险 / 权衡

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `unifiedMergeView` 的 diff 高亮样式可能与现有 CSS 变量不协调 | 视觉不一致 | 通过 CSS 自定义 `.cm-changedLine` 等类名 |
| CodeMirror 6 在 React 18 StrictMode 下双重 mount 可能导致问题 | 编辑器实例重复创建 | `@uiw/react-codemirror` 内部有 `useRef` guard，已验证兼容 |
| 大文件（>1000 行）的 diff 计算可能卡顿 | 性能下降 | `unifiedMergeView` 使用 Myers diff，性能足够；如有问题可后续加虚拟滚动 |
| 外部 `value` 更新时 CodeMirror 的受控行为 | 光标位置跳动 | `@uiw/react-codemirror` 的 `value` prop 在 doc 不同时才更新，不会重置光标 |

## 迁移计划

1. **安装依赖**：`npm install @uiw/react-codemirror @codemirror/lang-yaml @codemirror/merge`
2. **新建组件**：创建 `CodeMirrorYamlEditor.tsx`
3. **更新引用**：`ChatTab.tsx` 中替换 import
4. **清理 CSS**：删除 `global.css` 中 Monaco diff hack 规则
5. **清理构建配置**：`vite.config.ts` 和 `vite.web.config.ts` 移除 monaco plugin
6. **卸载旧依赖**：`npm uninstall monaco-editor vite-plugin-monaco-editor`
7. **验证**：`npm run build` + 手动测试编辑/diff/模式切换

**回滚策略**：如果 CodeMirror 方案有问题，恢复 `MonacoYamlEditor.tsx` 并还原 import 即可——props 接口完全兼容，回滚成本极低。

## 待确认问题

- `unifiedMergeView` 的默认 diff 高亮颜色是否需要与现有 `--success`/`--danger` CSS 变量对齐？
- 是否需要保留 Monaco 作为 fallback（建议不保留，保持代码干净）？
