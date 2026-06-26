## 背景

### 当前状态

`pipeline.yaml` 的读写操作散落在 7 个文件中，没有统一的文档抽象。写入路径 5 条，读取路径 3 条，格式转换逻辑分散在 3 处。

```
                        ┌──────────────────────────┐
      写入路径           │      pipeline.yaml        │         读取路径
                        │                          │
pipeline_tools.py ──────┤  Pydantic + exclude_      ├────── parser.py
(Pydantic CRUD)         │  defaults=True            │       (yaml.load → validate → PipelineDef)
                        │                          │
record_step.py ─────────┤  raw dict + yaml.dump     ├────── pipeline_tools.py
(绕过 Pydantic)          │                          │       (_load_pipeline_yaml)
                        │                          │
generator.py ───────────┤  raw dict + yaml.dump     ├────── routes.py / service.py
(write_pipeline_learned)│                          │       (yaml.load 直接取字段)
                        │                          │
edit_pipeline.py ───────┤  文本覆盖 (不验证)         │
                        │                          │
routes.py ──────────────┤  Pydantic validate         │
(api_save_pipeline)     │                          │
                        └──────────────────────────┘

                        ┌──────────────────────────┐
      格式转换           │                          │
                        │                          │
schema.py ──────────────┤  _convert_browser_op()    │   {goto: url} ↔ {type: goto, value: url}
                        │  ops_to_yaml()            │
                        │                          │
record_step.py ─────────┤  手猜格式 (:84-96)        │   与 ops_to_yaml 不一致
                        │                          │
generator.py ───────────┤  调 ops_to_yaml             │
                        └──────────────────────────┘
```

具体问题：

1. **5 条写入路径**各自决定是否 validate、是否 checkpoint、是否 push event。`record_step.py` 绕过 Pydantic，`edit_pipeline.py` 不做任何验证。
2. **`_dump_pipeline_yaml()` 使用 `exclude_defaults=True`**（`pipeline_tools.py:52`），导致 `description=""`, `depends_on=[]`, `params={}` 等默认值字段在写回时被丢弃。
3. **`record_step.py:84-96`** 中 `browser_ops` 的格式构建逻辑是手写的，与 `ops_to_yaml()` 不一致。
4. **`browser_ops` 字段类型为 `list[dict] | None`**（`schema.py:22`），无任何结构约束。
5. **`PipelineYaml/StepYaml`（Pydantic）与 `PipelineDef/StepDef`（dataclass）** 之间通过手写 40 行 `to_step_def()` 转换，包含格式转换 + 类型收窄 + 派生字段计算。

### 执行器依赖分析

`runner_preset.py` 是 pipeline 的执行引擎。它消费 `StepDef.to_runtime_dict()` 产出的 step dict，其中 `browser_ops` 必须是**内部格式** `{type: "goto", value: "url"}`。证据在：

- `runner_preset.py:82-86`（`_resolve_step_urls`）：`op.get("type") == "goto"` — 直接读 type 字段
- `runner_preset.py:338`（`execute_browser_step`）：传入 step_def dict，executor 内部也用 `op["type"]`

当前内部格式由 `to_step_def()` 中的 `_convert_browser_op()` 保证。重构后必须继续保证 runner 拿到内部格式，无论转换在哪里发生。

### 约束

- 不修改执行器（`runner_preset.py`, `step_machine.py`, `executor.py`）——它们必须继续收到内部格式 browser_ops
- 不修改 `graph.py`、`resolver.py`——同上
- YAML 文件格式不变（`{goto: "url"}` 作为存储格式）——已有数据兼容
- 不删除任何文件——`pipeline_tools.py` 的删除留给 Hermes Phase 2

## 目标 / 非目标

**目标：**
- 提供单一 `PipelineStore` 类，统一所有 pipeline.yaml 的读、写、验证操作
- 格式转换集中在 PipelineStore 边界：**load 时 YAML 格式 → 内部格式，save 时内部格式 → YAML 格式**
- `PipelineYaml.browser_ops` 在模型中始终持有**内部格式**，`to_step_def()` 不再需要转换
- 消除 `exclude_defaults=True`，改为 `_strip_defaults()` 后处理
- `record_step.py` 不再手搓 raw dict，改用 PipelineStore
- `generator.py:write_pipeline_learned` 改用 PipelineStore
- API 签名不变，已有数据兼容

**非目标：**
- 不改变 `PipelineDef` / `StepDef` dataclass 模型（执行器依赖它们）
- 不删除任何文件
- 不改变 YAML 文件的存储格式（`{goto: "url"}` 保持）
- 不处理 Hermes 集成

