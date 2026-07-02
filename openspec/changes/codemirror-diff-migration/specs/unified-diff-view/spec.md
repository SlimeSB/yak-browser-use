## ADDED Requirements

### Requirement: 单栏 inline diff 渲染
当 `hasDiff` 为 true 时，组件 MUST 使用 `@codemirror/merge` 的 `unifiedMergeView({ original })` extension 实现单栏 diff 视图——只显示 modified 文本，用不同背景色高亮新增和删除的行段，不得出现任何 origin 面板或分栏布局。

#### Scenario: 正常渲染 diff
- **WHEN** 用户打开包含 `pendingEdit` 的 diff 模式（`original !== undefined && original !== modified`）
- **THEN** 编辑器 MUST 只显示 modified 内容，新增行有绿色背景，删除行有红色背景
- **AND** 编辑器 MUST 是整个容器内唯一可见的代码面板，无额外分栏

#### Scenario: unifiedMergeView extension 配置正确
- **WHEN** 组件进入 diff 模式
- **THEN** extensions 列表 MUST 包含 `unifiedMergeView({ original })`，且值为 `pendingEdit.original`
- **AND** extensions MUST 包含 `EditorState.readOnly.of(true)`，禁止用户直接编辑

### Requirement: CSS 和布局兼容
组件 MUST 的编辑器容器适应父容器的 flex 布局（`flex: 1, min-height: 0`），编辑器内部 `.cm-editor` 圆角与现有 UI 设计一致。

#### Scenario: 容器尺寸自适应
- **WHEN** 编辑器被放入 flex column 父容器
- **THEN** 编辑器 MUST 填满剩余空间，不会出现溢出或高度为零的情况
