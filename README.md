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

| # | Feature | Why It Matters |
|---|--------|----------------|
| 1 | **Live DOM highlighting with cross-tab isolation** — Two-layer overlay (container + floating divs), RAF-throttled repaint, MutationObserver for lightweight re-render. Periodic background guard prevents desync across tabs. Every tab gets its own highlight state. | Most browser AI tools have no live highlights, or use inline styles that tear on scroll and leak across tabs. Ybu's system survived real production stress tests — it stays put after navigation, scroll, and SPA transitions. |
| 2 | **Three snapshot strategies for different page types** — `progressive` (density-adaptive DOM walk, ≤200 elements, fold dense containers with `expand_branch`) for normal pages; `a11y` (accessibility tree, works in iframes and locked DOM) for tricky pages; `simplified` (structured summary: headings, links, lists, tables, body text) for low-token overview. The LLM selects the right mode — you never worry about the choice. | Single-strategy snapshots fail on different page types (SPA, iframe-heavy, locked DOM). Three strategies maximize coverage without the LLM having to figure out the page's quirks — it just picks the right mode for the job. |
| 3 | **Progressive snapshot's adaptive density disclosure** — Not truncation. The walker reads the document depth-first, measures container density per depth, folds anything above threshold, and presents a flattened view with `expand_branch` handles the LLM can pull on demand. | Other frameworks truncate at N elements and lose the rest. Progressive's fold-and-expand lets the LLM see the page shape and dig into relevant sections without wasting tokens on boilerplate. |
| 4 | **Pipeline as byproduct** — Ybu doesn't require pre-defined pipelines. Chat first, record later. `pipeline.yaml` is a recording artifact from chat sessions, not a design starting point. Useful flows get saved and replayed. | Lowers the adoption bar: you don't plan automation flows, you just chat and the Agent writes them for you. Pipeline design emerges from real interaction instead of upfront spec. |
| 5 | **Shared Store dual-syntax template resolution** — `{path}` (whole-value reference, preserves type) and `${path}` (inline string interpolation, `$` prefix disambiguates from JSON braces). Designed as two separate needs, not accidental inconsistency. | Pass entire data structures between tools (`{step_3}`), or interpolate values inside URLs and templates (`https://${host}/api`). Each syntax has clear semantics and failure modes. |
| 6 | **Scratchpad for heavy data** — HTML dumps, screenshot base64, element lists go to in-memory scratchpad. LLM sees summaries and fetches detail on demand via `browser_source(cached=true)` or `browser_get_element_by_number(@e5)`. | Keeps the LLM context window clean without discarding data. The Agent decides what detail it needs rather than guessing up-front. |
| 7 | **Eval Agent + Shared Store data bridge** — The eval subagent inherits the main conversation's `shared_store`. Tools write results via `source_key`, and eval reads them through `{path}` / `${path}` template resolution. Eval can verify tool outputs inline, and tool flows can trigger eval as a verification step. | Eval is not a separate post-hoc system — it lives in the same data flow as tools. The shared store bridges tool production and eval consumption, enabling real-time verification loops. |
| 8 | **Three-step pipeline with programmatic checks** — Pipeline steps are `goal → ops → check`, where `check` supports `url_contains`, `element_exists`, `text_contains`, `element_visible` — deterministic programmatic verification, not LLM opinion. | Most pipeline frameworks leave verification to the LLM. Ybu's programmatic checks are fast, deterministic, and independent of LLM cost/latency — a trivial check doesn't need a model call. |
| 9 | **Structured error recovery ecosystem** — `error_classifier` (categorizes failures) → `retry_utils` (configurable backoff) → `turn_context` (per-turn retry counters), guided by `error_recovery` system prompt. All wired together, not ad-hoc try/except. | Real browser automation fails constantly (network timeout, element not found, CDP disconnect). A structured recovery pipeline means the Agent survives real-world chaos without dumping errors on the user. |
| 10 | **Guardian approval gate + circuit breaker + compensation rollback** — Three-layer safety lifecycle. Guardian gates sensitive operations for human approval, circuit breaker prevents cascading failures, compensation undoes changes on rollback. | Browser automation can break things. The safety lifecycle means destructive operations require approval, repeated failures don't cascade, and rollback is possible — not just "oops." |
|| 11 | **Chat + Browser Sync & Streaming LLM** — User types commands → Agent operates browser → reasoning, text deltas, and tool calls stream back via WebSocket in real-time | No config files, no scripts. Just natural language driving the browser. See the Agent think as it works, not just the final result. |
|| 12 | **Rich Browser Toolkit** — 22 browser atomics (goto, click, fill, snapshot, scroll, eval, hover, tab…) covering daily automation | Broad enough for real-world tasks, granular enough for precise control. |
|| 13 | **Custom Tool Scripts** — Hot-load Python scripts via ToolRegistry; built-in captcha, file I/O, format conversion | Extend the agent without modifying core code. Drop in a script, it just works. |
|| 14 | **Electron Desktop + REST API** — React + Vite + Monaco Editor frontend with diff editor; FastAPI backend serving REST endpoints and WebSocket event streams | An IDE-like environment for building pipelines, with an API that integrates into any frontend or CI pipeline. |
|| 15 | **Connection Health & Session Persistence** — CDP heartbeat + process watcher + auto-disconnect handling; per-pipeline session directories with full conversation history | Keeps long-running automation alive through network blips and browser restarts. Never lose context — pick up where you left off. |
|| 16 | **Flexible Providers** — DeepSeek / OpenAI / any OpenAI-compatible provider via flat JSON config | Use the model you want, not the one we chose for you. |

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
│  chat mode / preset mode / error recovery            │
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
       ├→ Feed step list into conversation_loop
       ├→ System prompt = build_system_prompt() + Step list
       ├→ error_recovery.md loaded unconditionally in Agent init
       ├→ LLM sees the full step list
       ├→ Executes steps one by one with browser_* tools
       ├→ shared_store passthrough for data flow
       └→ Guided error recovery via error_recovery.md prompt + retry utilities
