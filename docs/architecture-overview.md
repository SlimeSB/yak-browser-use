# YAK Browser-Use 架构概览

> 最后更新: 2026-06-15

## 项目定位

yak-browser-use（简称 ybu）是一个面向非技术用户的浏览器自动化框架。核心交互模型是 **Agent 在 conversation_loop 中跟用户聊天同时操作浏览器**——用户在 chat 中输入自然语言指令，Agent 通过 LLM 驱动浏览器操作完成任务。

Pipelines 是 Agent 工作的副产品（预设），可保存下来供后续回放使用。

---

## 目录结构

```
yak-browser-use/
├── __main__.py              # CLI 入口 (run/serve/chrome/convert/debug...)
├── pyproject.toml            # 项目配置 + 依赖
│
├── api/                      # FastAPI REST + WebSocket 接口层
│   ├── routes.py             # 路由注册 (chat/run/chrome/pipeline/workspace)
│   ├── service.py            # 业务逻辑 (session管理/chat处理/preset管理)
│   ├── state.py              # 全局引擎状态 engine_state
│   └── errors.py             # API 错误类型
│
├── engine/                   # 核心执行引擎 ★
│   ├── agent.py              # Agent 入口 (chat 模式入口 + 流式 LLM call)
│   ├── runner.py             # Chat 模式 runner (轻量包装)
│   ├── runner_preset.py      # Preset 模式 runner (完整 pipeline 编排器)
│   ├── executor.py           # 核心执行器 (browser/tool/goal 三层)
│   ├── scratchpad.py         # 内存数据缓存 (重数据不进 LLM context)
│   ├── delivery.py           # 交付报告生成
│   ├── state.py              # RunContext 数据类
│   ├── events.py             # EventSink 事件管道
│   ├── step_machine.py       # StepMachine (pipeline DAG 遍历)
│   ├── planner.py            # 运行时恢复规划器
│   │
│   ├── _harness/             # Conversation loop 基础设施 ★
│   │   ├── conversation_loop.py    # 核心对话循环 (chat + preset 共用)
│   │   ├── tools.py                # 工具注册 (browser_*/goal_run/record_step/pipeline_*/todo)
│   │   ├── tool_executor.py        # 顺序工具调用执行器
│   │   ├── pipeline_tools.py       # pipeline_load/list/update/add/remove/create 实现
│   │   ├── pipeline_task_adapter.py # StepDef → TaskDescriptor (仅 preset 模式用)
│   │   ├── iteration_budget.py     # LLM 轮次预算控制
│   │   ├── tool_guardrails.py      # 工具调用护栏
│   │   ├── turn_context.py         # 每轮次上下文 (重试计数器等)
│   │   ├── error_classifier.py     # API 错误分类
│   │   └── retry_utils.py          # 重试工具函数
│   │
│   └── _lifecycle/           # Pipeline 生命周期管理
│       ├── compensation.py   # 补偿/撤销逻辑
│       ├── guardian.py       # 审核门控
│       ├── tool_runner.py    # _PH- 工具生命周期
│       └── fallback.py       # 页面状态评估
│
├── cdp/                      # Chrome DevTools Protocol 层
│   ├── helpers.py            # CDPHelpers (浏览器操作高级封装)
│   ├── daemon.py             # CDP Daemon 管理
│   ├── discover.py           # Chrome 发现/连接
│   └── launcher.py           # Chrome 启动
│
├── compiler/                 # Pipeline 编译
│   ├── models.py             # PipelineDef / StepDef 数据类
│   ├── schema.py             # PipelineYaml / StepYaml Pydantic 模型
│   ├── parser.py             # YAML 解析器
│   └── resolver.py           # 依赖解析器
│
├── tools/                    # 自定义工具脚本
│   ├── record_step.py        # record_step 工具 (LLM 调用记录步骤到 pipeline)
│   ├── todo.py / todo_store.py   # todo 任务管理工具
│   ├── edit_pipeline.py      # Pipeline 编辑工具
│   └── extract.py / data.py  # 数据处理工具
│
├── prompts/                  # Prompt 模板 (Markdown)
│   ├── chat/system.md        # Chat 模式系统提示
│   ├── preset/system.md      # Preset 模式系统提示
│   ├── guidance/             # 策略/恢复指导
│   ├── guardrails/           # 护栏提示
│   └── skill/                # 技能提示 (goal-execution 等)
│
├── params/                   # 持久化参数管理
│   ├── manager.py            # ParamManager (替代旧的 credentials 系统)
│
├── workspace/                # 工作区管理
│   ├── manager.py            # WorkspaceManager
│   ├── version_manager.py    # 版本快照管理
│   └── path_guard.py         # 路径安全校验
│
├── cli/                      # CLI 命令实现
│   ├── run.py / serve.py / chrome.py / ...
│
├── utils/                    # 工具函数
│   ├── browser.py            # LLM 创建 / provider 配置
│   ├── tool_cdp.py           # 受限 CDP 封装 (供工具脚本使用)
│   └── logging.py            # 日志配置
│
├── assets/                   # 静态资源
│   └── simplify-dom.js       # DOM 简化脚本 (元素编号/摘要)
│
└── openspec/                 # 设计文档 & 规格
```

