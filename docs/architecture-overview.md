# Yak Browser-Use Architecture Overview

> Last updated: 2026-06-19

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
│   ├── state.py              # Global engine_state
│   └── errors.py             # API error types
│
├── engine/                   # Core execution engine ★
│   ├── agent.py              # Agent entry (chat mode entry + streaming LLM call)
│   ├── runner.py             # Chat mode runner (lightweight wrapper)
│   ├── runner_preset.py      # Preset mode runner (full pipeline orchestrator)
│   ├── executor.py           # Core executor (browser/tool/goal three-layer)
│   ├── scratchpad.py         # In-memory data cache (heavy data stays out of LLM context)
│   ├── delivery.py           # Delivery report generation
│   ├── state.py              # RunContext data class
│   ├── events.py             # EventSink event pipeline
│   ├── step_machine.py       # StepMachine (pipeline DAG walker)
│   ├── planner.py            # Runtime recovery planner
│   │
│   ├── _harness/             # Conversation loop infrastructure ★
│   │   ├── conversation_loop.py    # Core agent turn loop (shared by chat + preset)
│   │   ├── tools.py                # Tool definitions (browser_*/goal_run/record_step/pipeline_*/todo)
│   │   ├── tool_executor.py        # Sequential tool call dispatcher
│   │   ├── pipeline_tools.py       # pipeline_load/list/update/add/remove/create implementations
│   │   ├── pipeline_task_adapter.py # StepDef → TaskDescriptor (preset mode only)
│   │   ├── iteration_budget.py     # LLM turn budget control
│   │   ├── tool_guardrails.py      # Tool call guardrails
│   │   ├── turn_context.py         # Per-turn context (retry counters, etc.)
│   │   ├── error_classifier.py     # API error classification
│   │   └── retry_utils.py          # Retry utility functions
│   │
│   └── _lifecycle/           # Pipeline lifecycle management
│       ├── compensation.py   # Compensate / rollback logic
│       ├── guardian.py       # Approval gate
│       ├── tool_runner.py    # _PH- tool lifecycle
│       └── fallback.py       # Page state assessment
│
├── cdp/                      # Chrome DevTools Protocol layer
│   ├── helpers.py            # CDPHelpers (high-level browser operation wrappers)
│   ├── daemon.py             # CDP Daemon management
│   ├── discover.py           # Chrome discovery / connection
│   └── launcher.py           # Chrome launch
│
├── compiler/                 # Pipeline compilation
│   ├── models.py             # PipelineDef / StepDef data classes
│   ├── schema.py             # PipelineYaml / StepYaml Pydantic models
│   ├── parser.py             # YAML parser
│   └── resolver.py           # Dependency resolver
│
├── tools/                    # Custom tool scripts
│   ├── record_step.py        # record_step tool (LLM records steps to pipeline)
│   ├── todo.py / todo_store.py   # Todo task management tools
│   ├── edit_pipeline.py      # Pipeline editing tools
│   └── extract.py / data.py  # Data processing tools
│
├── prompts/                  # Prompt templates (Markdown)
│   ├── chat/system.md        # Chat mode system prompt
│   ├── preset/system.md      # Preset mode system prompt
│   ├── guidance/             # Strategy / recovery guidance
│   ├── guardrails/           # Guardrail prompts
│   └── skill/                # Skill prompts (goal-execution, etc.)
│
├── params/                   # Persistent parameter management
│   ├── manager.py            # ParamManager (replaces legacy credential system)
│
├── workspace/                # Workspace management
│   ├── manager.py            # WorkspaceManager
│   ├── version_manager.py    # Version snapshot management
│   └── path_guard.py         # Path security validation
│
├── cli/                      # CLI command implementations
│   ├── run.py / serve.py / chrome.py / ...
│
├── utils/                    # Utility functions
│   ├── browser.py            # LLM creation / provider config
│   ├── tool_cdp.py           # Restricted CDP wrapper (for tool scripts)
│   └── logging.py            # Logging configuration
│
├── assets/                   # Static assets
│   └── simplify-dom.js       # DOM simplification script (element numbering / summary)
│
└── openspec/                 # Design docs & specifications
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
executor.py                  # Logic layer — parses operation types, constructs params
     │
     ▼
cdp/helpers.py (CDPHelpers) # Protocol layer — CDP WebSocket calls
     │
     ▼
cdp_daemon (CDPDaemon)      # Transport layer — WS ↔ Chrome DevTools
     │
     ▼
Chrome Browser
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
- `record_step` appends to `userdata/workspaces/<name>/pipeline.yaml` after each operation
- Streaming events via WebSocket to frontend (turn_start/tool_start/text_chunk, etc.)
- Streaming LLM pushes reasoning content and text deltas in real-time

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
| | `browser_snapshot` | Page snapshot (interactive/full/simplified) |
| | `browser_scroll` | Scroll the page |
| | `browser_source` | Get full page HTML |
| | `browser_eval` | Execute JavaScript |
| | `browser_get_element_by_number` | Get element details by @eN |
| **Goal** | `goal_run` | Set complex goal (execute via todo + browser_*) |
| **Recording** | `record_step` | Record an operation to pipeline.yaml |
| **Pipeline** | `pipeline_load/list/update_step/add_step/remove_step/create` | Manage and edit presets |
| **Tasks** | `todo` | Task list management |

### Executor (`engine/_harness/tool_executor.py`)

Unified routing for all tool calls:
- `browser_*` → `executor.execute_browser_op()` (core logic, no file I/O)
- `pipeline_*` → handler functions in `pipeline_tools.py`
- `goal_run` → returns a prompt message (LLM decomposes itself)
- `todo` → `todo.py` task management
- Others → `executor.execute_tool()` (loads custom Python scripts from `tools/`)

### Scratchpad (`engine/scratchpad.py`)

**In-memory cache** for heavy browser data, never enters LLM messages:
- `store()` → stores URL/title/elements/element_map/summary
- `get_scratchpad().summary` → LLM sees "Page title: xxx | 15 interactive elements"
- `element_map` → `@e5` → CSS selector mapping
- `raw_html` → cached page HTML source

### Three-Layer Execution Logic (`engine/executor.py`)

```
Core functions (no file I/O)     Pipeline wrappers (write files)
─────────────────                ─────────────────────
execute_browser_op()  ───→       execute_browser_step()
execute_tool()        ───→       execute_tool_step()
execute_goal()        ───→       execute_goal_step()
```

- **Core functions**: used exclusively by chat mode tool_executor — no disk writes, return plain result dicts
- **Pipeline wrappers**: used by legacy preset mode — call core functions then write step.json + screenshot + page HTML

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
                    {response, turn_count, …}
```

### Preset Mode (New)

```
Data               run_preset_loop()
                    │
StepDef[] ───────→ PipelineTaskAdapter.build_descriptor()
                    │  → TaskDescriptor
                    ▼
                prompts/preset/system.md
                    │  {pipeline} placeholder substitution
                    ▼
                run_conversation_loop(preset_mode=True)
                    │  LLM sees step list
                    │  → browser_* tools execute each step
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
