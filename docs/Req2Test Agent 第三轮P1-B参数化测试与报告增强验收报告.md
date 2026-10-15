# Req2Test Agent 第三轮P1-B参数化测试与报告增强验收报告

验收日期：2026-10-15。范围：P1-B 参数化执行、结构化断言、测试数据隔离、JUnit 与 CI 产物。未开展 P1-C/P2，未合并或部署。

## 1. 版本及依赖

独立工作区 `/Users/xing/Desktop/req2test-data-driven-testing`，分支 `feature/data-driven-testing`。
基于 P1-A 提交 `affcfcacda6f2813cfdbb01050bfbd47d730aa9b`。
核查时 PR #5、#6 均 Open，因此本轮 PR 以 `feature/api-testing-enhancement` 为 base，依赖 #6 → #5。
原部署工作区及其 `railway.json` 未提交文件保持原样。最终发布 SHA、PR 和 CI 在交付章节补充；此版 CI 仍 Pending，不能视为通过。

## 2. 已实现的数据流

登录 → 上传 JSON/CSV → `expand_dataset` 离线展开 → 脱敏预览 → 用户明确提交 → 既有任务队列 → `ExecutionConfig/HttpTestSpec` → HTTP/Pytest → 共享断言 → 脱敏结果 → PostgreSQL/Redis/页面 → JUnit。
OpenAPI `ContractPlan.datasets` 按接口标识接受数据集，复用相同展开逻辑；状态码变化时选择契约对应响应 Schema。
没有增加第三方依赖、数据表或执行框架。

每行保留 `case_id/data_id/source`，可分别指定请求数据、预期状态码和断言。JSON/CSV 上限 1 MiB、20 行；重复 ID、未知字段、重复 JSON 键、错误 JSON/CSV 明确报错。CSV 结构化单元格为 JSON；空单元格继承模板。来源行号为逻辑记录索引（CSV 计入表头），多行 CSV 单元格不宣称物理行定位。

结构化断言支持 JSON Pointer、存在性、JSON 类型、值相等/不等、长度、数值最小/最大值；多断言逐项保留通过/失败、预期、实际与路径。兼容状态码/JSON 包含/文本与本地 JSON Schema。预期 422 等 4xx/5xx 不会无条件失败。Schema 错误包含路径且不回显敏感值；禁止外部引用。

## 3. 副作用、隔离与重试边界

双执行器含写请求集合：HTTP 真实执行一轮，Pytest **复核已记录结果**，标记 `replayed_http_result`，耗时 0（原网络耗时归 HTTP）。整个集合回放，以保留读请求在写请求之间的观察时点。不是第二轮独立网络测试。纯读取集合仍分别发请求；HTTP-only/Pytest-only 均真实执行。

Mock 隔离须管理员同时开启 `REQ2TEST_ENV=test` 与 `REQ2TEST_ENABLE_MOCK_LIFECYCLE=true`，仅字面量 loopback 根地址且具备专用协议。每次创建 UUID 空间，注入隔离请求头，可准备虚构商品；父进程 finally 清理。断言失败、请求超时、Pytest 超时仍尝试清理；失败/未确认清理写入错误报告。禁止自动清理外部系统；不接受任意清理 URL/脚本。

HTTP 请求不自动业务重试。既有 Worker 的最终持久化重试复用缓存结果，原回归覆盖不重复调用执行器；崩溃、缓存丢失、消息重投时不承诺外部请求 exactly-once。强杀父进程不能保证 finally；Mock 空间 10 分钟后不可访问，下一次准备时回收过期空间。外部系统幂等依赖业务契约，未新增通用事务或回滚引擎。

## 4. JUnit 与 CI

新增鉴权接口 `/api/v1/tasks/{task_id}/reports/junit.xml`；任务未结束返回 409，跨用户访问 404。结果包含集合摘要、逐用例状态、数据来源、预期/实际、断言、耗时、错误类别与脱敏证据；保留 Markdown/CSV/JSON。

JUnit `failure` 表示断言不符；`error` 表示连接/超时、执行器缺失记录、隔离失败或持久化截断；禁用/跳过单独标记。一个数据行使用双工具会有两个 testcase，不能等同于两次 HTTP 请求。XML 使用标准转义并过滤非法控制字符，已由 XML parser 验证；未逐一验证 Jenkins/GitLab 等所有消费工具。

GitHub Actions：PostgreSQL preflight → pytest JUnit/log → 严格统计门禁 → Demo 评测 → `always()` 上传现有产物。失败、错误、跳过、空报告/缺失报告均拒绝通过，环境错误独立标记，不输出连接凭证。保留产物 14 天。依赖安装失败或 Runner 服务故障可能无法生成/上传产物，须如实保留失败状态。

