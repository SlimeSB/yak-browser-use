# ACKNOWLEDGMENTS

yak-browser-use stands on the shoulders of these open-source projects. Every line of code we wrote was shaped by their ideas and craftsmanship.

---

## Actively Referenced

### [browser-use](https://github.com/browser-use/browser-use) — MIT
Agent API (`Browser(cdp_url=...)`), custom action registration via Tools, `history.model_actions()` operation extraction. The foundation of ybu's agent/tool architecture.

### [browser-use/browser-harness](https://github.com/browser-use/browser-harness) — MIT
CDP Daemon + Helpers architecture, `agent_helpers.py` hot-reload, `ensure_real_tab()` session recovery, coordinate-click priority, IPC design. The `_harness/` naming and orchestration skeleton originated here.

### [browser-use/web-ui](https://github.com/browser-use/web-ui) — MIT
LangGraph state-machine orchestration, human-in-the-loop interaction, CustomBrowser extension. ybu's runner design drew from its state-machine approach.

### [browser-use-desktop](https://github.com/browser-use/browser-use-desktop) — MIT
Electron desktop integration and frontend-backend IPC. Inspired ybu's Electron frontend architecture.

### [browser-use-terminal](https://github.com/browser-use/browser-use-terminal) — MIT
Terminal-based CLI interaction patterns and TUI presentation ideas.

### [Stagehand](https://github.com/browserbase/stagehand) — MIT
Natural-language `act/extract/observe` API, auto-caching invalidation, self-healing design. ybu's `browser_*` toolset was inspired by Stagehand's API semantics.

### [Stagehand Python SDK](https://github.com/browserbase/stagehand-python) — MIT
Python SDK architecture layering and API client design patterns.

### [Hermes Agent](https://github.com/nousresearch/hermes-agent) — MIT
Agent framework design, tool system, skill system. ybu's skill loader and tool registry reference Hermes' approach.

### [agent-browser](https://github.com/epical-ai/agent-browser) — Apache 2.0
CDP daemon architecture, snapshot system design, CLI interaction patterns. ybu's CDP connection management and DOM walk approach drew from this project.

### [agent-browser-cli](https://github.com/sleepinginsummer/agent-browser-cli) — MIT
CDP CLI interaction patterns and LLM-agent browser control workflow organization.

### [bb-browser](https://github.com/epical-ai/bb-browser) — MIT
Triple-connection CDP architecture (control/input/capture), protocol design, cross-session isolation patterns. Shaped ybu's CDP layer design.

---

## Previously Referenced, Now Deprecated

### [KWCode（铠悟代码）](https://github.com/val1813/kwcode) — No LICENSE (studied for learning, no code copied)
Deterministic expert pipeline architecture, error-strategy routing, cognitive gating. Early productor-bu error handling was influenced by this project; later ybu moved to tool self-healing + circuit breaker.

---

## Sibling Projects (Shared Design Language)

### [productor-sprite](./../productor-sprite/)
A sibling Electron + CDP automation project sharing CDP connection management, process health checks, overlay rendering, and other infrastructure patterns. ybu's proactive Edge disconnect detection (heartbeat + process waiter) was battle-tested here first.

---

## Declaration

All projects listed above are released under their respective licenses. yak-browser-use **referenced their design ideas and API patterns** and does not contain copied protected code. License copies are available in each project's original repository. If any reference is missing or improperly attributed, please contact the maintainers for correction.

Thank you to every open-source contributor. Your code lit the way.

---

## Contributors (Individuals)

- **daoyu0619-cyber** — <282251643+daoyu0619-cyber@users.noreply.github.com>

---

**中文版**

---

# 致谢

yak-browser-use 在设计和实现过程中参考了以下开源项目。每一行代码的背后都有这些项目的智慧沉淀。

---

## 活跃参考

### [browser-use](https://github.com/browser-use/browser-use) — MIT
Agent API 设计（`Browser(cdp_url=...)` 接入方式）、Tools 自定义 action 注册机制、`history.model_actions()` 操作提取模式。ybu 的 agent/tool 架构根基。

### [browser-use/browser-harness](https://github.com/browser-use/browser-harness) — MIT
CDP Daemon + Helpers 架构模式、`agent_helpers.py` 热加载机制、`ensure_real_tab()` session 恢复、坐标点击优先策略、IPC 设计。ybu 的 `_harness/` 命名和编排骨架源自这里。

### [browser-use/web-ui](https://github.com/browser-use/web-ui) — MIT
LangGraph 状态机编排模式、人在回路交互设计、CustomBrowser 继承扩展模式。ybu 的 runner 设计参考了其状态编排思路。

### [browser-use-desktop](https://github.com/browser-use/browser-use-desktop) — MIT
Electron 桌面集成模式、前后端 IPC 架构。ybu 的 Electron 前端设计受此启发。

### [browser-use-terminal](https://github.com/browser-use/browser-use-terminal) — MIT
终端 CLI 交互模式、agent-browser TUI 呈现思路。

### [Stagehand](https://github.com/browserbase/stagehand) — MIT
自然语言 `act/extract/observe` API 设计、auto-caching 失效检测机制、self-healing 设计理念。ybu 的 `browser_*` 工具集设计受其 API 语义启发。

### [Stagehand Python SDK](https://github.com/browserbase/stagehand-python) — MIT
Python SDK 架构分层、API 客户端设计模式。

### [Hermes Agent](https://github.com/nousresearch/hermes-agent) — MIT
Agent 框架设计、工具系统、技能系统。ybu 的 skill loader、tool registry 参考了 Hermes 的设计。

### [agent-browser](https://github.com/epical-ai/agent-browser) — Apache 2.0
CDP 守护进程架构、snapshot 系统设计、CLI 交互模式。ybu 在 CDP 连接管理和 DOM walk 方面参考了其实现。

### [agent-browser-cli](https://github.com/sleepinginsummer/agent-browser-cli) — MIT
CDP 命令行交互模式、LLM-agent 浏览器控制的工作流组织。

### [bb-browser](https://github.com/epical-ai/bb-browser) — MIT
CDP 三连接架构（control/input/capture）、协议设计、跨会话隔离模式。ybu 的 CDP 层设计受此启发。

---

## 曾经参考，现已弃用

### [KWCode（铠悟代码）](https://github.com/val1813/kwcode) — 无 LICENSE（仅参考学习，未引用代码）
确定性专家流水线架构、错误策略路由、认知门控。早期的 productor-bu 错误治理机制受其影响，后续 ybu 改用工具自愈 + circuit breaker 模式。

---

## 兄弟项目（共享设计语言）

### [productor-sprite](./../productor-sprite/)
同源的 Electron + CDP 自动化项目，共享 CDP 连接管理、进程健康检查、高亮渲染等基础设施模式。ybu 的 Edge 进程退出的主动断线检测（心跳 + process waiter）来自此项目的经验验证。

---

## 声明

以上项目均在各自许可证条款下发布。yak-browser-use **参考了其设计思路和 API 模式**，未直接复制受保护代码。每个项目的许可证副本可在其原始仓库中找到。如有遗漏或不当引用，请联系项目维护者更正。

感谢所有开源社区的贡献者，你们的代码照亮了我们的路。

---

## 贡献者（个人）

- **daoyu0619-cyber** — <282251643+daoyu0619-cyber@users.noreply.github.com>
