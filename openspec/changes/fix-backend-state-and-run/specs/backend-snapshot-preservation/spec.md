## ADDED Requirements

### Requirement: api_run 异常时必须保留 pipeline 快照
`api_run` 在 pipeline 执行过程中抛出异常时，MUST 将 snapshot 文件移动到 `_errors/` 子目录而不是删除。

#### Scenario: 正常执行完成
- **WHEN** pipeline 正常执行完成（`run_pipeline` 返回无异常）
- **THEN** snapshot 文件 MUST 保留在 `versions/` 目录
- **AND** snapshot 文件内容 MUST 与写入时一致

#### Scenario: pipeline 执行抛异常
- **WHEN** `run_pipeline` 抛出异常
- **THEN** snapshot 文件 MUST 被移动到 `_errors/` 子目录
- **AND** snapshot 文件 MUST 不被删除
- **AND** `_errors/` 目录下的文件名 MUST 保留原始的 `snapshot_{ts}.pipeline.yaml` 名称
