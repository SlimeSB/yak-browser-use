# ParamsTab Render

## Requirements

### ParamsTab 必须从 credentialStore 获取状态
ParamsTab MUST 删除 7 个 props，全部改为内部 useCredentialStore(selector)。

#### Scenario: 渲染凭据列表
- **WHEN** ParamsTab 被激活
- **THEN** 组件 MUST 通过 useCredentialStore(s => s.credKeys) 获取凭据列表

#### Scenario: 添加凭据
- **WHEN** 用户点击"添加"按钮
- **THEN** MUST 调 credentialStore.addCredential()
"@
  }
  "PipelinesTab-render" = @{
    path = "D:\translate-project\yak-browser-use\openspec\specs\PipelinesTab-render\spec.md"
    content = @"
# PipelinesTab Render

## Requirements

### PipelinesTab 必须从 pipelineStore 获取数据而非 props
PipelinesTab MUST 不再接收 5 个 props，改为内部 usePipelineStore selector 以及 useUiStore selector。

#### Scenario: 渲染 pipelines 列表
- **WHEN** PipelinesTab 被激活
- **THEN** 组件 MUST 展示来自 usePipelineStore(s => s.pipelines) 的卡片列表

#### Scenario: 点击 Run 按钮
- **WHEN** 用户在 PipelinesTab 中点击某个 pipeline 的 "Run" 按钮
- **THEN** PipelinesTab MUST 调 pipelineStore.setActivePreset(name) + uiStore.setActiveTab('exec')
"@
  }
  "SettingsTab-render" = @{
    path = "D:\translate-project\yak-browser-use\openspec\specs\SettingsTab-render\spec.md"
    content = @"
# SettingsTab Render

## Requirements

### SettingsTab 必须从 connectionStore / uiStore / pipelineStore 获取状态
SettingsTab MUST 删除 8 个 props，全部改为内部 selector。

#### Scenario: 切换 reviewMode
- **WHEN** 用户点击"人工审核"按钮
- **THEN** SettingsTab MUST 调 pipelineStore.setReviewMode('human' | 'llm' | 'none')

#### Scenario: 切换 theme
- **WHEN** 用户点击"亮色/暗色"按钮
- **THEN** SettingsTab MUST 调 uiStore.setTheme('light' | 'dark')

#### Scenario: 切换 highlightMode
- **WHEN** 用户点击"a11y / progressive / off"按钮
- **THEN** SettingsTab MUST 调 connectionStore.setHighlightMode('a11y' | 'progressive' | 'off')
"@
  }
  "StatusBar-render" = @{
    path = "D:\translate-project\yak-browser-use\openspec\specs\StatusBar-render\spec.md"
    content = @"
# StatusBar Render

## Requirements

### StatusBar 必须从 pipelineStore 和 connectionStore 获取状态
StatusBar MUST 删除 2 个 props：events（来自 pipelineStore）、connected（来自 connectionStore），改为内部 selector。

#### Scenario: 显示连接状态
- **WHEN** 渲染 StatusBar
- **THEN** MUST 展示一个 conn-dot 指示器 + 连接/断开文案，数据来自 useConnectionStore(s => s.connected)

#### Scenario: 显示步骤进度
- **WHEN** pipelineStore.events 含 step_start/step_end
- **THEN** MUST 显示 "步骤 stepDone/stepTotal"

#### Scenario: 就绪状态
- **WHEN** stepTotal === 0
- **THEN** MUST 显示"就绪"文案
