# Yak Browser-Use

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
| `ybu run <path>` | Execute an agent.md pipeline |
| `ybu serve` | Start the REST API server |
| `ybu convert <path>` | Convert a document to agent.md format |
| `ybu chrome <subcommand>` | Chrome/Chromium management |
| `ybu param set/list/delete` | Persistent parameter management |
| `ybu pipeline <subcommand>` | Pipeline lifecycle management |
| `ybu daemon <subcommand>` | CDP daemon management |
| `ybu tool <subcommand>` | Tool debugging utilities |
| `ybu debug <subcommand>` | Debugging tools |

## Architecture

```
yak-browser-use/
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
