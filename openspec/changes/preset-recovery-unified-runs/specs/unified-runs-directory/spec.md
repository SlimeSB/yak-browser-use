## ADDED Requirements

### Requirement: WorkspaceManager SHALL provide unified create_run entry
`WorkspaceManager` MUST 提供统一的 `create_run(exec_type="preset")` 方法，支持创建 preset run 和 agent session 两种类型的执行目录。两种类型共享同一套 `runs/{id}/` 基础结构，差异在于：preset 类型创建 `final/` 目录，agent 类型仅创建 `downloads/` 目录。

#### Scenario: Create preset run
- **WHEN** 调用 create_run("preset")
- **THEN** 系统 MUST 创建 runs/{YYYYMMDD_HHMMSS}/ 目录
- **AND** 创建 downloads/ 和 final/ 子目录
- **AND** 写入 _run.json 包含 {"type": "preset", ...}

#### Scenario: Create agent session run
- **WHEN** 调用 create_run("agent")
- **THEN** 系统 MUST 创建 runs/{recovery_YYYYMMDD_HHMMSS_hex}/ 目录（前缀 `recovery_`）
- **AND** 仅创建 downloads/ 子目录（不创建 final/）
- **AND** 写入 _run.json 包含 {"type": "agent", ...}

### Requirement: Session creation SHALL trigger run directory creation
`SessionStore.new_session()` MUST 在创建 session 记录的同时调用 `WorkspaceManager.create_run("agent")` 建立对应的执行目录，session_id 和 run_id 保持独立。

#### Scenario: User starts new chat session
- **WHEN** 前端调用 /api/session/new
- **THEN** system MUST 在 session/ 下创建 session 记录
- **AND** MUST 在 runs/ 下创建对应目录结构
- **AND** 浏览器下载路径绑定到新 session 的 runs directory

### Requirement: detect_crashed_runs SHALL only process preset runs
`detect_crashed_runs()` MUST 只处理 `_run.json` 中 `type == "preset"` 的 run，跳过 `type == "agent"` 的 run。

#### Scenario: Mix of preset and agent runs
- **WHEN** runs/ 下有 preset run（type=preset）和 agent run（type=agent）
- **WHEN** detect_crashed_runs 被调用
- **THEN** MUST 仅检查并标记 preset 类型的 run
- **AND** MUST 跳过 agent 类型的 run

### Requirement: cleanup_old_runs SHALL not distinguish by type
`cleanup_old_runs()` MUST 对 runs/ 下所有子目录按时间排序清理，不区分 preset/agent 类型。

#### Scenario: Recovery created multiple runs
- **WHEN** 1 次 preset run + 3 次 recovery 产生了 3 个 agent session run（recovery_ 前缀） + 1 次 re-run
- **WHEN** cleanup_old_runs(max_runs=20) 被调用
- **THEN** MUST 按目录名时间排序保留最近 20 个（混合类型）

### Requirement: _resolve_input_files SHALL resolve downloads/ prefix run-relative
`_resolve_input_files()` MUST 将 `downloads/` 前缀解析为 `run_dir / ref`（run 级别路径）。无 fallback。

#### Scenario: Preset run references its own download
- **WHEN** preset run 中 tool_result 包含 "downloads/video.mp4"
- **THEN** MUST 解析为 runs/{run_id}/downloads/video.mp4

#### Scenario: Legacy workspace-level download not found
- **WHEN** run_dir / "downloads/video.mp4" 不存在
- **THEN** MUST 返回原路径并 log warning（不 fallback 到其他位置）

### Requirement: _looks_like_run_id SHALL match both preset and agent run IDs
`_looks_like_run_id()` 正则 MUST 同时匹配 preset run ID（`YYYYMMDD_HHMMSS`）和 agent run ID（`recovery_YYYYMMDD_HHMMSS_hex`）。

#### Scenario: Preset run ID recognized
- **WHEN** name = "20260702_143052"
- **THEN** _looks_like_run_id MUST return True

#### Scenario: Agent run ID recognized
- **WHEN** name = "recovery_20260702_143052_a1b2c3"
- **THEN** _looks_like_run_id MUST return True

### Requirement: _run.json SHALL include type field
`_run.json` MUST 包含 `type` 字段，值为 "preset" 或 "agent"，用于前端 UI 和生命周期管理逻辑区分。

#### Scenario: List runs response
- **WHEN** 前端请求 run 列表
- **THEN** 返回的每个 run 对象 MUST 包含 type 字段
- **AND** 前端可据此决定展示方式

## MODIFIED Requirements

### Requirement: PlaywrightBridge download path resolution
当前 `_resolve_download_path()` 返回 `WORKSPACES_ROOT / pipeline_name / "downloads"`。修改后 MUST 返回 `WORKSPACES_ROOT / pipeline_name / "runs" / run_id / "downloads"`。方法名从 `set_download_pipeline(pipeline_name)` 改为 `set_download_dir(pipeline_name, run_id)`。

#### Scenario: No run_id set
- **WHEN** set_download_dir 尚未被调用
- **THEN** _resolve_download_path MUST 返回 None
- **AND** 浏览器下载走 Playwright 默认行为（默认 download 目录）

#### Scenario: run_id set
- **WHEN** set_download_dir(name, run_id) 已被调用
- **THEN** MUST 返回对应的 runs/{run_id}/downloads/ 路径
- **AND** 所有 page 的下载行为绑定到此目录

### Requirement: connect_chrome SHALL NOT bind download path
当前 `engine_state.connect_chrome()` 在连接时绑定 pipeline_name 到 bridge。修改后 MUST 不再在连接时绑定下载路径，延迟到首次 set_download_dir() 调用时。

#### Scenario: Chrome connected for chat
- **WHEN** 用户连接 Chrome 到 chat pipeline
- **THEN** MUST 不绑定任何 run_id 的下载路径
- **AND** 下载行为为 Playwright 默认下载

#### Scenario: Preset run starts after connect
- **WHEN** 用户发起 /api/run
- **THEN** 系统 MUST 在 run_pipeline 开始时调用 set_download_dir(name, run_id)
