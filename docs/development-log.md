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

## 2026-07-16 — IDEA-DB-001

- 类型：Harness SQLite 持久化
- 目标：建立独立于 OpenCode 内部数据的 IDEA 业务库，保证 Case 可迭代、Run 不覆盖、输入和配置快照不可篡改。
- 实现：新增 SQLite v1 Schema 及初始化器，建立设计文档列出的 21 张核心表、外键、索引、WAL/忙等待配置和不可变触发器；提供 Case/Run 创建、查询、列表、状态更新和显式删除方法。
- 持久化语义：重新分析创建具有 `parent_run_id` 的新 Run；`run_inputs` 不允许 UPDATE；Run 的 Case、日期、模型、Skill/Workflow 版本和配置快照不允许 UPDATE；删除只由显式方法触发并留存最小 `deletion_events` 记录。
- 涉及文件：`backend/idea/database.py`、`backend/tests/test_database.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_database backend.tests.test_config -v`，12 项全部通过；覆盖迁移、双 Run 历史、输入/配置不可变、状态可更新、Run 删除审计及 Case 级联删除；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-DB-001] add immutable case and run storage`
- 已知限制：运行目录中的报告/附件原子写入与文件删除由 `IDEA-RUNSTORE-001` 实现；严格状态迁移由 `IDEA-WF-001` 实现。

## 2026-07-16 — IDEA-RUNSTORE-001

- 类型：Harness 耐久 Run Store
- 目标：为每次 IDEA Run 保存不受缓存清理影响的输入、附件、结构化报告、Markdown 报告和可校验 manifest。
- 实现：新增 Case/Run 安全路径布局、原子字节/文本/JSON 写入、附件快照、SHA-256 文件清单、完整性复验与显式 Run/Case 目录删除。
- Harness 门禁：未存在 `input/input.json` 不得写入完成报告；`manifest.json` 必须最后原子落盘；校验时逐文件比对大小和哈希；阻止路径穿越和重名附件。
- 涉及文件：`backend/idea/run_store.py`、`backend/tests/test_run_store.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_run_store backend.tests.test_database backend.tests.test_config -v`，18 项全部通过；新增 6 项覆盖完整 Run、篡改检测、输入门禁、路径穿越、手动删除隔离和重名附件；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-RUNSTORE-001] add durable run manifests`
- 已知限制：报告内容及完成状态的业务校验将由 Workflow 和 Report Validator 完成。

## 2026-07-16 — IDEA-CACHE-001

- 类型：Harness FIFO 缓存
- 目标：建立默认 1 GiB 上限的可重建缓存，超限时严格按首次成功写入顺序清理，且不得触及持久 Run 结果。
- 实现：新增原子缓存写入、单调 `sequence` FIFO 索引、低水位回落、读取租约、强制清理、容量统计和启动修复；文件路径由类别与 key 哈希构造。
- FIFO 语义：读取不更新顺序；超限后按 `sequence ASC` 删除到低水位；租约中条目暂时跳过；单个对象大于容量上限时不入缓存；相同 key 的不同内容视为冲突并拒绝覆盖。
- 隔离保证：Cache Store 只接收 `storage.cache_dir`，测试同时建立独立历史文件并验证清理后仍存在。
- 涉及文件：`backend/idea/cache.py`、`backend/tests/test_cache.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_cache backend.tests.test_run_store backend.tests.test_database backend.tests.test_config -v`，25 项全部通过；新增 7 项覆盖 FIFO 顺序、读取不续期、租约、超大对象、key 冲突、孤儿修复和路径防护；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-CACHE-001] enforce FIFO cache capacity`
- 已知限制：生产配置的 1 GiB/0.9 GiB 阈值由已验证的统一配置注入；本单元测试用 10/6 字节缩小阈值验证边界。

## 2026-07-16 — IDEA-HEALTH-001

- 类型：Harness 启动接线与健康检查
- 目标：将统一配置、业务库和 FIFO 缓存接入 FastAPI 实际启动路径，并分组件报告系统是正常、降级还是核心错误。
- 实现：FastAPI 导入时严格加载配置、迁移 SQLite、初始化并修复缓存；新增 `/api/system/health`、`/api/system/config`、`/api/system/cache` 和手动缓存清理接口；原 `/api/health` 保留兼容并返回聚合状态。
- 健康维度：FastAPI、配置源、SQLite 读写、OpenCode 可执行文件、模型认证是否存在、EXA MCP 配置、本地 Google Patents 网络探测、缓存容量/可写性和 Workflow 恢复器。
- 降级语义：EXA 或 Google Patents 单路失败时仍允许核心系统工作并标记 `degraded`；模型认证、数据库、缓存或执行引擎失效时标记 `error`；响应永不返回 API Key。
- 涉及文件：`.gitignore`、`backend/idea/health.py`、`backend/main.py`、`backend/tests/test_health.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_health backend.tests.test_cache backend.tests.test_run_store backend.tests.test_database backend.tests.test_config -v`，30 项全部通过；通过 `main` 实际导入和缓存接口冒烟测试；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-HEALTH-001] expose component health and cache status`
- 已知限制：Workflow 恢复器在 `IDEA-WF-001` 前明确报告 `pending`；EXA 本单元只校验配置存在，真实调用状态由 Provider 工具调用审计记录。

