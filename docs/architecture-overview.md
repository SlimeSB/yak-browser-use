# Yak Browser-Use Architecture Overview

> Last updated: 2026-06-22

## Project Positioning

**yak-browser-use** (aliased as **ybu**) is a browser automation AI Agent framework. The core interaction model is **Agent chats with the user in a conversation_loop while operating the browser** — the user types natural language instructions in chat, and the Agent drives browser operations via LLM to complete tasks.

Pipelines are byproducts of Agent work (presets), saved for later replay.

---

## Directory Structure

```
yak-browser-use/
├── __main__.py              # CLI entry (serve/run/logs)
├── pyproject.toml            # Project config + dependencies
│
├── api/                      # FastAPI REST + WebSocket API layer
│   ├── routes.py             # Route registration (chat/run/chrome/pipeline/workspace)
│   ├── service.py            # Business logic (session mgmt / chat / preset mgmt)
│   ├── server.py             # FastAPI server lifecycle
│   ├── state.py              # Global engine_state
│   └── errors.py             # API error types
│
├── engine/                   # Core execution engine ★
│   ├── agent.py              # Agent entry (chat mode + streaming LLM call)
│   ├── runner.py             # Chat mode runner (lightweight wrapper)
│   ├── runner_preset.py      # Preset mode runner (full pipeline orchestrator)
│   ├── executor.py           # Core executor (browser/tool/goal three-layer)
│   ├── ops.py                # Browser operation dispatcher (bridge-based)
│   ├── scratchpad.py         # In-memory data cache (heavy data stays out of LLM context)
│   ├── delivery.py           # Delivery report generation
│   ├── state.py              # RunContext data class
│   ├── events.py             # EventSink event pipeline
│   ├── step_machine.py       # StepMachine (pipeline DAG walker)
│   ├── planner.py            # Runtime recovery planner
│   ├── eval_agent.py         # Eval Agent for pipeline verification
│   ├── _param_resolver.py    # Param resolver (${} / _source_key templating)
│   │
│   ├── _harness/             # Conversation loop infrastructure ★
│   │   ├── conversation_loop.py    # Core agent turn loop (shared by chat + preset)
│   │   ├── tools.py                # Tool definitions (browser_*/goal_run/record_step/pipeline_*/todo/skill)
│   │   ├── tool_executor.py        # Sequential tool call dispatcher + shared_store
│   │   ├── pipeline_tools.py       # pipeline_load/list/update/add/remove/create implementations
│   │   ├── pipeline_task_adapter.py # StepDef → TaskDescriptor (preset mode only)
│   │   ├── iteration_budget.py     # LLM turn budget control
│   │   ├── tool_guardrails.py      # Tool call guardrails
│   │   ├── turn_context.py         # Per-turn context (retry counters, etc.)
│   │   ├── error_classifier.py     # API error classification
│   │   ├── retry_utils.py          # Retry utility functions
│   │   └── skill_tools.py          # Skill injection for agent
│   │
│   └── _lifecycle/           # Pipeline lifecycle management
│       ├── compensation.py   # Compensate / rollback logic (async-locked)
│       └── guardian.py       # Approval gate + circuit breaker
│
├── cdp/                      # Chrome DevTools Protocol layer ★
│   ├── playwright_bridge.py  # PlaywrightBridge — unified driver (health check, process watch)
│   ├── helpers.py            # CDPHelpers (high-level browser operation wrappers)
│   ├── protocols.py          # BrowserBridge protocol (interface definition)
│   ├── profiles.py           # Browser profile management
│   ├── session.py            # CDP session management
│   ├── daemon.py             # CDP Daemon management
│   ├── discover.py           # Chrome discovery / connection
│   └── launcher.py           # Chrome launch / port management
│
├── compiler/                 # Pipeline compilation
│   ├── models.py             # PipelineDef / StepDef data classes
│   ├── schema.py             # PipelineYaml / StepYaml Pydantic models
│   ├── parser.py             # YAML parser
│   ├── graph.py              # DAG builder / cycle detection
│   ├── resolver.py           # Dependency resolver
│   ├── diff.py               # Pipeline diff computation
│   ├── generator.py          # Pipeline generator
│   └── prepare.py            # Pre-execution preparation
│
├── tools/                    # Tool registry + implementations
│   ├── registry.py           # ToolRegistry — central dispatch & schema generation
│   ├── adapters.py           # Tool adaptation layer
│   ├── record_step.py        # record_step tool (LLM records steps to pipeline)
│   ├── todo.py / todo_store.py   # Todo task management tools
│   ├── edit_pipeline.py      # Pipeline editing tools
│   ├── extract.py / data.py  # Data processing tools
│   ├── captcha.py            # DOM-based captcha recognition (ddddocr)
│   ├── file_read.py          # File reading tool
│   ├── file_write.py         # File writing tool
│   ├── format_convert.py     # Format conversion (CSV/JSON/Excel)
│   └── _path_utils.py        # Path utility helpers
│
├── llm/                      # LLM client layer
│   ├── client.py             # LLM client (OpenAI-compatible)
│   └── messages.py           # Message construction / parsing
│
├── prompts/                  # Prompt templates (Markdown)
│   ├── chat/system.md        # Chat mode system prompt
│   ├── eval_agent/system.md  # Eval Agent system prompt
│   ├── guidance/             # Strategy / recovery guidance
│   ├── guardrails/           # Guardrail prompts
│   ├── skill/                # Skill prompts (goal-execution, etc.)
│   ├── planner-plan.md       # Planner plan prompt
│   ├── planner-expand.md     # Planner expand prompt
│   ├── replan-on-failure.md  # Recovery replan prompt
│   ├── generate-handler.md   # Handler generation prompt
│   └── _loader.py            # Prompt loader
│
├── params/                   # Persistent parameter management
│   ├── manager.py            # ParamManager (flat JSON config)
│
├── workspace/                # Workspace management
│   ├── manager.py            # WorkspaceManager
│   ├── version_manager.py    # Version snapshot management
│   └── path_guard.py         # Path security validation
│
├── cli/                      # CLI command implementations
│   ├── run.py                # ybu run
│   ├── serve.py              # ybu serve
│   └── logs.py               # ybu logs
│
├── utils/                    # Utility functions
│   ├── browser.py            # LLM creation / provider config
│   ├── tool_cdp.py           # Restricted CDP wrapper (for tool scripts)
│   ├── logging.py            # Logging configuration
│   ├── skill_loader.py       # Skill file loading
│   └── response_logger.py    # Response logging
│
├── tests/                    # Unit & integration tests
│   ├── conftest.py           # Pytest fixtures / shared setup
│   ├── fixtures/             # Test fixture data
│   ├── test_agent.py         # Agent module tests
│   ├── test_api_routes.py    # API endpoint tests (REST + WebSocket)
│   ├── test_runner.py        # Chat runner tests
│   ├── test_runner_preset.py # Preset runner tests
│   ├── test_registry.py      # ToolRegistry tests
│   ├── test_planner.py       # Planner tests
│   ├── test_conversation_loop.py  # Conversation loop tests
│   ├── test_tool_executor.py # Tool executor tests (shared_store)
│   ├── test_progressive.py   # Progressive snapshot tests
│   ├── test_a11y_snapshot.py # A11y snapshot tests
│   ├── test_ops.py           # Browser ops tests
│   ├── test_param_resolver.py # Param resolver tests
│   ├── test_compiler_*.py    # Compiler (parser/graph/resolver/diff/generator)
│   ├── test_pipeline_tools.py
│   ├── test_delivery.py / test_events.py / test_state.py
│   ├── test_scratchpad.py / test_step_machine.py
│   ├── test_turn_context.py / test_iteration_budget.py
│   ├── test_file_io.py / test_format_convert.py
│   ├── test_path_guard.py / test_version_manager.py / test_workspace_manager.py
│   ├── test_harness_tools.py / test_pipeline_task_adapter.py
│   ├── test_retry_utils.py / test_error_classifier.py
│   ├── test_tool_guardrails.py / test_todo_store.py
│   ├── test_run_check.py / test_exact_match.py / ... (50+ test files)
│
├── electron/                 # Electron desktop frontend
│   └── src/
│       └── renderer/         # React + Vite + Monaco Editor (diff editor support)
│
└── docs/                     # Documentation
    └── architecture-overview.md  # Full architecture deep-dive (this file)
```