实现依据：[pytest JUnit 文档](https://docs.pytest.org/en/stable/how-to/output.html)、[GitHub artifact 文档](https://docs.github.com/en/actions/tutorials/store-and-share-data)。本地子进程故意失败和跳过验证门禁拒绝、JUnit 与日志仍生成；真正 GitHub 失败归档验证状态将在交付章节注明。

## 5. 实际验证结果

| 验证 | passed | failed | skipped | error |
|---|---:|---:|---:|---:|
| 本地完整 pytest，真实隔离 PostgreSQL | 420 | 0 | 0 | 0 |
| 原有 P1-A/P0 回归（包含在完整集） | 369 | 0 | 0 | 0 |
| P1-B 新增（包含在完整集） | 51 | 0 | 0 | 0 |

本地有 1 条 Starlette/AnyIO 弃用 warning，不是失败或跳过。Ruff 历史 137、本轮 137、新增 0，未宣称全仓 Ruff 零告警。

- 登录多组数据：正常、密码错误 401、缺失/类型错误 422；额外故意设预期 200/实际 422 验证失败后继续其余行。
- 真实 Worker 数据集 5 行：HTTP 4 pass/1 expected test failure；Pytest 回放同样 4/1。JUnit 10 testcase、2 failure、0 error/skip；这是故障验收样例的正确结果，不是完整 pytest 有 2 项失败。
- 独立 HTTP、独立 Pytest、双工具均验证创建→查询→更新→删除，两次运行各自独立空间；同名商品不冲突、不重复写。请求超时后清理，延迟写入被已移除空间拒绝。
- 准备失败不执行、清理失败形成错误报告；Pytest 硬超时父进程清理为模拟回归，未宣称真实杀进程演练。
- 真实浏览器 CSV 上传→4 行预览→任务提交→HTTP 4 pass/Pytest 4 pass→JUnit 按钮返回 HTTP 200。任务页完成后手动刷新一次；不是新增自动刷新能力。
- 真实 API/RabbitMQ/Celery/PG/Redis：数据集执行、两次隔离创建、结果持久化与 JUnit 导出；Cookie/Bearer、非法 Origin 拒绝、用户隔离、RBAC、WebSocket、Chroma 知识库 CRUD/重建通过。
- 原 OpenAPI YAML 5 接口生成 17 用例，经 Worker HTTP 17 pass、Pytest 17 回放 pass。原 P1-A JSON/YAML、安全回归保持通过。
- Evaluation Center 真实队列 Demo 评测完成，3 个既有样本 98.45/100（门槛 80）。这是确定性 Demo 分数，**不是模型准确率**；未调用真实 LLM。

修复证据：最初新测试因缺少新模块失败，后续第一轮完整回归 413 pass/1 fail 暴露未完成任务可导出；真实 Worker 首次暴露详情缺少 lifecycle。两项修复后完整 420 pass。额外扩展公共脱敏识别断言路径，避免 `/password` 等叶节点 expected/actual 从预览/持久化/JUnit 旁路泄露。

原始日志保存在 `/Users/xing/Desktop/Req2Test-P1B-evidence-20261015`；仓库提交精简汇总 `docs/p1b-evidence/validation-summary.json`，不提交环境文件、运行日志或数据库数据。

## 6. 修改文件与核心入口

| 文件 | 主要职责 |
|---|---|
| `data_driven.py` | `expand_dataset/compile_data_plan`，严格 JSON/CSV 与数据身份 |
| `execution_models.py` | `JsonAssertion/AssertionOutcome`，行元数据、隔离配置与逐行 Pytest 结果 |
| `assertions.py`, `schema_assertions.py` | 共享判定、路径定位、多断言与敏感叶节点 |
| `http_tool.py`, `pytest_runner.py`, `tool_calling.py` | 独立失败、固定模板、结果回放、隔离 finally 与失败归因 |
| `mock_lifecycle.py`, `examples/mock_api.py` | 本地专用协议、前置数据、UUID 空间、过期与安全清理 |
| `openapi_import.py` | 接口级数据集复用、行级响应 Schema |
| `junit_report.py` | `to_junit_xml`，统计、缺失证据和失败输出 |
| `api.py`, `datasets_ui.py`, `contracts_ui.py`, `task_ui.py` | 预览/提交、上传入口、逐行显示和 JUnit 下载 |
| `security/redaction.py`, `db/services/task_persistence.py` | 断言路径脱敏、lifecycle 详情保留 |
| `examples/data/login.json/csv` | 虚构可运行数据样例 |
| `scripts/ci_test_gate.py`, `.github/workflows/tests.yml` | 环境检查、不可跳过的完整统计、失败归档 |
| `scripts/smoke_data_driven.py`, `smoke_security.py` | 复用原端到端冒烟并扩展 P1-B |
| `tests/test_data_driven.py`, `test_data_lifecycle.py`, `test_structured_assertions.py`, `test_ci_test_gate.py`, `tests/db/test_datasets_api.py` | 新增 51 项自动化回归 |
| `README.md`, 本报告与证据摘要 | 使用、边界与验收交付 |

## 7. 尚未验证与残留限制

未验证生产环境、真实企业 API/业务数据、真实 LLM、所有 CI 平台导入效果；未进行高并发/性能和分布式 exactly-once 保证。清理只针对本地虚构 Mock；不同外部系统需另行设计授权、幂等和清理契约。沿用 P1-A 的 OpenAPI 子集限制，没有扩展组合/循环/远程引用。保留历史 Ruff 和依赖弃用 warning，不扩大整改范围。

## 8. 简历可写能力与 P1-C 建议

可写：基于 FastAPI/Pytest 实现 JSON/CSV 参数化 API 测试，统一状态码/JSON Pointer/Schema 断言；复用 HTTP/Pytest 与异步 Worker，隔离虚构 Mock 数据，输出脱敏 JUnit；实际本地回归 420 项通过、零跳过。应明确写请求双工具是结果复核，不写成“两套独立请求均通过”。

尚不能写：生产级通用数据清理、业务 exactly-once、真实模型高准确率、性能容量、全 OpenAPI 支持、跨平台 JUnit 全兼容。P1-C 建议先定义评测指标与基线、版本化数据和分层场景、区分确定性断言与 LLM 评分，再进行经过人工审查的样本扩充；本轮未实施。

## 9. 交付状态

本地功能验收完成；等待独立提交、PR 与 GitHub CI 最终核对。本节将在远端结果可核实后更新。
