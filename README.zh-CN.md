<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="logo.png">
    <img src="logo.png" alt="yak-browser-use logo" width="240">
  </picture>
</p>

<h1 align="center">Yak Browser-Use</h1>

<p align="center">
  <strong>CHAT · BROWSER · AUTOMATE</strong>
</p>

<p align="center">
  <em>一个让 AI Agent 跟你聊天同时操控浏览器的自动化框架</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%E2%89%A53.12-blue?style=flat-square&logo=python" alt="Python ≥3.12">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" alt="Alpha">
  <img src="https://img.shields.io/badge/Playwright-ready-45ba4b?style=flat-square&logo=playwright" alt="Playwright">
  <img src="https://img.shields.io/badge/Electron-desktop-47848F?style=flat-square&logo=electron" alt="Electron Desktop">
  <a href="./README.md"><img src="https://img.shields.io/badge/README-English-blue?style=flat-square" alt="English"></a>
</p>
<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md">简体中文</a>
</p>

---

## 项目简介

**yak-browser-use**（简称 **ybu**）是一个面向浏览器自动化的 AI Agent 框架。核心交互模型：

> **你跟 Agent 聊天 → Agent 自主操控浏览器 → 实时同步给你看**

支持两种模式：

- **Chat 模式** — 自然语言对话式操控，Agent 边聊边操作浏览器
- **Preset 模式** — 预设 Pipeline 回放，Agent 按编排步骤自动执行

