## 背景

当前 system 中已经存在完整的变量传递基础设施：

1. **`shared_store`（dict）**：存在于 `ToolContext` 和 pipeline runner 的 `run_pipeline()` 中，跨 turn 存活
2. **`resolve_params()`**（`engine/_param_resolver.py`）：已有 `{*path}` 和 `${path}` 模板解析能力
3. **`bind` 机制**（`tool_executor.py:238-240`）：pipeline 模式下 `_execute_single_tool_call` 会从 args 中 pop `bind` 并将结果存入 `shared_store`
4. **`ToolContext.shared_store`**：chat 模式和 pipeline 模式都有实例

但问题在于：
- `browser_eval_js` 的 schema 没有暴露任何变量绑定参数，handler 只返回 `{"ok": True, "result: ...}`
- `file_write` 的 schema description **已有** `{key}` 模板语法描述（registry.py:578），但 **handler 从未实现** 模板替换逻辑
- `format_convert` 的 `_format_convert_handler`（registry.py:854-864）只做格式嗅探返回信息，**从未调用真正的 `format_convert()` 函数**——这是已有 bug
- `format_convert` 只接受文件路径，不接受内存数据
- Agent 不知道 `shared_store` 的存在

**约束**：
- 必须完全向后兼容，现有 pipeline 和 chat 行为不受影响
- `shared_store` 的 dict 结构已经是 `{step_name: {ok, data}}`（pipeline 模式）或 `{key: value}`（简化模式），新变量存入不得冲突
- 模板语法必须统一：`{key}`（不用 `{*key}` 或 `${key}`），理由见"决策 2"

## 目标 / 非目标

**目标：**
- Agent 能够将 `browser_eval_js` 的结果存入命名变量（`output_to` 参数）
- Agent 能够在 `file_write` 的 content 中通过 `{key}` 引用已存变量
- Agent 能够将内存中的 JSON 数据直接转为目标文件（CSV/XLSX）
- 修复 `_format_convert_handler` 不调用 `format_convert()` 的 bug
- 所有功能在 chat 模式和 pipeline 模式均可用

**非目标：**
- 不做通用的"变量浏览器"UI
- 不做跨 session 持久化（变量只在当前 session 内存活）
- 不修改 shared_store 的现有 pipeline 语义（step_name → {ok, data} 结构保持不变）
- 不做 type-aware 自动序列化选择（统一用 `json.dumps()` 序列化）

## 关键决策

### 决策 1：eval_js 使用 `output_to` 而非复用 `bind`

虽然 `tool_executor.py` 已有 `bind` 机制（pop 参数 → shared_store[source_key]），但 `output_to` 更明确：
- `bind` 在 `tool_executor.py` 中被 pop 掉，handler 不知道发生了绑定
- `output_to` 让 handler 感知到变量存续，可以做后续处理（如 `_output_to` 标记在返回中）
- 两者独立存在，pipeline 模式的 bind 机制不改变

**实现位置**：`tools/registry.py` 的 `_eval_js_handler` 内部处理 `output_to`

### 决策 2：file_write 模板语法统一为 `{key}`

**背景**：registry.py:578 的 schema description 已经写了 `{key}` 语法。`_param_resolver.py` 里有 `{*path}` 和 `${path}` 语法。为避免混乱，file_write 使用与 schema description 一致的 `{key}`。

**不使用 `resolve_params()` 的原因**：
- `resolve_params` 专为 pipeline 的 `${path}` 递归解析设计，会误解析 `$` 开头的文本
- file_write 只需要最简单的单变量替换（`{key}` → value），不需要递归
- 正则 `re.compile(r'\{(\w+)\}')` 轻量且易于维护

**实现策略**：
- 正则匹配所有 `{word}` 模式
- 仅在 `shared_store` 中存在该 key 时才替换
- 找不到时保留原文 `{key}` 并在返回中加 `_warnings` 字段
- 替换值统一用 `json.dumps(value, ensure_ascii=False)` 序列化

### 决策 3：format_convert handler 修复 + source_json 扩展

**Bug 修复**：`_format_convert_handler`（registry.py:854-864）当前只做 `_sniff_format()` 返回格式信息，改为调用真正的 `format_convert()` 函数。

**source_json 扩展**：在 `format_convert()` 函数签名中增加可选参数 `source_json: Any = None`，当提供时跳过从文件读取，直接根据 `target_fmt` 分流到对应的序列化函数。

**不包装临时文件的原因**：
- 避免不必要的文件系统 I/O
- 保留 `source` 文件不存在的错误语义
- 减少临时文件清理的复杂度

## 风险 / 权衡

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| shared_store 变量名与 pipeline step 名称冲突 | 数据被覆盖 | 不做特殊处理，文档说明 Agent 应使用语义明确的变量名 |
| file_write 模板替换误匹配 | 含 `{xxx}` 的文本被意外替换 | 只在 `shared_store` 中找到对应 key 时才替换，否则保留原文 |
| CSV 格式化不支持复杂嵌套 JSON | 数据丢失或格式错乱 | 超过 1 层嵌套的字段序列化为 JSON 子字符串（`json.dumps`） |
| format_convert handler 修复改变了行为 | 依赖当前"只返回信息"行为的代码可能受影响 | 检查所有调用方（无——handler 只被 chat/pipeline 工具调用器使用，且当前行为是 bug） |

## 迁移计划

1. **实现阶段**：先修 bug（task 1.1），再加新特性（task 2.x），最后修正 schema 描述（task 3.x）
2. **测试覆盖**：每个新增参数都有对应测试用例，format_convert handler 修复有回归测试
3. **Schema 更新**：registry schema 变更自动生效（动态加载）
4. **回滚策略**：所有新参数可选，旧调用路径不变，直接回滚代码即可

## 待确认问题

- 无（方案已完全确定）