## 2026-07-16 — IDEA-PROVIDER-001

- 类型：检索 Provider 契约与 Harness 调用门禁
- 目标：为 EXA、本地 Google Patents 及后续缓存降级建立相同的严格输入/输出契约，防止未真实执行、超时或返回结构错误的调用被记为成功。
- 实现：新增严格 `SearchQuery`、`FetchRequest`、`SearchHit`、`FetchedDocument`、`ProviderResult` 模型，抽象 `SearchProvider`，以及对搜索/抓取进行真实异步执行、超时和契约校验的 `ProviderRunner`。
- 状态语义：`SUCCESS`、`EMPTY`、`TIMEOUT`、`ERROR`、`CONTRACT_ERROR`、`DISABLED` 相互独立；只有真实返回且通过契约的结果才是成功；空结果是“成功调用但无命中”，不伪造文献。
- 契约校验：命中项必须是已验证模型、Provider 名必须匹配执行者、排名不得重复、结果不得超过请求上限、每项必须有公开号或可追溯 URL。
- 涉及文件：`backend/idea/providers/__init__.py`、`backend/idea/providers/base.py`、`backend/tests/test_provider_contract.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_provider_contract backend.tests.test_health backend.tests.test_cache backend.tests.test_run_store backend.tests.test_database backend.tests.test_config -v`，38 项全部通过；新增 8 项覆盖真实命中、空结果、超时、异常、Provider/排名契约、超量结果、全文抓取和显式禁用；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-PROVIDER-001] define audited search contracts`
- 已知限制：具体 HTTP/MCP 调用将在 `IDEA-GPAT-001`、`IDEA-GPAT-002` 和 `IDEA-EXA-001` 接入本契约。

## 2026-07-16 — IDEA-GPAT-001

- 类型：本地 Google Patents 搜索 Provider
- 目标：不经 EXA MCP，在本地构造 Google Patents 查询、解析分页搜索结果并返回统一 Provider 命中，以消除单一远程 MCP 依赖。
- 实现：新增 Google Patents 查询 URL 编码、分页/数量/国家参数、可容错 HTML Parser、公开号链接回退提取、请求限速、指数重试、环境代理失败后直连降级和 FIFO 响应缓存。
- 配置变更：统一配置和 Schema 新增 `trust_environment_proxy` 与 `fallback_to_direct`；依赖声明更改为 `httpx[socks]`，使有效 SOCKS 环境可直接使用，未安装 SOCKS 支持时仍能回退直连。
- 首轮测试：1 项失败；公开号同时从链接和页面字段提取后被拼接两次。
- 修正：页面显式结构化字段覆盖链接推导值，链接只在页面字段缺失时回退。
- 离线测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_google_patents_search ... -v`，43 项全部通过；新增 5 项覆盖真实结构 fixture、URL/分页、数量上限、响应缓存和断网错误；配置/Schema JSON 与 `git diff --check` 通过。
- 在线冒烟测试：实际调用返回 `ERROR / ConnectTimeout / 0 hits`；当前机器的 SOCKS 环境代理端口拒绝连接，回退直连也在 5 秒内超时。系统正确保留故障而未伪报成功。
- 涉及文件：`config/ai4patent.json`、`config/ai4patent.schema.json`、`backend/requirements.txt`、`backend/idea/config.py`、`backend/idea/providers/google_patents.py`、`backend/idea/providers/__init__.py`、`backend/tests/fixtures/google_patents_search.html`、`backend/tests/test_google_patents_search.py`、`docs/development-log.md`。
- 提交主题：`feat(idea): [IDEA-GPAT-001] add local Google Patents search`
- 已知限制：当前部署环境需要可用的外网直连或代理才能获得实时 Google 命中；断网时使用已缓存响应或后续 EXA Provider。

## 2026-07-16 — IDEA-GPAT-002

