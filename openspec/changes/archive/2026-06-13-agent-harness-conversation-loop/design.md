## Context

YBU 定位为面向非技术用户的浏览器自动化桌面应用。用户不需要理解 agent.md 或 pipeline 概念。产品形态是 **chat + 浏览器实时操作同步**——用户打开桌面应用，通过 chat 指挥 AI 操作浏览器，实时看到浏览器画面反馈。

核心架构：从 Hermes Agent 抽取 conversation_loop 作为执行引擎，集成 browser-use 作为浏览器操作能力。Hermes 的 conversation_loop（4,245 行）是经过生产验证的 agent turn loop，提供自由 tool-calling、错误分类、guardrail 保护、retry 等完整能力。

## Goals / Non-Goals

**Goals:**
- 从 Hermes 抽取完整 agent harness（conversation_loop + tool_executor + 6 个子模块）
- 集成 browser-use 作为浏览器工具后端
- chat 作为唯一用户交互方式
- 独立的 prompt 文件管理
- IPC/Service 层支持 Electron 前端
- 会话历史可保存为预设（可选）

**Non-Goals:**
- 不强制用户理解 pipeline 或 agent.md
- 不改变 browser-use 的浏览器控制能力
- 不引入 gateway/plugin/CLI TUI 等 Hermes 层面功能
- 不支持多会话并发 — 一个浏览器实例同时只跑一个 conversation_loop（多会话的浏览器状态冲突不可控）

## Architecture

```
┌─ Electron 前端 ───────────────────────────────┐
│  Chat 界面  ←→  IPC  ←→  API Server           │
│  (用户打字)     (ws)    (FastAPI + service)    │
└────────────────────┬──────────────────────────┘
                     ↓ ws/events
┌────────────────────┴──────────────────────────┐
│              Engine Layer                       │
│                                                  │
│  ┌─ 两种执行模式 ──────────────────────────┐   │
│  │                                          │   │
│  │  ① Chat 模式（默认）                    │   │
│  │     conversation_loop ← prompts/loader    │   │
│  │       ├── tools: browser 原子操作          │   │
│  │       │   (goto/click/fill/snapshot)      │   │
│  │       ├── tools: goal_run（browser-use）  │   │
│  │       ├── tools: data/export              │   │
│  │       ├── tool_executor → executor.py     │   │
│  │       │   (execute_browser/tool/goal_step) │   │
│  │       └── error_classifier + guardrails   │   │
│  │                                          │   │
│  │  ② 预设回放模式                          │   │
│  │     compiler → StepDef[]                  │   │
│  │       → PipelineTaskAdapter               │   │
│  │       → TaskDescriptor → conversation_loop │   │
│  │       → tool_executor → executor.py       │   │
│  │         (execute_browser/tool/goal_step)   │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  agent.py — browser-use Agent 集成（goal_run）  │
│  runner.py — 启动入口                            │
│  workspace/ — 执行结果和日志                     │
│  session/ — 会话持久化                           │
└─────────────────────────────────────────────────┘
```

**关键设计原则**: tool_executor 在 chat 模式和预设回放模式**都委托 executor.py**（`execute_browser_step`/`execute_tool_step`/`execute_goal_step`）执行实际工具操作。executor.py 提供 CompensationRegistry、sanitize_result、PathGuard、超时 + 错误码标准化等共享基础设施。两种模式的区别仅在于**编排方式不同**：

- **Chat 模式**: `conversation_loop → tool_executor → executor.py`（LLM 自主决定调用哪个工具）
- **预设回放模式**: `PipelineTaskAdapter → executor.py`（按 StepDef 列表顺序执行）

这样基础设施不会丢失，两条路径不会 diverge。

## Decisions

### 1. 一次抽完整 harness 还是分批
**决策**: 一次抽取所有 hadness 模块（conversation_loop + tool_executor + error_classifier + retry_utils + tool_guardrails + turn_context + iteration_budget）

**理由**:
- conversation_loop 依赖所有子模块，分批会导致中间状态不可用
- 这些模块在 Hermes 中已经是独立抽取的，可以整体搬迁

### 2. browser-use 集成方式
**决策**: 保持 YBU 现有 agent.py 的 browser-use Agent 集成，将 browser-use 的能力封装为 conversation_loop 可调用的工具

**理由**:
- YBU 已有的 `_build_action_for_callable()` 和 `_create_agent_tools()` 工作良好
- browser-use Agent 的 goal 能力保留为 `goal_run` 工具
- 原子操作（goto/click/fill）注册为独立工具

