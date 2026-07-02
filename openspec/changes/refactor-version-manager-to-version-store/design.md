## 背景

### 当前状态

`VersionManager`（`workspace/version_manager.py`）提供以下能力：
- 有序版本号管理（`_next_version()` 自动递增）
- 文件快照存储（`pipe.pipeline.yaml` + `tools/` 目录）
- meta JSON（`trigger_run_id`、`summary`、`upgraded_tools`、`learned_goals`）
- LATEST / STALE 指针文件
- API 路由消费：`api_list_versions`、`api_get_version`、`api_relearn`、`api_restart_pipeline`

**硬耦合问题**：
- `create_version()` 强制接收 `pipe_pipeline: Path` + `tools_dir: Path`，写入固定文件名 `pipe.pipeline.yaml`
- meta schema 预设了 `trigger_run_id`、`upgraded_tools`、`learned_goals` 字段
- 无法用于 omni-api 的 preset 版本管理（需要 `success_rate`、`verified_date`、`target_domains` 等字段）

**调用状态**：
- preset-recovery change 已删除 `run_pipeline` 内的 `create_version` 调用
- 当前存活调用者：`api_restart_pipeline`（依赖 LATEST version 读取）
- 前端 `VersionPanel` 消费 `/api/versions/*` 路由

## 目标 / 非目标

**目标：**
- 将 VersionManager 的核心能力（有序版本号 + 文件快照 + meta + LATEST/STALE 指针）泛化为通用 `VersionStore`
- 保留 `VersionManager` 薄封装层，确保现有 API 路由零改动
- 为未来 omni-api 的 preset auto_record 预留接口

**非目标：**
- 不修改现有 API 路由行为
- 不迁移磁盘上的旧 `versions/` 数据
- 不实现 omni-api preset 场景（未来独立 change）
- 不修改前端 VersionPanel

## 关键决策

### 1. VersionStore 接受 files dict + meta dict

**选择**：泛化后的核心接口为 `create_version(files: dict[str, str], meta: dict) -> str`，文件名和内容由调用者通过 dict 传入。

**原因**：消除对 `pipe.pipeline.yaml` 和 `tools/` 目录的硬耦合，让存储层完全不感知业务语义。

**备选方案**：保留 `pipe_pipeline` + `tools_dir` 参数但增加可选 `extra_files` dict。被否决——半泛化比不泛化更糟糕，调用者仍然需要理解两种模式。

### 2. VersionManager 作为 VersionStore 的薄封装

**选择**：`VersionManager` 保留原有方法签名，内部实例化 `VersionStore`，将 `pipe_pipeline` + `tools_dir` 转换为 `files` dict 后委托调用。

**原因**：
- 现有 API 路由全部通过 `VersionManager` 类交互，保留它 = 零改动
- 未来 omni-api 可以直接用 `VersionStore`，绕过 `VersionManager` 的业务耦合

**代价**：多一层间接调用，但 VersionManager 当前不是热点路径，性能影响为零。

### 3. 新增 workspace/__init__.py 导出 VersionStore

**选择**：在 `workspace/__init__.py` 中同时导出 `VersionManager` 和 `VersionStore`。

**原因**：未来 omni-api change 可以直接 `from yak_browser_use.workspace import VersionStore`，不需要回来改导出。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| VersionManager 薄封装遗漏边缘行为 | API 路由行为变化 | 保留现有 `test_version_manager.py` 作为回归测试 |
| files dict 中的路径分隔符问题（如 "tools/extract.py"） | 跨平台路径问题 | 使用 `Path` 的 `/` 运算符构建子目录，自动处理分隔符 |
| omni-api meta schema 未稳定 | VersionStore 接口仍需演进 | VersionStore meta 是 open dict，schema 由调用者负责 |

## 迁移计划

**上线步骤**：

1. 新建 `workspace/version_store.py` 实现 VersionStore
2. 修改 `workspace/version_manager.py` 内部委托 VersionStore
3. 更新 `workspace/__init__.py` 导出
4. 运行现有 `test_version_manager.py` 确保全部通过
5. （可选）新增 `test_version_store.py` 测试泛化能力

**回滚**：VersionManager 接口签名不变，回滚 = 恢复旧文件，零数据迁移。

**兼容**：磁盘上的 `versions/<N>/` 目录结构不变，旧 VersionManager 创建的 meta.json 格式不变。

## 待确认问题

无。
