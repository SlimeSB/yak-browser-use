## 1. 常量与核心函数

- [ ] 1.1 在 `playwright_bridge.py` 中新增 `_NON_INTERACTIVE_TAGS` frozenset（script、style、meta、link、br、hr、noscript、head、title、base、template、html、body）
- [ ] 1.2 在 `playwright_bridge.py` 中新增 `_SKIP_CHILDREN_TAGS` frozenset（svg、canvas）
- [ ] 1.3 重写 `_is_interactive_progressive`：默认返回 True，仅检查 `_NON_INTERACTIVE_TAGS` 和 `input[type=hidden]`
- [ ] 1.4 删除 `_is_interactive_progressive` 中的 onclick/tabindex/contenteditable 启发式检测
- [ ] 1.5 删除 `_is_interactive_progressive` 中的 div/span/li + data-v-/data-react- 启发式检测
- [ ] 1.6 删除 `_is_interactive_progressive` 中 `a[href]` 缺少 href 时排除的逻辑（黑名单下不再需要）
- [ ] 1.7 修改 `CollectState.walk()`：在子节点遍历前检查 `_SKIP_CHILDREN_TAGS`，跳过匹配标签的子节点递归

## 2. 测试更新

- [ ] 2.1 更新 `test_is_interactive_progressive`：4 个 case 从 False→True（a 无 href、div/span/li 裸标签），新增 script/style 黑名单 case
- [ ] 2.2 重命名 `test_collect_state_skips_non_interactive` 为 `test_collect_state_skips_blacklisted`，验证 script/style 被跳过
- [ ] 2.3 更新 `test_collect_state_marks_whitelist`：外层 root div 现在被捕获，elements_all 从 3→4，给 root 独立 backendNodeId 避免 ref 冲突
- [ ] 2.4 更新 `test_collect_state_container_stats`：body/div 本身变为 element，element_all 计数增加；total_descendants 不变
- [ ] 2.5 新增 `test_collect_state_skips_svg_children`：验证 svg 自身被收集但子节点不遍历
- [ ] 2.6 新增 `test_collect_state_skips_canvas_children`：验证 canvas 自身被收集但子节点不遍历

## 3. 验证与收尾

- [ ] 3.1 运行 `pytest backend/tests/test_progressive.py -v` 确保所有测试通过
- [ ] 3.2 运行 `pytest backend/tests/ -v` 确保无回归
- [ ] 3.3 运行 lint 检查确保代码风格一致