## 关键决策

### 决策 1：PipelineStore 放在 `compiler/` 而非 `workspace/`

**选择**：`compiler/pipeline_store.py`

**原因**：PipelineStore 的职责是解析 + 验证 + 格式转换——编译器语义。它直接依赖 `schema.py` 和 `models.py`，都在 compiler/ 下。

**备选方案**：`workspace/` —— 被拒绝，workspace/ 不该知道 YAML 格式细节。

---

### 决策 2：PipelineStore 在边界做格式转换

**选择**：load 时 YAML 格式 → 内部格式，save 时内部格式 → YAML 格式。`PipelineYaml.browser_ops` 始终存内部格式。

**完整流转路径**：

```
存储 (文件)                       模型 (PipelineYaml)                 运行时 (StepDef.to_runtime_dict)
┌──────────────────┐              ┌────────────────────┐              ┌──────────────────────┐
│ browser_ops:     │  load()      │ .browser_ops = [   │  to_step_def│ step_dict["browser_  │
│   - goto: "url"  │ ──────────▶  │   {type: "goto",   │ ──────────▶ │ ops"] = [            │
│   - fill:         │  _from_yaml  │    value: "url"},  │  (纯映射,   │   {type: "goto",     │
│       selector:#q │  _ops()     │   {type: "fill",   │  不再转换)  │    value: "url"},    │
│       value:text   │              │    selector: "#q", │              │   ...                │
│                   │              │    value: "text"}  │              │ ]                    │
└──────────────────┘              │ ]                  │              │                      │
                                  └────────────────────┘              └──────────┬───────────┘
                                       │                                       │
                                       │  save()                               ▼
                                       │  _to_yaml_ops()              runner_preset.py
                                       ▼  + yaml.dump                op.get("type") ✅
                                  ┌──────────────────┐
                                  │ browser_ops:      │
                                  │   - goto: "url"   │
                                  │   - fill:          │
                                  │       selector:#q │
                                  │       value:text   │
                                  └──────────────────┘
```

**为什么这样选**：

- `runner_preset.py:82-86` 用 `op.get("type")` 读 browser_ops——它必须永远是内部格式。把转换放在存储/模型的边界上（而不是在 `to_step_def` 里），让模型本身就是"真相之源"。
- `to_step_def()` 原来的 40 行中有 12 行是格式转换逻辑——消除后只剩字段映射和派生字段计算。
- 所有写入路径统一走 `PipelineStore.save()`，自动获得格式转换——不再需要每个调用方自己调 `ops_to_yaml()`。

**备选方案**：PipelineYaml 存 YAML 格式，`to_step_def()` 做转换 —— 被拒绝，因为这让模型内部格式依赖转换层，且 runner 只在经过 `to_step_def` 后才能拿到正确格式，中间态不安全。

---

### 决策 3：不用 Pydantic 的 `exclude_defaults`，用自定义 `_strip_defaults()`

**选择**：`_dump` 时对 `model_dump()` 结果递归去除 `None`, `""`, `[]`, `{}`

**原因**：
- `exclude_defaults=True` 会丢弃用户手写的空值字段，破坏 round-trip
- `exclude_unset=True` 在 `model_dump()` → `model_validate()` 循环中状态丢失
- 自定义函数确定性行为，不依赖 Pydantic 内部状态

```python
def _strip_defaults(obj):
    if isinstance(obj, dict):
        return {k: v for k, v in
                ((k, _strip_defaults(v)) for k, v in obj.items())
                if v is not None and v != "" and v != [] and v != {}}
    if isinstance(obj, list):
        return [_strip_defaults(v) for v in obj]
    return obj
```

---

### 决策 4：PipelineStore 只做纯数据层

**选择**：PipelineStore 负责 YAML 读写的纯数据操作，checkpoint 和事件推送留在上层（pipeline_tools.py）

**原因**：checkpoint 依赖 `api.state.engine_state`，引入会导致依赖方向混乱。

**PipelineStore 接口**：

