## ADDED Requirements

### Requirement: SettingsTab 必须从 connectionStore / uiStore / pipelineStore 获取状态
SettingsTab MUST 删除以下 **8 个** props，全部改为内部 selector：

| prop | 来源 store | selector |
|------|-----------|----------|
| `reviewMode`, `onReviewModeChange` | pipelineStore | `usePipelineStore(s => s.reviewMode)` + `usePipelineStore(s => s.setReviewMode)` |

> **设计说明（E4）：** reviewMode 归入 pipelineStore 的理由：
> - reviewMode 直接影响 pipelineStore.run() 的行为（前置插入 `review_mode: "..."`），run() 需要直接读取它
> - 如果 reviewMode 放在 uiStore 或 connectionStore，run() 就需要跨 store 依赖，增加隐式耦合
> - reviewMode 虽是设置，但它的消费场景是管道运行语义范畴（不是连接行为也不是 UI 布局偏好）
> - 因此这是 "影响某 store 核心 action 的配置 MUST 与那个 store 同域" 原则的应用
| `chatLayoutReversed`, `onChatLayoutReversedChange` | uiStore | `useUiStore(s => s.chatLayoutReversed)` + `useUiStore(s => s.setChatLayoutReversed)` |
| `theme`, `onThemeChange` | uiStore | `useUiStore(s => s.theme)` + `useUiStore(s => s.setTheme)` |
| `highlightMode`, `onHighlightModeChange` | connectionStore | `useConnectionStore(s => s.highlightMode)` + `useConnectionStore(s => s.setHighlightMode)` |

#### Scenario: 切换 reviewMode
- **WHEN** 用户点击"人工审核"按钮
- **THEN** SettingsTab MUST 调 `pipelineStore.setReviewMode('human' | 'llm' | 'none')`，MUST NOT 通过 props.onReviewModeChange

#### Scenario: 切换 theme
- **WHEN** 用户点击"亮色/暗色"按钮
- **THEN** SettingsTab MUST 调 `uiStore.setTheme('light' | 'dark')`，内部 MUST 自动同步 localStorage 和 document.documentElement data-theme 属性

#### Scenario: 切换 chatLayoutReversed
- **WHEN** 用户点击"Editor First / Chat First"按钮
- **THEN** SettingsTab MUST 调 `uiStore.setChatLayoutReversed(true|false)`，MUST 自动同步 localStorage('chat-layout-reversed')

#### Scenario: 切换 highlightMode
- **WHEN** 用户点击"a11y / progressive / off"按钮
- **THEN** SettingsTab MUST 调 `connectionStore.setHighlightMode('a11y' | 'progressive' | 'off')`，MUST 自动同步 localStorage('highlight-mode')

#### Scenario: 切换语言
- **WHEN** 用户点击 English / 中文 按钮
- **THEN** SettingsTab MUST 调 `i18n.changeLanguage('en' | 'zh-CN')`（非 store 行为，i18n 不纳入本次重构范围）

#### Scenario: 切换 LLM provider preset
- **WHEN** 用户点击 provider preset 按钮
- **THEN** SettingsTab MUST 调 `api.applyPreset(preset)`（api 调用直接在 SettingsTab 内部执行，因为 providerConfig 是组件内 useState）

#### Scenario: 保存 provider config
- **WHEN** 用户点击 Save 按钮
- **THEN** SettingsTab MUST 调 `api.setProviderConfig(...)` 显示 saved 状态后 2 秒自动消失

#### Scenario: 测试 provider
- **WHEN** 用户点击 Test 按钮
- **THEN** SettingsTab MUST 调 `api.testProvider(...)` 显示 ok/fail 结果 4 秒后自动消失

#### Scenario: providerConfig / presets / presetsError 是组件内 useState
- **WHEN** 用户编辑 model / api_key / api_base 字段
- **THEN** providerConfig MUST 保留为组件 useState；presets / activePresetId / presetsError MUST 在组件挂载时调 api 获取，不纳入 store
