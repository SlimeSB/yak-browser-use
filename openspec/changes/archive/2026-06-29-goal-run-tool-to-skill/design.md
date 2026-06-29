## 背景

`goal_run` tool 的 handler（`_goal_run_handler`）只返回一段提示文字，不执行任何实际操作。`goal-execution` SKILL.md（tag:system）已在每次对话中自动注入几乎相同的指令，LLM 无需调用 tool 即可获得复杂目标执行的指引。tool 的存在只是多消耗一次 LLM round-trip。

同时，`record_step.py` 整文件是死代码——零生产调用者，registry 注释写着 `# record_step (removed — merged into pipeline_add_step)`。

## 目标 / 非目标

**目标：**
- 删除 `goal_run` tool 注册和 handler，将 goal-run 从 tool 降级为纯 skill
- 删除 `record_step.py` 死代码文件
- 删除 `include_goal_run` 参数和相关分支逻辑
- 更新 prompt 文件去掉 goal_run 引用
- 更新 spec 和文档
- 清理相关测试

**非目标：**
- 不修改 pipeline YAML 中 `op_type == "goal_run"` 的逻辑（YAML step 类型，非 LLM tool）
- 不修改 `goal-execution` skill 的核心指令内容（仅去掉"调 goal_run 后"等过时引用）
- 不修改 `goal_description` schema 字段

## 关键决策

1. **直接删除而非标记 deprecated**：`goal_run` tool 始终是 no-op（返回提示文字），无任何外部调用者依赖，直接删除不会造成破坏。

2. **保留 pipeline YAML 兼容性**：`pipeline_tools.py` 中 `op_type == "goal_run"` 是 YAML step 类型标识，与 LLM tool 无关。YAML 中用户可能已创建 goal_run 类型的 step，删除会破坏已有 pipeline。

3. **测试先行**：先删测试再删代码，确保删除路径清晰可验证。

## 风险 / 权衡

- **风险低**：`goal_run` 始终是 no-op，删除不影响任何终端用户功能
- **唯一注意点**：需确保 `goal-execution` SKILL.md 的 system tag 仍然有效注入，LLM 仍能获得复杂目标执行的指引
- **回滚简单**：恢复被删除的文件和代码行即可

## 迁移计划

1. 删除测试（E 步骤）
2. 删除代码（A 步骤）
3. 更新 prompt（B 步骤）
4. 更新 active spec（C 步骤）
5. 更新文档（D 步骤）
6. 运行 pytest + lint 验证

无需数据迁移，无需停机。

## 待确认问题

无。所有变更路径已在 plan 中明确。