```

**Key Points:**
- Repeatable automation workflow
- Pipeline three-step design: **goal** → **ops** (browser ops) → **check** (programmatic verification)
- `check` supports: `url_contains` / `element_exists` / `text_contains` / `element_visible`
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
│   ├── eval_agent.py         # Eval Agent for verification
│   ├── delivery.py / events.py / state.py
│   ├── _param_resolver.py    # Templated param resolution
│   │
│   ├── _harness/             # Conversation loop infrastructure ★
│   │   ├── conversation_loop.py   # Core agent turn loop
│   │   ├── tools.py               # Tool definitions (browser_*/goal_run/…)
│   │   ├── tool_executor.py       # Sequental dispatcher + shared_store
│   │   ├── pipeline_tools.py      # Pipeline CRUD tools
│   │   ├── pipeline_events.py     # Centralized WS event propagation
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
│   ├── discover.py           # Chrome discovery / connection
│   └── launcher.py           # Chrome launch / port mgmt
│
├── compiler/                 # Pipeline compilation
│   ├── models.py / schema.py # Data classes & Pydantic models
│   ├── parser.py             # YAML parser
│   ├── graph.py / resolver.py# DAG builder + dependency resolver
│   ├── prepare.py            # Pre-execution step preparation
│   ├── step_type.py          # Unified step type inference
│   ├── diff.py               # Op diff computation
│   ├── generator.py          # Handler prompt & code generation
│
├── tools/                    # Tool registry + implementations
│   ├── registry.py           # ToolRegistry — central dispatch (43 tools)
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
├── workspace/                # Workspace management (manager/version/path/session)
│   └── session_store.py      # Per-pipeline session persistence
├── cli/                      # CLI (run.py / serve.py / logs.py)
├── utils/                    # Utilities (browser/logging/tool_cdp/skill_loader/…)
├── tests/                    # 800+ unit & integration tests
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

1. **PlaywrightBridge Unified Driver** — All browser operations go through `PlaywrightBridge` (`connect_over_cdp()`), gaining auto-wait / auto-scroll / auto-retry, plus health check heartbeat, process watcher, disconnect handling, and SSRF guard. `BrowserBridge` protocol (`cdp/protocols.py`) defines the interface contract.

2. **File as Contract** — pipeline.yaml is a static contract, strictly validated at compile time (DAG cycle detection, file reference validation), minimizing surprises at runtime.

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

See [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md) for project references and contributor credits.

---

<p align="center">
  <img src="logo.png" alt="yak" width="64">
  <br/>
  <sub>Built with yak power · Chat · Browser · Automate</sub>
</p>
