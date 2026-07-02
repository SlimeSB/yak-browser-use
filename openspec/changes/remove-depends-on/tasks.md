## 1. 数据模型层

- [ ] 1.1 schema.py — 删除 `StepYaml.depends_on` 字段定义（第 21 行）及 `to_step_def()` 中的 `depends_on=self.depends_on` 传参（第 101 行）
- [ ] 1.2 models.py — 删除 `StepDef.depends_on` 字段（第 17 行）及 `to_runtime_dict()` 中的 `"depends_on": self.depends_on` 输出（第 36 行）

## 2. 核心逻辑层

- [ ] 2.1 graph.py — 删除 `build_graph` 中的 `if step.depends_on:` 显式分支（第 54-72 行），只保留 `elif i > 0` 隐式顺序边；同步更新文档注释（第 29-30 行）
- [ ] 2.2 pipeline_store.py — 删除 `update_step` 中的 depends_on 处理（第 270-271 行），删除 `remove_step` 的 depends_on 清理逻辑（第 336-338 行）及对应的文档注释（第 325 行）
- [ ] 2.3 generator.py — 删除 `generate_handler_prompt` 输出中的 `"depends_on"` 键（第 35 行）

## 3. 工具层与注册层

- [ ] 3.1 pipeline_tools.py — 删除 `pipeline_view` 中的 `"depends_on": s.depends_on` 输出（第 103 行），删除 `pipeline_add_step` 的 `depends_on` 参数（第 174 行）及处理代码（第 206-207 行）
- [ ] 3.2 registry.py — 删除 3 处 tool schema 描述中的 depends_on 相关说明：pipeline_update_step 的 updates 描述（第 568 行）、pipeline_add_step 的 depends_on 参数 schema（第 585 行）、pipeline_create 的 steps 描述（第 613 行）

## 4. 测试清理

- [ ] 4.1 conftest.py — 删除 `SAMPLE_PIPELINE_YAML` 中的 `"depends_on": ["step_1"]`（第 26 行），删除 `sample_step_defs` 中的 `depends_on=["s1"]`（第 66 行）和 `depends_on=["s2"]`（第 68 行）
- [ ] 4.2 test_compiler_parser.py — 删除 `SAMPLE_YAML` 中的 `depends_on:` 块（第 29-30 行），删除整个 `test_parse_with_depends_on` 测试方法（第 137-155 行）
- [ ] 4.3 test_compiler_graph.py — 删除 `test_explicit_depends_on_replaces_sequential`（第 42-51 行）和 `test_depends_on_by_name`（第 53-60 行）两个测试
- [ ] 4.4 test_compiler_generator.py — 删除 `depends_on=[]` 参数（第 375 行）
- [ ] 4.5 test_pipeline_tools.py — 删除 sample 数据中的 `"depends_on": ["step_1"]`（第 35 行），删除 `test_pipeline_update_step_depends_on`（第 239-251 行）、`test_pipeline_add_step_with_depends_on`（第 416-430 行）、`test_pipeline_remove_step_cleans_depends_on`（第 499-511 行）三个测试
- [ ] 4.6 test_pipeline_store.py — 删除 `SAMPLE_YAML_TEXT` 中的 `depends_on:` 块（第 162-163 行），删除 `test_empty_depends_on_excluded`（第 292-296 行，已无意义），删除 `test_non_default_values_preserved`（第 298-309 行，只剩 params 单独测），将 `test_update_step_description_and_depends`（第 422-427 行）精简为仅测 description，删除 `test_remove_step_cleans_depends_on`（第 460-464 行）

## 5. 验证与收尾

- [ ] 5.1 运行全量测试：`cd backend && pytest`，确认所有测试通过
- [ ] 5.2 运行类型检查（如 mypy/pyright），确认无相关类型错误
