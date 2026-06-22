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

## 特性总览

| # | 特性 | 为什么重要 |
|---|------|-----------|
| 1 | **跨 Tab 隔离的实时 DOM 高亮** — 双层覆盖层（容器 + 浮动高亮块），RAF 节流重绘，MutationObserver 轻量增量更新。后台定时守卫线程防止跨 tab 不同步。每个 tab 保有独立高亮状态。 | 大多数浏览器 AI 工具要么没有实时高亮，要么用内联样式——滚动就崩、跨 tab 就串。Ybu 的高亮经受了真实业务压力测试——导航、滚动、SPA 切换后仍然稳定。 |
| 2 | **三种快照策略适配不同页面类型** — `progressive`（密度自适应 DOM 遍历，≤200 元素，折叠密集容器，`expand_branch` 按需展开）适合普通页面；`a11y`（无障碍树，iframe / 锁定 DOM 仍可用）适合复杂页面；`simplified`（结构化摘要：标题、链接、列表、表格、正文）适合低成本概览。LLM 自动选择最合适的策略，不需要你操心。 | 单一快照策略在不同页面类型（SPA、iframe 密集、锁定 DOM）上各自失败。三种策略最大化覆盖率，LLM 不需要理解页面结构细节——只管选对模式就行。 |
| 3 | **渐进式快照的密度自适应折叠** — 不是简单的截断。遍历器深度优先读文档，每层测量容器密度，折叠超过阈值的内容，展平后通过 `expand_branch` 句柄让 LLM 按需展开。 | 其他框架截断 N 个元素后直接丢掉剩余内容。Ybu 的折叠-展开机制让 LLM 看到页面全貌，然后只深入感兴趣的区域，不浪费 token 在模板代码上。 |
| 4 | **Pipeline 是副产品** — 不需要预先定义 Pipeline。先聊天，后录制。`pipeline.yaml` 是聊天过程的录制产物，不是设计的起点。有用的流程保留下来后续回放。 | 降低使用门槛：不需要规划自动化流程，只管跟 Agent 聊天，它替你写。Pipeline 设计从真实交互中涌现，而不是前期写死。 |
| 5 | **共享存储的双语法模板解析** — `{path}`（全值引用，保留类型）+ `${path}`（内联字符串插值，`$` 前缀消歧义避免跟 JSON 花括号打架）。刻意设计的两个独立语法，不是无心不一致。 | 在不同工具间传递整个数据结构（`{step_3}`），或在 URL 和模板里插值（`https://${host}/api`）。每种语法有清晰的语义和失败模式。 |
| 6 | **Scratchpad 承载重数据** — HTML 源码、截图 base64、元素列表存入内存缓存。LLM 看到摘要，通过 `browser_source(cached=true)` 或 `browser_get_element_by_number(@e5)` 按需获取细节。 | 保持 LLM 上下文窗口清洁的同时不丢弃数据。Agent 根据需要决定需要什么细节，而不是预先猜测。 |
| 7 | **Eval Agent 与 Shared Store 数据互通** — Eval 子 Agent 继承主对话的 `shared_store`。工具通过 `source_key` 写入结果，eval 通过 `{path}` / `${path}` 模板解析读取。Eval 可以内联验证工具产出，工具流程可以触发 eval 作为验收步骤。 | Eval 不是独立的事后系统——它跟工具生活在同一数据流里。共享存储桥接了工具生产和 eval 消费，实现实时验证循环。 |
| 8 | **三步 Pipeline + 程序化验收** — Pipeline 步骤是 `goal → ops → check`，`check` 支持 `url_contains`、`element_exists`、`text_contains`、`element_visible`——确定性程序化验证，不依赖 LLM 判断。 | 大多数 Pipeline 框架把验证交给 LLM。Ybu 的程序化 check 快速、确定、不消耗 LLM token——简单的验收不需要模型调用。 |
| 9 | **结构化错误恢复生态** — `error_classifier`（错误分类）→ `retry_utils`（可配退避）→ `turn_context`（轮次重试计数器），辅以 `error_recovery` 系统提示词引导。全链路打通，不是临时 try/except。 | 真实浏览器自动化持续失败（超时、元素找不到、CDP 断连）。结构化的恢复链路让 Agent 在真实世界的混乱中存活下来，而不是把错误砸用户脸上。 |
| 10 | **审核门控 + 熔断器 + 补偿回滚** — 三层安全生命周期。Guardian 对敏感操作要求人工审批，熔断器防止连续失败级联扩散，补偿机制支持变更回滚。 | 浏览器自动化会搞坏东西。安全生命周期意味着破坏性操作需要审批、连续失败不会级联、回滚是可行的——不只是"哦豁"。 |
|| 11 | **Chat + 浏览器同步与流式 LLM** — 用户输入指令 → Agent 操作浏览器 → 推理过程、文本增量、工具调用结果全部通过 WebSocket 实时流式推送 | 无需配置文件、无需脚本。用自然语言就能驱动浏览器。看到 Agent 边思考边工作，而不是只看到最终结果。 |
|| 12 | **丰富浏览器工具集** — 22 个浏览器原子操作（goto、click、fill、snapshot、scroll、eval、hover、tab…）覆盖日常自动化 | 足够全面应对真实任务，又足够精细实现精确控制。 |
|| 13 | **自定义工具脚本** — 通过 ToolRegistry 热加载 Python 脚本；内置验证码、文件 IO、格式转换 | 不修改核心代码即可扩展 Agent 能力。丢进一个脚本，它就工作。 |
|| 14 | **Electron 桌面 + REST API** — React + Vite + Monaco 编辑器前端（支持 Diff）；FastAPI 后端同时提供 REST 端点和实时 WebSocket 事件流 | 一个 IDE 级环境用于编写和调试自动化流程，同时提供 API 对接任何前端或 CI pipeline。 |
|| 15 | **连接健康检测与会话持久化** — CDP 心跳 + 进程监控 + 自动断线处理；每个 Pipeline 独立 session 目录保存完整对话历史 | 让长时间运行的自动化在网络抖动和浏览器重启后仍保持在线。再也不丢上下文——重启后从上一次的地方继续。 |
|| 16 | **Provider 灵活配置** — 支持 DeepSeek / OpenAI / 任意 OpenAI-compatible 提供商，平铺 JSON 配置 | 用你想用的模型，不是我们替你选的。 |

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

