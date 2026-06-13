## Why

yak-browser-use（YBU）的目标是让非技术人员即开即用地完成浏览器自动化任务。用户不需要写 agent.md、不需要理解 pipeline 概念——只需要打开桌面应用，通过 chat 指挥 AI 操作浏览器。

产品形态：**chat + 浏览器操作实时同步**。用户看着浏览器画面发出指令，Agent 在 conversation_loop 中自主调用浏览器工具完成任务，每一步实时反馈。

## What Changes

### 核心执行模型
- **执行引擎**: conversation_loop（Agent 自由 tool-calling loop）
- **工具集**: browser-use 集成（goto/click/fill/snapshot 等）+ 数据处理 + 导出
- **交互方式**: chat + 浏览器实时可见
- **pipeline**: 可选副产品——完成后的步骤可保存为预设，未来复用

### 新增模块（从 Hermes 抽取的 harness）
- `engine/_harness/conversation_loop.py` — 核心 agent turn loop
- `engine/_harness/tool_executor.py` — 工具调用执行
- `engine/_harness/error_classifier.py` — 结构化错误分类（13 种错误类型）
- `engine/_harness/retry_utils.py` — 抖动退避
- `engine/_harness/tool_guardrails.py` — 工具调用保护
- `engine/_harness/turn_context.py` — Turn 前置准备
- `engine/_harness/iteration_budget.py` — 迭代预算

### 新增模块（YBU 特有）
- `api/service.py` — API service 层
- `api/ipc.py` — Electron IPC 通信

### Prompts 独立管理
- `prompts/` 目录 — 独立 prompt 文件，通过 _loader.py 加载
- `prompts/chat/system.md` — chat 模式 system prompt
- `prompts/execution/system.md` — 执行模式 system prompt（复用已有文件）

### 修改模块
- `engine/agent.py` — 增强，集成 conversation_loop + tools + goal_run 后端
- `engine/runner.py` — 改为 conversation_loop 的启动入口
- `engine/state.py` — 增加 conversation 级状态
- `api/server.py` — 增加 service 层和 chat endpoint
- `electron-app/` — chat 界面

### 保留不变
- browser-use 集成（agent.py 中已有）— `goal_run` 工具的后端
- workspace / version_manager（执行结果记录）
- compiler（agent.md 解析，作为预设回放的底层）

### 新增模块（适配层）
- `engine/_harness/pipeline_task_adapter.py` — 预设回放时，将 StepDef[] 转为 conversation_loop 的 task 描述

## Capabilities

### New Capabilities
- `agent-harness`: 从 Hermes 抽取的完整 agent harness（conversation_loop + tool_executor + error_classifier + retry_utils + tool_guardrails + turn_context + iteration_budget）
- `browser-chat`: chat + 浏览器操作的实时交互模式
- `session-history`: 会话历史保存 + 预设管理
- `ipc-service`: Electron 前后端通信 + API service 层
- `prompts`: 独立 prompt 文件管理

### Modified Capabilities
- （无现有 spec 变更）

## Impact

- 新增 ~12 个 Python 文件（~3,500 行），修改 ~5 个现有文件
- 无新增外部依赖
- compiler 保留但只用于预设回放，不再是核心入口
- chat 成为唯一用户交互方式
- 向后兼容：现有 agent.md 文件可作为预设导入
