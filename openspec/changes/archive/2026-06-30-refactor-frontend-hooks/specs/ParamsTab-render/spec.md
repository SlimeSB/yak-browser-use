## ADDED Requirements

### Requirement: ParamsTab 必须从 credentialStore 获取状态
ParamsTab MUST 删除以下 **7 个** props：`credKeys`、`credKey`、`onCredKeyChange`、`credValue`、`onCredValueChange`、`onCredSet`、`onCredDelete`，全部改为内部 `useCredentialStore(selector)`。

| prop | 来源 store | selector |
|------|-----------|----------|
| `credKeys` | credentialStore | `useCredentialStore(s => s.credKeys)` |
| `credKey` | credentialStore | `useCredentialStore(s => s.credKey)` |
| `onCredKeyChange` | credentialStore | `useCredentialStore(s => s.setCredKey)` |
| `credValue` | credentialStore | `useCredentialStore(s => s.credValue)` |
| `onCredValueChange` | credentialStore | `useCredentialStore(s => s.setCredValue)` |
| `onCredSet` | credentialStore | `useCredentialStore(s => s.addCredential)` |
| `onCredDelete` | credentialStore | `useCredentialStore(s => s.removeCredential)` |

#### Scenario: 渲染凭据列表
- **WHEN** ParamsTab 被激活
- **THEN** 组件 MUST 通过 `useCredentialStore(s => s.credKeys)` 获取凭据列表；每个 key  MUST 显示为 掩码占位符（••••••••），不显示真实值

#### Scenario: 空凭据状态
- **WHEN** credKeys.length === 0
- **THEN** MUST 显示空状态文案 t('paramsTab.noParams')，MUST NOT 崩溃

#### Scenario: 输入新凭据
- **WHEN** 用户在 key/value 输入框中输入内容
- **THEN** MUST 分别调 `credentialStore.setCredKey(value)` + `credentialStore.setCredValue(value)` 同步更新 store

#### Scenario: 添加凭据
- **WHEN** 用户点击"添加"按钮
- **THEN** MUST 调 `credentialStore.addCredential()`，内部 MUST：
  1. 验证 credKey 和 credValue 均非空 trim
  2. 调 `api.setCredential(key, value)` 提交后端
  3. 清空本地 credKey 和 credValue 输入框（通过 setCredKey('') / setCredValue('')）
  4. 调 `api.listCredentials()` 并更新 credKeys 列表

#### Scenario: 删除凭据
- **WHEN** 用户点击某个凭据右侧的删除按钮（🗑）
- **THEN** MUST 调 `credentialStore.removeCredential(key)`，内部 MUST：
  1. 调 `api.deleteCredential(key)` 提交后端
  2. 自动从 credKeys 中移除该 key（更新本地列表）

#### Scenario: 输入框受控状态
- **WHEN** 用户在 key 输入框中键入
- **THEN** input 的 value MUST 由 `useCredentialStore(s => s.credKey)` 驱动；MUST NOT 使用 useState

#### Scenario: hint 文案与 mask 显示
- **WHEN** ParamsTab 被激活
- **THEN** 顶部 MUST 展示 hint 文案（t('paramsTab.hint')）；每个凭据行的 value 列 MUST 固定显示 •••••••• 占位符，从未存储的真实值

#### Scenario: 错误处理
- **WHEN** api.setCredential 或 api.deleteCredential 抛出异常
- **THEN** credentialStore 内部 MUST catch 并通过 store 暴露 error 字段；或 console.error 静默失败（当前实现选择后者）