创建 `userdata/provider.json`（或在 Electron 设置面板 → LLM Provider 中配置）：

```json
{
  "model": "deepseek-chat",
  "api_key": "sk-xxx...xxxx",
  "api_base": "https://api.deepseek.com"
}
```

---

## 命令参考

```text
ybu run <path>                执行 pipeline.yaml
ybu serve [--port PORT]       启动 REST API 服务
ybu logs [-f] [--source all]  查看统一日志
```

> CLI 命令只有 `serve`、`run`、`logs`。配置通过 REST API / Electron 设置面板进行，不存在 `ybu param` 等子命令。

---

## 架构说明

### 两层架构

```
┌─────────────────────────────────────────────────────┐
│                   编排层                             │
│  conversation_loop → LLM 决策 → tool_executor 执行   │
│  chat 模式 / preset 模式 / 错误恢复            │
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
       ├→ 将步骤列表送入 conversation_loop
       ├→ 系统提示 = build_system_prompt() + 步骤列表
       ├→ error_recovery.md 在 Agent 初始化时无条件加载
       ├→ LLM 看到完整步骤列表
       ├→ 用 browser_* 工具逐条执行步骤
       ├→ shared_store 透传支持数据流
       └→ 通过 error_recovery.md 提示词 + 重试工具引导错误恢复
```

