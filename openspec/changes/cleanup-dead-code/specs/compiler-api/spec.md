## REMOVED Requirements

### Requirement: compiler package SHALL NOT export diff_ops and related functions
**Reason:** `compiler/diff.py` 中的 6 个函数（`diff_ops`, `filter_rejected`, `add_to_rejected`, `save_suggestions`, `merge_extra_ops`, `extract_summary`）仅在 `tests/test_compiler_diff.py` 中被调用，生产代码（包括 Guardian 审批的上下游）已全部删除。

**Migration:** 删除 `compiler/diff.py` 整文件；删除 `compiler/__init__.py` 中的对应 import 和 `__all__` 导出；删除 `tests/test_compiler_diff.py`。

- **WHEN** 其他模块通过 `from yak_browser_use.compiler import ...` 导入
- **THEN** 导入列表 SHALL 不再包含 `diff_ops`, `filter_rejected`, `add_to_rejected`, `save_suggestions`, `merge_extra_ops`, `extract_summary`

#### Scenario: Import from compiler package after cleanup
- **WHEN** 代码写 `from yak_browser_use.compiler import diff_ops`
- **THEN** Python SHALL 抛出 `ImportError`，表明该符号已不存在

---

### Requirement: compiler SHALL NOT retain guardian field in PipelineYaml schema
**Reason:** Guardian 模块已删除，`PipelineYaml.guardian` 字段和 `to_pipeline_def()` 中的 frontmatter 传值是无意义的残留。

**Migration:** 删除 `schema.py:107` 的 `guardian: dict[str, Any] = Field(default_factory=dict)` 字段；删除 `to_pipeline_def()` frontmatter dict 中的 `"guardian": self.guardian` 条目。

- **WHEN** 用户定义 `pipeline.yaml` 时
- **THEN** schema SHALL 不再接受或传播 `guardian` 字段

#### Scenario: Define pipeline.yaml without guardian
- **WHEN** 用户在 `pipeline.yaml` 中写入 `guardian: {...}` 配置
- **THEN** Pydantic 校验 SHALL 忽略或报错（取决于 extra fields 配置）；解析后的 `frontmatter` 中 SHALL 不包含 `guardian` key