- 类型：本地 Google Patents 全文抓取与解析
- 目标：按公开号直接抓取 Google Patents 详情页，提取可供摘要筛选、独权核验和证据定位的结构化全文。
- 实现：新增公开号规范 URL 构造、详情页 HTML Parser、DC/itemprop 双源元数据提取、发明人/申请人/日期、摘要、逐项权利要求、逐段说明书及 `start/end/text/label` 证据 span；全文响应进入 FIFO `documents` 缓存。
- 门禁：页面没有公开号或没有任何专利文本章节时返回 `CONTRACT_ERROR`；请求公开号与页面公开号不同时返回 `CONTRACT_ERROR`；不允许用链接或模型推测的正文冒充已抓取内容。
- 解析容错：支持页面显式 claim/description block，也保留整节 itemprop 回退；正确处理 HTML 空元素，避免 `<meta>`/`<br>` 破坏章节深度计算。
- 涉及文件：`backend/idea/providers/base.py`、`backend/idea/providers/google_patents.py`、`backend/idea/providers/__init__.py`、`backend/tests/fixtures/google_patent_detail.html`、`backend/tests/test_google_patents_fetch.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_google_patents_fetch ... -v`，48 项全部通过；新增 5 项覆盖元数据/全文/span、公开号 URL、文档缓存、非法页面和公开号不匹配；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-GPAT-002] parse patent full text and evidence spans`
- 已知限制：实时抓取与搜索共用 `IDEA-GPAT-001` 记录的外网限制；页面结构变化会显式进入契约错误并需要更新 fixture/Parser。

## 2026-07-16 — IDEA-EXA-001

- 类型：EXA MCP 受控 Provider
- 目标：将 EXA 从“模型可自行决定是否调用”改为后端显式执行、契约校验和缓存的检索 Provider。
- 实现：新增 Streamable HTTP MCP 客户端，完整执行 `initialize`、`notifications/initialized`、`tools/call`，携带协议版本和 session header，并支持 JSON/SSE 响应解码、JSON-RPC id/error 校验、`isError` 门禁与环境代理失败后直连。
- Provider 适配：支持 EXA `structuredContent`、JSON 文本与 Markdown 回退结果；专利检索自动加 Google Patents 定向词；公开号从专利 URL 可追溯提取；搜索/抓取工具响应进入 FIFO 缓存。
- 统一配置：EXA 新增 `endpoint`、`search_tool`、`fetch_tool`，后端不再从超长 Skill 文本推测工具名。
- 离线测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_exa_provider ... -v`，55 项全部通过；新增 7 项覆盖 MCP 三步握手/session、SSE、结构化去重、JSON 文本、抓取回退、MCP 故障和缓存；配置/Schema JSON 与 `git diff --check` 通过。
- 在线冒烟测试：对真实 `https://mcp.exa.ai/mcp` 执行检索，返回 `SUCCESS / 3 hits / no error`；未输出或记录响应全文。
- 涉及文件：`config/ai4patent.json`、`config/ai4patent.schema.json`、`backend/idea/config.py`、`backend/idea/providers/exa.py`、`backend/idea/providers/__init__.py`、`backend/tests/test_exa_provider.py`、`docs/development-log.md`。
- 提交主题：`feat(idea): [IDEA-EXA-001] add audited EXA MCP provider`
- 已知限制：EXA 抓取返回的非结构化文本只能作为降级全文，章节精确度低于本地 Google HTML Parser，报告必须标注 `structured_sections=false`。

## 2026-07-16 — IDEA-MERGE-001

- 类型：双路检索合并、去重与溯源
- 目标：将 EXA 与本地 Google Patents 的命中确定性合并，减少同一文献/同族重复深读，同时不因模糊相似度误删独立文献。
- 实现：新增公开号、申请号和同族号规范化；使用并查集按多标识传递合并；输出标准化 `MergedHit`、所有来源、Provider 排名、查询 ID、URL 及原始命中数据。
- 去重优先级：标准化公开号→标准化申请号→已知同族 ID→URL；标题+优先权日+申请人相似只生成 `possible_family_keys`，不自动合并。
- 字段融合：标题/摘要选择信息更完整的值；公开号、申请号和同族保留标准化标识；不覆盖任何原始 Provider 记录。
- 涉及文件：`backend/idea/merge.py`、`backend/tests/test_merge.py`、`docs/development-log.md`。
- 测试：`PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_merge ... -v`，61 项全部通过；新增 6 项覆盖编号规范化、双 Provider 同公开号、A1/B2 同申请、跨国已知同族、模糊同族不误合并和多查询溯源；`git diff --check` 通过。
- 提交主题：`feat(idea): [IDEA-MERGE-001] merge and deduplicate provider hits`
- 已知限制：没有 Provider 明确同族 ID 时，模糊同族只标记待确认；不为节省分析量而强行合并。