---

## 两层架构

系统由 **两组独立的引擎** 构成：

### 上层：编排引擎

LLM（外部模型）做决策，编排层组装上下文和管理工具执行。

```
LLM (deepseek-chat / gpt-4o 等)
     │
     │ LLM 调用 (包含系统提示 + 对话历史 + 工具注册)
     ▼
conversation_loop ──→ tool_executor ──→ executor core (browser/tool/goal)
     │                     │
     │                     └── scratchpad (重数据缓存)
     │
     └── 返回 LLM 响应/工具结果
```

核心概念：
- **重数据不进 messages**：浏览器 HTML、截图、元素列表等大块数据通过 `scratchpad` 内存缓存，LLM 看到的只是摘要
- **编排层负责上下文组装**：每轮只保留必要的上下文，不累加全部工具输出到 messages
- **LLM 只做决策**：调用哪个工具、传什么参数，然后编排层帮它执行

### 下层：CDP 浏览器控制

```
executor.py                  # 逻辑层——解析操作类型、构造参数
     │
     ▼
cdp/helpers.py (CDPHelpers) # 协议层——CDP WebSocket 调用
     │
     ▼
cdp_daemon (CDPDaemon)      # 传输层——WS ↔ Chrome DevTools
     │
     ▼
Chrome Browser
```

---

## 两种运行模式

### 模式一：Chat 模式（交互式）

用户在前端发送自然语言消息 → Agent 自主操作浏览器 → 实时同步给用户看。

**调用链：**

```
POST /api/chat { message: "打开百度搜咖啡" }
  └→ service.process_chat_message()
       └→ run_conversation_loop()
            ├→ 加载 prompts/chat/system.md
            ├→ 注入 tool_strategy 指导
            ├→ LLM 调用 (带 browser_*/goal_run/record_step/todo 工具)
            ├→ LLM 返回工具调用 → tool_executor._execute_single_tool_call()
            │     ├→ browser_goto → execute_browser_op("goto", ...)
            │     ├→ browser_click → execute_browser_op("click", ...)
            │     └→ record_step  → 记录到 pipeline.yaml
            └→ LLM 返回文本 → 结束本轮
```

**关键特点：**
- 系统提示 `chat/system.md` 告诉 LLM "执行操作后调用 record_step 记录到 pipeline"
- LLM 可通过 `goal_run` 设定复杂目标，然后自己用 `todo` 拆解步骤逐步执行
- `record_step` 每次操作后自动追加到 `~/.ybu/sessions/presets/<name>.pipeline.yaml`
- 推流事件通过 WebSocket 通知前端（turn_start/tool_start/text_chunk 等）
- 流式 LLM 响应同时推送推理过程（reasoning_content）和文本增量

**入口文件：**
- `api/routes.py` → `POST /api/chat` 路由
- `api/service.py` → `process_chat_message()`
- `engine/agent.py` → `start_chat_agent()`, `_create_chat_llm_call()`
- `engine/runner.py` → `run_chat_loop()`
- `engine/_harness/conversation_loop.py` → `run_conversation_loop()`

---

### 模式二：Preset 模式（预设回放）

加载已有的 pipeline.yaml，让 Agent 按预设步骤执行。

**有两种执行路径：**

#### 路径 A：旧版 — StepMachine DAG 遍历（runner_preset.py）

