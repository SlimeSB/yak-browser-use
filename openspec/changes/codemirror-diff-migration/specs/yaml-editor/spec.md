## ADDED Requirements

### Requirement: CodeMirror 编辑器核心编辑功能
组件 MUST 在编辑模式下（`!hasDiff`）提供 YAML 语法高亮、2 空格缩进、行号、括号匹配、折行显示，并通过 `onChange` 回调实时向父组件报告内容变化。

#### Scenario: YAML 编辑正常
- **WHEN** 用户处于编辑模式（无 `pendingEdit` 或 `original === modified`）
- **THEN** 编辑器 MUST 显示 `value` 内容
- **AND** 用户编辑时 MUST 触发 `onChange(text)` 回调
- **AND** 语法高亮 MUST 覆盖 YAML 标量、键、注释

#### Scenario: 外部 value 变化能正确同步
- **WHEN** 外部通过 prop 传入新的 `value`（如重置 session、accept edit 后更新）
- **THEN** 编辑器 MUST 将新内容与当前文档比较，若不同 MUST 更新编辑器内容为最新的 prop 值
- **AND** 此更新 MUST **不**触发 `onChange` 回调

#### Scenario: Tab 缩进为 2 空格
- **WHEN** 用户在编辑器内按下 Tab 键
- **THEN** MUST 插入 2 个空格

## MODIFIED Requirements

### Requirement: YAML 编辑器组件实现从 Monaco 迁移到 CodeMirror 6
组件 MUST 保持与 `MonacoYamlEditor` 完全兼容的 props 接口——`value`、`original`、`modified`、`onChange`、`theme`——但内部实现改用 `@uiw/react-codemirror` 和 `@codemirror/lang-yaml`，不再依赖 `monaco-editor`。

#### Scenario: props 接口不变
- **WHEN** 父组件 `ChatTab.tsx` 传入 `value`/`original`/`modified`/`onChange`/`theme`
- **THEN** 组件 MUST 按照原接口定义的语义处理所有 props
- **AND** `hasDiff` 计算逻辑 MUST 保持不变：`original !== undefined && modified !== undefined && original !== modified`

#### Scenario: 模式切换正确
- **WHEN** `hasDiff` 从 true 变为 false（用户 confirm/revert 后）
- **THEN** 组件 MUST 从 diff 模式切换到编辑模式，编辑器变为可写
- **WHEN** `hasDiff` 从 false 变为 true（有新 pendingEdit）
- **THEN** 组件 MUST 从编辑模式切换到只读 diff 模式
- **AND** 模式切换 MUST 立即反映到 UI，不出现短暂的双面板或空白闪烁