```
PipelineStore
├── load(pipeline_name) → PipelineYaml          # 读文件 → 内部格式 → Pydantic 模型
├── save(pipeline_name, doc) → str             # Pydantic 模型 → YAML 格式 → 写文件
├── validate(yaml_text) → PipelineYaml         # 验证 + 格式转换
├── from_yaml(yaml_text) → PipelineYaml        # 同 validate
├── to_yaml(doc) → str                         # 序列化（不写盘）
├── load_meta(pipeline_name) → PipelineMeta    # 轻量读取（不验证 steps，不做格式转换）
│
├── update_step(doc, name, updates) → PipelineYaml
├── add_step(doc, step, after=None) → PipelineYaml
├── remove_step(doc, name) → PipelineYaml
│
├── ops_to_yaml(ops) → list[dict]              # 公开工具：内部格式 → YAML 格式
└── _from_yaml_ops(ops) → list[dict]           # 私有：YAML 格式 → 内部格式
```

其中 `PipelineMeta` 是轻量 dataclass：
```python
@dataclass
class PipelineMeta:
    name: str
    description: str
    step_count: int
```

---

### 决策 5：公共接口接受 YAML 格式 browser_ops

**选择**：`add_step()` 和 `update_step()` 中 browser_ops 参数接受 YAML 格式（与文件中一致的 `{goto: "url"}`）。PipelineStore 内部自动转成内部格式存储。

**原因**：
- `record_step.py`（LLM 路径）自然产生 YAML 格式——不增加调用方负担
- 外部调用方给的格式与 YAML 文件内容一致，认知简单
- 需要给内部格式的调用方（`generator.py:write_pipeline_learned`）提供 `ops_to_yaml()` 公开工具

**browser_ops 输入格式对照**：

| 调用方 | 产生的格式 | 如何适配 |
|--------|-----------|---------|
| `record_step.py` | YAML 格式 `{goto: "url"}` | 直接传，无需转换 |
| `pipeline_compile` | YAML 格式 `{goto: "url"}` | 直接传 |
| `write_pipeline_learned` | 内部格式 `{type: "goto", ...}` | 调 `store.ops_to_yaml()` 转后传入 |
| `pipeline_tools.py` CRUD | 任意（透传） | 统一要求 YAML 格式 |

---

### 决策 6：保持双层模型，但对齐类型

**选择**：`StepYaml`（Pydantic，YAML 边界验证）+ `StepDef`（dataclass，运行时），保持分离。但 `to_step_def()` 不再含格式转换——只剩字段映射 + 派生字段（`step_type`, `is_goal`）。

**原因**：执行器路径 13 个文件引用 StepDef，将格式转换提升到 PipelineStore 边界后，`to_step_def()` 从 40 行缩到 ~25 行纯映射。

---

### 决策 7：pipeline_list 使用 load_meta() 轻量读取

**选择**：`pipeline_list` 用 `PipelineStore.load_meta()` 只读 `name`/`description`/`step_count`，不做 Pydantic 验证、不做格式转换。

**原因**：列表可能几十个 pipeline，对每个做全量验证 + ops 转换意义不大。`load_meta()` 只做 `yaml.safe_load` + dict 访问。

---

### 决策 8：pipeline_compile 纳入重构范围

`pipeline_compile()`（`pipeline_tools.py:371-460`）在生成 `browser_ops` dict 时手写 `[{op_type: value}]`（YAML 格式）。纳入重构：改为调 `PipelineStore.ops_to_yaml()` 生成，确保格式一致。

---

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| PipelineYaml 内部存内部格式，`model_dump()` 直接输出会写坏文件 | 高 | 所有写入路径必须走 `PipelineStore.save()` 或 `PipelineStore.to_yaml()`——它们保证格式转换 |
| `_strip_defaults()` 误删有意义的空值 | 低 | YAML 重读时 Pydantic 默认值填补，语义等价 |
| 格式转换从 `to_step_def()` 移除 | 中 | runner 路径不变——`to_step_def()` 现在从 `PipelineYaml.browser_ops`（已是内部格式）直传 |
| `to_step_def()` 改名/修改引所有 13 个调用方 | 低 | 不改函数签名，只改内部实现——不需改调用方 |

## 迁移计划

1. 新增 `compiler/pipeline_store.py`，不修改任何现有文件
2. 运行 `pytest backend/tests/` 确认无回归
3. 逐个修改消费端（pipeline_tools.py → record_step.py → generator.py），每步运行测试
4. 最后清理 schema.py 中已不再对外暴露的 `_convert_browser_op` / `ops_to_yaml`

## 待确认问题

1. **`write_pipeline_learned` 的调用频率**：如极低，走 `store.ops_to_yaml()` 即可；如高频，可缓存转换结果
2. **新版 PipelineStore 需要 async 吗？** 当前所有 YAML 读写是同步小文件 I/O（<1MB），不需要。`async` 来自 WebSocket 事件，不走文件 I/O
