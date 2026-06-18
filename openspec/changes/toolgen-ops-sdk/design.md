## 背景

当前 `_PH-` 工具系统存在以下问题：

1. **流程断裂**：pipeline 遇到不存在的 `_PH-` 工具时返回 `TOOL_NOT_GENERATED` 错误直接终端失败（`runner_preset.py:779`），用户需手动触发 ph-tool-generation skill 生成代码后重新运行
2. **无约束生成**：LLM 生成的 Python 代码可任意调用 Playwright/CDP 底层接口、导入危险模块，质量不可控
3. **类型 bug**：`ToolRunner.load_and_call` 将 `CDPHelpers` 直接传给工具函数，但 `extract.py` 等调用的是 `ToolCDPHelpers` 的方法（`evaluate`/`wait` 签名不同），当前 `_PH-` 路径的浏览器工具实际不可用
4. **代码重复**：`extract.py`、`data.py`、`adapters.py` 各自实现了 `_save_output`、`_resolve_input_files`、`_load_records` 等辅助函数
5. **废弃文件**：`base.py`、`registry.py`、`schemas.py` 三个 1.0 时代遗留文件无任何引用
6. **无 schema 注册**：生成的工具 rename 后不会出现在 `get_all_tools()` 中

**约束条件**：
- `PlaywrightBridge` 本身不改动，ToolContext 是薄封装
- `execute_browser_op` 的 if-elif 链不改动
- `record_step`/`pipeline_*`/`todo` 等特殊工具不改动
- 旧 `ToolCDPHelpers` 路径保留兼容但不扩展
- `tools_dir` 沿用 `WorkspaceManager.tools_dir`（`userdata/workspaces/{pipeline_name}/tools/`）

## 目标 / 非目标

**目标：**
- 实现 `ToolContext` 统一 SDK，封装浏览器 ops + 数据 ops + CDP 逃逸口 + 安全机制
- 实现 inline 自动生成流程：捕获页面状态 → LLM 生成 → 安全检查 → 执行 → 重试
- 实现 schema 自动注册，生成的工具出现在 `get_all_tools()` 中
- 消除 `extract.py`/`data.py`/`adapters.py` 的重复代码
- 修复 `CDPHelpers`/`ToolCDPHelpers` 类型不匹配 bug
- 删除三个废弃文件
- 覆盖 preset 模式和 chat 模式

**非目标：**
- 不改 `PlaywrightBridge` 本身
- 不改 `execute_browser_op` 的 if-elif 链
- 不改 `record_step`/`pipeline_*`/`todo`/`todo_store` 等特殊工具
- 不实现正向库白名单（AST 只拒绝危险模块，不限制合法 import）
- 不处理 PyInstaller 打包兼容性（后续验证）

## 关键决策

### 决策 1：ToolContext 作为唯一 API 而非继承/混入

**选择**：新建独立的 `ToolContext` 类，通过组合持有 `PlaywrightBridge` 引用。

**原因**：
- `PlaywrightBridge` 是 834 行的大类，不应修改
- 组合优于继承：ToolContext 暴露的是受控子集，不是完整 bridge
- 便于注入安全机制（域名白名单、熔断器）而不侵入 bridge 代码

**备选方案**：
- 继承 `PlaywrightBridge` 并覆盖方法：会引入紧耦合，且 bridge 的方法签名不适合工具场景
- Mixin 模式：增加复杂度，且 Python 的 MRO 在异步场景下容易出错

### 决策 2：Inline 生成而非预生成

**选择**：pipeline 执行到 `_PH-` 步骤时，如果文件不存在则当场生成。

**原因**：
- 生成需要页面状态上下文（当前 DOM、URL），预生成时无法获取
- 减少用户操作步骤：不需要先运行生成命令再运行 pipeline
- 失败重试可以带错误上下文，提高生成质量

**备选方案**：
- 预生成（单独命令）：需要用户两步操作，且无法利用运行时页面状态
- 混合模式（预生成 + 运行时 fallback）：增加复杂度，收益有限

### 决策 3：函数名约定 = strip_ph_prefix 结果 + 连字符转下划线