---

## Two-Layer Architecture

The system is composed of **two independent engines**:

### Upper Layer: Orchestration Engine

The LLM (external model) makes decisions; the orchestration layer assembles context and manages tool execution.

```
LLM (deepseek-chat / gpt-4o, etc.)
     │
     │ LLM call (system prompt + conversation history + tool registrations)
     ▼
conversation_loop ──→ tool_executor ──→ executor core (browser/tool/goal)
     │                     │
     │                     └── scratchpad (heavy data cache)
     │
     └── returns LLM response / tool results
```

Core concepts:
- **Heavy data never enters messages**: Browser HTML, screenshots, element lists, etc., go through `scratchpad` in-memory cache; the LLM only sees summaries
- **Orchestration layer assembles context**: each turn keeps only necessary context, never appends all tool output to messages
- **LLM makes decisions only**: which tool to call, with what arguments — the orchestration layer executes them

### Lower Layer: CDP Browser Control

```
ops.py                      # Logic layer — dispatches via BrowserBridge protocol
     │
     ▼
BrowserBridge (protocols.py) # Interface contract (playwright_bridge.py implements it)
     │
     ▼
PlaywrightBridge             # Unified driver — Playwright connect_over_cdp()
     │                          auto-wait / auto-scroll / auto-retry
     │                          + health check / process watcher / disconnect handling
     ▼
Chrome Browser (CDP)
```

