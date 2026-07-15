# AI4Patent 追加式开发日志

> 本文件只允许在末尾追加。禁止删除、重排或修改既有条目。
> 发现旧记录有误时，新增更正条目并引用原 Work Unit ID。

## 2026-07-16 — IDEA-DESIGN-001

- 类型：技术设计基线
- 目标：固定 IDEA 完全重构的产品、Workflow、Agent、检索、缓存、持久化、前端、测试和 Git 开发协议。
- 实现：新增 `docs/idea-rebuild-technical-design.md`，确立一个入口 Skill、11 个 Workflow 步骤、7 类受限 Agent、EXA 与本地 Google Patents 双路检索、摘要/独权筛选漏斗、明确新颖性结论、Case/Run 永久历史、1 GiB FIFO 缓存和仅 IDEA 前端范围。
- 固定决策：内部全部共享可见；历史结果不自动删除；用户可手动删除；FIFO 只清理可重建缓存；应用配置集中到未来的 `config/ai4patent.json`。
- 涉及文件：`docs/idea-rebuild-technical-design.md`、`docs/development-log.md`。
- 验证：待本 Work Unit 完成文档结构、JSON 示例和 Git diff 校验后执行提交。
- 提交主题：`docs(idea): [IDEA-DESIGN-001] define rebuild architecture`
- 已知限制：本 Work Unit 只创建设计与开发协议，不实现运行时代码。

## 2026-07-16 — IDEA-DESIGN-001-VERIFY

- 类型：验证记录
- 关联工作单元：`IDEA-DESIGN-001`
- 首次校验：失败；校验脚本误将缓存视为顶层 `cache`，实际设计为 `storage.cache`，未发现文档配置缺陷。
- 修正处理：仅修正验证脚本对配置层级的预期，未修改已确认设计。
- 最终验证：通过 `git diff --check`；通过 Python `json.loads` 解析配置示例；通过 1 GiB、FIFO、历史不自动删除、允许手动删除、仅启用 IDEA 及 19 个主章节的断言。
- 验证结果：`DOC_CHECK_OK`；技术设计文档 1167 行。

## 2026-07-16 — IDEA-CONFIG-001

- 类型：Harness 统一配置
- 目标：建立 IDEA 应用唯一配置源和启动阶段的严格校验，防止业务代码散落默认值或静默降级。
- 实现：新增 `config/ai4patent.json` 与 JSON Schema；新增 Pydantic 严格配置模型、环境变量配置路径覆盖、相对路径归一化和可序列化 Run 快照。
- 固定约束：仅 IDEA 功能可启用；历史不自动删除；缓存只能 FIFO；默认上限 1 GiB；深度核验下限不得低于 10；密钥只保存环境变量名和本地认证文件引用。
- 涉及文件：`config/ai4patent.json`、`config/ai4patent.schema.json`、`backend/idea/config.py`、`backend/idea/__init__.py`、`backend/tests/test_config.py`、`backend/tests/__init__.py`。
- 首轮测试：1 项失败；测试误将字段名 `api_key_env` 判定为真实密钥，实现中不存在密钥值。
- 修正：改为结构化断言 `model` 中不存在 `api_key` 或 `apiKey` 字段。
- 最终测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_config -v`，6 项全部通过；两个 JSON 文件通过 `json.tool`；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-CONFIG-001] add validated system configuration`
- 已知限制：本 Work Unit 只建立配置基础，后续 API 和 Workflow 接入将分别在对应 Work Unit 完成。
