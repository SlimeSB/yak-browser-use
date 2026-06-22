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
  <em>An AI Agent framework that chats with you while operating the browser</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%E2%89%A53.12-blue?style=flat-square&logo=python" alt="Python ≥3.12">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" alt="Alpha">
  <img src="https://img.shields.io/badge/Playwright-ready-45ba4b?style=flat-square&logo=playwright" alt="Playwright">
  <img src="https://img.shields.io/badge/Electron-desktop-47848F?style=flat-square&logo=electron" alt="Electron Desktop">
  <a href="./README.zh-CN.md"><img src="https://img.shields.io/badge/README-中文-blue?style=flat-square" alt="中文"></a>
</p>
<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md">简体中文</a>
</p>

---

## What is Ybu?

**yak-browser-use** (aliased as **ybu**) is a browser automation AI Agent framework. Its core interaction model:

> **You chat with the Agent → Agent controls the browser → You watch it happen in real-time**

Two modes:
- **Chat Mode** — natural language conversational control, Agent browses while chatting
- **Preset Mode** — replay recorded pipelines, Agent executes pre-defined steps autonomously

Built on [Playwright](https://playwright.dev/) `connect_over_cdp()` and an OpenAI-compatible LLM client.

---

## Features

| | Capability | Description |
|---|------------|-------------|
| **🗣️ Chat + Browser Sync** | Type commands, Agent operates the browser, everything streams back in real-time |
| **🔧 Rich Browser Toolkit** | goto / click / fill / snapshot (progressive/a11y/raw) / scroll / eval / hover / tab management… full daily automation coverage |
| **📸 Smart Snapshot** | Progressive DOM walk with density-adaptive disclosure + A11y accessibility tree; `expand_branch` for folded containers |
| **📋 Pipeline Recording** | Agent automatically records operations into pipeline.yaml as you chat; save and replay later |
| **🤖 Agent Swimlane** | When a pipeline step fails, the Agent autonomously recovers — no manual intervention needed |
| **🛡️ Safety Guards** | PathGuard, SSRF guard, domain whitelisting, circuit breaker, Guardian approval gate — multiple safety layers |
| **🏓 Streaming LLM** | Real-time reasoning stream, text deltas, tool name push — all via WebSocket to the frontend |
| **🖥️ Electron Desktop** | React + Vite + Monaco Editor (with diff editor), full desktop experience |
| **🔌 REST + WebSocket API** | FastAPI backend with both REST endpoints and real-time event push |
| **📂 Custom Tool Scripts** | Hot-load Python scripts via ToolRegistry; built-in captcha, file I/O, format conversion |
| **🔗 Shared Store** | Tool-to-tool data passing via `${}` templates and `_source_key` — pipeline data flow |
| **💓 Connection Health** | CDP health check heartbeat + browser process watcher + auto-disconnect handling |
| **🔦 Configurable Highlights** | Switchable highlight modes (a11y / progressive / off) via API or Electron settings UI |
| **🔑 Flexible Providers** | DeepSeek / OpenAI / any OpenAI-compatible provider, flat JSON config |

---

## Quick Start

### Prerequisites

| Dependency | Version | Install |
|------------|---------|---------|
| Python | ≥ 3.12 | [python.org](https://python.org) |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org) |
| Chrome / Chromium | ≥ 120 | Your existing Chrome, or `uv run playwright install chromium` |

### Install

```bash
# Windows one-click
install.bat

# Or manual three steps
cd backend
uv sync                              # Install Python deps
uv run playwright install chromium   # Install Playwright Chromium
cd ../electron
npm install                          # Install Electron frontend deps
```

### Start

```bash
# CLI mode
cd backend
uv run python __main__.py --help

# Start REST API server
uv run python __main__.py serve --port 8080

# Start Electron desktop
cd electron
npm run electron:dev
```

### Configure Provider

Create `userdata/provider.json` (or configure via Electron Settings → LLM Provider):

```json
{
  "model": "deepseek-chat",
  "api_key": "sk-xxx...xxxx",
  "api_base": "https://api.deepseek.com"
}
```

---

## Commands

```text
ybu run <path>                 Execute a pipeline.yaml
ybu serve [--port PORT]        Start the REST API server
ybu logs [-f] [--source all]   View unified logs
```

> CLI commands: `serve`, `run`, `logs`. Config via REST API / Electron Settings (not CLI subcommands).

---

## How It Works

### Two-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│              Orchestration Layer                     │
│  conversation_loop → LLM decides → tool_executor     │
│  chat mode / preset mode / agent swimlane            │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│              Browser Control Layer (CDP)              │
│  PlaywrightBridge → connect_over_cdp() → Chrome      │
│  CDPHelpers / ToolContext / ToolCDPHelpers           │
└─────────────────────────────────────────────────────┘
```

### Two Execution Modes

#### Chat Mode (Interactive)

```
POST /api/chat { message: "Open Baidu and search for coffee" }
  └→ service.process_chat_message()
       └→ run_conversation_loop()
            ├→ Load chat/system.md + pipeline context
            ├→ LLM call (browser_* / goal_run / todo / skill / expand_branch)
            ├→ LLM returns tool calls → tool_executor (with shared_store)
            │     ├→ browser_goto  → ops.py → PlaywrightBridge.goto()
            │     ├→ browser_click → ops.py → PlaywrightBridge.click()
            │     ├→ browser_snapshot → progressive/a11y/raw snapshot
            │     └→ record_step   → append to pipeline.yaml
            └→ LLM returns text → end turn
```

**Key Points:**
- User watches the browser and types commands; Agent operates autonomously
- Streaming LLM response (reasoning + text) pushed in real-time
- WebSocket event stream: turn_start / tool_start / text_chunk
- Agent auto-records operation steps to pipeline.yaml
- Tool-to-tool data passing via shared_store (`${}` templates / `_source_key`)

#### Preset Mode (Pipeline Replay)

```
POST /api/run { pipeline: "..." }
  └→ run_pipeline() / run_preset_loop()
       ├→ Load previously recorded pipeline.yaml
       ├→ PipelineTaskAdapter builds TaskDescriptor (step list + progress)
       ├→ System prompt = build_system_prompt() + TaskDescriptor + error_recovery.md
       ├→ LLM sees the full step list
       ├→ Executes steps one by one with browser_* tools
       ├→ shared_store passthrough for data flow
       └→ Agent Swimlane — auto-recover on failure
```

**Key Points:**
- Repeatable automation workflow
- Pipeline three-step design: **goal** → **ops** (browser ops) → **check** (programmatic verification)
- `check` supports: `url_contains` / `element_exists` / `text_contains` / `element_visible`
- Falls back from ops to goal on failure for dynamic Agent decision
- Pipeline context injected into system prompt for workspace awareness

---

## Project Structure

```
yak-browser-use/
├── __main__.py              # CLI entry (run/serve/logs)
├── pyproject.toml            # Project config + deps
│
├── api/                      # FastAPI REST + WebSocket
│   ├── routes.py             # Route registration
│   ├── service.py            # Business logic
│   ├── server.py             # Server lifecycle
│   └── state.py / errors.py  # Engine state & error types
│
├── engine/                   # Core execution engine ★
│   ├── agent.py              # Agent entry + streaming LLM call
│   ├── runner.py             # Chat mode runner
│   ├── runner_preset.py      # Preset mode orchestrator
│   ├── executor.py           # Pipeline wrappers (browser/tool/goal)
│   ├── ops.py                # Browser op dispatcher via BrowserBridge
│   ├── scratchpad.py         # In-memory data cache
│   ├── step_machine.py       # Pipeline DAG walker
│   ├── planner.py            # Runtime recovery planner
│   ├── eval_agent.py         # Eval Agent for verification
│   ├── delivery.py / events.py / state.py
│   ├── _param_resolver.py    # Templated param resolution
│   │
│   ├── _harness/             # Conversation loop infrastructure ★
│   │   ├── conversation_loop.py   # Core agent turn loop
│   │   ├── tools.py               # Tool definitions (browser_*/goal_run/…)
│   │   ├── tool_executor.py       # Sequental dispatcher + shared_store
│   │   ├── pipeline_tools.py      # Pipeline CRUD tools
│   │   ├── pipeline_task_adapter.py  # StepDef → TaskDescriptor
│   │   ├── iteration_budget.py    # LLM turn budget control
│   │   ├── tool_guardrails.py     # Tool call guardrails
│   │   ├── turn_context.py        # Per-turn context (retry counters)
│   │   ├── error_classifier.py    # Error classification
│   │   ├── retry_utils.py         # Retry utilities
│   │   └── skill_tools.py         # Skill injection
│   │
│   └── _lifecycle/           # Pipeline lifecycle management
│       ├── guardian.py       # Approval gate + circuit breaker
│       └── compensation.py   # Rollback / undo support
│
├── cdp/                      # Chrome DevTools Protocol layer ★
│   ├── playwright_bridge.py  # PlaywrightBridge — unified driver
│   │                        #   (health check / process watch / disconnect)
│   ├── helpers.py            # CDPHelpers high-level API
│   ├── protocols.py          # BrowserBridge protocol interface
│   ├── profiles.py / session.py  # Profile & session management
│   ├── daemon.py             # CDP Daemon management
│   ├── discover.py           # Chrome discovery / connection
│   └── launcher.py           # Chrome launch / port mgmt
│
├── compiler/                 # Pipeline compilation
│   ├── models.py / schema.py # Data classes & Pydantic models
│   ├── parser.py             # YAML parser
│   ├── graph.py / resolver.py# DAG builder + dependency resolver
│   ├── prepare.py            # Pre-execution step preparation
│   ├── diff.py               # Op diff computation
│   ├── generator.py          # Handler prompt & code generation
│
├── tools/                    # Tool registry + implementations
│   ├── registry.py           # ToolRegistry — central dispatch (~35 tools)
│   ├── adapters.py           # Tool data adaptation (csv↔json, field mapping)
│   ├── captcha.py            # DOM-based CAPTCHA recognition (ddddocr)
│   ├── file_read.py / file_write.py / format_convert.py
│   ├── extract.py / data.py  # Data extraction & processing
│   ├── todo.py / todo_store.py  # Todo list management
│   ├── record_step.py        # Pipeline step recording
│   ├── edit_pipeline.py      # Pipeline editing with rollback
│   └── _path_utils.py        # Path traversal prevention
│
├── llm/                      # LLM client layer
│   ├── client.py             # LLMClient — OpenAI-compatible adapter
│   └── messages.py           # Message types (vendored OpenAI format)
│
├── prompts/                  # Prompt templates (Markdown)
│   ├── _loader.py            # Prompt loader (load_prompt / build_system_prompt)
│   ├── chat/system.md        # Chat mode system prompt (main)
│   ├── eval_agent/           # Eval Agent prompts
│   │   ├── system.md
│   │   └── js_lib.js
│   ├── guidance/             # Strategy & recovery guidance
│   │   ├── tool_strategy.md  #   Tool selection strategy
│   │   └── error_recovery.md #   Error recovery instructions
│   ├── guardrails/           # Guardrail prompt fragments
│   │   ├── blocked.md / exact_failure.md / no_progress.md
│   │   └── same_tool_failure.md / warning_prefix.md
│   ├── skill/                # System skills
│   │   ├── goal-execution/SKILL.md
│   │   ├── skill-authoring/SKILL.md
│   │   └── web-standard-paths/SKILL.md
│   ├── planner-plan.md / planner-expand.md
│   ├── replan-on-failure.md / generate-handler.md
│   └── _archived/            # Deprecated prompts
│
├── params/                   # Persistent parameter manager (ParamManager)
├── workspace/                # Workspace management (manager/version/path)
├── cli/                      # CLI (run.py / serve.py / logs.py)
├── utils/                    # Utilities (browser/logging/tool_cdp/skill_loader/…)
├── tests/                    # 50+ unit & integration tests
│
├── electron/                 # Electron desktop frontend
│   └── src/
│       └── renderer/         # React + Vite + Monaco Editor (diff)
│
├── docs/                     # Documentation
│   └── architecture-overview.md  # Full architecture deep-dive
│
├── logo.png                  # Project logo
├── install.bat               # Windows one-click installer
├── run.bat                   # Quick launch script
├── README.md                 # This file (English)
└── README.zh-CN.md           # Chinese translation
```

---

## Key Design Decisions

1. **No Spawned Sub-Agents** — `goal_run` is a mode switch, not a sub-Agent spawn. The main LLM decomposes goals with `todo` + `browser_*` tools, eliminating isolation overhead.

2. **Heavy Data Goes to Scratchpad** — Large payloads (HTML, element lists, screenshot base64) go to an in-memory scratchpad. The LLM sees summaries and fetches details on demand via `browser_source(cached=true)` or `browser_get_element_by_number(@e5)`.

3. **Pipeline is a Byproduct** — pipeline.yaml is a recording artifact from chat sessions, not the design starting point. Useful flows get saved and replayed later.

4. **PlaywrightBridge Unified Driver** — All browser operations go through `PlaywrightBridge` (`connect_over_cdp()`), gaining auto-wait / auto-scroll / auto-retry, plus health check heartbeat, process watcher, disconnect handling, and SSRF guard. `BrowserBridge` protocol (`cdp/protocols.py`) defines the interface contract.

5. **File as Contract** — pipeline.yaml is a static contract, strictly validated at compile time (DAG cycle detection, file reference validation), minimizing surprises at runtime.

6. **Progressive Snapshot by Default** — Density-adaptive DOM walk replaces old interactive snapshot. LLM sees at most 200 elements; dense containers folded with `expand_branch` for on-demand expansion. Falls back to a11y accessibility tree for locked/iframed pages.

7. **Shared Store for Tool Data Flow** — Runtime memory bus enables tool-to-tool data passing via `${step_name.output}` templates and `_source_key` parameters, supporting pipelined workflows in both Chat and Preset modes.

---

## Development

```bash
# Create and activate venv
cd backend
uv venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Coverage
uv run pytest --cov=.

# Open Chrome remote debugging port
chrome.exe --remote-debugging-port=9222
```

### Dev Commands

| Command | Description |
|---------|-------------|
| `uv run python __main__.py serve --port 8080` | Start API server |
| `uv run python __main__.py run path/to/pipeline.yaml` | Run a pipeline |
| `uv run python __main__.py logs -f` | Tail logs live |
| `cd electron && npm run electron:dev` | Start Electron frontend |

---

## Architecture Docs

For a full architectural deep-dive (data flow diagrams, design principles, execution paths), see [`docs/architecture-overview.md`](docs/architecture-overview.md).

---

## License

MIT © 2026 Yak Browser-Use Contributors

---

<p align="center">
  <img src="logo.png" alt="yak" width="64">
  <br/>
  <sub>Built with yak power · Chat · Browser · Automate</sub>
</p>