**选择**：`_PH-crack-captcha` 生成的函数名为 `crack_captcha`（`strip_ph_prefix` 返回 `crack-captcha`，再将连字符替换为下划线以符合 Python 标识符规范）。

**原因**：
- 与现有 `ToolRunner.load_and_call` 的 `func_name=strip_ph_prefix(tool_name)` 一致
- 避免改动 `load_and_call` 的查找逻辑
- 语义清晰：去掉前缀就是实际功能名

### 决策 4：LLM 响应提取用正则匹配 markdown code block

**选择**：从 `llm_call` 返回的 `.completion`（注意：`create_pipeline_llm_call` 返回原始 LLM 响应，属性名是 `.completion` 而非 `.content`）中用正则提取第一个 ` ```python ... ``` ` 代码块，fallback 为整段 completion。

**原因**：
- LLM 倾向于在 markdown code block 中输出代码
- 正则提取比完整解析更轻量、容错性更好
- fallback 保证即使格式不标准也能尝试执行

### 决策 5：Chat 模式纳入 scope

**选择**：chat 模式下 `tool_executor.py` 的 `else` 分支遇到 `_PH-` 工具时同样触发 inline 生成。

**原因**：
- 共用 `_inline_generate_and_execute` 函数，增量成本小
- 避免 chat 模式成为二等公民
- 用户可能在 chat 中直接调用 pipeline 工具

## 风险 / 权衡

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 生成代码质量不稳定 | 重试消耗 token 和时间 | 3 次重试上限 + 错误上下文反馈 + few-shot 示例 |
| 生成代码执行副作用 | 可能修改页面状态 | ToolContext 封装浏览器操作，限制直接 CDP 访问 |
| 危险模块导入 | 任意代码执行 | AST 安全检查拒绝 10 类危险模块（含 shutil、socket）；已知盲区（`__import__`、`exec`、`eval`）在文档中注明 |
| 生成文件命名冲突 | 不同 pipeline 同名工具覆盖 | 按 `pipeline_name` 分子目录 |
| `importlib` 在 PyInstaller 下不可用 | Release 版本无法加载生成工具 | 后续验证，必要时改用 `exec()` + 文件读取 |
| mid-pipeline 生成的 schema 对当前 agent 不可见 | chat 模式首次无法调用新工具 | 影响有限（_PH- 是 pipeline 内部调用），prompt 中告知 LLM |
| 内联重试与 StepMachine 重试嵌套 | 最多 3N 次 LLM 调用 | 内联重试 3 次后返回失败，由 StepMachine 决定是否重试整个步骤 |

## 迁移计划

1. **Phase 1**：创建 `ToolContext`（`ops.py`）+ prompt 模板（`generate.md`）
2. **Phase 2**：修改 `runner_preset.py` 实现 inline 生成流程 + `llm_call` 传递链
3. **Phase 3**：修改 `tool_executor.py` 支持 chat 模式 inline 生成
4. **Phase 4**：修改 `tool_runner.py` 实现 schema 自动注册
5. **Phase 5**：修改 `tools.py` 支持动态注册表
6. **Phase 6**：迁移 `extract.py`/`data.py`/`adapters.py` 至 ToolContext
7. **Phase 7**：删除废弃文件，标注 deprecated
8. **Phase 8**：编写测试（`test_ops.py`、`test_ops_safety.py`、`test_ph_generation.py`）
9. **Phase 9**：运行现有测试套件验证兼容性

**回滚方案**：删除 `ops.py` 和 `generate.md`，还原各文件的修改（git revert）。生成的 `userdata/workspaces/{pipeline}/tools/` 目录可手动删除。

**兼容性安排**：
- 旧工具（extract/data/adapters）内部重构但外部行为不变
- `ToolCDPHelpers` 保留兼容但标注 deprecated
- `execute_tool` 的 `CAPABILITIES` 检查保留兼容
- `load_and_call` 保留旧路径作为 fallback

## 待确认问题

- PyInstaller 打包后 `importlib.util.spec_from_file_location` 是否可用（后续实测验证）
- `userdata/workspaces/` 在 PyInstaller 打包后的路径映射（后续实测验证）
- 是否需要限制单次生成的代码行数上限（建议 200 行，超出则拒绝）
