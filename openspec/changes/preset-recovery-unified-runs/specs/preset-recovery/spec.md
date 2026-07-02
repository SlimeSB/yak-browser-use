## ADDED Requirements

### Requirement: Preset pipeline terminal failure SHALL collect failure context
当 preset pipeline step 因不可重试错误（选择器错误、check 失败、JS 错误等）失败时，系统 MUST 收集失败上下文信息并存储在 RunContext.failure_context 中，包含失败 step 的 index、名称、定义、错误码、错误信息、执行结果、execution tree 及已完成步骤列表。step_result 按 10K 字符截断以防超大 payload。

#### Scenario: Step selector not found
- **WHEN** 一个 browser step 使用了不存在的 CSS 选择器
- **THEN** 系统 MUST 在 RunContext.failure_context 中记录 step_index、error_code="SELECTOR_NOT_FOUND"、step_result（截断后）和 execution_tree（来自 StepMachine 内存快照，不依赖文件）
- **AND** 系统 MUST NOT 将 run 标记为 "failed"，而是保持 "running" 状态

#### Scenario: Check assertion fails
- **WHEN** 一个 step 的程序化 check 断言不通过
- **THEN** 系统 MUST 在 failure_context 中记录 error_code="CHECK_FAILED" 和 check 的错误信息

#### Scenario: step_result exceeds size limit
- **WHEN** step_result JSON 序列化后超过 10,000 字符
- **THEN** 系统 MUST 截断为前 10,000 字符并追加 "...[truncated]" 后缀

### Requirement: api_run SHALL implement recovery loop
`api_run` endpoint MUST 在首次 run_pipeline 返回 failure_context 时进入 recovery 循环，循环次数不超过 MAX_RECOVERY_ATTEMPTS（默认 3 次）。每次循环新建独立 agent session，发送 recovery prompt，等待 agent 修复 yaml 后重跑 pipeline。re-run 时从 `WORKSPACES_ROOT / pipeline_name / "pipeline.yaml"` 重新读取并 parse（唯一真相源，agent 通过 edit_pipeline 修改后的文件）。

#### Scenario: First attempt fails, recovery succeeds on second
- **WHEN** 首次 run_pipeline 返回 failure_context
- **THEN** 系统 MUST 调用 service.new_session() 创建独立 recovery session
- **AND** 调用 process_chat_message() 将 build_recovery_prompt(failure_context) 发送给 agent
- **AND** agent 修复 pipeline.yaml 后，从 pipeline.yaml 重新解析 yaml 并新建 run_dir 从头重跑
- **AND** 重跑成功时退出循环返回 status="completed"

#### Scenario: All recovery attempts exhausted
- **WHEN** 连续 3 次 recovery 后 pipeline 仍然失败
- **THEN** 系统 MUST 将最终 run 标记为 "failed"
- **AND** MUST 不创建版本快照（VersionManager 已不参与此流程）
- **AND** 返回 status="failed"

#### Scenario: Agent calls pipeline_finish(status="failed")
- **WHEN** agent 判断无法修复并调用 pipeline_finish(status="failed", summary="...")
- **THEN** recovery loop 必须立即终止，不再尝试后续 recovery
- **AND** 最终 status 为 "failed"

### Requirement: Recovery prompt SHALL include complete failure context
`_build_recovery_prompt()` MUST 将 failure_context 格式化为包含以下信息的 user message。prompt 模板如下：

```
## Pipeline Recovery (Attempt {attempt}/{max_attempts})

The preset pipeline "{pipeline_name}" failed at step {step_index} "{step_name}".

### Error
- Code: {error_code}
- Message: {error_message}

### Failed Step Definition
```json
{step_def_json}
```

### Step Result (truncated)
{step_result_truncated}

### Execution Tree
```json
{execution_tree_json}
```

### Completed Steps
{completed_steps_list}

### Instructions
1. Use `pipeline_view` to see the full pipeline
2. Use browser tools (`snapshot`, `click`, etc.) to diagnose the current page state
3. Use `edit_pipeline` to fix the yaml
4. Call `pipeline_finish(status="completed")` when done, or `pipeline_finish(status="failed", summary="<reason>")` if you cannot fix it
```

#### Scenario: Build prompt for selector error
- **WHEN** failure_context 包含 error_code="SELECTOR_NOT_FOUND"
- **THEN** 生成的 prompt MUST 按上述模板格式化
- **AND** MUST 包含失败 step 的完整 browser_ops 定义（在 Failed Step Definition JSON 中）
- **AND** MUST 包含 recovery 指令（pipeline_view → browser tools → edit_pipeline → pipeline_finish）

### Requirement: Recovery session SHALL be independent and identifiable
每次 recovery MUST 通过 service.new_session() 创建全新独立 session，不污染现有 chat session 历史。recovery session 的 run_id 必须以 `recovery_` 前缀标识。

#### Scenario: User has existing chat messages
- **WHEN** 用户在 chat session 中有历史消息
- **THEN** recovery 创建的 session MUST 是独立的，不包含用户历史消息
- **AND** recovery session 出现在 session 列表中，run_id 以 `recovery_` 前缀开头
- **AND** 用户可从 session 列表中区分 recovery session 和普通 chat session

### Requirement: Agent MUST use pipeline_finish to exit recovery session
Recovery session 中 agent MUST 调用 pipeline_finish 工具来结束 session（通过 budget exhaust 机制退出 conversation loop）。

