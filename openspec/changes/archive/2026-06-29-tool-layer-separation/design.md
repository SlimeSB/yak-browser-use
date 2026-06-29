## 背景

当前工具系统按功能分散注册在 `tools/registry.py` 中，共 38 个工具，无分层概念。存在以下问题：

1. **数据工具可写 pipeline 文件**：`file_write` 接受任意相对路径，可覆盖 `pipeline.yaml`，绕过 `edit_pipeline` 的 checkpoint / diff / WebSocket push 安全网。
2. **工具边界模糊**：`file_read` 带有 head/max_chars/编码检测等智能逻辑，`format_convert` 直接暴露给 LLM，偏离"数据工具 simple & stupid"原则。
3. **子 Agent 冗余**：`eval_agent` 启动独立 LLM 循环，但主 Agent 已有 `eval_js` + `browser_snapshot`，实际使用率和效果均不佳。
4. **工具名不统一**：`eval_js` 和 `wait_for_download` 需要浏览器上下文但无 `browser_` 前缀，`record_step` 与 `pipeline_add_step` 功能重叠。
5. **pipeline_load 返回不完整**：仅返回 `browser_op_count` 而非完整 ops 列表，LLM 需要先 `file_read` pipeline.yaml 才能看到完整内容。
6. **pipeline_update_step 粒度过粗**：修改一个 browser_op 值需重传整个 `browser_ops` 列表。

## 目标 / 非目标

**目标：**
- 建立三层工具架构：Agent 工具 / Browser ops / 内部数据工具
- LLM 不可调用内部数据工具（`file_read`、`file_write`、`format_convert`）
- `file_write` 限定 workspace 子目录，杜绝覆盖 pipeline.yaml
- 合并语义重叠的工具，统一命名规范
- `pipeline_update_step` 支持深路径 patch，减少 token 消耗
- `pipeline_load` 返回完整 `browser_ops` 列表
- 新增 `read_data` 作为 Agent 统一数据入口

**非目标：**
- 不引入 YAML 文本模糊匹配（raw patch mode）
- 不改动 browser_* 原子操作（goto、click、fill 等）
- 不改动 skill_*、todo、goal_run、captcha 工具
- 不改动 shared_store 数据流通机制
- 不改动 WebSocket 推送格式

## 关键决策

### 决策 1：三层架构而非两列

原计划将工具分为"Agent 工具"和"数据处理工具"两列。讨论后确定 `file_read` 和 `format_convert` 本质上已具备智能限制（head 截断、编码检测、格式推断），属于 Agent 保护 LLM 的逻辑。真正 "simple & stupid" 的只有 `file_write`。

最终架构为三层：

```
Agent 工具（LLM 可调）              Browser ops（需 CDP）          底层工具（仅返元信息）
pipeline_view                      browser_goto / click / ...     file_read
pipeline_add_step                  browser_eval_js               file_write（+沙箱）
pipeline_update_step               browser_wait_for_download     format_convert
pipeline_remove_step
pipeline_create
pipeline_compile
read_data（唯一返全文）
```

**原因**：`eval_js` 和 `wait_for_download` 依赖 CDP 上下文，与 browser_* 同质。Agent 工具管理 pipeline 和数据入口。底层工具对 LLM 可见（编写 pipeline YAML 时需引用 `tool_name: file_write`），但仅返回元信息 —— `read_data` 是唯一返回文件全文内容的通道。

### 决策 2：底层工具仅返回元信息

`file_read`、`file_write`、`format_convert` 全部保留在 registry，LLM 可调用但仅返回元信息：

| 工具 | 返回值 |
|---|---|
| `file_read` | `{"ok": True, "path": "...", "size": ..., "encoding": "..."}` |
| `file_write` | `{"ok": True, "path": "...", "size": ...}` |
| `format_convert` | `{"ok": True, "source": "...", "target": "...", "source_fmt": "...", "target_fmt": "..."}` |

`read_data` 是唯一可返回文件全文内容的工具。**原因**：LLM 需要知道这些工具存在以编写 pipeline YAML（`tool_name: file_write`），但不能通过它们绕开 `read_data` 的渐进式披露保护。

