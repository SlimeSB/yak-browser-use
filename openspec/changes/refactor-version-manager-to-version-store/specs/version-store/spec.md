## ADDED Requirements

### Requirement: VersionStore SHALL provide generic versioned file storage
`VersionStore` MUST 提供通用的有序版本存储，接受任意 `{文件名: 内容}` dict 和 `meta` dict，不硬编码任何文件名或目录结构。每次 `create_version()` 生成递增版本号，将文件快照写入 `store_dir/<version>/`，meta 写入 `store_dir/<version>/meta.json`。

#### Scenario: Create version with arbitrary files
- **WHEN** 调用 `create_version(files={"pipeline.yaml": "content", "tools/extract.py": "code"}, meta={"success_rate": 0.95})`
- **THEN** MUST 创建 `store_dir/<N>/pipeline.yaml`、`store_dir/<N>/tools/extract.py`、`store_dir/<N>/meta.json`
- **AND** MUST 更新 `store_dir/LATEST` 指向新版本号

#### Scenario: Version numbers auto-increment
- **WHEN** 连续调用 `create_version()` 三次
- **THEN** 三次版本号 MUST 分别为 "1"、"2"、"3"
- **AND** MUST 基于已有版本目录中的最大编号递增

### Requirement: VersionStore SHALL support loading and listing versions
`VersionStore` MUST 提供 `load_version(version)` 返回指定版本的文件内容和 meta，`list_versions()` 返回所有版本的 meta 列表（按版本号排序），`get_latest()` 返回最新版本号。

#### Scenario: Load existing version
- **WHEN** 版本 "3" 存在且包含 `pipeline.yaml`
- **THEN** `load_version("3")` MUST 返回 `({"pipeline.yaml": <content>}, {"success_rate": 0.95})`

#### Scenario: Load non-existent version
- **WHEN** 请求的版本号不存在
- **THEN** MUST 返回 None

#### Scenario: List versions returns sorted metadata
- **WHEN** 存在版本 1、2、3
- **THEN** `list_versions()` MUST 返回按版本号升序排列的 meta dict 列表

### Requirement: VersionStore SHALL preserve backward compatibility
`version_manager.py` MUST 保留 `VersionManager` 类作为 `VersionStore` 的薄封装，确保现有 API 路由（`/api/versions/*`）无需改动即可继续工作。

#### Scenario: Existing API routes still work
- **WHEN** 前端调用 `GET /api/versions/{pipeline}`
- **THEN** MUST 返回版本列表，行为与重构前一致
- **AND** 底层存储仍使用 `workspaces/<name>/versions/` 目录

#### Scenario: VersionManager delegates to VersionStore
- **WHEN** 代码调用 `VersionManager.create_version(trigger_run_id, summary, pipe_pipeline, tools_dir)`
- **THEN** MUST 内部转换为 VersionStore 的 `create_version(files={...}, meta={...})` 调用
- **AND** 文件名 MUST 为 `pipe.pipeline.yaml`，tools 目录 MUST 被扁平化存储

#### Scenario: Backward compat meta schema preserved
- **WHEN** 通过 VersionManager 创建版本
- **THEN** meta.json MUST 包含 `trigger_run_id`、`summary`、`version`、`created_at` 字段

### Requirement: VersionStore SHALL support stale marker
`VersionStore` MUST 提供 `mark_stale()` / `clear_stale()` / `is_stale()` 方法，在 `store_dir/STALE` 文件中标记/取消/查询 stale 状态。

#### Scenario: Mark stale
- **WHEN** 调用 `mark_stale()`
- **THEN** MUST 在 `store_dir/STALE` 创建空文件

#### Scenario: Check stale status
- **WHEN** STALE 文件存在
- **THEN** `is_stale()` MUST return True

#### Scenario: Clear stale
- **WHEN** 调用 `clear_stale()`
- **THEN** MUST 删除 `store_dir/STAST` 文件

### Requirement: VersionStore SHALL be path-agnostic
`VersionStore` MUST 接受任意 `store_dir` 路径，不假设其在 `workspaces/` 目录下。使用者负责传入正确的存储根目录。

#### Scenario: Store in presets directory
- **WHEN** 传入 `store_dir=Path("presets/my-preset/versions")`
- **THEN** MUST 在 `presets/my-preset/versions/` 下创建版本目录

#### Scenario: Store in workspace directory
- **WHEN** 传入 `store_dir=Path("workspaces/my-pipeline/versions")`
- **THEN** MUST 在 `workspaces/my-pipeline/versions/` 下创建版本目录

## MODIFIED Requirements

### Requirement: workspace version storage layout
当前 `VersionManager` 硬编码 `pipe.pipeline.yaml` 文件名和 `tools/` 子目录结构。修改后：`VersionStore` 接受任意文件 dict，`VersionManager` 封装层负责将 `pipe_pipeline` Path + `tools_dir` Path 转换为 files dict。

#### Scenario: VersionManager creates pipeline-specific files
- **WHEN** 调用 `VersionManager.create_version(trigger_run_id, summary, pipe_pipeline=Path("pipeline.yaml"), tools_dir=Path("tools"))`
- **THEN** 版本目录 MUST 包含 `pipe.pipeline.yaml`（来自 pipe_pipeline 参数）和 `tools/` 子目录（来自 tools_dir 拷贝）
- **AND** meta.json MUST 包含 `trigger_run_id`、`summary`、`version`、`created_at`

#### Scenario: Direct VersionStore usage with custom schema
- **WHEN** 直接实例化 `VersionStore(store_dir, "preset")` 并调用 `create_version(files={"preset.yaml": "..."}, meta={"success_rate": 0.9})`
- **THEN** 版本目录 MUST 包含 `preset.yaml` 和 `meta.json`
- **AND** meta.json MUST 原样保存调用者传入的所有字段

## REMOVED Requirements

### Requirement: Hardcoded pipe.pipeline.yaml filename
**Reason**: `VersionStore` 泛化为通用文件存储，不再假设存储的是 pipeline yaml。文件名由调用者通过 `files` dict 的 key 决定。
**Migration**: 现有通过 `VersionManager` 创建的版本数据不变（磁盘上的 `pipe.pipeline.yaml` 文件仍存在），新代码路径通过 `VersionManager` 封装层继续使用旧文件名。
