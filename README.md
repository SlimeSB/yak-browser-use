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
  <img src="https://img.shields.io/pypi/v/yak-browser-use?style=flat-square&logo=pypi&label=PyPI" alt="PyPI">
  <img src="https://img.shields.io/github/actions/workflow/status/SlimeSB/yak-browser-use/ci.yml?branch=main&style=flat-square&label=CI" alt="CI">
  <img src="https://img.shields.io/badge/python-%E2%89%A53.12-blue?style=flat-square&logo=python" alt="Python ≥3.12">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" alt="Alpha">
  <img src="https://img.shields.io/badge/Playwright-ready-45ba4b?style=flat-square&logo=playwright" alt="Playwright">
  <img src="https://img.shields.io/badge/Electron-desktop-47848F?style=flat-square&logo=electron" alt="Electron Desktop">
  <img src="https://img.shields.io/badge/Web%20UI-uvx-8A2BE2?style=flat-square&logo=web" alt="Web UI">
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

> **Built from the ground up.** ybu is an independent codebase with its own conversation loop, progressive snapshot engine, CDP integration, and pipeline compiler — designed entirely from scratch for this project. It has zero browser-use dependencies and shares no code with any other browser automation framework.

---

## Features

| # | Feature | Why It Matters |
|---|--------|----------------|
| 1 | **Live DOM highlighting with cross-tab isolation** — Two-layer overlay (container + floating divs), RAF-throttled repaint, MutationObserver for lightweight re-render. Periodic background guard prevents desync across tabs. Every tab gets its own highlight state. | Most browser AI tools have no live highlights, or use inline styles that tear on scroll and leak across tabs. Ybu's system survived real production stress tests — it stays put after navigation, scroll, and SPA transitions. |
| 2 | **Three snapshot strategies for different page types** — `aria` (Playwright aria_snapshot(mode="ai"), YAML 语义树, LLM 友好 token 最少) for first-glance understanding; `a11y` (CDP Accessibility.getFullAXTree, structured elements with ref/selector for click/fill) for actionable interaction; `progressive` (density-adaptive DOM walk, ≤200 elements, fold dense containers with `expand_branch`) for complex long pages. The LLM selects the right mode — you never worry about the choice. | Single-strategy snapshots fail on different page types (SPA, iframe-heavy, locked DOM). Three strategies maximize coverage without the LLM having to figure out the page's quirks — it just picks the right mode for the job. |
| 3 | **Progressive snapshot's adaptive density disclosure** — Not truncation. The walker reads the document depth-first, measures container density per depth, folds anything above threshold, and presents a flattened view with `expand_branch` handles the LLM can pull on demand. | Other frameworks truncate at N elements and lose the rest. Progressive's fold-and-expand lets the LLM see the page shape and dig into relevant sections without wasting tokens on boilerplate. |
| 4 | **Pipeline as byproduct** — Ybu doesn't require pre-defined pipelines. Chat first, record later. `pipeline.yaml` is a recording artifact from chat sessions, not a design starting point. Useful flows get saved and replayed. | Lowers the adoption bar: you don't plan automation flows, you just chat and the Agent writes them for you. Pipeline design emerges from real interaction instead of upfront spec. |
| 5 | **Shared Store dual-syntax template resolution** — `{path}` (whole-value reference, preserves type) and `${path}` (inline string interpolation, `$` prefix disambiguates from JSON braces). Designed as two separate needs, not accidental inconsistency. | Pass entire data structures between tools (`{step_3}`), or interpolate values inside URLs and templates (`https://${host}/api`). Each syntax has clear semantics and failure modes. |
| 6 | **Scratchpad for heavy data** — HTML dumps, screenshot base64, element lists go to in-memory scratchpad. LLM sees summaries and fetches detail on demand via `browser_source(cached=true)` or `browser_get_element_by_number(@e5)`. | Keeps the LLM context window clean without discarding data. The Agent decides what detail it needs rather than guessing up-front. |
| 7 | **Eval Agent + Shared Store data bridge** — The eval subagent inherits the main conversation's `shared_store`. Tools write results via `source_key`, and eval reads them through `{path}` / `${path}` template resolution. Eval can verify tool outputs inline, and tool flows can trigger eval as a verification step. | Eval is not a separate post-hoc system — it lives in the same data flow as tools. The shared store bridges tool production and eval consumption, enabling real-time verification loops. |
| 8 | **Three-step pipeline with programmatic checks** — Pipeline steps are `goal → ops → check`, where `check` supports `url_contains`, `element_exists`, `text_contains`, `element_visible` — deterministic programmatic verification, not LLM opinion. | Most pipeline frameworks leave verification to the LLM. Ybu's programmatic checks are fast, deterministic, and independent of LLM cost/latency — a trivial check doesn't need a model call. |
| 9 | **Structured error recovery ecosystem** — `error_classifier` (categorizes failures) → `retry_utils` (configurable backoff) → `turn_context` (per-turn retry counters), guided by `error_recovery` system prompt. All wired together, not ad-hoc try/except. | Real browser automation fails constantly (network timeout, element not found, CDP disconnect). A structured recovery pipeline means the Agent survives real-world chaos without dumping errors on the user. |
| 10 | **Guardian approval gate + circuit breaker + compensation rollback** — Three-layer safety lifecycle. Guardian gates sensitive operations for human approval, circuit breaker prevents cascading failures, compensation undoes changes on rollback. | Browser automation can break things. The safety lifecycle means destructive operations require approval, repeated failures don't cascade, and rollback is possible — not just "oops." |
| 11 | **Chat + Browser Sync & Streaming LLM** — User types commands → Agent operates browser → reasoning, text deltas, and tool calls stream back via WebSocket in real-time | No config files, no scripts. Just natural language driving the browser. See the Agent think as it works, not just the final result. |
| 12 | **Rich Browser Toolkit** — 22 browser atomics (goto, click, fill, snapshot, scroll, eval, hover, tab…) covering daily automation | Broad enough for real-world tasks, granular enough for precise control. |
| 13 | **Custom Tool Scripts** — Hot-load Python scripts via ToolRegistry; built-in captcha, file I/O, format conversion | Extend the agent without modifying core code. Drop in a script, it just works. |
| 14 | **Electron Desktop + Web UI** — React + Vite + Monaco Editor frontend with diff editor; FastAPI backend serving REST endpoints, WebSocket event streams, and static frontend. Run as Electron desktop app or `uvx yak-browser-use` for instant browser-based UI. | An IDE-like environment for building pipelines, with an API that integrates into any frontend or CI pipeline. One-command web launch removes the Electron dependency for quick demos. |
| 15 | **Connection Health & Session Persistence** — CDP heartbeat + process watcher + auto-disconnect handling; per-pipeline session directories with full conversation history | Keeps long-running automation alive through network blips and browser restarts. Never lose context — pick up where you left off. |
| 16 | **Flexible Providers** — DeepSeek / OpenAI / any OpenAI-compatible provider via flat JSON config | Use the model you want, not the one we chose for you. |

