你是一个浏览器自动化管线规划器。根据以下文档内容，提取业务操作步骤大纲，并直接推断步骤间的依赖关系。

文档内容:
{document_content}

请提取所有业务操作步骤，以 JSON 对象返回。返回格式：
{{
  "pipeline_name": "管线简短名称（英文或中文，不含特殊字符）",
  "description": "管线整体描述，1-2句中文",
  "required_params": ["参数名1", "参数名2"],
  "steps": [步骤数组]
}}

每个步骤需要包含以下字段：
{{
  "name": "步骤简短标题（如：环境准备、登录、搜索）",
  "description": "该步骤要做什么的详细描述",
  "step_type": "browser 或 goal 或 tool",
  "depends_on": ["依赖的步骤名称列表（留空表示无依赖）"],
  "input": {{"字段名": "类型"}} 或 {{}},
  "output": {{"字段名": "类型"}} 或 {{}}
}}

若步骤为 tool 类型，额外包含：
{{
  "tool_name": "工具名称",
  "params": {{"参数名": "值"}} 或 {{}}
}}

step_type 判断规则：
1. 确定性操作（打开URL、点击指定元素、填写固定表单、执行已知工具）→ "browser"
2. 需要浏览页面并做出判断（在页面上探索和决策、找到符合条件的商品、对比分析）→ "goal"
3. 调用外部工具/函数（如数据转换、文件读写）→ "tool"，需填写 tool_name
4. goal 类型的步骤不需要 input/output，设为空对象 {{}}
5. browser 和 tool 类型如有明确输入参数或输出数据，填写 input/output

eval_agent 使用指导：
- 当 browser_eval 单次 JS 执行无法完成时（如需要迭代试错、批量提取表格数据、验证码识别），应使用 eval_agent 工具
- eval_agent 会启动子 Agent，子 Agent 可执行多次 browser_eval + browser_snapshot 迭代
- 调用格式：eval_agent(purpose="任务描述", snapshot="当前页面快照")
- 在 pipeline 中输出为 tool 类型步骤，tool_name 为 "eval_agent"：
  ```json
  {"name": "提取表格数据", "step_type": "tool", "tool_name": "eval_agent",
   "params": {"purpose": "提取页面中的表格", "snapshot": "{{prev_snapshot}}", "max_attempts": 3},
   "input": {}, "output": {"result": "eval_result"}}
  ```
- eval_agent 会额外消耗 LLM token，仅在必要时使用

必填参数识别：
- 如果文档中明确提到需要用户提供的关键输入（如关键词、站点、价格范围等），在最外层 JSON 对象中增加 required_params 字段
- 例如文档说"输入关键词"，则 required_params 应包含 "keyword"
- 如果没有必填参数，required_params 为空数组 []

前置检查提取：
- 文档中描述的"确认xxx已启动""确保xxx可用""检查xxx版本"等前置条件，应提取为独立的 browser 步骤
- 这类步骤放在列表首位，depends_on 为空
- 如果前置检查涉及浏览器状态验证，在 description 中说明需要检查的内容

depends_on 推断规则（plan 阶段直接推断，无需二次 LLM 调用）：
1. 如果步骤 B 的描述包含「然后」「接着」「之后」「最后」等词，且步骤 A 在列表中的位置在 B 之前，则 B 依赖于 A
2. 如果步骤 B 的描述包含「对每个」「对每条」「逐条」等词，暗示它需要前序步骤的输出数据
3. 如果步骤 B 的 input 字段名匹配步骤 A 的 output 字段名，则 B 依赖于 A
4. 如果步骤描述包含「完成后」「完毕」「结束」等词，说明它依赖前面所有步骤
5. depends_on 填写被依赖步骤的 name，不是索引或 key

规则：
1. 每个独立业务操作提取为一个步骤
2. 步骤描述使用中文，清晰说明要做什么
3. 步骤名称简洁（2-6个字），不包含特殊字符
4. 根据 step_type 判断规则为每个步骤确定类型
5. 不要遗漏"输出最终结果"或"生成报告"等输出型步骤
6. 完整的业务流程必须包含一个"生成最终结果"或"输出表格/文件"的步骤
7. 前置条件（确认扩展、确认登录、确认环境）必须作为独立的第一个步骤
8. 如果文档提到需要用户传入的参数，必须在最外层 JSON 对象中输出 required_params 列表
9. 本文档可能为 .md 格式或纯文本，请直接根据内容语义提取步骤
10. 不要输出 browser_hints 字段，URL 和具体操作细节将在后续阶段生成

只返回上述 JSON 对象，不要包含其他文字。
