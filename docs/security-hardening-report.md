# Req2Test Agent 第二轮P0安全整改与回归验收报告

验收日期：2026-10-14（Asia/Shanghai）。范围仅为第一轮报告中的 P0-1～P0-4，以及整改直接引起的兼容性问题。**四项均已实现，并通过本报告列明的验证；未宣称生产级安全或真实模型准确率。**

## 1. 版本、工作区与交付

- 基础版本：第一轮确认的远端 main commit `0a9f2c7923e5ece32cd68d5e60a5831a645dd0eb`。本次恢复时再次查询远端，结果一致。
- 整改分支：`feature/security-hardening`；独立工作区：`/Users/xing/Desktop/req2test-security-hardening`。
- **远端实现 Commit SHA：`a665b157ae8e6503e22077eb141c2f46940b8c9f`**。本机验收实现 commit 为 `97b9d1cf9c90b73ec1c4b3cff7ce61b888545420`；因本机 Git 无推送凭据，使用已连接 GitHub 上传，两者 Git tree 均为 `51228bb551b6d557b4b8b0a01e001aa1863d0028`，源码逐字节一致。其后的提交只交付报告及测试证据，最终分支 SHA 以 PR head 和随附本地正式报告为准。
- 原部署工作区 `/Users/xing/Desktop/req2test-agent-release-check` 仍为 `codex/render-free-neon`，HEAD `19c8f817f2d3164408a35d62f964607afa6167f5`；未跟踪的 `railway.json` 保留。没有 reset、clean、强制切换、强制推送或生产操作。
- PR：创建后补充链接；不自动合并、不部署。

本次首先恢复昨天已有的未提交实现、测试和执行日志，而非重新开发。Docker 原已关闭，昨天的临时容器已经消失；恢复 Docker 后仅新建带安全验证标签的三只临时容器，没有启动或修改其他历史部署栈。

## 2. P0 修复前后与证据

| 问题 | 根因及修复前行为 | 最小修复与兼容策略 | 已验证证据 |
|---|---|---|---|
| P0-1 重定向越权 | 两个 HTTP 客户端自动跟随 Location，只校验初始地址 | HTTP Tool 与生成的 Pytest 均 `follow_redirects=False`。30x 按原响应测试，不自动访问下一跳，即便下一跳也在白名单内 | 301/302/303/307/308 × 两执行器 × 越权、同主机、相对路径、循环；夹具只收到初始请求，重定向目标请求数为 0 |
| P0-2 执行器校验不一致 | Pytest-only 与直接 Runner 绕过 HTTP Tool 的主机校验 | 共享 `validate_execution_target`，在公共执行入口、Runner invoke、模板生成及生成模块加载时校验；拒绝非 HTTP(S)、嵌入凭证、非法端口、控制符、base query/fragment及未授权主机 | HTTP-only、Pytest-only、双工具、直接调用；拒绝发生于网络/子进程启动前；合法本机目标和管理员 remote override 的既有语义保留 |
| P0-3 敏感值旁路 | 各处正则不一致；JSON/dict repr、断言值、模型输入和后台异常绕过脱敏 | 共享结构化/文本脱敏，先脱敏再截断；覆盖报告、证据、持久化、状态、导出和 LLM 消息。执行输入与断言本身保持原值 | 合成凭证在 HTTP JSON、超时输出、422、数据库、Redis、WebSocket、日志、导出及 Mock LLM 捕获消息中不可见；非敏感诊断字段保留 |
| P0-4 Cookie CSRF/Origin | 仅 SameSite=Lax，没有服务端可信来源校验 | 全局 Cookie Origin 中间件按显式配置精确匹配 scheme/host/port；不信任 Host/Forwarded。Cookie 变更与 WebSocket 缺失/null/异源 Origin 拒绝。Bearer-only API 保留 | 登录/退出、任务、知识库、管理、评测接口矩阵；真实 Cookie 与 Bearer 任务完成；恶意 Cookie 请求返回 403；JWT、RBAC、数据归属测试通过 |