---

## Two Execution Modes

### Mode 1: Chat Mode (Interactive)

User sends natural language messages in the frontend → Agent autonomously operates the browser → results stream back to the user in real-time.

**Call chain:**

```
POST /api/chat { message: "Open Baidu and search for coffee" }
  └→ service.process_chat_message()
       └→ run_conversation_loop()
            ├→ Load prompts/chat/system.md
            ├→ Inject tool_strategy guidance
            ├→ LLM call (with browser_*/goal_run/record_step/todo tools)
            ├→ LLM returns tool calls → tool_executor._execute_single_tool_call()
            │     ├→ browser_goto  → execute_browser_op("goto", …)
            │     ├→ browser_click → execute_browser_op("click", …)
            │     └→ record_step   → append to pipeline.yaml
            └→ LLM returns text → end turn
```

**Key features:**
- System prompt `chat/system.md` tells the LLM to "call record_step after each operation to record to the pipeline"
- LLM can use `goal_run` to set complex goals, then split into steps with `todo` and execute
- `record_step` appends to `workspaces/<name>/pipeline.yaml` after each operation
- Streaming events via WebSocket to frontend (turn_start/tool_start/text_chunk, etc.)
- Streaming LLM pushes reasoning content and text deltas in real-time
- **Configurable highlight mode**: a11y / progressive / off — set via API or Electron settings UI
- **Tool-to-tool data passing** via `shared_store` (template resolution `${}` / `_source_key`)
- **Pipeline context injection** in system prompt for agent workspace awareness

**Entry files:**
- `api/routes.py` → `POST /api/chat` route
- `api/service.py` → `process_chat_message()`
- `engine/agent.py` → `start_chat_agent()`, `_create_chat_llm_call()`
- `engine/runner.py` → `run_chat_loop()`
- `engine/_harness/conversation_loop.py` → `run_conversation_loop()`

---

### Mode 2: Preset Mode (Pipeline Replay)

Load an existing pipeline.yaml and let the Agent execute the pre-defined steps.

**Two execution paths:**

#### Path A: Legacy — StepMachine DAG Walk (runner_preset.py)