### 决策 3：沙箱放在 handler 层而非工具函数层

`file_write` 的沙箱限制（不可写 workspace 根目录）放在 `_file_write_handler`（registry.py）中实现，而非修改 `file_write` 函数本身。

**原因**：Agent 工具内部需要通过 `file_write` 写调试产物时，直接 import 调用不进 handler，不受沙箱限制。两层区分：

| 路径 | 谁调 | 沙箱生效 |
|---|---|---|
| LLM → handler → file_write | LLM | ✓ |
| Agent 工具 → import → file_write | 内部代码 | ✗ |

### 决策 4：read_data 内部串联 file_read + format_convert

`read_data` 是 Agent 唯一的数据读取入口。内部逻辑：
1. 调 `file_read` 读文件
2. 如果是二进制（xlsx 等），调 `format_convert` 转换
3. 应用 head/max_chars 截断
4. 返回文本

LLM 一个 `read_data` 调用完成读取+转换+截断，不需要知道内部机制。

### 决策 5：深路径 patch 格式

`pipeline_update_step` 的 `updates` 支持两种 value 格式：

```
// 深路径 patch — key 包含 [n]
{"browser_ops[2].text": "新值"}

// 全量替换 — value 是 list 或 object
{"browser_ops": [{...}, {...}]}
```

同一个 `updates` dict 中可混用。`PipelineStore.update_step` 按 key 格式自动判断策略。

**备选方案**：JSON Patch (RFC 6902) 或 JSON Merge Patch (RFC 7396)。放弃原因：
- RFC 6902 需要引入 `op` 字段增加复杂度
- RFC 7396 对数组操作支持弱
- 当前方案只覆盖实际需求（修改 browser_ops[n] 的某个字段），无需完整规范

### 决策 6：合并而非新增

`pipeline_load` + `pipeline_list` → `pipeline_view`（一个工具两种用法），而非同时保留。

`record_step` → `pipeline_add_step`（合并 op_type 参数），而非新增工具。

**原因**：减少 LLM 选择负担，一个概念一个工具。

### 决策 7：移除 eval_agent

`eval_agent` 子 Agent 需要独立 LLM 循环、独立 budget、独立 prompt，复杂度高但实际使用率低。主 Agent 已有 `browser_eval_js` + `browser_snapshot`，可自行迭代试错。数据流通走 `shared_store` 即可。YAGNI。

## 风险 / 权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| file_write 沙箱可能误伤合法写入 | 用户无法在 workspace 根目录写数据文件 | workspace 根目录仅供 pipeline 结构化文件使用，数据文件应在 `downloads/` 子目录 |
| pipeline_view 参数可选可能引起歧义 | LLM 可能混淆两种用法 | tool description 明确说明：无参返回列表，有 `name` 参数返回详情 |
| 深路径 key 解析复杂度 | `"browser_ops[2].text"` 解析可能出错 | 正则 `<key>\\[(\\d+)\\]\\.(.+)` 拆分，仅支持一层数组索引 + 一层字段，边界明确 |
| 移除 eval_agent 后复杂 DOM 操作不可用 | 某些场景主 Agent 迭代次数多 | 主 Agent 已有 browser_eval_js 的多轮能力，且 snapshot 提供元素引用 |
| 工具数量变化影响 LLM token 消耗 | 新增 read_data，移除 format_convert / eval_agent，净变化小 | 合并操作减少工具数，总体略减 |

## 迁移计划

1. **实现阶段**：按 tasks.md 顺序执行，每个 task 独立可测
2. **测试**：更新 `tests/test_registry.py`（工具数量断言）、`tests/test_pipeline_tools.py`（新行为）、`tests/test_file_io.py`（沙箱）
3. **回滚**：变更无数据迁移，直接 revert commit 即可恢复
4. **兼容性**：工具名变更（`eval_js` → `browser_eval_js`）为 **BREAKING**，已有 pipeline 中引用的 `eval_js` 需更新为 `browser_eval_js`

## 待确认问题

- 无。所有设计决策已在讨论中达成一致。
