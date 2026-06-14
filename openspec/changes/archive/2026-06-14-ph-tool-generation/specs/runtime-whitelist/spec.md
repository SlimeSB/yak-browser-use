## ADDED Requirements

### Requirement: 白名单配置文件格式
项目根目录 MUST 存在 `runtime-whitelist.json` 文件，定义 subagent 生成 `_PH-` 工具代码时可用的 Python 库范围。文件 MUST 包含 `stdlib`、`bundled_deps`、`forbidden` 三个数组字段，以及 `description` 和 `notes` 两个说明字段。

#### Scenario: 文件结构完整
- **WHEN** 读取 `runtime-whitelist.json`
- **THEN** 文件 MUST 包含 `stdlib` 数组（Python 标准库模块名列表）
- **AND** 文件 MUST 包含 `bundled_deps` 数组（项目依赖中被打包进 EXE 的第三方库列表）
- **AND** 文件 MUST 包含 `forbidden` 数组（明确禁止使用的库列表）
- **AND** 文件 MUST 包含 `description` 字段说明文件用途
- **AND** 文件 MUST 包含 `notes` 数组提供使用注意事项

#### Scenario: stdlib 包含常用标准库
- **WHEN** 检查 `stdlib` 数组内容
- **THEN** MUST 至少包含 `csv`、`json`、`xml`、`html.parser`、`re`、`pathlib`、`os`、`shutil`、`io`、`typing`、`dataclasses`、`collections`、`math`、`datetime`、`urllib`、`itertools`、`functools`、`enum`、`textwrap`、`copy`、`hashlib`、`string`、`uuid`、`base64`、`statistics`

#### Scenario: bundled_deps 与 pyproject.toml 一致
- **WHEN** 检查 `bundled_deps` 数组内容
- **THEN** MUST 包含 `aiohttp`、`pydantic`、`pyyaml`、`yaml`、`fastapi`、`uvicorn`、`websockets`
- **AND** 列表内容 MUST 与 `pyproject.toml` 中 `[project] dependencies` 声明的运行时依赖保持一致

#### Scenario: forbidden 包含常见数据科学和 Web 库
- **WHEN** 检查 `forbidden` 数组内容
- **THEN** MUST 至少包含 `pandas`、`numpy`、`requests`、`BeautifulSoup`、`bs4`、`lxml`、`openpyxl`、`scikit-learn`、`matplotlib`、`selenium`、`tensorflow`、`torch`、`transformers`、`flask`、`django`、`Pillow`、`PIL`、`dotenv`、`httpx`

### Requirement: 白名单校验规则
系统 MUST 在验收 subagent 生成的代码时，检查所有 `import` 语句是否在 whitelist 范围内。任何不在 `stdlib` 或 `bundled_deps` 中的 import MUST 被拒绝。

#### Scenario: import 在 stdlib 中
- **WHEN** 生成的代码包含 `import csv` 或 `from pathlib import Path`
- **THEN** 验收通过，该 import 在 whitelist 的 `stdlib` 中

#### Scenario: import 在 bundled_deps 中
- **WHEN** 生成的代码包含 `import yaml` 或 `from pydantic import BaseModel`
- **THEN** 验收通过，该 import 在 whitelist 的 `bundled_deps` 中

#### Scenario: import 在 forbidden 中
- **WHEN** 生成的代码包含 `import pandas` 或 `from bs4 import BeautifulSoup`
- **THEN** 验收失败，返回错误信息指明 `pandas` 或 `bs4` 不在 whitelist 中
- **AND** 主 agent MUST 将代码打回 subagent 重新生成

#### Scenario: import 不在任何列表中
- **WHEN** 生成的代码包含一个不在 `stdlib`、`bundled_deps`、`forbidden` 中任何一个列表的 import
- **THEN** 验收失败，返回错误信息指明该库不在 whitelist 中
- **AND** 主 agent MUST 将代码打回 subagent 重新生成，并建议使用 stdlib 替代方案

### Requirement: 白名单同步规则
当 `pyproject.toml` 新增运行时依赖时，`runtime-whitelist.json` 的 `bundled_deps` MUST 同步更新。`forbidden` 列表 SHOULD 随项目经验持续补充。

#### Scenario: pyproject.toml 新增依赖
- **WHEN** 在 `pyproject.toml` 的 `[project] dependencies` 中新增一个运行时依赖（如 `httpx`）
- **THEN** MUST 同步将 `httpx` 添加到 `runtime-whitelist.json` 的 `bundled_deps` 数组中

#### Scenario: 发现新的 forbidden 库
- **WHEN** subagent 尝试使用一个未在 whitelist 中但实际在客户机 EXE 中不可用的库
- **THEN** SHOULD 将该库添加到 `runtime-whitelist.json` 的 `forbidden` 数组中
