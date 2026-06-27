## 背景

当前流水线定义文件 `*.agent.md` 是 Markdown + YAML 混合格式：

- **YAML frontmatter**（`---` 包裹）已用 `yaml.safe_load()` 解析
- **Markdown 标题**（`#`、`##`）作为流水线名和步骤名
- **Markdown 引用块**（`>`）作为描述
- **YAML 缩进块**（`browser:`、`depends_on:`）嵌入 Markdown 正文

解析器 `parser.py` 用逐行状态机处理这四种语法，共 433 行。渲染器 `render.py` 反向拼装字符串，177 行。校验器 `validate.py` 手动检查字段完整性，97 行。`generator.py` 的写回逻辑按行扫描、跳过、替换，约 80 行。格式转换层总计约 1059 行，占 compiler/converter 代码的近 60%。

然而文件的实质数据结构——流水线元数据 + 步骤列表 + 浏览器操作列表——天然就是 YAML 的映射/序列结构。**PyYAML 已是项目依赖**，迁移到纯 YAML 无需新增解析库。

### 约束

- `StepDef` / `AgentMD` dataclass 是 engine 消费的内部格式，**不可变**
- Engine 通过 `StepDef.to_runtime_dict()` 获得 dict，**接口不碰**
- 仓库内无存量 `*.agent.md` 文件，无数据迁移负担
- 项目语言为中文，但代码标识符和 API 路径使用英文

## 目标 / 非目标

**目标：**
- 消除 Markdown 混合格式的逐行解析/渲染代码，用标准 YAML 反序列化/序列化替换
- 用 Pydantic v2 定义 pipeline.yaml 的 schema，在解析时自动校验
- 统一文件扩展名为 `*.pipeline.yaml`
- 全仓变量名/函数名/参数名从 `agent_md` 改为 `pipeline`

**非目标：**
- 不改变 `StepDef` / `AgentMD` dataclass 结构
- 不改变 `to_runtime_dict()` 输出，engine 执行逻辑完全不受影响
- 不改变 DAG 构建（`graph.py`）、handler 解析（`resolver.py`）、diff 逻辑（`diff.py`）
- 不支持旧格式 `*.agent.md` 的回退读取

## 关键决策

### 1. 选择 Pydantic v2 而非手动校验

| 方案 | 优点 | 缺点 |
|------|------|------|
| Pydantic v2 | 类型安全、自动校验、IDE 友好、可从模型生成 JSON Schema | 新增依赖 |
| 手动 dict 检查 | 零依赖 | 代码多、易遗漏、无类型提示 |

选择 Pydantic：新增一个依赖的代价远小于维护手写校验逻辑的成本。项目已依赖多个外部库（browser-use、playwright、fastapi），增加 pydantic 风险可控。

### 2. 保持 StepDef / AgentMD 为内部格式，不直接暴露 Pydantic 模型

Pydantic 模型 (`PipelineYaml`, `StepYaml`) 定义 YAML 文件的 schema，提供 `to_step_def()` → `StepDef` 和 `to_agent_md()` → `AgentMD` 转换。这隔离了文件格式和内部表示：

```
pipeline.yaml ──[yaml.safe_load]──→ dict ──[Pydantic validate]──→ PipelineYaml
                                                                      │
                                                        to_agent_md() │
                                                                      ▼
                                                                 AgentMD
                                                                      │
                                                              to_runtime_dict()
                                                                      ▼
                                                              list[dict] → engine
```

这样做的好处是：如果未来 StepDef 结构需要调整，只需改 `to_step_def()` 映射逻辑，不影响 YAML schema。

### 3. YAML 格式设计

```yaml
# 顶层：流水线元数据 + 步骤序列
name: "my_pipeline"                  # 必填
description: "可选描述"              # 可选
required_params: ["param1"]          # 可选
system_prompt: "..."                 # 可选
url_aliases:                         # 可选，dict[str, str]
  prod: "https://prod.example.com"
constants:                           # 可选，dict[str, Any]，预植入 shared_store 供 {key} 模板
  api_urls:
    primary: "https://api.ex.com"
    secondary: "https://api2.ex.com"
  email: "user@example.com"
steps:                              # 必填，非空列表
  - name: "打开首页"                 # 必填
    description: >-                  # 可选，多行用 YAML block scalar
      多行描述第一行
      多行描述第二行
    depends_on: ["前置步骤名"]        # 可选，list[str]
    # 三种步骤类型，用互斥字段区分：
    browser_ops:                    # → step_type="browser"
      - goto: "https://..."
      - click: "#selector"
      - fill: {selector: "#x", value: "text"}
    # 或
    tool_name: "extract_table"      # → step_type="tool"
    # 或
    goal_description: "分析数据"    # → step_type="goal"，三个类型字段均无则默认 goal
    # 公共字段：
    input_ref: {key: value}          # 或字符串形式: input_ref: "raw_string"
    output_ref: [file.csv]
    input_schema: {param: type}
    output_schema: {param: type}
    params: {max_retries: 3}
    system_prompt: "步骤级提示"
```

### 4. 文件扩展名选择

