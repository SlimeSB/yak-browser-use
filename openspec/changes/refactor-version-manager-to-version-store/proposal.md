## Why

当前 `VersionManager` 类与 pipeline workspace 场景强耦合：硬编码了 `pipe.pipeline.yaml` 文件名、`tools/` 目录拷贝逻辑、以及 `trigger_run_id` / `upgraded_tools` / `learned_goals` 等 preset-run 专属 meta 字段。

这导致两个问题：
1. **无法复用**：未来 omni-api 的 preset auto_record 需要完全相同的有序版本管理（版本号递增 + 文件快照 + meta JSON + LATEST 指针），但 meta schema 不同（`success_rate`、`verified_date`、`target_domains`），当前类无法直接承接。
2. **无人调用**：在 preset-recovery change 中，`run_pipeline` 的自动版本快照已被移除（checkpoint 覆盖回退需求），VersionManager 在当前代码路径中实际处于"死代码"状态。

本次变更将 VersionManager 泛化为通用的 `VersionStore`，去掉硬耦合，使其能同时服务 workspace pipeline 场景和未来 omni-api preset 场景。

## What Changes

- **新增** `VersionStore` 类（`workspace/version_store.py`）：接受 `{文件名: 内容}` dict + meta dict，不硬编码文件名或目录结构
- **修改** `workspace/version_manager.py`：变为 `VersionStore` 的薄封装（保留旧接口签名，内部委托 VersionStore），确保现有 API 路由无需改动
- **修改** `api/routes.py`：`/api/versions/*` 路由中的 `VersionManager` 实例化改为可选（如果未来有新 consumer 再激活）
- **保留** 磁盘上的旧 `versions/` 目录结构（向后兼容）

## Capabilities

### New Capabilities
- `version-store`: 通用的有序版本存储，支持任意文件快照 + 可扩展 meta schema，可为 workspace pipeline 和 omni-api preset 提供版本管理

### Modified Capabilities
- `pipeline-versioning`: 从 VersionManager 的硬编码 pipeline-specific 逻辑改为 VersionStore 的通用文件快照 + 可配置 meta

## Impact

| 文件 | 影响 |
|---|---|
| `workspace/version_manager.py` | 重构为 VersionStore 委托（保留旧接口） |
| `workspace/version_store.py` | **新建**，核心泛化实现 |
| `workspace/__init__.py` | 导出改为 VersionStore |
| `api/routes.py` | VersionManager 导入保留（薄封装仍存在），无接口变动 |
| 前端 `VersionPanel.tsx` | 无影响（API 路由不变） |
| `test_version_manager.py` | 需更新为测试新版 VersionStore |
