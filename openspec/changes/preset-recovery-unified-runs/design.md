## 背景

### 当前状态

现有系统有两个独立的执行模型：

1. **Preset pipeline**：`run_pipeline()` 创建 `runs/{run_id}/` 目录，包含 step 产物、downloads、execution tree 等。失败后直接 set_status("failed")，无自愈能力。
2. **Agent chat session**：通过 `process_chat_message()` → `conversation_loop()` 执行，session 数据存储在 `session/{session_id}.json`，但浏览器下载写入 workspace 根目录的 `downloads/`，与 preset run 无统一隔离。

### 关键约束

- recovery session 需要 browser tools 诊断页面状态，不能简化为纯 LLM call
- agent session 和 preset run 的 ID 独立生成，但 `new_session()` 需确保 `runs/{session_id}/downloads/ 存在`
- agent run_id 加 `recovery_` 前缀，便于在 session 列表中识别

## 目标 / 非目标

**目标：**
- preset terminal failure 后自动启动 recovery session → agent 修复 yaml → 重跑
- 统一执行产物目录模型：`runs/{id}/` 同时服务 preset run 和 agent session
- 浏览器下载路径随执行上下文切换

**非目标：**
- 不修改 frontend pipelineStore 的交互逻辑（仅适配 _run.json 中 type 字段）
- 不改变 session/ 目录的对话消息存储格式
- 不修改 edit_pipeline 的 checkpoint 机制
- 不兼容旧的 workspace 级 downloads/ 路径（无 fallback）
- 不动 VersionManager（是未来 omni-api 的 VersionStore 候选，独立 change 重构）

## 关键决策

### 1. Recovery 走完整 process_chat_message + new_session 流程

**选择**：recovery 使用完整的 `service.new_session()` + `process_chat_message()` 流程，调用完整的 conversation_loop + tool executor + system prompt。

**原因**：recovery 需要 browser tools（snapshot/click 等）诊断页面状态来理解为什么 selector 失败。不能简化为纯 LLM call。

**代价**：每次 recovery 创建独立 session 记录（出现在 session 列表中）。用户能从 `recovery_` 前缀识别 recovery session，不影响功能。

### 2. run 重跑用新建 run_dir 而非原地覆盖

**选择**：每次 run_pipeline 调用（含 recovery 后的重跑）新建 run_dir，不复用同一 run_id。

**原因**：
- `run_pipeline` 内部的 step 目录清理逻辑已覆盖 per-step 覆盖重写
- 每次新建 run_dir 保留了失败尝试的历史记录，debug 时更有价值
- `cleanup_old_runs(max_runs=20)` 会自动清理最旧的

**替代方案**：复用 run_dir（原地覆盖）。被否决，因为需要额外的 reset 逻辑。

### 3. set_download_dir(name, run_id) 在每次执行开始时调用

**选择**：新增 `bridge.set_download_dir(name, run_id)`（替代旧 `set_download_pipeline(pipeline_name)`），在每次 run_pipeline 开始时调用。recovery 时重新绑定到新 run_id。

**原因**：确保浏览器下载始终写入当前活跃的执行目录。

### 4. _pipeline.log 不在 agent run 中产生

**选择**：`create_run("agent")` 不创建 _pipeline.log。`_setup_run_logger()` 只在 `run_pipeline()` 内部调用。

**原因**：agent 模式走 `process_chat_message()` → `conversation_loop()`，不经过 `_setup_run_logger()`。这个文件在 agent run 中永远为空。YAGNI——后续需要再加。

### 5. needs_recovery 不进 VALID_STATUSES

**选择**：`needs_recovery"` 不加入 `VALID_STATUSES` 集合。recovery 期间 run status 保持 "running"。

**原因**：`needs_recovery` 不是持久状态——它只存在于内存中的 `ctx.failure_context`。如果进程崩溃，`detect_crashed_runs()` 检测到 "running" 状态会标记为 "crashed"。不需要额外的状态。

### 6. detect_crashed_runs 用 type 字段判断

**选择**：`detect_crashed_runs()` 读取 `_run.json` 的 `type` 字段，只处理 `type == "preset"` 的 run。

**原因**：比检查 `_execution_tree.json` 文件存在更健壮。`_run.json` 是所有 run 的统一元数据，type 字段已经能准确区分 preset/agent。