技术底座基于 [Playwright](https://playwright.dev/) `connect_over_cdp()` 和 OpenAI-compatible LLM 客户端。

---

## 核心功能

| | 能力 | 说明 |
|---|------|------|
| **🗣️ Chat + 浏览器同步** | 用户在 chat 输入指令，Agent 自主操作浏览器，操作过程实时推送给用户 |
| **🔧 丰富浏览器工具集** | goto / click / fill / snapshot (progressive/a11y/raw) / scroll / eval / hover / tab 管理…… 覆盖日常自动化需求 |
| **📸 智能快照** | 渐进式 DOM 遍历（密度自适应折叠）+ 无障碍树快照；`expand_branch` 展开折叠容器 |
| **📋 Pipeline 编排** | 聊天过程中自动录制操作步骤到 pipeline.yaml，可保存为预设后续回放 |
| **🤖 Agent Swimlane** | Pipeline 执行出问题时 Agent 自动介入恢复，无需人工干预 |
| **🛡️ 安全护栏** | 路径守卫 (PathGuard)、SSRF 防护、域名白名单、熔断器、审核门控 (Guardian) — 多重安全机制 |
| **🏓 流式 LLM** | 流式推理 + 文本增量 + 工具名实时推送，WebSocket 推送到前端 |
| **🖥️ Electron 桌面** | React + Vite + Monaco 编辑器（支持 Diff 编辑器），提供完整桌面端体验 |
| **🔌 REST + WebSocket API** | FastAPI 后端，支持 REST 调用和实时事件推送 |
| **📂 工具注册中心** | ToolRegistry 集中管理内置工具（验证码、文件 IO、格式转换等） |
| **🔗 共享存储** | 工具间数据传递：`${}` 模板语法 + `_source_key` 参数，支持 Pipeline 数据流 |
| **💓 连接健康检测** | CDP 心跳检测 + 浏览器子进程监控 + 自动断连处理 |
| **🔦 可切换高亮模式** | 支持 a11y / progressive / off 三种高亮模式，API 或 Electron 设置面板切换 |
| **🔑 Provider 灵活配置** | 支持 DeepSeek / OpenAI / 任意 OpenAI-compatible 提供商，平铺 JSON 配置 |

---

## 快速上手

### 前置要求

| 依赖 | 版本 | 安装 |
|------|------|------|
| Python | ≥ 3.12 | [python.org](https://python.org) |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org) |
| Chrome / Chromium | ≥ 120 | 已安装的 Chrome，或 `uv run playwright install chromium` |

### 安装

```bash
# Windows 一键安装
install.bat

# 或手动三步
cd backend
uv sync                              # 安装 Python 依赖
uv run playwright install chromium   # 安装 Playwright Chromium
cd ../electron
npm install                          # 安装 Electron 前端依赖
```

### 启动

```bash
# CLI 模式
cd backend
uv run python __main__.py --help

# 启动 REST API 服务
uv run python __main__.py serve --port 8080

# 启动 Electron 桌面端
cd electron
npm run electron:dev
```

### 配置 Provider

创建 `userdata/provider.json`：

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "api_key": "sk-xxx...xxxx"
}
```

也可用 CLI 配置：`ybu param set provider.api_key "sk-xxx"`

---

## 命令参考

```text
ybu run <path>                执行 pipeline.yaml
ybu serve [--port PORT]       启动 REST API 服务
ybu logs [-f] [--source all]  查看统一日志
```

> 更多子命令：`chrome`、`param`、`pipeline`、`daemon`、`tool`、`debug` — 见 `ybu <subcommand> --help`。

---

## 架构说明

### 两层架构

```
┌─────────────────────────────────────────────────────┐
│                   编排层                             │
│  conversation_loop → LLM 决策 → tool_executor 执行   │
│  chat 模式 / preset 模式 / agent swimlane            │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│                 CDP 浏览器控制层                       │
│  PlaywrightBridge → connect_over_cdp() → Chrome      │
│  CDPHelpers / ToolContext / ToolCDPHelpers           │
└─────────────────────────────────────────────────────┘
```

### 两种运行模式

#### Chat 模式（交互式）

```
POST /api/chat { message: "打开百度搜咖啡" }
  └→ service.process_chat_message()
       └→ run_conversation_loop()
            ├→ 加载 chat/system.md + pipeline 上下文
            ├→ LLM 调用（browser_* / goal_run / todo / skill / expand_branch）
            ├→ LLM 返回工具调用 → tool_executor（带 shared_store）
            │     ├→ browser_goto  → ops.py → PlaywrightBridge.goto()
            │     ├→ browser_click → ops.py → PlaywrightBridge.click()
            │     ├→ browser_snapshot → progressive/a11y/raw 快照
            │     └→ record_step   → 写入 pipeline.yaml
            └→ LLM 返回文本 → 结束本轮
```

**特点：**
- 用户看着浏览器画面发出指令，Agent 自主操作
- 流式 LLM 响应（推理过程 + 文本增量）实时推送
- WebSocket 事件流通知前端（turn_start / tool_start / text_chunk）
- Agent 会自动记录操作步骤到 pipeline.yaml
- 工具间通过 shared_store 数据传递（`${}` 模板 / `_source_key`）

#### Preset 模式（预设回放）

```
POST /api/run { pipeline: "..." }
  └→ run_pipeline() / run_preset_loop()
       ├→ 加载已录制的 pipeline.yaml
       ├→ PipelineTaskAdapter 构建 TaskDescriptor（步骤列表 + 进度）
       ├→ LLM 看到完整步骤列表
       ├→ 用 browser_* 工具逐条执行步骤
       ├→ shared_store 透传支持数据流
       └→ Agent Swimlane — 遇到故障自动恢复
```

**特点：**
- 可重复执行的自动化流程
- Pipeline 三步设计：**goal**（目标描述）→ **ops**（浏览器操作列表）→ **check**（程序化验收）
- ops 失败时自动 fallback 到 goal 让 Agent 动态决策
- check 支持 `url_contains` / `element_exists` / `text_contains` / `element_visible` 验收
- Pipeline 上下文注入系统提示，Agent 感知工作空间

---

## 项目结构

```
yak-browser-use/
├── __main__.py              # CLI 入口（run/serve/logs）
├── pyproject.toml            # 项目配置 + 依赖
│
├── api/                      # FastAPI REST + WebSocket 接口
│   ├── routes.py             # 路由注册
│   ├── service.py            # 业务逻辑
│   ├── server.py             # 服务器生命周期
│   └── state.py / errors.py  # 引擎状态 & 错误类型
│
├── engine/                   # 核心执行引擎 ★
│   ├── agent.py              # Agent 入口 + 流式 LLM call
│   ├── runner.py             # Chat 模式 runner
│   ├── runner_preset.py      # Preset 模式 orchestrator
│   ├── executor.py           # Pipeline 包装执行器
│   ├── ops.py                # 浏览器操作分发（通过 BrowserBridge）
│   ├── scratchpad.py         # 内存数据缓存
│   ├── step_machine.py       # Pipeline DAG 遍历
│   ├── planner.py            # 运行时恢复规划器
│   ├── eval_agent.py         # Eval Agent 验收执行
│   ├── delivery.py / events.py / state.py
│   ├── _param_resolver.py    # 参数模板解析
│   │
│   ├── _harness/             # Conversation loop 基础设施 ★
│   │   ├── conversation_loop.py   # 核心对话循环
│   │   ├── tools.py               # 工具定义（browser_*/goal_run/…）
│   │   ├── tool_executor.py       # 工具调用执行器 + shared_store
│   │   ├── pipeline_tools.py      # Pipeline 管理工具
│   │   ├── pipeline_task_adapter.py  # StepDef → TaskDescriptor
│   │   ├── iteration_budget.py    # LLM 轮次预算控制
│   │   ├── tool_guardrails.py     # 工具护栏
│   │   ├── turn_context.py        # 每轮次上下文管理
│   │   ├── error_classifier.py    # 错误分类
│   │   ├── retry_utils.py         # 重试工具
│   │   └── skill_tools.py         # Skill 注入
│   │
│   └── _lifecycle/           # Pipeline 生命周期
│       ├── guardian.py       # 审核门控 + 熔断器
│       └── compensation.py   # 回滚/撤销支持
│
├── cdp/                      # Chrome DevTools Protocol 层 ★
│   ├── playwright_bridge.py  # PlaywrightBridge — 统一驱动
│   │                        #   （健康检测 / 进程监控 / 断连处理）
│   ├── helpers.py            # CDPHelpers 高级封装
│   ├── protocols.py          # BrowserBridge 协议接口
│   ├── profiles.py / session.py  # 配置 & 会话管理
│   ├── daemon.py             # CDP Daemon 管理
│   ├── discover.py           # Chrome 发现/连接
│   └── launcher.py           # Chrome 启动 / 端口管理
│
├── compiler/                 # Pipeline 编译
│   ├── schema.py / parser.py # YAML 模型 & 解析
│   ├── graph.py / resolver.py# DAG 构建 & 依赖解析
│   ├── diff.py / generator.py / prepare.py
│
├── tools/                    # 工具注册 + 实现
│   ├── registry.py           # ToolRegistry — 集中调度
│   ├── adapters.py           # 工具适配层
│   ├── captcha.py            # 验证码识别（ddddocr）
│   ├── file_read.py / file_write.py / format_convert.py
│   ├── extract.py / data.py  # 数据处理工具
│   ├── todo.py / todo_store.py  # 待办事项管理
│   ├── record_step.py        # Pipeline 步骤录制
│   ├── edit_pipeline.py      # Pipeline 编辑
│   └── _path_utils.py        # 路径工具
│
├── llm/                      # LLM 客户端层
│   ├── client.py             # OpenAI-compatible 客户端
│   └── messages.py           # 消息构造/解析
│
├── prompts/                  # Prompt 模板（Markdown）
│   ├── chat/system.md        # Chat 模式系统提示
│   ├── eval_agent/system.md  # Eval Agent 系统提示
│   ├── guidance/ / guardrails/ / skill/
│   └── planner-*.md / replan-on-failure.md / generate-handler.md
│
├── params/                   # 持久化参数管理
├── workspace/                # 工作区管理（manager/version/path）
├── cli/                      # CLI 命令（run.py / serve.py / logs.py）
├── utils/                    # 工具函数（browser/logging/tool_cdp/skill_loader/…）
├── tests/                    # 50+ 单元 & 集成测试
│
├── electron/                 # Electron 桌面前端
│   └── src/
│       └── renderer/         # React + Vite + Monaco Editor（Diff 支持）
│
├── docs/                     # 文档
│   └── architecture-overview.md  # 架构详解
│
├── logo.png                  # 项目 Logo
├── install.bat               # Windows 一键安装脚本
├── run.bat                   # 快速启动脚本
├── README.md                 # 英文 README
└── README.zh-CN.md           # 中文 README（本文件）
```

---

## 核心设计原则

1. **去子 Agent** — 不再 spawn browser-use Agent 作为子进程。`goal_run` 是模式切换信号，主 LLM 用 `todo` + `browser_*` 自己分步执行，减少隔离开销。

2. **重数据进 Scratchpad** — 浏览器返回的 HTML、元素列表、截图 base64 等大块数据存入内存缓存（scratchpad），LLM 看到的只是摘要，按需通过 `browser_source(cached=true)` 或 `browser_get_element_by_number(@e5)` 获取详情。

3. **Pipeline 是副产品** — pipeline.yaml 是 Agent 聊天过程的录制产物，不是设计的起点。Agent 聊天产生有用流程后保存下来供后续回放。

4. **PlaywrightBridge 统一驱动** — 所有浏览器操作通过 PlaywrightBridge (`connect_over_cdp()`)，获得 auto-wait / auto-scroll / auto-retry，外加健康检测心跳、子进程监控、断连处理和 SSRF 防护。`BrowserBridge` 协议（`cdp/protocols.py`）定义了接口契约。

5. **文件即契约** — pipeline.yaml 是静态契约，编译阶段严格校验（DAG 环检测、文件引用校验），运行时尽量减少意外。

6. **渐进式快照默认** — 密度自适应 DOM 遍历替代旧版交互式快照。LLM 最多看到 200 个元素；密集容器折叠后用 `expand_branch` 按需展开。对锁定/iframe 页面降级到 a11y 无障碍树。

7. **共享存储支持工具数据流** — 运行时内存总线通过 `${step_name.output}` 模板和 `_source_key` 参数实现工具间数据传递，同时在 Chat 和 Preset 模式中支持流水线工作流。

---

## 开发

```bash
# 创建并激活虚拟环境
cd backend
uv venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# 安装开发依赖
uv sync --dev

# 运行测试
uv run pytest

# 测试覆盖率
uv run pytest --cov=.

# 打开 Chrome 远程调试端口
chrome.exe --remote-debugging-port=9222
```

### 常用开发命令

| 命令 | 说明 |
|------|------|
| `uv run python __main__.py serve --port 8080` | 启动 API 服务 |
| `uv run python __main__.py run path/to/pipeline.yaml` | 执行 Pipeline |
| `uv run python __main__.py logs -f` | 实时查看日志 |
| `cd electron && npm run electron:dev` | 启动前端 |

---

## 架构文档

完整架构详解（数据流图、设计原则、执行路径）请见 [`docs/architecture-overview.md`](docs/architecture-overview.md)。

---

## 许可证

MIT © 2026 Yak Browser-Use Contributors

---

<p align="center">
  <img src="logo.png" alt="yak" width="64">
  <br/>
  <sub>Built with yak power · Chat · Browser · Automate</sub>
</p>