```
POST /api/run { pipeline: "..." }
  └→ routes.api_run()
       └→ run_pipeline() (from runner_preset.py)
            ├→ StepMachine(steps) — initialize DAG walker
            ├→ while not machine.is_done:
            │     ├→ approval gate (guardian)
            │     ├→ dispatch by step type:
            │     │     ├→ browser → execute_browser_step()
            │     │     ├→ goal    → execute_goal_step()
            │     │     └→ tool    → _execute_tool_step_with_guardian()
            │     ├→ check (programmatic verification)
            │     ├→ success → machine.end_step() → advance()
            │     ├→ failure → retry / recovery plan / abort
            │     └→ write _execution_tree.json
            ├→ version snapshot (VersionManager)
            └→ return RunContext
```

**Characteristics:**
- Fully deterministic execution — step definitions are explicit, LLM does not participate in decisions (except goal steps)
- `execute_browser_step` runs a `browser_ops` list sequentially
- `execute_tool_step` calls custom Python scripts from `tools/`
- `execute_goal_step` is a stub, effectively deprecated (delegated to chat-mode LLM)
- check fields support `url_contains / element_exists / text_contains / element_visible`
- Supports recovery planning (`RuntimePlanner`) — LLM analyses page state on failure and generates recovery steps
- Legacy `engine/executor.py` pipeline wrappers write files to step directories

#### Path B: New — Preset Loop (conversation_loop preset_mode)

```
run_preset_loop()
  ├→ PipelineTaskAdapter(step_defs, frontmatter).build_descriptor()
  │     → TaskDescriptor (pipeline name + step list + progress)
  ├→ load prompts/preset/system.md
  │     → inject {pipeline} placeholder (TaskDescriptor.format())
  │     + {tool_strategy} + {error_recovery}
  └→ run_conversation_loop(preset_mode=True)
       └→ LLM sees: "Pipeline: xxx | Steps: [pending] step_1 ..."
       └→ LLM uses browser_* tools to execute steps one by one
       └→ Summarises results when done
```

**Characteristics:**
- LLM "sees" the complete step list and decides execution order and approach
- System prompt `preset/system.md` is template-based, injecting pipeline description + strategy + recovery guidance
- `preset_mode=True` skips automatic `tool_strategy` injection (already loaded from preset prompt)
- More flexible than legacy deterministic execution but depends on LLM capability
- `record_step` is unnecessary (steps are pre-defined)

**Entry files:**
- `api/routes.py` → `POST /api/run` route (legacy)
- `engine/runner_preset.py` → `run_pipeline()` (legacy orchestrator)
- `engine/_harness/conversation_loop.py` → `run_preset_loop()` (new)
- `engine/_harness/pipeline_task_adapter.py` → `PipelineTaskAdapter`

---

## Shared Infrastructure

Both modes share the same infrastructure:

### Conversation Loop (`engine/_harness/conversation_loop.py`)

Core loop:
```
while budget.remaining > 0 and not interrupted:
    1. turn_context.build() — reset guardrails + retry counters
    2. assemble messages + system prompt
    3. LLM call (with registered tools)
    4. if tool_calls → tool_executor.execute()
       else → final_response = text, break
    5. check_exit_conditions() — budget/interrupt check
    6. budget.consume()
```

### Tool Registration (`engine/_harness/tools.py`)

All tool definitions (OpenAI-compatible function calling schemas):

| Category | Tool | Description |
|----------|------|-------------|
| **Browser** | `browser_goto` | Navigate to a URL |
| | `browser_click` | Click element by CSS selector |
| | `browser_fill` | Fill input field |
| | `browser_snapshot` | Page snapshot (progressive / a11y / raw) |
| | `browser_scroll` | Scroll the page |
| | `browser_source` | Get full page HTML |
| | `browser_eval` | Execute JavaScript |
| | `browser_get_element_by_number` | Get element details by selector |
| | `browser_expand_branch` | Expand folded progressive-snapshot container |
| **Goal** | `goal_run` | Set complex goal (execute via todo + browser_*) |
| **Recording** | `record_step` | Record an operation to pipeline.yaml |
| **Pipeline** | `pipeline_load/list/update_step/add_step/remove_step/create` | Manage and edit presets |
| **Tasks** | `todo` | Task list management |
| **Skill** | `skill` | Inject skill prompt into conversation |

