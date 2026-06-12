## ADDED Requirements

### Requirement: 将习得浏览器操作写回 pipeline.yaml
系统 MUST 通过 `write_pipeline_learned(yaml_text, step_name, new_ops) -> str` 函数将 Goal 步骤执行后获得的浏览器操作写回流水线定义。流程为：`yaml.safe_load()` → 找到目标步骤 → 添加/替换 `browser_ops` → `yaml.dump()`。

#### Scenario: 目标步骤原本无 browser_ops
- **WHEN** Goal 步骤原本不含 `browser_ops` 字段，传入 3 个新的操作字典
- **THEN** 输出 YAML 中该步骤新增 `browser_ops` 字段，包含 3 个操作，其他步骤内容不变

#### Scenario: 目标步骤原本有 browser_ops
- **WHEN** Goal 步骤原本已有 2 个 `browser_ops`，传入 5 个新操作
- **THEN** 输出 YAML 中该步骤的 `browser_ops` 被替换为 5 个新操作

#### Scenario: 目标步骤不存在
- **WHEN** 传入的 `step_name` 在流水线步骤列表中找不到匹配
- **THEN** 返回原始 YAML 文本不变，并记录警告日志

#### Scenario: 修改后 YAML 格式保留
- **WHEN** 写回后生成的 YAML 文本被 `yaml.safe_load()` 重新解析
- **THEN** 解析成功，得到合法的数据结构

### Requirement: 废弃旧写回函数
系统 MUST 移除 `write_agent_md_learned()` 函数，由 `write_pipeline_learned()` 替代。新函数操作 YAML 结构体而非按行扫描替换。

#### Scenario: 旧写回函数不可用
- **WHEN** 代码尝试调用 `write_agent_md_learned()`
- **THEN** 引发 ImportError，因为该函数已从模块中移除