### 3. Pipeline 预设
**决策**: 可选功能——conversation 结束后可一键保存为 agent.md 预设。现有 compiler 负责预设回放。

**理由**: 虽然日常使用不需要 pipeline，但保存常用操作为预设可以提升效率。

### 4. Prompts 独立管理
**决策**: 所有 system prompt 放在 `prompts/` 目录，通过 `_loader.py` 加载

**理由**: 不硬编码，方便调试和修改。conversation_loop 启动时按模式加载对应 prompt。

### 5. 浏览器生命周期
**决策**: 应用启动时自动连接 Chrome（复用 `cdp/daemon.py` 的启动/连接逻辑），整个应用生命周期共享一个浏览器实例。新会话开新标签页，不关闭旧标签页。画面同步通过 CDP `Page.captureScreenshot` 定时截屏推送。

**理由**:
- 用户打开应用就应该能用，不需要手动"连接浏览器"
- 共享实例避免重复启动开销
- 新标签页隔离不同会话的操作上下文

### 6. iteration_budget 默认值
**决策**: 默认 50 次 LLM round-trip（一次 API call = 1 次），用户可在设置中调整。

**理由**: Hermes 默认 90 次，对浏览器自动化场景 50 次足够（大多数任务在 10-20 次内完成）。

### 7. error_classifier 覆盖范围
**决策**: error_classifier 只处理 LLM API 调用错误（网络超时、rate limit、auth 等），不处理浏览器工具执行错误。浏览器操作失败由 tool_executor 捕获后标准化为错误信息返回给 Agent，由 Agent 在下一轮对话中自主判断如何修复。

**理由**: error_classifier 是针对 LLM provider 返回的错误设计的（HTTP 状态码、SDK 异常），浏览器执行错误是 DOM 操作层面的，分类逻辑完全不同。在 chat 模式下 Agent 有推理能力，可以自己判断怎么纠正。

### 8. runner 拆分
**决策**: 将 `runner.py` 拆分为两个入口：
- `runner.py` — chat 模式的 conversation_loop 入口（轻量，负责浏览器生命周期管理 + 启动 conversation_loop）
- `runner_preset.py` — 预设回放模式（复用现有 pipeline 逻辑：重试、recovery planning、compensation、Guardian）

**理由**: 当前 `runner.py` (648 行) 包含大量 pipeline 专属逻辑（StepMachine、retry、recovery、Guardian），与 conversation_loop 的执行模型差异大。拆分后 chat 入口保持轻量，preset 入口复用成熟的基础设施。

### 9. CDP 错误处理策略（chat 模式）
**决策**: Chat 模式下 tool_executor 捕获 CDP 异常后不自动重试分类，而是标准化错误信息并返回给 Agent。Agent 在下一轮对话中自主决定修复策略。

错误处理层次：
- 元素未找到 → 返回具体错误信息，Agent 修正 selector
- 超时 → tool_executor 重试 1 次，仍失败则回报
- CDP 连接断开 → 自动重连（3 次指数退避），失败则报用户
- 不可恢复错误 → 直接报用户

### 10. 迭代预算与 goal_run
**决策**: 
- 默认预算 50 次 LLM round-trip（一次 API call = 1 次）
- 当 Agent 调用 `goal_run` 时，外层 conversation_loop **暂停迭代预算计数**，内层 browser-use Agent 完成后恢复
- Tool call 失败 — 消耗预算（因为下一轮 LLM 调用需要处理错误信息）
- 中断恢复：保存当前会话状态（已执行步骤、错误、Agent 意图），恢复时让 Agent 总结当前状态并继续

- [风险] conversation_loop（4,245 行）抽取工作量大 → [缓解] 只抽取核心 turn loop 逻辑，移除 gateway/plugin/session persist 等 YBU 不需要的代码，预计适配后 ~800 行
- [风险] 从 Hermes 抽取后与上游 diverg → [缓解] 这些模块是纯函数/数据类，没有持续跟踪依赖

## Migration Plan

Phase 0: 基础设施（4 commits）— retry_utils + iteration_budget + error_classifier
Phase 1: 核心引擎（4 commits）— tool_guardrails + turn_context + tool_executor + conversation_loop
Phase 2: 整合（3 commits）— agent.py + runner.py + IPC/Service + prompts
Phase 3: 收尾（1 commit）— 测试 + 清理 + 预设保存
