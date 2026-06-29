## ADDED Requirements

### Requirement: browser_wait_for_download 工具注册
系统 MUST 注册 `browser_wait_for_download` 工具替代原有的 `wait_for_download`，纳入 browser ops 类。功能保持不变（轮询下载目录等待文件稳定），仅名称变更。

#### Scenario: browser_wait_for_download 出现在 browser ops 中
- **WHEN** `registry.get_schemas()` 被调用
- **THEN** 返回的 schema 列表中 MUST 包含 `browser_wait_for_download` 而非 `wait_for_download`

#### Scenario: 等待下载文件就绪
- **WHEN** LLM 调用 `browser_wait_for_download(timeout=60)`
- **THEN** 系统 MUST 轮询 workspace 下载目录，检测新文件
- **AND** 系统 MUST 等待文件大小稳定（> 100 bytes，1 秒内不变）
- **AND** 系统 MUST 返回 `{"ok": True, "path": "downloads/<filename>"}`

#### Scenario: 下载超时
- **WHEN** LLM 调用 `browser_wait_for_download(timeout=10)` 且 10 秒内无新文件
- **THEN** 系统 MUST 返回 `{"ok": False, "error": "timeout"}`

#### Scenario: browser_wait_for_download 参数不变
- **WHEN** LLM 查看 `browser_wait_for_download` 的 tool schema
- **THEN** schema MUST 包含参数 `timeout`（integer, optional, default=60）

## MODIFIED Requirements

### Requirement: 移除 wait_for_download 工具注册
原 `wait_for_download` 工具名 SHALL 从 registry 移除。**Reason:** 重命名为 `browser_wait_for_download` 以纳入 browser ops 分类体系。**Migration:** 调用方将 `wait_for_download(timeout=N)` 改为 `browser_wait_for_download(timeout=N)`。**BREAKING**。
