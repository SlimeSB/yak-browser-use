## Why

当前 `pipeline_update_step` 一次只能更新 pipeline 中的一个 step。当需要批量修改多个 step（如 step_1 改 browser_ops、step_2 改 description、step_3 改 browser_ops）时，Agent 要连续调用 3 次，每次加载/解析/写盘 pipeline.yaml 重复 3 遍，且 UI 会收到 3 次编辑事件。

本次变更将 `pipeline_update_step` 改造为支持字典格式的 `steps_updates`，一次调用完成多个 step 的更新。同时向后兼容旧的 `step_name` + `updates` 调用方式。

## What Changes

- `pipeline_update_step` 函数签名变更：主参数改为 `steps_updates: dict`（key=step_name, value=updates）
- 向后兼容：如果传旧的 `step_name` + `updates`，自动转换为 `{step_name: updates}` 格式
- 文件 IO 优化：一次加载、批量修改、一次写盘，减少到 1 次
- tool schema 更新：description 和 properties 说明新格式
- 批量错误收集：全部 step 更新尝试后统一返回错误信息

## Capabilities

### Modified Capabilities

- `pipeline-update-step`: 接口从单一 step 更新改造为支持批量字典格式，同时保留向后兼容

## Impact

- 文件：`backend/src/yak_browser_use/engine/_harness/pipeline_tools.py`
- 文件：`backend/src/yak_browser_use/tools/registry.py`（pipeline_update_step schema）
- `pipeline_update_step` 函数签名扩展（非破坏性，兼容旧调用方式）
- `pipeline_compile` 等调用方无需修改（因其走 registry dispatch，使用新 schema）