### Executor (`engine/_harness/tool_executor.py`)

Unified routing for all tool calls:
- `browser_*` → `executor.execute_browser_op()` via `ops.py` → `BrowserBridge.click/goto/fill/etc.`
- `pipeline_*` → handler functions in `pipeline_tools.py`
- `goal_run` → returns a prompt message (LLM decomposes itself)
- `todo` → `todo.py` task management
- `skill` → `skill_tools.py` skill injection
- Others → `executor.execute_tool()` (registered via `ToolRegistry` from `tools/registry.py`)

**Shared Store** (`tool_executor._shared_store`):
- Runtime memory bus for tool-to-tool data passing
- Template resolution: `${step_name.output_path}` inline syntax
- Source key: `_source_key` parameter fetches previous step's output
- Used in both Chat and Preset modes for pipelined data flow

### CDP Snapshot Modes

Three snapshot modes are available, configured globally via `highlight_mode`:

1. **Progressive** (default auto-scan) — DOM walk with density-adaptive disclosure:
   - Two-phase: `CollectState` collects all interactive elements, `build_llm_view` builds a compact view
   - Semantic container detection (tags / class patterns / child count) for smart grouping
   - LLM sees at most 200 elements; dense containers are folded with an `expand_hint`
   - `expand_branch` tool browses folded containers with pagination
   - Query filtering: case-insensitive text/tag/role match
   - Region sampling (8 equal bands) replaces old container-based LLM limits
   - `prog_label` (`:nth-of-type` based) replaces `@ref` for LLM element lookups

2. **A11y** — Playwright Accessibility Tree:
   - Stamps DOM via CDP `AXTree` and maps `role=…` selectors
   - `@a_N` ref-based interaction removed; LLM uses `selector` directly
   - Works with locked / iframed / shadow-DOM rich pages

3. **Off** — no snapshot, raw `browser_source` only

Snapshots return `url` and `title` for context. Debug dump available via F8 shortcut (saves page HTML + screenshot).

### PlaywrightBridge Health & Lifecycle

- **Health check**: periodic CDP heartbeat (`page.evaluate("1+1")`) with retry; triggers disconnect on double failure
- **Process watcher**: monitors spawned browser subprocess; auto-disconnects on exit
- **Disconnect handling**: idempotent cleanup (flag-guarded); fires callback to `EngineState`
- **SSRF guard**: only `http://` / `https://` URLs allowed in `goto()`
- **Auto-scan**: calls `_progressive_snapshot()` on page load, navigation, frame navigated, and new tabs

### Shared Store (`engine/_harness/tool_executor.py` — `_shared_store`)

Runtime memory bus for tool-to-tool data passing:
- **Template resolution**: `${step_name.output_field}` — resolves parameter values from prior step outputs
- **Source key**: `_source_key` parameter in any tool — fetches data from a named step's output
- **eval_agent support**: inherits shared_store context; producer/consumer data flow
- Used in both Chat and Preset modes (preset loop passthrough)

### Three-Layer Execution Logic (`engine/executor.py` + `engine/ops.py`)

```
ops.py                          executor.py (pipeline wrappers)
────────                       ─────────────────────
execute_browser_op()  ───→     execute_browser_step()
execute_tool()        ───→     execute_tool_step()
execute_goal()        ───→     execute_goal_step()
```

- **Core functions** (`ops.py`): used by chat mode tool_executor via `BrowserBridge` — no disk writes, return plain result dicts
- **Pipeline wrappers** (`executor.py`): used by legacy preset mode — call core functions then write step.json + screenshot + page HTML
- **BrowserBridge protocol** (`cdp/protocols.py`): interface defining `goto/click/fill/snapshot/scroll/eval/expand_branch/etc.`. `PlaywrightBridge` is the implementation.

---

## Key Technical Decisions

### 1. No Sub-Agents

No longer spawn browser-use Agent as a sub-agent. `goal_run` remains as a mode switch signal, but instead of spawning a sub-agent, the main LLM uses `todo` + `browser_*` to break down and execute steps itself.

