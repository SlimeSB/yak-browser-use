## ADDED Requirements

### Requirement: AST 危险模块导入检查

系统 MUST 在 LLM 生成代码后、执行前，通过 AST 遍历检查代码中是否导入了危险模块。危险模块列表统一从 `ToolContext.DANGEROUS_MODULES` 读取（`ToolContext` 定义在 `backend/engine/ops.py`，是本次变更新建的类，替代 `backend/tools/schemas.py` 中的旧 dataclass）。

#### Scenario: 检测到 import os
- **WHEN** 生成的代码包含 `import os`
- **THEN** 系统返回拒绝原因 `"禁止导入危险模块: os"`，不执行该代码，进入重试循环

#### Scenario: 检测到 from subprocess import run
- **WHEN** 生成的代码包含 `from subprocess import run`
- **THEN** 系统返回拒绝原因 `"禁止导入危险模块: subprocess"`，不执行该代码

#### Scenario: 检测到 import os.path
- **WHEN** 生成的代码包含 `import os.path`
- **THEN** 系统提取顶层模块名 `os`，判定为危险模块，返回拒绝原因

#### Scenario: 合法 import 通过检查
- **WHEN** 生成的代码包含 `import ddddocr` 或 `from PIL import Image`
- **THEN** 系统返回 `None`（安全），允许继续执行

#### Scenario: 语法错误的代码
- **WHEN** 生成的代码包含语法错误（如括号不匹配）
- **THEN** 系统返回 `"语法错误: ..."`，不执行该代码，进入重试循环

### Requirement: 危险模块列表

`ToolContext.DANGEROUS_MODULES` MUST 包含以下模块的顶层名称：
- `os`
- `subprocess`
- `sys`
- `shutil`
- `socket`
- `ctypes`
- `signal`
- `multiprocessing`
- `threading`
- `importlib`

#### Scenario: 危险模块列表不可变
- **WHEN** 尝试修改 `ToolContext.DANGEROUS_MODULES`
- **THEN** 由于使用 `frozenset`，修改操作抛出 `AttributeError`

### Requirement: 安全检查在语法检查之前执行

系统 MUST 先执行 AST 安全检查，再执行 `py_compile` 语法检查。如果安全检查拒绝，不进行语法检查。

#### Scenario: 安全检查拒绝后跳过语法检查
- **WHEN** AST 安全检查返回拒绝原因
- **THEN** 系统不调用 `py_compile`，直接将拒绝原因作为错误信息进入重试循环

#### Scenario: 安全检查通过后执行语法检查
- **WHEN** AST 安全检查返回 `None`
- **THEN** 系统调用 `py_compile` 进行语法检查

### Requirement: AST 检查的已知局限

系统 SHOULD 在文档中注明 AST 安全检查的已知盲区。以下技术不会被 AST import 扫描捕获：

- `__import__("os")` — 动态导入，AST 中表现为函数调用而非 import 语句
- `exec("import os")` / `eval(...)` / `compile(...)` — 内置函数，不产生 import 节点
- `builtins.__import__("os")` — 同上
- `importlib.import_module("os")` — `importlib` 本身被阻止，但 `from importlib import import_module` 会被顶层模块检查捕获
- `runpy.run_module("os")` — 不产生 import 节点
- `pkgutil.get_loader("os")` — 不产生 import 节点
- `marshal.loads(...)` + `types.FunctionType(...)` — 代码对象注入，无 import 语句

AST 安全检查是"尽力而为"的安全网，不是沙箱。域名白名单和熔断器提供额外的纵深防御。