**特点：**
- 可重复执行的自动化流程
- Pipeline 三步设计：**goal**（目标描述）→ **ops**（浏览器操作列表）→ **check**（程序化验收）
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
│   ├── eval_agent.py         # Eval Agent 验收执行
│   ├── delivery.py / events.py / state.py
│   ├── _param_resolver.py    # 参数模板解析
│   │
│   ├── _harness/             # Conversation loop 基础设施 ★
│   │   ├── conversation_loop.py   # 核心对话循环
│   │   ├── tools.py               # 工具定义（browser_*/goal_run/…）
│   │   ├── tool_executor.py       # 工具调用执行器 + shared_store
│   │   ├── pipeline_tools.py      # Pipeline 管理工具
│   │   ├── pipeline_events.py     # 集中式 WebSocket 事件推送
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
│   ├── discover.py           # Chrome 发现/连接
│   └── launcher.py           # Chrome 启动 / 端口管理
│
├── compiler/                 # Pipeline 编译
│   ├── models.py / schema.py # 数据类 & Pydantic 模型
│   ├── parser.py             # YAML 解析
│   ├── graph.py / resolver.py# DAG 构建 + 依赖解析
│   ├── prepare.py            # 执行前步骤准备
│   ├── step_type.py          # 统一步骤类型推断
│   ├── diff.py               # Op diff 计算
│   ├── generator.py          # Handler 生成 & 代码生成
│
├── tools/                    # 工具注册 + 实现
│   ├── registry.py           # ToolRegistry — 集中调度（43 工具）
│   ├── adapters.py           # 工具数据适配（csv↔json、字段映射）
│   ├── captcha.py            # 验证码识别（ddddocr）
│   ├── file_read.py / file_write.py / format_convert.py
│   ├── extract.py / data.py  # 数据提取 & 处理
│   ├── todo.py / todo_store.py  # 待办事项管理
│   ├── record_step.py        # Pipeline 步骤录制
│   ├── edit_pipeline.py      # Pipeline 编辑（支持回滚）
│   └── _path_utils.py        # 路径遍历防护
│
├── llm/                      # LLM 客户端层
│   ├── client.py             # LLMClient — OpenAI-compatible 适配器
│   └── messages.py           # 消息类型（vendored OpenAI 格式）
│
├── prompts/                  # Prompt 模板（Markdown）
│   ├── _loader.py            # Prompt 加载器（load_prompt / build_system_prompt）
│   ├── chat/system.md        # Chat 模式系统提示（主 prompt）
│   ├── eval_agent/           # Eval Agent prompts
│   │   ├── system.md
│   │   └── js_lib.js
│   ├── guidance/             # 策略 & 恢复指导
│   │   ├── tool_strategy.md  #   工具选择策略
│   │   └── error_recovery.md #   错误恢复指引
│   ├── guardrails/           # 护栏 prompt 片段
│   │   ├── blocked.md / exact_failure.md / no_progress.md
│   │   └── same_tool_failure.md / warning_prefix.md
│   ├── skill/                # 系统技能
│   │   ├── goal-execution/SKILL.md
│   │   ├── skill-authoring/SKILL.md
│   │   └── web-standard-paths/SKILL.md
│   ├── planner-plan.md / planner-expand.md
│   ├── replan-on-failure.md / generate-handler.md
│   └── _archived/            # 已废弃 prompt
│
├── params/                   # 持久化参数管理（ParamManager）
├── workspace/                # 工作区管理（manager/version/path/session）
│   └── session_store.py      # 每个 Pipeline 独立 session 持久化
├── cli/                      # CLI 命令（run.py / serve.py / logs.py）
├── utils/                    # 工具函数（browser/logging/tool_cdp/skill_loader/…）
├── tests/                    # 800+ 单元 & 集成测试
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

1. **PlaywrightBridge 统一驱动** — 所有浏览器操作通过 PlaywrightBridge (`connect_over_cdp()`)，获得 auto-wait / auto-scroll / auto-retry，外加健康检测心跳、子进程监控、断连处理和 SSRF 防护。`BrowserBridge` 协议（`cdp/protocols.py`）定义了接口契约。

2. **文件即契约** — pipeline.yaml 是静态契约，编译阶段严格校验（DAG 环检测、文件引用校验），运行时尽量减少意外。

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

项目参考及贡献者鸣谢请见 [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md)。

---

<p align="center">
  <img src="logo.png" alt="yak" width="64">
  <br/>
  <sub>Built with yak power · Chat · Browser · Automate</sub>
</p>