P0-3 恢复后的补漏包括：Pydantic 验证错误中的密码和 `input_value`；Celery 最终异常、重试 traceback 的原异常链、冲突异常、旧结果重放、首次及再次派发的 `argsrepr`；HTTPX 查询参数日志；HTTPCore/SDK debug 原始请求内容；知识库失败状态旧脱敏函数；文本包含断言中的原始期望值。敏感日志采用同一工具，无法可靠结构化解析的 transport/SDK debug 内容省略。

P0-4 明确区分：普通受保护接口同时携带有效 Bearer 与 Cookie 时使用 Bearer 身份，错误 Bearer 不回退 Cookie；空或非 Bearer 头不能绕过 Cookie 校验。登录、注册、退出属于会话变更，有 Origin 或会话 Cookie 时始终校验来源。无 Cookie/Origin 的非浏览器登录仍可用。默认可信来源仅为本地 8000 端口；部署自定义域名/端口必须配置 `REQ2TEST_TRUSTED_ORIGINS`。没有放宽策略来迁就测试，原测试客户端补充了符合场景的 Origin。

## 3. 修改文件与核心函数

下列路径均相对于仓库根目录。完整差异为实现 commit 的 38 个文件，不含后续证据文档。

| 文件 | 核心变更 |
|---|---|
| `src/req2test/security/execution.py`（新增） | `validate_execution_target` 共享目标授权 |
| `src/req2test/security/csrf.py`（新增） | `_origin`、`trusted_origin`、`CookieOriginMiddleware` |
| `src/req2test/security/redaction.py`（新增） | `is_sensitive_key`、`redact_text`、`redact_sensitive`、`safe_logger`、`protect_http_logs`、`safe_task_error` |
| `src/req2test/http_tool.py` | `HttpApiTestTool.invoke` 禁止跳转、报告脱敏、断言不回显原值 |
| `src/req2test/pytest_runner.py` | `render_pytest_module`、`PytestRunnerTool.invoke`：授权、固定模板、禁跳转、plain assertions、隔离 pytest 插件选项、stdout/stderr 脱敏 |
| `src/req2test/tool_calling.py` | `execute_with_tools` 共同校验；`analyse_failures` 出站消息脱敏 |
| `src/req2test/execution_models.py` | `_PublicOutput` 输出字段及序列化边界，输入模型不改变 |
| `src/req2test/llm.py` | `invoke_json` 的 system/human 消息、`build_chat_model` 的日志保护；连接凭证仍供客户端认证使用 |
| `src/req2test/diagnostics/evidence.py` | 共用脱敏并保留证据大小/字段限制 |
| `src/req2test/db/services/task_persistence.py` | `sanitize_config`、`safe_error_summary`、创建持久化、projection/detail/diagnostics 的旧数据读取保护 |
| `src/req2test/db/services/result_persistence.py` | `sanitize_result`、结果截断前统一脱敏 |
| `src/req2test/task_store.py` | Redis/内存缓存读写和返回值保护 |
| `src/req2test/worker.py` | `generate_test_cases`：最终输出、失败、冲突、重试异常链与再次入队元数据保护；既有有限重试分类保留 |
| `src/req2test/api.py` | 中间件、422 验证错误处理、错误响应、`_publish_task` 的参数展示保护 |
| `src/req2test/exporters.py` | Markdown/CSV/JSON 导出前复制并脱敏，不修改原结果 |
| `src/req2test/evaluation_api.py` | `_publish_evaluation` 参数展示保护 |
| `src/req2test/evaluation/models.py`、`safety.py`、`tasks.py` | 评测报告序列化、失败摘要、Worker 对外异常保护；保留 ValueError 等既有错误类型 |
| `src/req2test/db/services/evaluation_persistence.py`、`src/req2test/services/evaluation_service.py` | 评测样本/指标/错误持久化及 `run_dto` 读取保护 |
| `src/req2test/services/knowledge_service.py` | `_safe_error` 共用脱敏；文档错误读取保护，保留既有展示标记兼容性 |
| `.env.example`、`docker-compose.yml`、`SECURITY.md` | 可信 Origin、自定义脱敏字段和安全边界文档；无新增服务和数据库迁移 |
| `tests/test_security_targets.py`、`test_security_csrf.py`、`test_security_redaction.py`（新增） | 48 + 27 + 54 项安全回归 |
| `tests/db/test_security_boundaries.py`（新增） | 2 项真实 PostgreSQL 持久化及旧数据读取回归 |
| `tests/db/conftest.py` | 显式配置测试浏览器来源 |
| `tests/db/test_admin_console.py`、`test_api_task_persistence.py`、`test_authentication.py`、`test_evaluation_api.py`、`test_knowledge_product.py`、`test_task_ownership.py`、`test_task_product.py` | Cookie 测试客户端携带可信 Origin；保留业务断言 |
| `scripts/smoke_security.py`（新增） | 可复现的本机 API/Worker 链路验证；强制 test 环境、loopback 服务和专用数据库名；自动收回 API/Worker 进程 |

