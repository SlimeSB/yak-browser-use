## ADDED Requirements

### Requirement: 编辑器初始化

系统 MUST 在 ChatTab 右侧面板初始化 Monaco Editor（YAML 语言模式），替换现有裸 `<textarea>`。初始化时 MUST 加载当前 pipeline YAML 内容并渲染语法高亮。

#### Scenario: 正常加载 pipeline YAML
- **WHEN** 用户切换到 ChatTab 并选中一个 pipeline
- **THEN** Monaco Editor MUST 显示该 pipeline 的完整 YAML 内容
- **AND** 关键字（`name`、`steps`、`browser_ops` 等）MUST 有语法着色
- **AND** 字符串值、列表缩进 MUST 正确渲染

#### Scenario: 空 pipeline 默认内容
- **WHEN** pipeline 内容为空或新创建
- **THEN** Monaco Editor MUST 显示 YAML 格式的 placeholder 示例（非 Markdown 格式）

### Requirement: 编辑器双向绑定

编辑器 MUST 在用户修改内容时通过 `onChange` 回调将最新文本同步到父组件状态，确保保存、运行等功能拿到最新内容。

#### Scenario: 用户编辑 YAML 内容
- **WHEN** 用户在 Monaco Editor 中输入或删除文本
- **THEN** 父组件 `agentMdEditor` 状态 MUST 更新为最新值
- **AND** 延迟 MAY 通过 debounce（300ms）控制更新频率

#### Scenario: 外部刷新 pipeline 内容
- **WHEN** 父组件传入新的 `value` prop（如切换 pipeline 或刷新）
- **THEN** Monaco Editor MUST 替换为新的 YAML 内容
- **AND** 光标位置 SHOULD 重置到文档开头

### Requirement: 编辑器基础功能

Monaco Editor MUST 提供 YAML 编辑器的标准功能：代码折叠、缩进引导线、括号匹配、行号显示。

#### Scenario: 代码折叠
- **WHEN** 用户在 YAML 中点击可折叠区域（如 `steps:` 下属列表）
- **THEN** 该区域 MUST 折叠/展开
- **AND** 折叠线 MUST 显示在行号左侧

#### Scenario: Tab 缩进
- **WHEN** 用户按下 Tab 键
- **THEN** Monaco Editor MUST 插入 2 个空格（与 YAML 项目缩进风格一致）

### Requirement: 暗色主题

编辑器 MUST 使用与现有应用一致的暗色主题（`vs-dark`），背景色与 ChatTab 右侧面板融合。

#### Scenario: 主题一致性
- **WHEN** Monaco Editor 初始化
- **THEN** 编辑器背景色 MUST 为暗色（`vs-dark` 主题）
- **AND** 语法着色 MUST 在暗色背景下保持可读对比度
