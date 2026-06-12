## 1. 准备与基础改造

- [x] 1.1 将 `StepDef` 和 `AgentMD` dataclass 从 `compiler/parser.py` 提取到新文件 `compiler/models.py`，更新 `parser.py` 和 `compiler/__init__.py` 的导入路径，确保无循环导入
- [x] 1.2 在 `pyproject.toml` 中添加 `"pydantic>=2.0"` 依赖，运行 `uv lock` 更新锁文件
- [x] 1.3 确认 `compiler/schema.py` 文件不存在后，新建该文件，定义 `BrowserOp`、`StepYaml`、`PipelineYaml` 三个 Pydantic BaseModel（从 `models.py` 导入 `StepDef`、`AgentMD`）
- [x] 1.4 为 `StepYaml` 实现 `to_step_def() -> StepDef` 方法，包含 `step_type` 自动推断（browser_ops → browser、tool_name → tool、goal_description → goal、三字段均无默认 goal、同时存在报错）、`key` 从 `name` 自动生成、BrowserOp 单键映射到内部格式的转换逻辑
- [x] 1.5 为 `PipelineYaml` 实现 `to_agent_md() -> AgentMD` 方法，将 YAML 模型转换为内部 AgentMD 对象

## 2. 核心实现 — 解析/渲染/校验

- [x] 2.1 重写 `compiler/parser.py`：用 `yaml.safe_load()` + `PipelineYaml.model_validate()` 替代逐行状态机，新函数 `parse_pipeline(text, strict_mode=False) -> AgentMD`，保留 `StepDef` / `AgentMD` dataclass 不变（现已从 `models.py` 导入）
- [x] 2.2 重写 `converter/render.py`：用 `PipelineYaml` 构建 + `yaml.dump(..., default_flow_style=False, allow_unicode=True, sort_keys=False)` 替代字符串拼装，新函数 `render_steps_to_pipeline(steps, pipeline_name, description, required_params) -> str`
- [x] 2.3 重写 `converter/validate.py`：用 `PipelineYaml.model_validate()` 替代手动字段检查，新函数 `validate_pipeline(text) -> bool` 或返回校验结果
- [x] 2.4 更新 `compiler/__init__.py`：修改 docstring（agent.md → pipeline.yaml），更新导出函数名清单

## 3. 核心实现 — 生成器写回

- [x] 3.1 重写 `compiler/generator.py` 的 `write_agent_md_learned()` → `write_pipeline_learned(yaml_text, step_name, new_ops) -> str`：改用 `yaml.safe_load()` → 按 name 匹配步骤 → 修改 browser_ops → `yaml.dump(default_flow_style=False, allow_unicode=True, sort_keys=False)`
- [x] 3.2 在 `compiler/generator.py` 中移除旧的 `_format_op_line()` 辅助函数（YAML dump 自动处理格式）
- [x] 3.3 更新 `compiler/generator.py` 中其他引用 `agent.md` / `agent_md` 的变量名和 docstring

## 4. 全仓改名 — API 层

- [x] 4.1 更新 `api/routes.py`：变量名 `agent_md_text` → `pipeline_text`、`agent_md_path` → `pipeline_path`、`parse_agent_md` → `parse_pipeline` 等所有引用
- [x] 4.2 重写 `api/routes.py` 的 `_extract_pipeline_name()`：原逻辑解析 frontmatter 中的 `name:` 键和 `#` 标题，现改为 `yaml.safe_load(pipeline_text)["name"]`
- [x] 4.3 更新 `api/service.py`：函数名 `compile_agent_md()` → `compile_pipeline()`，参数 `agent_md_text` → `pipeline_text`，文件扩展名 `*.agent.md` → `*.pipeline.yaml`
- [x] 4.4 更新 `api/service.py` 的 `save_preset()`：写入 `.pipeline.yaml` 文件；`list_presets()`：匹配 `*.pipeline.yaml` glob
- [x] 4.5 重写 `api/service.py` 的 `compile_session_to_preset()`：当前逐行拼装 Markdown+YAML（`# title`、`## Step N:`、`browser:` 缩进块），改为用 `PipelineYaml` 构建 + `yaml.dump()` 输出纯 YAML（非简单改名，需重写生成逻辑）

## 5. 全仓改名 — 引擎层