## 4. 先失败、后修复的过程记录

详细命令、退出码、耗时和原日志 SHA256 见 [run-history.json](security-hardening-evidence/run-history.json)。以下为独立执行轮次，**不能累加为覆盖数量**。

| 轮次 | 结果 | 解释 |
|---|---|---|
| 整改前原测试基线 | 162 passed；0 failed/skipped/error | 昨天的基线，不代替整改后验收 |
| 初始新增安全测试 red | 98 failed、12 passed | 110 项测试先证明缺口，失败原始输出已归档 |
| 首轮实现 | 110 passed | 仅新增安全测试，当时尚未完成全回归 |
| 第一次全回归 | 16 failed、256 passed | Cookie 客户端缺 Origin、脱敏标记兼容、Alembic 关闭既有 logger 影响日志夹具 |
| 422 密码 / Celery 元数据 red | 分别 1 failed / 2 failed | 补充回显及后台异常缺口 |
| 第二、第三次全回归 | 1 failed、272 passed；随后 277 passed | 修复评测异常类型兼容，不能将中间通过数当最终验收 |
| 恢复后日志/断言、旧结果、知识库、边界 red | 分别 2 failed；1 failed；8 failed + 1 passed；2 failed | 补齐第三方日志、重放、共用脱敏、Pydantic 输入和 Origin 端口 0 的边界 |
| 重试/冲突 red | 2 failed | 原异常链及冲突返回仍可能泄漏；中间修复还有 1 项失败，修正公共任务边界后 64 项定向回归通过 |
| **最终完整验收** | **293 passed；0 failed；0 skipped；0 error** | 下面所有计数以本次 `acceptance-complete` 记录为准 |

初次真实链路脚本曾超时：Worker 已完成 Evaluation，但脚本把响应 `run.id` 误读为顶层 id，轮询 `/runs/None`。只修正脚本解析，没有为此修改评测接口。后续真实链路完成。

## 5. 最终验证结果

### 5.1 pytest 与 PostgreSQL

证据：[最终原始输出](security-hardening-evidence/pytest-final.txt)、[JUnit XML](security-hardening-evidence/pytest-final.xml)、[分组统计](security-hardening-evidence/test-summary.json)。最终耗时 18.45 秒（pytest），运行器墙钟 18.88 秒。

| 测试范围 | passed | failed | skipped | error |
|---|---:|---:|---:|---:|
| 原有测试 | 162 | 0 | 0 | 0 |
| 新增 P0 回归 | 131 | 0 | 0 | 0 |
| **完整测试集** | **293** | **0** | **0** | **0** |
| 其中真实 PostgreSQL 集成测试（是上面的子集） | 80 | 0 | 0 | 0 |

其中 JWT/Cookie 认证 7 项、RBAC 管理 5 项、任务归属 3 项、知识库产品 4 项、数据库 Worker 持久化/重试 10 项、评测 API 3 项、评测持久化 2 项、评测 Worker 2 项均通过。数量是测试函数及参数化项，不代表等量独立业务能力。知识库产品单测使用真实 PostgreSQL 与可控向量夹具；真实 Chroma 操作另由下一节补充。

唯一 warning 为 Starlette TestClient 使用已弃用的 AnyIO BlockingPortal 别名；属于依赖警告，不是 skipped/error。未修改密码哈希算法或取消密码校验。

