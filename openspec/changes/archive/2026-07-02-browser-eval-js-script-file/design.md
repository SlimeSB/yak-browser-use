## 背景

`browser_eval_js` 当前只支持 `code` 参数传递 JS 代码字符串。当代码量超过 10 行时，JSON 字符串拼接和转义成本很高。Playwright bridge 的 `evaluate()` 方法接收原始 JS 字符串，ToolRegistry 中的 handler 已经负责错误捕获和格式化。

Workspace 文件写入已有 `file_write` 工具支持，配合 `validate_path` 可以安全限制在 workspace 目录内。

## 目标 / 非目标

**目标：**
- 在 `browser_eval_js` 中新增 `script_file` 可选参数，支持从 workspace 路径读取 JS 代码
- 更新 tool description，增加 `return` 语法提示和 `script_file` 用法
- 保持 100% 向后兼容（`code` 参数行为不变）

**非目标：**
- 不引入 TypeScript 编译（避免额外运行时开销）
- 不新增专门工具，仅扩展现有 schema
- 不改变 `evaluate()` 底层逻辑

## 关键决策

**为什么用 `script_file` 而不是改进 `code` 参数：**
- `script_file` 是可选扩展，不影响现有调用
- Agent 可以先 `file_write` 写 JS 文件（多行编辑体验好），再 `browser_eval_js(script_file=...)` 调用
- 如需修改脚本，只需重新 `file_write` + 再次调 `browser_eval_js`

**路径安全：**
- 复用 `validate_path(file, pipeline=ctx.pipeline_name)`，限制在 workspace 安全目录内（和 `file_write` 一致）
- 不允读系统路径或上级目录穿越

**为什么不用 TypeScript：**
- Playwright `evaluate()` 原生只接受 JS 字符串
- 编译层增加 ~100ms 开销和维护负担
- 当前痛点是字符串转义痛苦，不是类型安全

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| `script_file` 文件存在但路径越过 workspace | `validate_path` 统一校验，失败返回明确 error |
| 文件读取编码问题 | 用 `utf-8` 读取，和 `file_write` 对应 |
| LLM 不知道新增参数 | description 中明确说明 + 给示例 |

## 迁移计划

1. 修改 `registry.py` 中 `_eval_js_handler` 逻辑和 `browser_eval_js` schema
2. 运行 `test_registry.py` 确认不破坏现有测试
3. 无需数据迁移（纯行为扩展）

## 待确认问题

无
