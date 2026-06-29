## 1. 核心实现

- [ ] 1.1 在 `registry.py` 中创建 `_data_keys_handler(args, ctx)` — 读取 `ctx.shared_store`，遍历 key，返回 `{name, type, size}` 列表
- [ ] 1.2 在 `registry.py` 中创建 `_data_browse_handler(args, ctx)` — 读取 `ctx.shared_store[key]`，根据值类型分页输出（元素列表用 `_build_snapshot_summary` 格式，字符串截断，dict 用 keys + repr）
- [ ] 1.3 在 `registry.py` 的 `_build_registry_impl()` 中注册 `data_keys` 和 `data_browse` 两个工具（含 schema 定义）
- [ ] 1.4 将 `_build_snapshot_summary` 从 `tool_executor.py` 提取到公共模块（或通过 import 复用），供 `_data_browse_handler` 使用

## 2. 验证与收尾

- [ ] 2.1 运行 `python -c "from yak_browser_use.tools.registry import build_registry; build_registry(); print(registry.get_names())"` 确认两个工具已注册
- [ ] 2.2 编写 `tests/test_data_browse.py` 覆盖：data_keys 正常/空/None、data_browse 元素列表/字符串/dict/key不存在/超出范围/None
- [ ] 2.3 运行 `python -m pytest tests/test_data_browse.py -x -q` 确认全部通过
