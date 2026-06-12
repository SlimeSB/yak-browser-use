## ADDED Requirements

### Requirement: Prompt 文件管理
系统 SHALL 将 system prompt 存放在独立的 `prompts/` 目录，通过 `prompts/_loader.py` 按需加载。

prompts/ 目录结构：
```
prompts/
├── _loader.py              — prompt 加载器（支持 {variable} 模板）
├── chat/
│   └── system.md           — chat 模式 system prompt
├── preset/
│   └── system.md           — 预设回放模式 system prompt（含 {pipeline} 变量）
├── guardrails/
│   ├── exact_failure.md    — 同参数重复失败警告 {tool_name} {count}
│   ├── same_tool_failure.md — 同工具重复失败警告 {tool_name} {count}
│   └── no_progress.md      — 幂等工具无进展警告 {tool_name} {count}
└── guidance/
    ├── tool_strategy.md    — 工具选择策略（原子工具优先，goal_run 何时使用）
    └── error_recovery.md   — 错误恢复指导（Agent 遇到工具失败时如何诊断）
```

#### Scenario: 加载 chat 模式 prompt
- **WHEN** 用户通过 chat 界面启动新会话
- **THEN** `_loader.load("chat/system")` 加载对应 prompt
- **THEN** prompt 注入 conversation_loop 的 system message

### Requirement: Prompt 模板变量
prompt 文件 SHALL 支持 `{variable}` 模板变量，通过 `_loader.load(name, **vars)` 传入。

模板替换策略 SHALL 为白名单变量的自定义替换（非 `str.format()`），避免 prompt 中自然出现的 `{}` 字符导致 KeyError：
```python
def load_prompt(name: str, **variables: str) -> str:
    text = _PROMPTS_DIR.joinpath(name).with_suffix(".md").read_text()
    for key, value in variables.items():
        text = text.replace(f"{{{key}}}", value)
    return text
```

仅显式传入的变量名被替换，未传入的 `{other}` 保持原样，不触发错误。

#### Scenario: 注入 pipeline 描述
- **WHEN** 预设回放模式
- **THEN** `_loader.load("preset/system", pipeline=task_descriptor)`
- **THEN** prompt 文件中 `{pipeline}` 被替换为 TaskDescriptor.format() 的输出
- **THEN** prompt 中的其他 `{文字}` 不受影响

#### Scenario: 未传入的变量保持原样
- **WHEN** prompt 文件包含 `{some_placeholder}` 但调用时未传入
- **THEN** `{some_placeholder}` 保持原样出现在输出中
- **THEN** 不抛出异常

### Requirement: 禁止硬编码文本
conversation_loop 及其子模块 SHALL 不包含任何面向 Agent 的自然语言指导文本。以下文本必须从 `prompts/` 加载：

| 文本类型 | 来源文件 | 调用点 |
|---------|---------|--------|
| 系统级 instruction | `prompts/chat/system.md` | conversation_loop 启动 |
| Guardrail 警告消息 | `prompts/guardrails/*.md` | tool_executor → after_call() |
| 工具选择策略 | `prompts/guidance/tool_strategy.md` | 注入 system prompt |
| 错误恢复指导 | `prompts/guidance/error_recovery.md` | tool_executor 工具失败时注入 |
| 预设 task 描述 | `prompts/preset/system.md` | 预设回放模式启动 |

代码中仅允许出现 `_loader.load("guardrails/exact_failure", tool_name="browser_click", count=5)` 这样的加载调用，不允出现内联的 f-string 或字符串常量。

#### Scenario: guardrail 警告从文件加载
- **WHEN** Agent 同参数失败 5 次触发 exact_failure warn
- **THEN** `_loader.load("guardrails/exact_failure", tool_name="browser_click", count=5)`
- **THEN** 返回 "browser_click with these exact arguments has failed 5 times this turn. Before retrying, consider: 1) inspect the latest error 2) verify the selector exists 3) try snapshot() to check page state."
- **THEN** 该文本追加到 tool result 末尾

#### Scenario: 错误恢复指导注入
- **WHEN** tool_executor 返回工具执行错误到 messages
- **THEN** `_loader.load("guidance/error_recovery")` 注入到下一轮 system message 的扩展段
- **THEN** Agent 看到指导后优先做诊断而非盲重试

#### Scenario: 禁止代码内硬编码
- **WHEN** 审查 conversation_loop、tool_executor、tool_guardrails 代码
- **THEN** 不存在 `f"Please try..."` / `"Hint: ..."` / `"Consider using..."` 等自然语言字符串
- **THEN** 所有此类文本从 `prompts/` 文件加载
