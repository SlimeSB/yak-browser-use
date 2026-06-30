# SettingsTab Render

## Requirements

### SettingsTab 必须从 connectionStore / uiStore / pipelineStore 获取状态
SettingsTab MUST 删除 8 个 props，全部改为内部 selector。

#### Scenario: 切换 reviewMode
- **WHEN** 用户点击"人工审核"按钮
- **THEN** SettingsTab MUST 调 `pipelineStore.setReviewMode('human' | 'llm' | 'none')`

#### Scenario: 切换 theme
- **WHEN** 用户点击"亮色/暗色"按钮
- **THEN** SettingsTab MUST 调 `uiStore.setTheme('light' | 'dark')`

#### Scenario: 切换 highlightMode
- **WHEN** 用户点击"a11y / progressive / off"按钮
- **THEN** SettingsTab MUST 调 `connectionStore.setHighlightMode('a11y' | 'progressive' | 'off')`
