## Why

当前系统存在两个问题：

1. **Preset pipeline 失败后无法自愈**：当 preset pipeline 的某个 step 因选择器错误、check 失败、JS 错误等原因失败时，整个 pipeline 直接标记为 "failed"，用户只能手动修改 yaml 后重新运行。这不仅浪费了之前已成功执行的步骤（需要全部重跑），还降低了自动化程度。

2. **执行产物目录不对称**：preset run 有自己的 `runs/{run_id}/` 目录，而 agent chat session 的下载文件散落在 workspace 根目录的 `downloads/` 下。两套执行体系各自演化，没有统一的产物隔离和清理机制。

本次变更将：让 preset pipeline 在 terminal failure 时自动启动 recovery session 修复 yaml 后重跑；统一执行产物模型，让 preset run 和 agent session 共享同一套 `runs/{id}/` 目录和生命周期管理。

## What Changes

- **新增** `WorkspaceManager.create_run(exec_type)` 统一入口，同时服务 preset run 和 agent session
- **新增** agent session 创建时自动建立 `runs/{session_id}/downloads/` 目录
- **新增** preset pipeline terminal failure 时收集 `failure_context` 并标记 `needs_recovery` 状态
- **新增** `api_run` 中的 recovery 循环：失败后新建 session → 调用 `process_chat_message()` 让 agent 修复 yaml → 重跑 pipeline
- **新增** `_build_recovery_prompt()` 格式化失败上下文为 agent prompt
- **修改** `PlaywrightBridge._resolve_download_path()` 基于 `run_id` 而非全局 workspace 解析下载路径
- **修改** `PlaywrightBridge.set_download_pipeline()` 接口，接受 `run_id` 参数
- **修改** `_resolve_input_files()` 的 `downloads/` 前缀解析为 run-relative（无 fallback）
- **修改** RunContext 新增 `failure_context` 字段
- **修改** `engine_state.connect_chrome()` 不再绑定全局下载路径，延迟到首次 `set_download_dir()` 调用
- **移除** 旧 `workspace/downloads/` 路径的 fallback（无消费方，YAGNI）

## Capabilities

### New Capabilities
- `preset-recovery`: preset pipeline terminal failure 后自动启动 agent recovery session 修复 yaml 并重新运行
- `unified-runs-directory`: 统一的执行产物目录模型，preset run 和 agent session 共享 `runs/{id}/` 结构

### Modified Capabilities
- `browser-download`: 浏览器下载路径从 workspace 级 `downloads/` 改为 `runs/{id}/downloads/`
- `unified-runs-directory`: agent session 创建时自动通过 `create_run("agent")` 在 `runs/` 下建立对应目录

## Impact

| 文件 | 影响 |
|---|---|
| `workspace/manager.py` | create_run 接口扩展，新增 exec_type 参数 |
| `workspace/session_store.py` | new_session 新增加载 run 目录创建 |
| `cdp/playwright_bridge.py` | set_download_pipeline 签名变更，下载路径解析逻辑变更 |
| `engine/executor.py` | _resolve_input_files 前缀解析变更 |
| `engine/runner_preset.py` | terminal failure 路径变更，新增 failure_context 收集 |
| `engine/state.py` | RunContext 新增 failure_context 字段 |
| `api/routes.py` | api_run 新增加权 recovery 循环 |
| `_run.json` | 新增 `type` 字段区分 preset/agent |
| 前端 `pipelineStore.ts` | run_id 仍然可获取，_run.json 中 type 字段可选消费 |