- [x] 5.1 更新 `engine/runner_preset.py`：参数 `agent_md_path` → `pipeline_path`，快照文件名 `snapshot_*.agent.md` → `snapshot_*.pipeline.yaml`，workspace 副本 `agent.md` → `pipeline.yaml`
- [x] 5.2 更新 `engine/executor.py`：参数 `agent_md_path` → `pipeline_path`，所有内部引用
- [x] 5.3 更新 `engine/agent.py`：参数 `agent_md_path` → `pipeline_path`
- [x] 5.4 更新 `engine/_lifecycle/tool_runner.py`：参数 `agent_md_path` → `pipeline_path`，`atomic_rename_ph()` 中的 `content.replace(ph_name, real_name)` 改为 `yaml.safe_load()` → 查找/替换 → `yaml.dump()` 的结构化操作
- [x] 5.5 更新 `workspace/version_manager.py`：所有 `agent_md` 引用（参数名 `pipe_agent_md` 等）→ `pipeline`，文件扩展名变更
- [x] 5.6 检查 `engine/step_machine.py`、`engine/events.py` 等是否有 agent_md 引用并更新

## 6. 全仓改名 — CLI 和转换器

- [x] 6.1 更新 `cli/convert.py`：docstring 和输出引用改为 pipeline.yaml
- [x] 6.2 更新 `cli/pipeline.py`：docstring 和内部引用，`_apply_approval()` 中 `parse_agent_md` → `parse_pipeline`、`write_agent_md_learned` → `write_pipeline_learned`，`pipe_agent_md` → `pipe_pipeline`，`.agent.md` → `.pipeline.yaml`
- [x] 6.3 更新 `cli/run.py`：docstring 和引用，`_detect_agent_md()` → `_detect_pipeline()` 按 `.pipeline.yaml` 后缀检测
- [x] 6.4 更新 `cli/tools.py`：参数 `agent_md_path` → `pipeline_path`
- [x] 6.5 更新 `converter/convert.py`：docstring 和调用的函数名，输出文件名后缀
- [x] 6.6 更新 `converter/__init__.py`：导出名 `render_steps_to_agent_md` → `render_steps_to_pipeline`、`validate_agentmd` → `validate_pipeline`、`validate_agentmd_strict` → `validate_pipeline_strict`
- [x] 6.7 更新 `converter/validate.py` 的 `show_draft()`：当前 ANSI 高亮规则针对 Markdown（`#` cyan、`##` yellow、`>` dim），迁移到 YAML 后需改为 YAML 语法高亮（键名、字符串值、注释）或简化为裸文本预览
- [x] 6.8 核实 `compiler/graph.py` 中的 agent_md 引用并更新
- [x] 6.9 移除 `compiler/parser.py` 的 `parse_step_browser_ops()` 函数（迁移后 browser_ops 直接从 `StepDef.browser_ops` 字段获取，无需专门解析；其唯一的调用方 `cli/pipeline.py` 同步改为直接访问字段）

## 7. LLM 提示词更新

- [x] 7.1 搜索 `prompts/` 目录下所有引用 "agent.md" 或 "agent_md" 的文件
- [x] 7.2 将提示词中关于输出格式的描述从 "agent.md 格式" 改为 "pipeline.yaml 格式"，从 "Markdown+YAML" 改为 "纯 YAML"
- [x] 7.3 更新 `prompts/generate-handler.md` 中 "根据以下 agent.md 步骤定义" → "根据以下 pipeline.yaml 步骤定义"
- [x] 7.4 检查 `prompts/planner-plan.md`、`prompts/planner-expand.md` 中关于步骤格式的示例描述是否需要更新

## 8. 编译错误检查

- [x] 8.1 运行 Python 编译检查确认无语法错误：遍历所有 `.py` 文件执行 `python -m py_compile`
- [x] 8.2 确认所有导入路径正确，无 `ImportError`（特别注意 `compiler/__init__.py` 的导出变更和 `models.py` 的提取）

## 9. schema.py 单元测试

- [x] 9.1 新建 `tests/test_schema.py`，为 `PipelineYaml` 编写以下用例：
  - 最小合法文件（仅 name + steps）校验通过
  - 缺少 name 字段 → ValidationError
  - steps 为空列表 → ValidationError
  - browser_ops + goal_description 同时存在 → ValidationError
  - 三个类型字段均无 → step_type 默认 "goal"
- [x] 9.2 为 `StepYaml.to_step_def()` 编写用例：browser/tool/goal 各类型转换正确性、key 从 name 生成、BrowserOp 单键映射转换
- [x] 9.3 为 `PipelineYaml.to_agent_md()` 编写用例：往返信息不丢失

## 10. 验证与收尾

- [x] 10.1 运行现有测试套件 `pytest`，确认所有测试通过（engine 行为不应有变化）
- [x] 10.2 新建一个测试用 `pipeline.yaml` 文件，手动验证：`parse_pipeline()` → `to_runtime_dict()` → engine 能正确消费
- [x] 10.3 手动验证渲染往返一致性：`render_steps_to_pipeline()` 输出 → `parse_pipeline()` → `to_agent_md()` 信息不丢失
- [x] 10.4 手动验证写回流程：解析 pipeline.yaml → 调用 `write_pipeline_learned()` → 重新解析无错误