选择 `*.pipeline.yaml` 而非 `*.agent.yaml` 或 `*.yaml`：
- 与文件名语义一致（表示一个流水线定义，不是通用 agent）
- 保持 `*.pipeline.*` 前缀可区分于普通 YAML 配置文件
- 与当前 `*.agent.md` 命名模式保持一致

### 5. Converter（NL → 流水线）的 LLM 输出格式

`converter/convert.py` 通过 LLM 从自然语言文档提取步骤计划，LLM 当前输出 JSON，然后 `render.py` 把它拼成 agent.md。迁移后 LLM 仍输出 JSON plan，但渲染阶段改为 `yaml.dump()` 产出 `pipeline.yaml`。LLM 提示词中关于输出格式的描述从 "生成 agent.md" 改为 "生成 pipeline.yaml"。

### 6. BrowserOp 转换策略

YAML 中 BrowserOp 的格式为单键映射（键即操作类型）：

```yaml
browser_ops:
  - goto: "https://..."
  - click: "#selector"
  - fill: {selector: "#x", value: "text"}
```

Pydantic 模型 `BrowserOp` 使用 `dict` pass-through 接收任意键，不在 Pydantic 层做类型校验。原因：YAML 格式中 discriminator（区分字段）是**可变的键名**（`goto`、`click`、`fill` 等），Pydantic discriminated union 需要固定字段名，强制适配的复杂度与收益不匹配。

格式转换在 `StepYaml.to_step_def()` 中完成：遍历每个 dict 的唯一键值对 → 键为 `type`、值为参数展开：

| YAML 输入 | 转换后内部格式 |
|-----------|---------------|
| `{goto: "url"}` | `{type: "goto", value: "url"}` |
| `{fill: {selector, value}}` | `{type: "fill", selector, value}` |
| `{scroll: 300}` | `{type: "scroll", value: 300}` |
| 未知键 + 标量 | `{type: key, value: val}` |
| 未知键 + dict | `{type: key, ...dict}` |

未知键名原样通过，保持对新操作类型的开放性。

### 7. 参数注入策略（`{{param}}` 占位符）

采用**结构化替换**而非文本替换：

```
yaml_text ──[yaml.safe_load]──→ dict ──[递归替换 {{key}}]──→ dict ──[Pydantic validate]──→ PipelineYaml
```

原因：在 YAML 文本层做 `str.replace` 存在安全风险——参数值可能包含 `:`、`"`、`#`、`\n` 等 YAML 特殊字符，会破坏文档结构导致 `yaml.safe_load()` 解析失败。已有 `yaml.safe_load()` 解析能力，没有理由继续在文本层操作。

实现：递归遍历 dict/list 结构，对每个 `str` 值用 `str.replace` 替换 `{{key}}`，参数不存在的占位符保留原样 + 记录 WARNING。

### 8. yaml.dump() 输出规范

所有 `yaml.dump()` 调用统一使用以下参数确保输出一致性和可读性：

```python
yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

- `default_flow_style=False`：全部使用 block style，避免 inline dict 造成不一致
- `allow_unicode=True`：保留中文和特殊字符，不转义
- `sort_keys=False`：保持键的插入顺序（`name` 在 `steps` 之前）

## 风险 / 权衡

| 风险 | 级别 | 缓解 |
|------|------|------|
| Pydantic v2 学习曲线 | 低 | 模型定义简单（3-4 个类），团队可参考现有 schema.py |
| YAML 手写易错（缩进敏感） | 中 | Pydantic 校验在加载时立即报错，错误信息包含字段路径 |
| 多行字符串格式需适应 | 低 | YAML 的 `|` 和 `>` 与 Markdown 写法类似 |
| LLM 输出 YAML 稳定性 | 低 | Converter 的渲染由代码完成（yaml.dump），LLM 仍输出 JSON，不直接生成 YAML |

## 迁移计划

1. **Phase 0：更新依赖** — `pyproject.toml` 加 `pydantic>=2.0`（必须先于任何使用 Pydantic 的代码）
2. **Phase 1：提取类型定义 + 新增 schema.py** — 将 StepDef/AgentMD 从 parser.py 移至 `compiler/models.py`，解决后续 schema.py ↔ parser.py 的循环导入；然后定义 Pydantic 模型，独立于现有代码，可单独测试
3. **Phase 2：重写 parser.py / render.py / validate.py** — 替换为 YAML 版本，保持导出函数签名兼容（仅改名）
4. **Phase 3：修改 generator.py 写回逻辑** — load→修改→dump 替代逐行替换
5. **Phase 4：改名蔓延处理** — 全仓 `agent_md` → `pipeline` 变量名、函数名、参数名
6. **Phase 5：更新 LLM 提示词** — prompts/ 中引用 agent.md 的描述改为 pipeline.yaml
7. **Phase 6：schema.py 单元测试** — Pydantic 模型校验、转换、往返
8. **Phase 7：运行集成测试** — 现有测试套件验证 engine 行为不变

回滚：git revert 即可。内部 StepDef/AgentMD 未变，engine 接口未变，回滚无副作用。

## 待确认问题

- 无。方案已在前期讨论中确认（格式：YAML，扩展名：pipeline.yaml，校验：Pydantic，兼容：不需要）。
