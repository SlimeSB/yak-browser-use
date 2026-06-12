## ADDED Requirements

### Requirement: chat + 浏览器同步
系统 SHALL 支持 chat 交互与浏览器操作实时同步：
- 用户在 chat 界面输入自然语言指令
- Agent 在 conversation_loop 中自主调用浏览器工具执行
- 执行过程和结果实时反馈到 chat 界面
- 浏览器画面在应用中实时可见

#### Scenario: 用户指令触发浏览器操作
- **WHEN** 用户输入 "打开百度搜索咖啡机"
- **THEN** conversation_loop 启动
- **THEN** Agent 调用 browser_goto("https://baidu.com")
- **THEN** Agent 调用 browser_fill("搜索框", "咖啡机")
- **THEN** Agent 调用 browser_click("搜索按钮")
- **THEN** Agent 返回 "已打开百度并搜索了咖啡机"

### Requirement: 浏览器工具注册
系统 SHALL 注册以下浏览器工具供 Agent 调用：

- `browser_goto(url)` — 导航到 URL
- `browser_click(selector)` — 点击元素
- `browser_fill(selector, text)` — 填写输入框
- `browser_snapshot()` — 截图 + HTML 快照
- `browser_scroll(direction)` — 滚动页面（通过 `browser_eval("window.scrollBy(...)")` 实现）
- `browser_source()` — 获取页面源码
- `browser_eval(js)` — 执行 JS
- `goal_run(description)` — browser-use Agent 自主完成目标

#### Scenario: goal_run 保留 LLM 自主能力
- **WHEN** 任务需要 LLM 自主判断页面内容
- **THEN** Agent 可以选择调用 `goal_run("在页面中找到评分最高的商品")`
- **THEN** browser-use Agent 自主操作浏览器完成任务

### Requirement: chat 上下文保持
多次对话 SHALL 共享同一浏览器会话，用户可以在一次 session 中连续操作。

#### Scenario: 连续操作同一页面
- **WHEN** 用户先 "打开百度"，再 "搜索咖啡机"
- **THEN** 两次操作在同一浏览器标签页中执行
- **THEN** 第二次操作在搜索结果页面上进行

### Requirement: 多指令拆解
系统 SHALL 支持一句话包含多个指令，Agent 在 conversation_loop 中自主拆解并依次执行。

#### Scenario: 一句话多操作
- **WHEN** 用户输入 "打开百度搜索咖啡机，找到前5个结果，导出到桌面"
- **THEN** Agent 自主拆解为：goto → fill → click → extract → export
- **THEN** 每个操作作为一次 tool call 依次执行
- **THEN** 所有操作在同一 loop 中完成，无需用户分步输入

### Requirement: 模糊指令理解
当指令不明确时，Agent SHALL 基于上下文自主判断意图并执行，必要时向用户确认。

#### Scenario: 模糊指令自主判断
- **WHEN** 用户在当前页面上说 "帮我看看这个咖啡机怎么样"
- **THEN** Agent 调用 browser_snapshot() 获取当前页面内容
- **THEN** Agent 自主决定：提取商品信息、评分、价格
- **THEN** Agent 返回分析结果

#### Scenario: 无法判断时询问用户
- **WHEN** 指令有多个合理解释且上下文不足以判断
- **THEN** Agent 在 chat 中询问用户澄清

### Requirement: 单会话约束
系统 SHALL 保证一个浏览器实例同时只运行一个 conversation_loop。多会话并发不被支持。

- 新会话请求在旧会话未结束时 SHALL 被拒绝
- 用户必须先结束/取消当前会话才能开始新会话
- 提供"重置"按钮清空当前会话状态并开始新会话

**理由**: 多会话共享同一浏览器实例会导致标签页状态冲突、CDP session 竞争、cookie/存储污染。LBU 的定位是 pipeline 引导的单任务操作，不需要多会话并发。

#### Scenario: 拒绝并发会话
- **WHEN** 用户在一个活跃会话期间尝试创建新会话
- **THEN** 系统拒绝，提示"当前有任务正在执行，请先结束或取消"

#### Scenario: 重置开始新会话
- **WHEN** 用户点击"重置"
- **THEN** 当前 conversation_loop 被取消
- **THEN** 会话历史保存
- **THEN** 清空 messages 列表和浏览器标签页上下文
- **THEN** 开始全新会话

### Requirement: 浏览器生命周期
浏览器实例 SHALL 在应用启动时自动连接，整个应用生命周期共享一个实例。
- 启动时：调用现有 daemon/daemon.py 启动/连接 Chrome
- 新会话：在共享实例中开新标签页
- 关闭应用：断开 CDP 连接（不关闭 Chrome 进程，保留用户浏览器）
- 画面同步：通过 CDP `Page.captureScreenshot` 定时截屏推送前端

#### Scenario: 应用启动自动连接
- **WHEN** 用户打开 LBU 桌面应用
- **THEN** daemon 自动连接 Chrome（现有逻辑）
- **THEN** 用户无需手动操作即可开始 chat

#### Scenario: 多会话标签页隔离
- **WHEN** 用户开始新会话
- **THEN** 在共享浏览器中打开新标签页
- **THEN** 旧标签页保留（不关闭），可随时切换

### Requirement: 多标签页管理
系统 SHALL 管理共享浏览器实例中的多个标签页，支持 Agent 操作与用户手动切换共存。

- conversation_loop 绑定到当前激活的标签页（CDP targetId）
- 用户手动切换标签页时，CDP 事件通知 conversation_loop 更换绑定的 targetId
- Agent 的 tool call 在执行前 SHALL attach 到当前标签页的 CDP session
- 新会话创建时 SHALL 通过 `Target.createTarget` 开新标签页

#### Scenario: 用户手动切标签页后 Agent 操作正确
- **WHEN** Agent 正在操作标签页 A
- **THEN** 用户手动切换到标签页 B
- **THEN** 下一次 tool call 前 conversation_loop 检测到 targetId 变更
- **THEN** tool_executor attach 到标签页 B 的 CDP session
- **THEN** 后续操作在标签页 B 上执行

#### Scenario: 新会话开新标签页
- **WHEN** 用户创建新会话
- **THEN** 调用 `Target.createTarget` 打开新标签页
- **THEN** conversation_loop 绑定到新标签页

### Requirement: CDP 连接管理
系统 SHALL 处理 CDP WebSocket 连接的断开和重连，保证会话不丢失。

- CDP 连接断开时（WebSocket 关闭/超时）→ 自动尝试重连（3 次指数退避：1s / 2s / 4s）
- 重连成功后 → 重新 attach 到当前标签页，恢复操作
- 3 次重连全部失败 → 通知用户 "浏览器连接丢失"，保存当前会话状态
- 重连期间不消耗 iteration_budget（Agent 没有收到新信息，不产生 LLM 调用）

#### Scenario: CDP 短暂断开后自动恢复
- **WHEN** CDP WebSocket 意外断开
- **THEN** 系统自动尝试重连（1s / 2s / 4s 退避）
- **THEN** 重连成功后 conversation_loop 继续执行
- **THEN** 用户无需手动干预

#### Scenario: CDP 多次重连失败后通知
- **WHEN** CDP 重连 3 次全部失败
- **THEN** 系统通过 WebSocket 推送错误事件到前端
- **THEN** 前端显示 "浏览器连接丢失，请检查 Chrome 是否运行"
- **THEN** 会话状态保存，用户可稍后恢复
