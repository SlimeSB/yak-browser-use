# Learning Browser-Use

A clean, learnable browser automation framework based on browser-use, CDP, and browser-use Agent.

## Quick Start

```bash
# Install dependencies
install.bat

# Run CLI
python __main__.py --help

# Start Electron app
cd electron && npm run electron:dev
```

## Commands

| Command | Description |
|---------|-------------|
| `lbu run <path>` | Execute an agent.md pipeline |
| `lbu serve` | Start the REST API server |
| `lbu convert <path>` | Convert a document to agent.md format |
| `lbu chrome <subcommand>` | Chrome/Chromium management |
| `lbu param set/list/delete` | Persistent parameter management |
| `lbu pipeline <subcommand>` | Pipeline lifecycle management |
| `lbu daemon <subcommand>` | CDP daemon management |
| `lbu tool <subcommand>` | Tool debugging utilities |
| `lbu debug <subcommand>` | Debugging tools |

## Architecture

```
learning-browser-use/
├── cdp/          Chrome DevTools Protocol connection
├── engine/       Step execution engine (runner, executor, agent)
├── compiler/     agent.md compiler (parser, graph, generator)
├── converter/    NL-to-agent.md converter
├── params/       Persistent parameter store (JSON)
├── tools/        Tool registration and data tools
├── api/          FastAPI REST + WebSocket bridge
├── cli/          Command-line interface
├── workspace/    Pipeline workspace management
├── electron/     Electron desktop frontend
└── utils/        Shared utilities
```