---

## Quick Start

### One-command (no install required)

```bash
uvx yak-browser-use
```

Opens the Web UI in your browser — zero setup. The first run auto-installs the package and dependencies.

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
# Quickest — launch Web UI from PyPI (no local setup needed)
uvx yak-browser-use

# Or after local install:
cd backend
uv run python -m yak_browser_use web      # Web UI (browser-based)
uv run python -m yak_browser_use serve     # REST API server
uv run python -m yak_browser_use --help    # All CLI commands

# Electron desktop (requires Node.js)
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
ybu web                        Start the Web UI (browser, no Electron)
ybu logs [-f] [--source all]   View unified logs
```

> CLI commands: `serve`, `run`, `web`, `logs`. Config via Web UI / Electron Settings (not CLI subcommands).

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
| yak-browser-use/
| ├── backend/
| │   ├── src/
| │   │   └── yak_browser_use/        # All Python source code ★
| │   │       ├── __main__.py         # CLI entry (run/serve/web/logs)
| │   │       ├── pyproject.toml      # Project config + deps
| │   │       │
| │   │       ├── api/                # FastAPI REST + WebSocket
| │   │       │   ├── routes.py       # Route registration
| │   │       │   ├── service.py      # Business logic
| │   │       │   ├── server.py       # Server lifecycle
| │   │       │   └── state.py / errors.py
| │   │       │
| │   │       ├── engine/             # Core execution engine ★
| │   │       │   ├── agent.py        # Agent entry + streaming LLM
| │   │       │   ├── runner.py       # Chat mode runner
| │   │       │   ├── runner_preset.py# Preset mode orchestrator
| │   │       │   ├── executor.py     # Pipeline wrappers
| │   │       │   ├── ops.py          # Browser op dispatcher
| │   │       │   ├── scratchpad.py / step_machine.py
| │   │       │   ├── eval_agent.py / delivery.py / events.py
| │   │       │   ├── _param_resolver.py
| │   │       │   │
| │   │       │   ├── _harness/       # Conversation loop ★
| │   │       │   │   ├── conversation_loop.py
| │   │       │   │   ├── tools.py / tool_executor.py
| │   │       │   │   ├── pipeline_tools.py / pipeline_events.py
| │   │       │   │   ├── iteration_budget.py / turn_context.py
| │   │       │   │   ├── tool_guardrails.py / error_classifier.py
| │   │       │   │   ├── retry_utils.py / skill_tools.py
| │   │       │   │
| │   │       │   └── _lifecycle/     # Pipeline lifecycle
| │   │       │       ├── guardian.py    # Approval gate + circuit breaker
| │   │       │       └── compensation.py# Rollback / undo
| │   │       │
| │   │       ├── cdp/                # Chrome DevTools Protocol ★
| │   │       │   ├── playwright_bridge.py  # Unified driver
| │   │       │   ├── helpers.py / protocols.py
| │   │       │   ├── profiles.py / session.py
| │   │       │   ├── discover.py / launcher.py
| │   │       │
| │   │       ├── compiler/           # Pipeline compilation
| │   │       │   ├── models.py / schema.py / parser.py
| │   │       │   ├── graph.py / resolver.py / prepare.py
| │   │       │   ├── diff.py / generator.py / step_type.py
| │   │       │
| │   │       ├── tools/              # Tool registry (43 tools)
| │   │       │   ├── registry.py     # Central dispatch
| │   │       │   ├── adapters.py / captcha.py
| │   │       │   ├── file_read.py / file_write.py / format_convert.py
| │   │       │   ├── extract.py / data.py
| │   │       │   ├── todo.py / todo_store.py
| │   │       │   ├── record_step.py / edit_pipeline.py
| │   │       │   └── _path_utils.py
| │   │       │
| │   │       ├── llm/                # LLM client
| │   │       ├── prompts/            # Prompt templates (Markdown)
| │   │       ├── params/             # Persistent parameter manager
| │   │       ├── workspace/          # Workspace management
| │   │       ├── cli/                # CLI commands
| │   │       ├── utils/              # Utilities
| │   │       │   └── _path.py        # project_root() resolver
| │   │       └── static/             # Web UI frontend (build artifact)
| │   │
| │   ├── tests/                      # 800+ unit & integration tests
| │   ├── README.md                   # This file
| │   └── uv.lock                     # Lockfile
| │
| ├── electron/                       # Electron desktop frontend
| │   ├── src/renderer/               # React + Vite + Monaco Editor
| │   ├── vite.web.config.ts          # Web build config → backend static/
| │   └── package.json
| │
| ├── .github/workflows/              # CI/CD automation
| │   ├── ci.yml                      # Test on push/PR
| │   └── release.yml                 # Publish on tag / manual
| │
| ├── logo.png / install.bat / run.bat
| └── README.md / README.zh-CN.md
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
| `uv run python -m yak_browser_use serve --port 8080` | Start API server |
| `uv run python -m yak_browser_use web` | Start Web UI (browser) |
| `uv run python -m yak_browser_use run path/to/pipeline.yaml` | Run a pipeline |
| `uv run python -m yak_browser_use logs -f` | Tail logs live |
| `uv run python -m yak_browser_use --help` | Show all CLI commands |
| `cd electron && npm run electron:dev` | Start Electron frontend |
| `cd electron && npm run dev:web` | Start Web frontend dev server (Vite HMR + proxy) |

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