### 5.2 真实本机 API 与 Worker

已验证：临时 PostgreSQL 16、Redis 7、RabbitMQ 3.13；本机 Uvicorn + Celery 5.6.3（solo，concurrency=1）+ Chroma 1.5.9。容器仅绑定 loopback 随机端口，PostgreSQL 使用 tmpfs，Redis 禁止持久化。全部为生成的测试账号、合成凭证和本机目标。

[链路结果](security-hardening-evidence/smoke-results.json)、[Worker 日志](security-hardening-evidence/smoke-worker.txt)、[API 日志](security-hardening-evidence/smoke-api.txt) 证明：

- `/ready` 确认三项基础设施可用；真实注册、Cookie 登录、工作台 HTTP 页面响应正常，异源状态变更 403。
- 普通用户知识库上传 403；仅在临时数据库提升新生成测试用户为 admin 后，管理接口可读，知识库上传、详情、查询、重新索引、全量重建和删除全部成功。
- Req2Test Demo 真实排队执行：GET health 与 POST echo 均通过 HTTP Tool/Pytest；POST 请求携带合成敏感值，实际断言使用原值，报告/状态/数据库/日志不含这些明文。
- 故意缺少请求体的负例返回 422，被报告为 contract_mismatch，HTTP 1 项失败且 Pytest 失败。这是**预期业务负例**，链路验证脚本因此通过；没有将这个业务失败宣称为执行用例通过。
- Cookie WebSocket 终态可读且脱敏；Bearer-only、无 Origin/无 Cookie 的任务完成；logout 后 `/me` 返回 401。
- Evaluation Center 通过真实 RabbitMQ/Celery 完成，得分 98.45；PostgreSQL 结果列与 Worker 日志检查通过。

真实 smoke 退出 0，运行器墙钟 7.50 秒。重试、dead-letter、重复投递等故障路径有定向单元/真实数据库集成测试，**未执行实际断网、杀 Worker 或 broker 故障注入的全链路演练**。

### 5.3 离线评测与 LLM

`golden_demo`（3 条离线样本）以 demo 模式执行，得分 **98.45/100**，门槛 80，通过；[评测结果](security-hardening-evidence/golden-evaluation.json) 保存数据集摘要、配置和逐样本指标。报告配置中的模型名称是默认元数据，**未调用真实大模型**。

LLM 出站脱敏通过 Mock 客户端捕获实际 system/human 消息及失败分析 payload 验证；真实外部供应商、真实 API Key、模型质量/准确率、付费模型端到端行为尚未验证。

### 5.4 Ruff

使用 Ruff 0.16.6 执行 `python -m ruff check . --no-cache --output-format json`。基线 **139** 项，最终 **137** 项；按相对文件路径 + 规则 + message 比较，忽略代码增删导致的行号漂移，**新增 0，消除 2**。退出码仍为 1，不能描述为 Ruff 全绿。

消除项：知识库服务 I001 导入排序；Worker 一项既有 RUF100（改后对应处理确需 BLE001 注释）。残留主要为 B008 51、I001 39、RUF100 18、UP037 14，其余 15。未扩大范围清理历史诊断。[对比](security-hardening-evidence/ruff-comparison.json)、[基线](security-hardening-evidence/ruff-baseline.json)、[最终诊断](security-hardening-evidence/ruff-final.json)。`git diff --check` 通过。

## 6. 复现方法与证据口径

使用独立环境并安装项目依赖。设置 `REQ2TEST_ENV=test`、合成 `JWT_SECRET_KEY`；`DATABASE_URL` 和 `REQ2TEST_TEST_DATABASE_URL` 指向临时 PostgreSQL，数据库名 `req2test_security_test`；`REDIS_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND` 指向临时 loopback Redis/RabbitMQ。不可载入生产 `.env`。本次测试使用干净环境变量白名单，未使用生产配置。

```sh
python -m pytest -q --junitxml=/tmp/req2test-p0-tests.xml
python scripts/run_eval.py --dataset evals/golden_demo.jsonl --mode demo --min-score 80 --output /tmp/req2test-p0-eval.json
python scripts/smoke_security.py --output-dir /tmp/req2test-p0-smoke
python -m ruff check . --no-cache --output-format json
```