#### Scenario: Agent fixes pipeline successfully
- **WHEN** agent 调用 edit_pipeline 修复 yaml
- **THEN** agent MUST 调用 pipeline_finish(status="completed") 结束 session
- **AND** pipeline_finish 内部调用 budget.exhaust() → conversation_loop 自然退出

#### Scenario: Agent cannot fix pipeline
- **WHEN** agent 判断无法修复
- **THEN** agent MUST 调用 pipeline_finish(status="failed", summary="<原因>")
- **AND** recovery loop 终止，不再尝试

### Requirement: Browser download path SHALL be bound to current execution
`PlaywrightBridge` MUST 将浏览器下载路径绑定到当前执行的 run_id。preset run 开始时绑定到 preset run_id，recovery session 开始时绑定到 agent session run_id（recovery_前缀），re-run 时绑定到新的 run_id。

#### Scenario: Preset run starts
- **WHEN** api_run 首次调用 run_pipeline
- **THEN** 系统 MUST 调用 bridge.set_download_dir(name, ctx.run_id)
- **AND** 浏览器下载文件保存到 runs/{run_id}/downloads/

#### Scenario: Recovery session starts
- **WHEN** recovery loop 中新建 agent session
- **THEN** 系统 MUST 调用 bridge.set_download_dir(name, recovery_session_run_id)
- **AND** agent 运行期间的下载不再写入 preset run_id 的目录

#### Scenario: Re-run after recovery
- **WHEN** agent 修复 pipeline 后重新 run_pipeline
- **THEN** 系统 MUST 调用 bridge.set_download_dir(name, new_preset_run_id)
- **AND** re-run 期间的下载写入新 preset run 的目录

### Requirement: api_run SHALL use pipeline.yaml as single source of truth
`api_run` MUST 不再生成或使用 `snapshot_NNNN.pipeline.yaml`。直接 parse request.pipeline text，pipeline yaml 的唯一真相源是 `WORKSPACES_ROOT / pipeline_name / "pipeline.yaml"`（由前端/用户/agent 维护）。

#### Scenario: Successful run
- **WHEN** 用户发起 /api/run 且 pipeline 执行成功
- **THEN** MUST 不在 `versions_dir/` 下生成 `snapshot_NNNN.pipeline.yaml`
- **AND** MUST 不在 `wm.root/` 下拷贝 `pipeline.yaml`（唯一真相源由外部管理）

#### Scenario: Failed run
- **WHEN** 用户发起 /api/run 且 pipeline 执行失败
- **THEN** MUST 不在 `versions_dir/_errors/` 下保存 snapshot
- **AND** 错误信息通过 RunContext.errors 返回

#### Scenario: Re-run after recovery
- **WHEN** recovery loop 中重新运行 pipeline
- **THEN** MUST 从 `WORKSPACES_ROOT / pipeline_name / "pipeline.yaml"` 读取最新内容
- **AND** 重新 parse 后传入 run_pipeline

### Requirement: run_pipeline SHALL NOT auto-create version snapshots
`run_pipeline` MUST 不再调用 `VersionManager.create_version`。`pipeline_path` 参数移除后，run_pipeline 不再负责将 yaml 拷贝到 workspace 或 versions/ 目录。`VersionManager` 类本身保留等待未来 omni-api 复用。

#### Scenario: run_pipeline success no longer creates version
- **WHEN** run_pipeline 执行完成（成功或失败）
- **THEN** MUST 不调用 VersionManager.create_version
- **AND** MUST 不导入 VersionManager

#### Scenario: api_restart_pipeline uses pipeline.yaml
- **WHEN** 用户重启 pipeline
- **THEN** MUST 从 `WORKSPACES_ROOT / pipeline_name / "pipeline.yaml"` 读取 yaml
- **AND** MUST 不从 versions/ 目录加载 LATEST version

### Requirement: run_pipeline SHALL eliminate pipeline_path parameter
`run_pipeline()` 的 `pipeline_path` 参数 MUST 被移除。run_pipeline 不再负责拷贝 pipeline.yaml 到 workspace 或在 versions_dir 下保存 snapshot。

#### Scenario: No pipeline.yaml exists
- **WHEN** workspace 目录下尚无 pipeline.yaml
- **THEN** run_pipeline MUST 正常运行（不因缺少 pipeline.yaml 报错）
- **AND** 不创建任何版本快照

## MODIFIED Requirements

### Requirement: run_pipeline terminal failure path
当前 terminal failure 路径设 final_status="failed" 并 set_status(run_dir, "failed")。修改后：当 step 因不可重试错误失败时，系统 MUST 收集 failure_context、设 final_status="needs_recovery"、保持 run status 为 "running"、跳过 fill_final 和 create_version_snapshot。

#### Scenario: Terminal failure with retryable error
- **WHEN** step 失败且 machine.needs_retry() 返回 True
- **THEN** 行为不变：按 retry 配置重试

#### Scenario: Terminal failure with non-retryable error
- **WHEN** step 失败且 machine.needs_retry() 返回 False
- **THEN** 系统 MUST 收集 failure_context 到 ctx.failure_context
- **AND** final_status = "needs_recovery"
- **AND** MUST NOT 调用 wm.set_status(run_dir, "failed")
- **AND** MUST NOT 执行 fill_final 和 create_version 逻辑
- **AND** break 退出 while 循环
