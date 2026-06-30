## 背景

`state.py` 中 `engine_state = _EngineState()` 是模块级全局单例，所有路由 handler 通过 `from state import engine_state` 直接读写。当前 `_EngineState` 没有提供重置方法，导致：

- 测试之间无法隔离状态（bridge、running_pipeline、ws_clients 残留）
- 需要 monkey-patch 整个模块才能 mock，不符合项目现有 pytest 惯例

`routes.py` 中 `api_run` 在执行 pipeline 前将内容写入 snapshot 文件。正常路径保留 snapshot（用于 audit），但异常路径的 `finally` 块执行 `snapshot_path.unlink()`，导致调试时无法查看出问题的 pipeline 内容。

约束：
- 不引入新依赖
- 不修改路由 handler 签名（避免连锁改动）
- 不改动 `api_run` 的同步执行方式（那是另一个问题）

## 目标 / 非目标

**目标：**
- 为 `_EngineState` 新增 `reset_for_test()` 方法，支持测试隔离
- `api_run` 异常时保留 snapshot 到 `_errors/` 子目录，不删除

**非目标：**
- 不引入 FastAPI `Depends` 依赖注入（改动范围太大）
- 不拆分 `routes.py`（独立 change）
- 不改变 `api_run` 的同步等待行为（独立 change）
- 不修改 `service.py` 的职责边界

## 关键决策

### D1：用 `reset_for_test()` 方法而非 `Depends` 注入

**原因：**
- `Depends` 需要改 60+ 个 handler 签名，风险和回归面太大
- `reset_for_test()` 是零侵入方案：只在测试代码的 `setup/teardown` 中调用，生产路径完全不受影响
- 命名中明确包含 `_for_test`，防止误用

**备选方案 `Depends`：**
- 更符合 FastAPI 最佳实践
- 但改动量过大，且当前没有后端测试覆盖，收益不明确
- 等后端测试覆盖率上来后可以再考虑升级

### D2：异常快照移到 `_errors/` 而非保留在原位

**原因：**
- 保留在 `versions/` 目录会污染正常版本列表
- `_errors/` 子目录语义明确，方便按需清理
- 文件内容不变，只是移动位置

## 风险 / 权衡

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| `reset_for_test()` 被生产代码误调用 | 低 | 方法名含 `_for_test` 后缀，code review 中容易被发现 |
| `_errors/` 目录长期不清理堆积磁盘 | 低 | 可以后续加定时清理逻辑；当前 pipeline 执行频率不高 |

## 迁移计划

上线为单一 commit，无数据迁移。回滚：`git revert` 即可。

测试策略：
- 先写测试（TDD 绿测试），验证 `reset_for_test()` 和 snapshot 保留行为
- 测试通过后再改实现代码
- 跑全量 `pytest` 确认无回归

## 待确认问题

无。
