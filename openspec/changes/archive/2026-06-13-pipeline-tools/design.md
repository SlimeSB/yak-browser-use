## 背景

当前 `engine/_harness/tools.py` 中注册了 `edit_pipeline` 工具，Agent 通过它全量替换 pipeline YAML 文件。`tools/edit_pipeline.py` 实现了 checkpoint 备份 + difflib diff + WebSocket push 的安全机制。`tools/record_step.py` 支持边执行边追加单步。

问题：
- Agent 无法读取 pipeline 结构（无 `pipeline_load`、`pipeline_list`）
- Agent 只能全量替换 YAML，无法增量修改单步
- 全量替换消耗大量 token，且容易出错

## 目标 / 非目标

**目标：**
- 提供 6 个扁平 pipeline 操作工具，覆盖 CRUD 全流程
- 读操作（load/list）返回摘要而非全量，token 友好
- 写操作复用 `tools/edit_pipeline.py` 的 checkpoint + diff + WebSocket 机制
- 所有写操作经过 Pydantic 验证（StepYaml → PipelineYaml）

**非目标：**
- 不修改 `tools/edit_pipeline.py` 和 `tools/record_step.py`
- 不改变 `tools/` 目录下动态 import 的执行路径
- 不涉及前端 UI 变更

## 关键决策

### 1. 扁平工具 vs 嵌套工具

选择 6 个扁平工具而非一个 `pipeline` 工具 + sub-action 参数。原因：
- OpenAI function calling 对扁平工具的支持更好
- 每个工具职责单一，LLM 更容易正确调用
- 参数校验更精确（required 字段各不同）

### 2. pipeline_load 返回摘要而非全量

`pipeline_load` 返回步骤摘要（name、type、description、depends_on、browser_op_count），不暴露每个 browser_op 的细节和 input_schema/output_schema。原因：
- Agent 只需要了解结构来做修改决策，不需要完整 YAML
- 大幅减少 token 消耗
- 当前设计不提供全量 YAML 读取能力，Agent 通过摘要信息即可完成增量修改

### 3. 写操作复用 edit_pipeline() 而非 record_step()

`pipeline_update_step` / `add_step` / `remove_step` 内部调用 `tools/edit_pipeline.py` 的 `edit_pipeline()` 函数。原因：
- `edit_pipeline()` 已实现 checkpoint + diff + WebSocket 的完整安全链
- `record_step()` 的机制类似但语义不同（边执行边记录 vs 事后编辑）
- 复用而非重复实现，降低维护成本

### 4. pipeline_create 不走 edit_pipeline()

新建文件没有旧内容可 diff，直接 `yaml.dump` 写入，但同样推 WebSocket 事件（用空字符串作为 original）。

### 5. 路由放在 tool_executor 而非 executor

`pipeline_*` 工具不走 `execute_tool()` 的动态 import 路径，直接在 `_execute_single_tool_call()` 中通过 import + dispatch 调用。原因：
- `pipeline_tools.py` 是框架内置模块，不需要动态发现
- 避免在 `tools/` 目录下创建 6 个独立文件
- 路由逻辑集中在一处，易于维护

### 6. browser_ops 格式

LLM 传入的 `browser_ops` 已经是 YAML 单键格式（`{goto: url}`），与 `record_step.py` 一致，直接赋值即可，不需要调用 `ops_to_yaml()` 转换。

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| 删除 `edit_pipeline` 工具后，已有 Agent prompt 可能引用该工具名 | `edit_pipeline` 工具名从 schema 移除，LLM 不会再看到；`tools/edit_pipeline.py` 文件保留，内部函数仍可用 |
| 6 个工具增加 LLM 选择负担 | 每个工具有清晰的 description，LLM 可根据意图选择 |
| 并发写 pipeline 文件可能冲突 | 当前架构是单 Agent 顺序执行，不存在并发写场景 |

## 迁移计划

1. 修改 `tools.py` schema，删除 `EDIT_PIPELINE_TOOL`，新增 6 个工具定义
2. 新建 `pipeline_tools.py` 实现
3. 修改 `tool_executor.py` 路由
4. 更新测试
5. 无需数据迁移，`tools/edit_pipeline.py` 和 `tools/record_step.py` 保持不变

回滚：恢复 `tools.py` 和 `tool_executor.py` 的旧版本，删除 `pipeline_tools.py`。

## 待确认问题

- 无