```
POST /api/run { pipeline: "..." }
  └→ routes.api_run()
       └→ run_pipeline() (from runner_preset.py)
            ├→ StepMachine(steps) — 初始化 DAG 遍历器
            ├→ while not machine.is_done:
            │     ├→ 审核门控 (guardian)
            │     ├→ 按步骤类型分发：
            │     │     ├→ browser → execute_browser_step()
            │     │     ├→ goal    → execute_goal_step()
            │     │     └→ tool    → _execute_tool_step_with_guardian()
            │     ├→ 检查 check（程序化验收）
            │     ├→ 成功 → machine.end_step() → advance()
            │     ├→ 失败 → 重试 / 恢复计划 / 终止
            │     └→ 写 _execution_tree.json
            ├→ 版本快照 (VersionManager)
            └→ 返回 RunContext
```

**特点：**
- 完全确定性执行——步骤定义明确，LLM 不参与决策（goal 步骤除外）
- `execute_browser_step` 逐个执行 `browser_ops` 列表
- `execute_tool_step` 调用 `tools/` 目录下的自定义 Python 脚本
- `execute_goal_step` 是 stub，实际已废弃（委托给 chat 模式的 LLM）
- check 字段支持 `url_contains / element_exists / text_contains / element_visible` 验收
- 支持恢复计划（`RuntimePlanner`）——失败时 LLM 分析页面状态生成恢复步骤
- 旧版 `engine/executor.py` 的 pipeline 包装器会写文件到 step 目录

#### 路径 B：新版 — Preset Loop（conversation_loop preset_mode）

```
run_preset_loop()
  ├→ PipelineTaskAdapter(step_defs, frontmatter).build_descriptor()
  │     → TaskDescriptor (pipeline 名 + 步骤列表 + 进度)
  ├→ 加载 prompts/preset/system.md
  │     → 注入 {pipeline} 占位符 (TaskDescriptor.format())
  │     + {tool_strategy} + {error_recovery}
  └→ run_conversation_loop(preset_mode=True)
       └→ LLM 看到："Pipeline: xxx | 步骤: [待完成] step_1 ..."
       └→ LLM 用 browser_* 工具逐条执行步骤
       └→ 完成后汇报总结
```

**特点：**
- 让 LLM"看到"完整的步骤列表，自主决定执行顺序和方式
- 系统提示 `preset/system.md` 模板化，注入 pipeline 描述 + 策略 + 恢复指导
- `preset_mode=True` 时跳过 `tool_strategy` 自动注入（已从 preset 提示中加载）
- 相比旧版的纯确定性执行，新版更加灵活但依赖 LLM 能力
- record_step 不再需要（步骤已预定义）

**入口文件：**
- `api/routes.py` → `POST /api/run` 路由（旧版）
- `engine/runner_preset.py` → `run_pipeline()`（旧版编排器）
- `engine/_harness/conversation_loop.py` → `run_preset_loop()`（新版）
- `engine/_harness/pipeline_task_adapter.py` → `PipelineTaskAdapter`

---

## 共享的基础设施

两种模式共用同一套基础设施：

### Conversation Loop (`engine/_harness/conversation_loop.py`)

核心循环：
```
while budget.remaining > 0 and not interrupted:
    1. turn_context.build() — 重置护栏+重试计数器
    2. 组装 messages + system prompt
    3. LLM 调用 (携带工具注册)
    4. 如果有工具调用 → tool_executor.execute()
       否则 → final_response = 文本, break
    5. check_exit_conditions() — budget/中断检查
    6. budget.consume()
```

### 工具注册 (`engine/_harness/tools.py`)

所有工具的定义（OpenAI-compatible function calling schemas）：

| 工具类别 | 工具 | 说明 |
|---------|------|------|
| **浏览器** | `browser_goto` | 导航到 URL |
| | `browser_click` | CSS 选择器点击 |
| | `browser_fill` | 输入框填写 |
| | `browser_snapshot` | 页面快照 (interactive/full/simplified) |
| | `browser_scroll` | 页面滚动 |
| | `browser_source` | 获取 HTML 源码 |
| | `browser_eval` | 执行 JavaScript |
| | `browser_get_element_by_number` | 按 @eN 获取元素详情 |
| **目标** | `goal_run` | 设定复杂目标（用 todo + browser_* 执行） |
| **录制** | `record_step` | 将操作记录到 pipeline.yaml |
| **Pipeline** | `pipeline_load/list/update_step/add_step/remove_step/create` | 管理和编辑预设 |
| **任务** | `todo` | 任务列表管理 |

### 执行器 (`engine/_harness/tool_executor.py`)

统一路由所有工具调用：
- `browser_*` → `executor.execute_browser_op()`（核心逻辑，无文件 I/O）
- `pipeline_*` → `pipeline_tools.py` 中的处理函数
- `goal_run` → 返回提示消息（LLM 自行拆解）
- `todo` → `todo.py` 任务管理
- 其他 → `executor.execute_tool()`（加载 tools/ 目录下的自定义 Python 脚本）

