## ADDED Requirements

### Requirement: output_exists 验收
系统 SHALL 支持 `output_exists` check 类型，验证 step_dir 下指定路径的文件是否存在。

#### Scenario: 文件存在时通过
- **WHEN** check 为 `{output_exists: "output.csv"}` 且 step_dir/output.csv 存在
- **THEN** run_check 返回 `{ok: true}`

#### Scenario: 文件不存在时失败
- **WHEN** check 为 `{output_exists: "output.csv"}` 且 step_dir/output.csv 不存在
- **THEN** run_check 返回 `{ok: false, error: "输出文件不存在: output.csv"}`

#### Scenario: 缺少 step_dir 参数时报错
- **WHEN** check 包含 output_exists 但 run_check 被调用时 step_dir=None
- **THEN** run_check 返回 `{ok: false, error: "output_exists/file_contains 需要 step_dir"}`

#### Scenario: 路径穿越被拒绝
- **WHEN** check 为 `{output_exists: "../../../etc/passwd"}` 或 `{file_contains: {path: "../secret", text: "x"}}`
- **THEN** path 解析后不在 step_dir 内，run_check 返回 `{ok: false, error: "路径越界: {path}"}`

### Requirement: file_contains 验收
系统 SHALL 支持 `file_contains` check 类型，验证文件内容是否包含指定文本。

#### Scenario: 文件包含文本时通过
- **WHEN** check 为 `{file_contains: {path: "out.csv", text: "BV"}}` 且文件内容包含 "BV"
- **THEN** run_check 返回 `{ok: true}`

#### Scenario: 文件不包含文本时失败
- **WHEN** check 为 `{file_contains: {path: "out.csv", text: "BV"}}` 且文件内容为 "title,date"
- **THEN** run_check 返回 `{ok: false}`

#### Scenario: 文件不存在时失败
- **WHEN** check 包含 file_contains 但目标文件不存在
- **THEN** run_check 返回 `{ok: false}` 并提示文件不存在

#### Scenario: 文件路径指向目录时失败
- **WHEN** check 为 `{file_contains: {path: "subdir", text: "x"}}` 但 subdir 是目录而非文件
- **THEN** run_check 返回 `{ok: false, error: "路径不是文件: subdir"}`
