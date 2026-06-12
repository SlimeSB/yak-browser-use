## Why

当前流水线定义文件 `agent.md` 采用 Markdown + YAML frontmatter 的混合格式。解析和渲染这层混合格式需要：

- `compiler/parser.py`（433 行，其中 StepDef/AgentMD 约 50 行将提取至 models.py）— 逐行状态机解析
- `converter/render.py`（177 行）— 拼装字符串生成
- `converter/validate.py`（97 行）— 手动字段检查
- `compiler/generator.py` 中写回逻辑（~80 行）— 按行扫描替换

总计约 787 行代码专门服务于格式转换（不含 dataclass 定义），占编译器/转换器代码的近 50%。而文件的实质内容——流水线名、步骤定义、浏览器操作——本身就是类 YAML 结构（frontmatter 已是 YAML，browser 块是 YAML 缩进）。迁移到纯 YAML 格式 `pipeline.yaml` 可用 `yaml.safe_load()`/`yaml.dump()` 直接处理，消除全部逐行解析逻辑，代码量缩减 75%+。项目已依赖 PyYAML，无需新增解析库。

## What Changes

- **新增** `compiler/schema.py` — Pydantic v2 模型定义 pipeline.yaml 的 schema，提供 `to_step_def()` / `to_agent_md()` 转换方法
- **重写** `compiler/parser.py` — 用 `yaml.safe_load()` + Pydantic 校验替代逐行状态机，从 433 行缩减至约 80 行
- **重写** `converter/render.py` — 用 `yaml.dump()` 替代字符串拼装，从 177 行缩减至约 30 行
- **重写** `converter/validate.py` — 用 Pydantic 校验替代手动字段检查，从 97 行缩减至约 40 行
- **重写** `compiler/generator.py` 的写回逻辑 — `write_agent_md_learned()` 从逐行替换改为 load→修改→dump
- **BREAKING**：文件扩展名 `*.agent.md` → `*.pipeline.yaml`，不再兼容旧格式
- **改名**：全仓 `agent_md` / `agent.md` 引用 → `pipeline` / `pipeline.yaml`（API 路由、服务层、引擎参数、CLI 命令、docstring）
- **新增依赖**：`pydantic>=2.0` 加入 `pyproject.toml`
- **更新**：LLM 提示词模板中涉及 agent.md 格式的描述改为 pipeline.yaml

## Capabilities

### New Capabilities
- `pipeline-schema`: Pydantic 模型定义 pipeline.yaml 的完整 schema，含浏览器操作、工具步骤、Goal 步骤的字段规范
- `pipeline-yaml-parser`: 用 yaml.safe_load() + Pydantic 校验替代 Markdown+YAML 混合解析
- `pipeline-yaml-render`: 用 yaml.dump() 将步骤定义输出为纯 YAML
- `pipeline-learned-writeback`: Goal 步骤执行后将习得操作写回 YAML 的 load→修改→dump 流程

### Modified Capabilities
- `agent-md-parser`: 不再按行解析 Markdown 标题/引用块，改为标准 YAML 反序列化（能力名保持不变，行为变更）
- `agent-md-renderer`: 不再输出 Markdown 标记，改为标准 YAML 序列化
- `agent-md-validator`: 不再手动检查标题/缩进，改为 Pydantic schema 校验

## Impact

受影响文件（30+ 处引用变更）：

- `compiler/parser.py`：核心重写，导出函数 `parse_agent_md()` → `parse_pipeline()`。StepDef/AgentMD dataclass 提取至新增 `compiler/models.py`
- `compiler/models.py`：**新增**——从 `parser.py` 提取 StepDef/AgentMD dataclass，供 `schema.py` 和 `parser.py` 共用
- `compiler/schema.py`：**新增**——Pydantic v2 模型定义 pipeline.yaml 的 schema
- `compiler/__init__.py`：更新导出清单和 docstring
- `compiler/generator.py`：`write_agent_md_learned()` → `write_pipeline_learned()`，逻辑重写
- `compiler/graph.py`：变量名 `agent_md` → `pipeline`（2 处）
- `converter/render.py`：`render_steps_to_agent_md()` → `render_steps_to_pipeline()`，用 yaml.dump()
- `converter/validate.py`：`validate_agentmd()` → `validate_pipeline()`，用 Pydantic
- `converter/convert.py`：docstring 和输出格式变更
- `api/routes.py`：变量名 `agent_md_text` → `pipeline_text`，`_extract_pipeline_name()` 重写
- `api/service.py`：`compile_agent_md()` → `compile_pipeline()`，`compile_session_to_preset()` 重写
- `engine/runner_preset.py`：参数 `agent_md_path` → `pipeline_path`，快照文件名变更
- `engine/executor.py`：参数 `agent_md_path` → `pipeline_path`
- `engine/agent.py`：同上
- `engine/_lifecycle/tool_runner.py`：参数 `agent_md_path` → `pipeline_path`，`atomic_rename_ph()` 重写
- `workspace/version_manager.py`：参数 `pipe_agent_md` → `pipe_pipeline`，扩展名变更
- `cli/convert.py`、`cli/pipeline.py`、`cli/run.py`、`cli/tools.py`：docstring 和引用更新
- `prompts/`：LLM 提示词中描述输出格式的部分改为 YAML
- `pyproject.toml`：新增 `pydantic>=2.0` 依赖
- `tests/test_schema.py`：**新增**——Pydantic 模型单元测试

不受影响的模块：`StepDef` / `AgentMD` dataclass（保持为内部格式，仅移至 `models.py`）、`compiler/resolver.py`、`compiler/diff.py`、`engine/` 执行逻辑（仅参数名变更）。