### 脚手架 (Scratchpad) (`engine/scratchpad.py`)

浏览器大块数据的**内存缓存**，不进入 LLM messages：
- `store()` → 存储 URL/title/elements/element_map/summary
- `get_scratchpad().summary` → LLM 看到的是"页面标题: xxx | 15个可交互元素"
- `element_map` → `@e5` → CSS 选择器的映射
- `raw_html` → 页面 HTML 源码缓存

### 三层层级执行逻辑 (`engine/executor.py`)

```
核心函数 (无文件 I/O)          Pipeline 包装器 (写文件)
─────────────────              ─────────────────────
execute_browser_op()  ───→     execute_browser_step()
execute_tool()        ───→     execute_tool_step()
execute_goal()        ───→     execute_goal_step()
```

- **核心函数**仅供 chat 模式 tool_executor 使用——不写磁盘，返回纯结果 dict
- **Pipeline 包装器**用于旧版 preset 模式——调用核心函数后写 step.json + 截图 + 页面 HTML

---

## 关键技术决策

### 1. 去子 Agent

不再 spawn browser-use Agent 作为子 Agent。`goal_run` 保留为模式切换信号，但不是启动子 Agent，而是让主 LLM 用 `todo` + `browser_*` 自己分步执行。

### 2. 重数据进 scratchpad

浏览器返回的 HTML（可能几万字符）、元素列表（几百个）、截图 base64 等不直接塞进 LLM messages。它们存入 scratchpad，LLM 看到的是摘要。LLM 需要时再通过 `browser_source(cached=true)` 读取 HTML 或 `browser_get_element_by_number(@e5)` 获取元素详情。

### 3. Pipeline 三步设计

每个 pipeline step 包含三个可选阶段：
- **goal**（Agent 驱动阶段/仅 fallback 参考）——用 goal_description 描述目标
- **ops**（Preset 执行阶段/Agent 参考）——具体的 browser_ops 列表
- **check**（程序化验收）——支持 url_contains / element_exists / text_contains / element_visible

Preset 回放时优先执行 ops；ops 失败时 fallback 到 goal 让 Agent 动态决策；check 是新的验收机制，独立于执行路径。

### 4. Chat + 浏览器实时同步

用户通过 WebSocket 接收实时事件流：turn_start/tool_start/tool_end/chat.text_chunk/chat.think_chunk 等。这就是"用户看着浏览器画面发出指令，Agent 自主操作"的产品形态。

### 5. Provider 配置扁平化

配置只走 `~/.ybu/provider.json` 平铺 JSON，没有环境变量 / dotenv fallback。预设提供商：deepseek、mimo、opencode-go。

---

## 数据流图

### Chat 模式

```
User ──POST /api/chat──→ routes.chat_message()
                           │
                           ▼
                        service.process_chat_message()
                           │
                   ┌───────▼─────────┐
                   │  run_conversation_loop()
                   │                  │
                   │    LLM call ──→  │  ← prompts/chat/system.md
                   │       │          │
                   │       ▼          │
                   │  tool_executor ──│──→ scratchpad
                   │       │          │
                   │       ▼          │
                   │  executor.py     │
                   │  (browser/tool)  │
                   │       │          │
                   └───────┬─────────┘
                           │
                           ▼
                    JSONResponse
                    {response, turn_count, ...}
```

### Preset 模式（新版）

```
Data               run_preset_loop()
                    │
StepDef[] ───────→ PipelineTaskAdapter.build_descriptor()
                    │  → TaskDescriptor
                    ▼
                prompts/preset/system.md
                    │  {pipeline} 替换
                    ▼
                run_conversation_loop(preset_mode=True)
                    │  LLM 看到步骤列表
                    │  → browser_* 逐条执行
                    ▼
                ConversationResult
```

---

## 关键设计原则

1. **先静态再动态** —— pipeline.yaml 是静态契约，编译阶段解析校验，运行时尽量减少意外
2. **少耦合** —— 引擎/编排层/CDP 层清晰的职责边界
3. **文件即契约** —— pipeline.yaml 是 Agent 工作的产物和回放的依据，版本化存储在 workspace
4. **Validation-first** —— 先验证不变的部分，再处理动态的 LLM 决策
5. **增量开发** —— 倾向 incremental placeholder 而非一步到位完整实现