smoke 会迁移专用临时数据库、写入合成数据并运行知识库重建；仅能用于专用测试服务。无真实 PostgreSQL 时原数据库 fixture 会 skip，因此应检查 JUnit，不得仅凭退出 0 宣称全量通过。本次 PostgreSQL 可用，跳过数为 0。运行环境版本见 [runtime-versions.txt](security-hardening-evidence/runtime-versions.txt)。

PR 中的证据副本清理了行尾空白，并将本机绝对路径替换为 `$REPO`、`$VENV`、`$EVIDENCE`；完整原始记录保留在本地 `/Users/xing/Desktop/Req2Test-security-evidence-20261013`。历史 SHA256 对应本地未替换的原日志。证据均为合成测试数据。

## 7. 残留风险与尚未验证

1. 目标授权是 hostname 策略，尚无 DNS pinning、IP 网段/端口隔离或操作系统级执行沙箱；显式 remote override 仍可扩大访问面。本轮关闭所有自动重定向，没有实现按跳放行。
2. 脱敏是字段/上下文规则，不保证识别无标签的任意秘密、未知编码或自由文本全部个人信息。可通过 `REQ2TEST_REDACT_FIELDS` 补充。旧数据读取已保护，但没有清洗旧数据库/Redis/备份/日志；如曾保存真实凭证，需另行评估轮换及清理。
3. broker 仍需承载实际执行凭证；`argsrepr` 只保护日志/事件展示，不是消息加密。模型客户端认证凭证、登录 token、授权用户资料和知识库原始业务文档不能一概抹除，否则会破坏功能。外部 APM、原始 SQL 参数日志、第三方抓包须独立约束。
4. 合法浏览器需部署者显式配置可信 Origin；本次验证包含 TestClient 和真实 HTTP Cookie/Origin 交互，但未开展多浏览器人工 UI 点击、生产反向代理或 HTTPS 部署验收。
5. Worker 真实链路仅单进程 solo；多机/高并发、真实 broker 故障恢复、50 并发性能尚未验证。没有访问生产数据库或线上业务数据。
6. 历史 Ruff 137 项和 Starlette/AnyIO 警告仍在。预期 422 的业务判定及嵌套 JSON 提取等第一轮 P1 问题未修改；不能因本次 P0 通过便宣称所有历史问题清零。
7. GitHub CI 状态以 PR 实时检查为准；本报告的主要验收证据为上述本机隔离执行。真实 LLM、外部网络目标、生产运行均不在已验证范围。

## 8. 回滚方法

本轮无 schema migration、依赖升级或生产部署。尚未合并时可直接关闭 PR，保留整改分支与证据即可，原部署目录不受影响。若未来已合并，先在独立回滚分支 `git revert a665b157ae8e6503e22077eb141c2f46940b8c9f`（如实际采用 squash，则 revert 对应 squash commit），解决正常冲突后运行原测试、Demo、认证及评测再提交回滚 PR；不要 reset/force push。文档提交可以保留作为历史记录。

回滚会重新引入已知 P0，须限制暴露面并制定替代修复。它不会恢复已脱敏的数据，也不撤销历史凭证泄漏。生产回滚需要单独授权，本轮未执行。

## 9. 后续建议（只建议，本轮未实现）

**P1 测试开发**：修复预期 422 与分类的一致性及嵌套 JSON 提取；扩充 Golden Dataset 的边界/异常案例；为安全矩阵和离线评测建立固定版本 CI 门禁；补充浏览器同站不同源、真实重试故障注入和跨平台 Runner 验证。以可重复数据描述覆盖率和质量，不将 demo 得分写成真实模型准确率。

**P2 运维与技术支持**：规范可信来源、目标白名单与 broker 权限配置；提供日志脱敏与凭证轮换/旧数据清理流程；增加任务链路故障排查手册、备份恢复演练和受控环境性能基线；后续单独评估 DNS/网络出口隔离及沙箱。上述均须独立确定范围，不混入本轮安全 PR。