### 2. Heavy Data Goes to Scratchpad

Browser HTML (potentially tens of thousands of characters), element lists (hundreds), screenshot base64, etc., do not go directly into LLM messages. They are stored in the scratchpad; the LLM sees summaries. When needed, the LLM reads HTML via `browser_source(cached=true)` or gets element details via `browser_get_element_by_number(@e5)`.

### 3. Pipeline Three-Step Design

Each pipeline step has three optional phases:
- **goal** (Agent-driven phase / fallback reference) — describes the objective via `goal_description`
- **ops** (Preset execution phase / Agent reference) — specific `browser_ops` list
- **check** (Programmatic verification) — supports `url_contains / element_exists / text_contains / element_visible`

Preset replay executes ops first; if ops fail, falls back to goal for dynamic Agent decision-making; check is the new verification mechanism, independent of the execution path.

### 4. Chat + Browser Real-Time Sync

Users receive real-time event streams via WebSocket: `turn_start/tool_start/tool_end/chat.text_chunk/chat.think_chunk`, etc. This is the product form of "user watches the browser screen, issues commands, Agent operates autonomously".

### 5. Flat Provider Config

Configuration uses a flat `userdata/provider.json` JSON file — no environment variables / dotenv fallback. Built-in providers: deepseek, mimo, opencode-go.

### 6. Progressive Snapshot by Default

The progressive snapshot mode is the default auto-scan strategy. It walks the full DOM depth, applies density-adaptive disclosure to keep LLM context compact, and supports `expand_branch` for drilling into folded containers. Replaces the deprecated interactive snapshot mode.

### 7. PlaywrightBridge as Unified Driver

All browser operations go through `PlaywrightBridge` (`connect_over_cdp()`), which provides:
- Auto-wait / auto-scroll / auto-retry for all interaction ops
- Health check heartbeat to detect browser disconnection
- Subprocess watcher for isolated-mode browser cleanup
- Idempotent disconnect handling with callback notification
- SSRF guard on `goto()`
- Per-page element cache for multi-tab highlight support

### 8. Configurable Highlight System

Three highlight modes (a11y / progressive / off) switchable at runtime via API or Electron settings UI. The highlight injection uses a single bootstrap script (`_HIGHLIGHT_BOOTSTRAP`) rendered via Canvas overlay, with periodic guard refresh every 2 s.

---

## Data Flow Diagrams

### Chat Mode

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
                    │       │          │        + pipeline context
                    │       ▼          │
                    │  tool_executor ──│──→ scratchpad
                    │       │          │     shared_store
                    │       ▼          │
                    │  ops.py          │
                    │  (BrowserBridge) │  → PlaywrightBridge
                    │       │          │     (health check /
                    │       ▼          │      process watch /
                    │  tools/registry   │      disconnect handling)
                    │  (captcha/todo/   │
                    │   file_io/...)    │
                    └───────┬─────────┘
                            │
                            ▼
                     JSONResponse
                     {response, turn_count, …}
```

### Preset Mode (New)

```
Data               run_preset_loop()
                     │
StepDef[] ───────→ PipelineTaskAdapter.build_descriptor()
                     │  → TaskDescriptor (step list + progress)
                     ▼
                 prompts/preset/system.md
                     │  {pipeline} + {tool_strategy} + {error_recovery}
                     ▼
                 run_conversation_loop(preset_mode=True)
                     │  LLM sees step list
                     │  → browser_* tools execute each step
                     │  → shared_store passthrough for tool data flow
                     ▼
                 ConversationResult
```

---

## Key Design Principles

1. **Static before dynamic** — pipeline.yaml is a static contract, parsed and validated at compile time, minimising surprises at runtime
2. **Low coupling** — clear responsibility boundaries between engine / orchestration / CDP layers
3. **File as contract** — pipeline.yaml is both the artifact of Agent work and the basis for replay, versioned in the workspace
4. **Validation-first** — validate the immutable parts first, then handle dynamic LLM decisions
5. **Incremental development** — prefer incremental placeholders over fully complete implementations in one go
