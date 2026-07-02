## 1. 核心实现：VersionStore

- [ ] 1.1 新建 `workspace/version_store.py`，实现 `VersionStore` 类：
  - `__init__(self, store_dir: Path)` — 仅接收存储目录，不预设业务语义
  - `create_version(files: dict[str, str], meta: dict) -> str` — 递增版本号，写入 `store_dir/<version>/`（files dict 的 key 作为子路径），meta 序列化为 `meta.json`，更新 `LATEST`
  - `load_version(version: str) -> tuple[dict, dict] | None` — 返回 `(files_dict, meta_dict)`
  - `list_versions() -> list[dict]` — 返回所有版本的 meta（按版本号升序）
  - `get_latest() -> str | None` — 读取 `LATEST` 文件
  - `mark_stale()` / `clear_stale()` / `is_stale()` — 操作 `STALE` 文件
  - `_next_version() -> str` — 内部方法，扫描已有版本目录取最大编号 +1

## 2. VersionManager 薄封装重构

- [ ] 2.1 修改 `workspace/version_manager.py`，将 `VersionManager` 内部实现改为委托 `VersionStore`：
  - `__init__` 内部实例化 `VersionStore(versions_dir)`
  - `create_version(trigger_run_id, summary, pipe_pipeline, tools_dir, ...)` — 将 `pipe_pipeline` 读为文件内容、`tools_dir` 遍历为文件 dict，合并为 `files` 参数；将 `trigger_run_id`/`upgraded_tools`/`learned_goals` 打包为 `meta` dict；调用 `VersionStore.create_version(files, meta)`
  - `load_version()` / `list_versions()` / `get_latest()` / `mark_stale()` / `clear_stale()` / `is_stale()` — 透传给 VersionStore
  - `try_create_version()` — 同上转换逻辑
  - `save_snapshot()` — 转换为 `create_version(files={...}, meta={...})` 调用

- [ ] 2.2 更新 `workspace/__init__.py`，新增 `from yak_browser_use.workspace.version_store import VersionStore` 导出

## 3. 测试

- [ ] 3.1 运行现有 `backend/tests/test_version_manager.py`，确保全部通过（接口签名未变）
- [ ] 3.2 新建 `backend/tests/test_version_store.py`，覆盖：
  - 创建带自定义文件名和 meta 的版本
  - 版本号递增正确性
  - load_version / list_versions 正确性
  - files dict 含子路径（如 "tools/extract.py"）时正确创建目录结构
  - mark_stale / clear_stale / is_stale 状态转换

## 4. 验证与收尾

- [ ] 4.1 手动验证：运行一个有 preset pipeline 的 `/api/run`，确认 `versions/` 目录不再有新快照写入（run_pipeline 已不加调用）
- [ ] 4.2 确认 `api_restart_pipeline` 仍正常工作（它从 LATEST version 加载）
- [ ] 4.3 确认前端 VersionPanel 正常展示版本列表
- [ ] 4.4 代码审查：确认 VersionStore 不引入对 `pipeline`、`tools`、`pipe` 等业务关键词的任何硬编码