### 7. Re-run 从 pipeline.yaml 唯一真相源读取

**选择**：recovery loop 中 re-run 时，从 `WORKSPACES_ROOT / pipeline_name / "pipeline.yaml"` 重新读取并 parse。不使用 `versions_dir / snapshot_*.pipeline.yaml`。

**原因**：agent 通过 `edit_pipeline` 工具修改的就是 `pipeline.yaml`（唯一真相源），checkpoint 备份在同目录（`{edit_id}.orig`）。snapshot 文件是历史存档，不会被 edit_pipeline 更新。

### 8. _resolve_input_files 无 fallback

**选择**：`downloads/` 前缀始终解析为 `run_dir / ref`，不保留旧 workspace 级 downloads/ 的 fallback。

**原因**：当前没有代码消费旧 workspace 级 downloads/ 路径。YAGNI——后续需要再加。

### 9. VersionManager 保留不动，仅删除 run_pipeline 内的自动版本快照调用

**选择**：`VersionManager` 类原样保留在 `workspace/version_manager.py` 中，仅删除 `run_pipeline()` 内对 `create_version()` 的调用（L437-459）。`versions/` 目录文件 I/O 路径不再被本次 change 的代码触发。

**原因**：
- VersionManager 是未来 omni-api `v1 auto_record` 的天然存储层，不适合在当前 change 中删除或重构
- `run_pipeline` 成功时自动存版本快照是冗余的（checkpoint 覆盖了回退需求）
- `api_restart_pipeline` 从 LATEST version 读取 → 改为从 `pipeline.yaml` 读取（不依赖 VersionManager）
- 泛化 VersionManager → VersionStore 留到未来独立 change（当前 meta schema 未稳定，猜不准接口）

**代价**：VersionManager 留在 codebase 里暂时无人调用（等待 omni-api change 激活）。

## 生产者 / 消费者模型

### 生产者

| 资源 | preset 生产者 | agent 生产者 |
|---|---|---|
| `runs/{id}/` + `_run.json` | `create_run("preset")` | `create_run("agent")`（由 new_session 触发） |
| `downloads/` | bridge (via `set_download_dir(name, run_id)`) | bridge（同） |
| `_pipeline.log` | `_setup_run_logger`（run_pipeline 内） | 不产生 |
| `_execution_tree.json` | `StepMachine` + `_write_execution_tree` | 不产生 |
| `{step_name}/` | per-step executor | 不产生 |
| `final/` | `fill_final` | 不产生 |

### 消费者

| 消费者 | 行为 |
|---|---|
| `cleanup_old_runs()` | 按时间排所有 run 子目录，不区分 type（正则匹配两种 ID 格式） |
| `detect_crashed_runs()` | 只处理 `_run.json.type == "preset"` 的 run |
| 前端 pipelineStore | 可选消费 `_run.json` 的 `type` 字段决定 UI 展示 |
| `_resolve_input_files()` | `downloads/` 前缀解析为 `run_dir / ref`，无 fallback |

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| recovery 无限循环 | 用户等待时间过长 | MAX_RECOVERY_ATTEMPTS=3 硬上限 |
| agent 改坏 pipeline | re-run 持续失败 | checkpoint 机制支持手动 revert |
| _run.json 的 type 字段前端未消费 | 无影响 | type 是可选字段 |
| failure_context 过大 | recovery prompt token 超限 | step_result 截断 10K 字符 |
| agent 在 recovery session 中做多余操作 | 浪费 budget | prompt 明确指示只用 edit_pipeline + pipeline_finish |

## 迁移计划

**上线步骤**：

1. 先实现统一 runs/ 目录模型（create_run 扩展、set_download_dir、regex 更新、detect_crashed_runs type 过滤）
2. 再实现 preset-recovery 循环（failure_context 收集、api_run recovery loop、_build_recovery_prompt）
3. 前端适配 type 字段（可选，可后续做）

**回滚**：failure_context 和 recovery 逻辑在 api_run 中，如果出现问题，可快速回滚到原行为。旧行为是直接 set_status("failed")。

**兼容**：`_resolve_input_files` 不再 fallback 到旧 workspace 级 downloads/，旧数据不会被新代码路径消费。

## 待确认问题

无。
