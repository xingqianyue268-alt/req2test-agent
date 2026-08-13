# Phase 4A：业务数据持久化层架构设计

## 0. 文档范围与已锁定决策

Phase 4A 的目标是为 Req2Test Agent 引入可追溯、可迁移、可测试的长期业务数据层，同时保留现有实时任务链路。

本阶段锁定以下技术选型：

- 业务数据库：PostgreSQL 16
- ORM：纯 SQLAlchemy 2.x Declarative Mapping
- Migration：Alembic
- PostgreSQL Driver：psycopg 3
- Session：同步 SQLAlchemy Session
- Redis：实时任务状态、WebSocket Progress、临时缓存和 Celery Result Backend
- RabbitMQ：Celery 异步消息 Broker
- ChromaDB：RAG Vector Store

本阶段不实现登录、JWT、Admin UI、RBAC，也不引入 async SQLAlchemy、SQLModel 或新的向量数据库。

## 1. 当前系统数据流

### 1.1 创建与执行任务

当前 `POST /api/v1/tasks` 的主要流程为：

```text
Client
  -> FastAPI 生成 UUID task_id
  -> Redis TaskStore.create() 写入 queued 状态
  -> Celery.delay() 向 RabbitMQ 发布任务
  -> Redis TaskStore 记录 celery_task_id
  -> Celery Worker 执行 LangGraph 工作流
  -> Worker 高频更新 Redis stage/progress
  -> Worker 执行 HTTP Tool / Pytest / Failure Analysis
  -> Worker 将完整 result 或 error 写回 Redis
  -> HTTP polling 与 WebSocket 从 Redis 读取状态
```

仅在 local development 或 test 环境中，TaskStore 才允许在 Redis 不可用时退化为进程内 memory store；Celery eager 模式可在 API 进程内直接执行任务。生产环境禁止把 memory fallback 当作 Redis 故障替代：Redis 不可用时仍允许从 PostgreSQL 查询历史业务数据，但必须拒绝创建新的异步任务并返回明确的 503。

### 1.2 当前持久化边界

- TaskStore 的 Redis key 为 `req2test:task:{task_id}`，默认 TTL 为 86400 秒。
- Redis 当前同时承担实时状态和短期结果历史；TTL 到期后业务记录消失。
- TaskStore 更新采用 read-modify-write，没有跨 PostgreSQL/Redis 的事务或状态版本控制。
- Celery 自身 task id 仅保存在 Redis 状态中。
- 测试用例、执行结果、Review、Failure Analysis 只存在于最终结果 payload。
- ChromaDB 独立保存 RAG 文档、metadata 与 embedding；当前没有关系数据库目录记录。

### 1.3 当前配置与部署

- `docker-compose.yml` 已包含 RabbitMQ、Redis、API 和 Worker，尚无 PostgreSQL。
- API 与 Worker 通过环境变量共享 Redis/Celery 配置。
- Python 依赖尚无 SQLAlchemy、Alembic 和 psycopg。
- `/health` 当前主要报告应用状态与 TaskStore backend，并不检查关系数据库。Phase 4A 将其固定为 liveness；另建 `/ready` 承担依赖 readiness。

## 2. 新的数据层架构

```mermaid
flowchart LR
    C["Client"] --> A["FastAPI"]
    A --> P[("PostgreSQL\nBusiness Source of Truth")]
    A --> R[("Redis\nLive Task Projection")]
    A --> Q["RabbitMQ"]
    Q --> W["Celery Worker"]
    W --> R
    W --> P
    W --> V[("ChromaDB\nVectors and RAG Content")]
    R --> S["Polling / WebSocket"]
    P --> H["History / Results / Export"]
```

### 2.1 PostgreSQL

PostgreSQL 是长期业务数据的唯一 Source of Truth，保存 User、Task、TestCase、Execution、KnowledgeDocument，以及任务的最终或关键生命周期状态。

### 2.2 Redis

Redis 是任务实时状态的可重建投影，负责高频 progress、WebSocket 推送、短期完整结果缓存和 Celery Result Backend。Redis 丢失后应能从 PostgreSQL 恢复终态和历史摘要，但不会把每一次细粒度进度写入 PostgreSQL。

### 2.3 Session 与依赖注入

- 使用 `create_engine(DATABASE_URL, pool_pre_ping=True)` 创建进程级 Engine。
- 使用 `sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)`。
- FastAPI 的 `get_db()` 每个请求 yield 一个 Session，并在请求结束时关闭。
- Celery Worker 每个任务或持久化边界独立创建 Session；绝不通过 Celery 参数传递 Session。
- Repository 显式接收 Session，事务边界由 service/use-case 层控制。
- 数据库 URL 使用 `postgresql+psycopg://`。
- 表结构只由 Alembic 管理，应用启动时不调用 `Base.metadata.create_all()`。

## 3. 数据模型与关系

所有 UUID 使用 PostgreSQL 原生 `UUID(as_uuid=True)`；时间字段使用带时区的 `DateTime(timezone=True)`，数据库默认值为 `now()`。枚举状态在 Phase 4A 可先使用受约束的字符串，避免 PostgreSQL ENUM 演进成本，并在应用层使用 Python Enum。

```mermaid
erDiagram
    USER ||--o{ TASK : owns
    TASK ||--o{ TEST_CASE : contains
    TASK ||--o{ EXECUTION : records
    TEST_CASE o|--o{ EXECUTION : may_produce

    USER {
      uuid id PK
      string email UK
      string password_hash
      string role
      boolean is_active
    }
    TASK {
      uuid id PK
      uuid user_id FK
      string celery_task_id UK
      string status
      string stage
      smallint progress
      bigint state_version
      jsonb generation_config
      jsonb execution_config
    }
    TEST_CASE {
      uuid id PK
      uuid task_id FK
      string case_id
      integer version
      jsonb preconditions
      jsonb steps
    }
    EXECUTION {
      uuid id PK
      uuid task_id FK
      uuid test_case_id FK
      string kind
      boolean passed
      string failure_category
    }
    KNOWLEDGE_DOCUMENT {
      uuid id PK
      string vector_collection
      string vector_document_id
      jsonb metadata
      string index_status
    }
```

### 3.1 User (`users`)

字段：

- `id`: UUID，主键
- `email`: `VARCHAR(255)`，非空、唯一、索引；写入前标准化为小写
- `password_hash`: `VARCHAR(255)`，非空；只允许密码哈希，绝不保存明文
- `role`: `VARCHAR(32)`，非空，默认 `member`
- `is_active`: Boolean，非空，默认 true
- `is_verified`: Boolean，非空，默认 false；只为后续 FastAPI Users 兼容性预留，本阶段无认证行为
- `created_at`, `updated_at`

User 与 Task 为一对多。删除 User 时，Task 的 `user_id` 使用 `ON DELETE SET NULL`，避免删除账号导致企业测试历史被级联删除。

### 3.2 Task (`tasks`)

字段：

- `id`: UUID，主键；同时作为 API task id、Redis key 标识和 Celery 业务参数
- `user_id`: nullable UUID，外键到 `users.id`，`ON DELETE SET NULL`
- `celery_task_id`: nullable `VARCHAR(255)`，Celery 投递后写入；非空值唯一
- `title`: `VARCHAR(255)`，非空。现有 API 未提供 title 时由 service 取 requirement 第一行；第一行为空时使用 `Untitled Test Task`，保持 API contract 向后兼容
- `requirement_text`: Text，非空
- `status`: `VARCHAR(32)`，如 queued/running/completed/failed
- `stage`: `VARCHAR(64)`，当前生命周期阶段
- `progress`: SmallInteger，0 到 100 的 CHECK constraint
- `state_version`: BigInteger，默认 0；用于单调状态更新和 Redis 投影新旧判断
- `generation_config`: JSONB，非空，默认空对象
- `execution_config`: JSONB，非空，默认空对象
- `result_summary`: nullable JSONB，保存 Review、Coverage、Pytest 等可查询摘要，不复制 Redis 的全部瞬时 payload
- `result_payload`: nullable JSONB，长期保存经过脱敏与大小限制的最终结构化结果，供 Task Detail 恢复完整历史
- `error`: nullable Text
- `created_at`, `updated_at`, `completed_at`

约束与索引：

- `celery_task_id` 建立 `WHERE celery_task_id IS NOT NULL` 的唯一部分索引。
- `(user_id, created_at)` 与 `(status, updated_at)` 建立组合索引。
- generation/execution config 写入前必须移除 API Key、Authorization header 等秘密；LLM API Key 不进入数据库。
- `result_payload` 至少可包含需求拆分、测试用例、AI Review、裁剪后的 retrieved context 摘要、HTTP/Pytest 结果、Failure Analysis 与工具执行信息。禁止保存 API Key、Authorization、完整敏感 header、无限 response body 或无限 LLM raw payload；context、response 与错误堆栈必须经过字段 allowlist、脱敏和大小上限处理。

### 3.3 TestCase (`test_cases`)

字段：

- `id`: UUID，主键
- `task_id`: UUID，非空外键到 `tasks.id`，`ON DELETE CASCADE`
- `case_id`: `VARCHAR(64)`，例如 TC-001
- `module`, `title`, `priority`, `test_type`
- `source_requirement`: Text
- `preconditions`: JSONB，非空，默认空数组
- `steps`: JSONB，非空，默认空数组
- `version`: Integer，默认 1；只为以后版本管理预留，本阶段不实现版本操作
- `created_at`, `updated_at`

使用 `(task_id, case_id, version)` 唯一约束，并为 `task_id` 建立索引。当前 Pydantic `TestCase` 与 ORM 模型可能重名，实现时使用模块命名空间或 `TestCaseORM` 别名，避免破坏 API contract。

### 3.4 Execution (`executions`)

字段：

- `id`: UUID，主键
- `task_id`: UUID，非空外键到 `tasks.id`，`ON DELETE CASCADE`
- `test_case_id`: nullable UUID，外键到 `test_cases.id`，`ON DELETE SET NULL`
- `kind`: `VARCHAR(32)`，例如 http/pytest
- `attempt`: Integer，默认 1
- `idempotency_key`: `VARCHAR(255)`，唯一，用于 Celery retry 防止重复落库
- `method`, `path`
- `expected_status`, `actual_status`
- `passed`: Boolean，非空
- `duration_ms`: Numeric 或 Float
- `response_excerpt`: nullable Text，只保存截断且脱敏后的片段
- `error`: nullable Text
- `failure_category`: nullable `VARCHAR(64)`，例如 contract_mismatch
- `created_at`

HTTP 行应包含 method/path/status；Pytest 汇总行可允许这些字段为空，由 service 层执行 kind-specific 校验。为 `(task_id, created_at)`、`(task_id, passed)` 和 `failure_category` 建立索引。不得保存完整认证 header 或无限制响应体。

### 3.5 KnowledgeDocument (`knowledge_documents`)

字段：

- `id`: UUID，主键
- `title`, `source_name`, `kind`
- `vector_collection`: `VARCHAR(255)`，记录 Chroma collection
- `vector_document_id`: `VARCHAR(255)`，关联 ChromaDB 中的真实向量文档
- `metadata`: JSONB，非空，默认空对象
- `index_status`: `VARCHAR(32)`，如 pending/indexing/indexed/failed
- `error`: nullable Text
- `created_at`, `updated_at`

使用 `(vector_collection, vector_document_id)` 唯一约束，并为 `index_status`、`source_name`、`kind` 建立索引。SQLAlchemy Declarative 的 `metadata` 是保留属性，实现时 Python 属性命名为 `document_metadata`，数据库列名仍为 `metadata`。向量和 embedding 继续只存 ChromaDB。

## 4. 存储职责划分

| 组件 | 权威数据 | 生命周期 | 禁止承担的职责 |
| --- | --- | --- | --- |
| PostgreSQL | 用户、任务历史、用例、执行记录、知识文档目录、关键终态 | 长期 | 高频 WebSocket progress、向量 embedding、消息投递 |
| Redis | 实时 stage/progress、短期 result、缓存、Celery result | TTL/可重建 | 永久业务历史的唯一来源 |
| RabbitMQ | Celery command/message | 消费后结束 | 业务查询、结果存储 |
| ChromaDB | RAG 文本、metadata、embedding、相似度检索 | 长期向量索引 | 用户/任务/执行关系数据 |

KnowledgeDocument 是 PostgreSQL 与 ChromaDB 的目录关联，不是 embedding 副本。RabbitMQ 与 Redis 继续保留，不能因 PostgreSQL 的引入而移除。

## 5. 推荐目录结构

```text
src/req2test/
├── settings.py
├── api_dependencies.py
├── db/
│   ├── __init__.py
│   ├── base.py
│   ├── session.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── task.py
│   │   ├── test_case.py
│   │   ├── execution.py
│   │   └── knowledge_document.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── users.py
│   │   ├── tasks.py
│   │   ├── test_cases.py
│   │   ├── executions.py
│   │   └── knowledge_documents.py
│   └── services/
│       ├── __init__.py
│       ├── task_persistence.py
│       └── knowledge_catalog.py
├── api.py
├── worker.py
├── task_store.py
└── rag.py

alembic.ini
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── <revision>_create_business_tables.py

tests/db/
├── conftest.py
├── test_models.py
├── test_repositories.py
├── test_task_persistence.py
├── test_migrations.py
└── test_api_task_persistence.py
```

## 6. 需要新增的 Python 文件

- `settings.py`：集中读取 DATABASE_URL、数据库 pool 与现有 Redis/Celery/Chroma 配置。
- `api_dependencies.py`：提供同步 `get_db()` 等 FastAPI dependency。
- `db/base.py`：Declarative Base、UUID/timestamp mixin 和 naming convention。
- `db/session.py`：Engine、Session factory、Worker 使用的 session context manager。
- `db/models/*.py`：五个 ORM model；`models/__init__.py` 统一导入，确保 Alembic 能发现全部 metadata。
- `db/repositories/*.py`：按聚合提供明确、可测试的 CRUD 与查询，不在 route 中散落 SQL。
- `db/services/task_persistence.py`：任务创建、生命周期 milestone、终态批量持久化和幂等处理。
- `db/services/knowledge_catalog.py`：协调 PostgreSQL 目录状态与 Chroma upsert。
- `alembic/env.py` 与第一份 migration。
- `tests/db/*.py`：数据库、Repository、迁移、任务/API 持久化测试。

## 7. 需要修改的现有文件

- `pyproject.toml`、`requirements.txt`：增加 SQLAlchemy 2.x、Alembic、`psycopg[binary]` 和必要的测试依赖。
- `.env.example`：增加 DATABASE_URL 与 PostgreSQL compose 变量，所有示例值保持非生产秘密。
- `src/req2test/api.py`：注入 Session；创建 PostgreSQL Task 后再创建 Redis 投影和发布 Celery；GET 在 Redis 缺失/陈旧时回退 PostgreSQL；扩展 health。
- `src/req2test/worker.py`：写入 started/关键 milestone/final/failed；终态在单个数据库事务中保存 Task、TestCase、Execution。
- `src/req2test/task_store.py`：保留 Redis 实时职责，增加 `state_version`、从数据库重建投影和幂等终态辅助方法。
- `src/req2test/rag.py`、`src/req2test/kb_cli.py`：索引时更新 KnowledgeDocument 目录状态；不改变 Chroma 的向量职责。
- `docker-compose.yml`、`docker-compose.override.yml`：增加 PostgreSQL、迁移服务、volume、health dependency 与 DATABASE_URL。
- `Dockerfile`：只在迁移/健康检查确有需要时补充运行依赖，不在镜像构建时执行 migration。
- `README.md`：补充数据库启动、迁移、测试和故障恢复操作。

## 8. Alembic 方案

### 8.1 配置

- 根目录保留 `alembic.ini`，实际 URL 由 `settings.py` 注入，避免在配置文件中提交密码。
- `alembic/env.py` 导入全部 ORM models，并将 `Base.metadata` 设为 `target_metadata`。
- 开启 `compare_type=True` 和 `compare_server_default=True`。
- offline 与 online migration 都支持；online migration 使用事务执行。
- 为 constraint/index 定义稳定 naming convention，避免不同环境产生随机名称。

### 8.2 第一份 migration

按依赖顺序创建：

1. `users`
2. `tasks`
3. `test_cases`
4. `executions`
5. `knowledge_documents`
6. 所有 unique/check/index/foreign key

外键删除策略：

- `tasks.user_id -> users.id`: `ON DELETE SET NULL`
- `test_cases.task_id -> tasks.id`: `ON DELETE CASCADE`
- `executions.task_id -> tasks.id`: `ON DELETE CASCADE`
- `executions.test_case_id -> test_cases.id`: `ON DELETE SET NULL`

生产部署不让 API 和 Worker 同时抢跑 migration。Compose 中使用一次性的 `migrate` service 执行 `alembic upgrade head`；API/Worker 等待该服务成功完成。Migration 文件必须进入版本控制并在独立数据库上验证，不能只依赖 autogenerate 输出。

Downgrade 按外键逆序删除表。由于 downgrade 可能丢数据，只用于开发或有备份的紧急回滚，正常生产回滚优先回滚应用而保留向前兼容 schema。

## 9. Docker 方案

新增 `postgres:16-alpine`：

```yaml
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: ${POSTGRES_DB:-req2test}
    POSTGRES_USER: ${POSTGRES_USER:-req2test}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-req2test_dev}
  volumes:
    - postgres_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
    interval: 5s
    timeout: 5s
    retries: 10
```

API、Worker 和 migrate 共用：

```text
DATABASE_URL=postgresql+psycopg://req2test:...@postgres:5432/req2test
```

启动依赖：

```text
postgres healthy
  -> migrate: alembic upgrade head
  -> API + Worker

redis healthy + rabbitmq healthy
  -> API + Worker
```

`GET /health` 是纯 liveness，只表示 FastAPI 进程能够响应，不因 PostgreSQL、Redis 或 RabbitMQ 临时不可用而失败。`GET /ready` 是 readiness，最终检查 PostgreSQL、Redis、RabbitMQ 是否满足接收新任务的条件；Phase 4A-1 先以数据库 `SELECT 1` 建立接口结构，Redis/RabbitMQ 完整检查在任务持久化接入阶段补齐。依赖不满足时 `/ready` 返回 503，而 `/health` 仍返回 200。

生产环境中 Redis 不可用时，历史查询可以回退 PostgreSQL，但 `POST /api/v1/tasks` 必须返回明确 503，不能接受无法提供可靠实时状态的新异步任务。memory TaskStore fallback 仅允许 local development 和 test。RabbitMQ 不可用时同样不能假装任务已成功投递。

PostgreSQL 使用独立 named volume。ChromaDB 继续使用自己的持久目录或 volume，不能与 PostgreSQL volume 混合；若 API 与 Worker 都需要访问同一 Chroma 数据，Compose 应显式挂载同一 Chroma volume。

## 10. 数据一致性策略

PostgreSQL、Redis 和 RabbitMQ 之间不存在单一 ACID 事务。Phase 4A 使用“数据库权威状态 + Redis 可重建投影 + 幂等 Worker + 单调版本”实现最终一致性。

### 10.1 创建任务

1. FastAPI 在 PostgreSQL 事务中创建 `Task(status=queued, state_version=1)` 并 commit。
2. 使用相同 Task UUID 创建 Redis 实时投影。
3. 向 RabbitMQ 发布 Celery task，业务参数中传 Task UUID。
4. 将返回的 Celery task id 写入 PostgreSQL 和 Redis。

Task title 在 service 层生成：优先使用显式 title，其次使用 requirement 第一行，最终回退为 `Untitled Test Task`。该规则不进入 ORM model，也不要求当前 API 客户端增加字段。

若数据库写入失败，返回 503，不创建 Redis 状态、不投递消息，避免无历史的孤儿任务。若消息发布失败，保留数据库记录并更新为 `failed/dispatch_failed`，同步 Redis，返回明确错误；后续可安全重试投递。若消息已发布但 API 在记录 Celery id 前崩溃，Worker 用自身 `request.id` 和业务 Task UUID 自愈关联。

### 10.2 执行中

- 每个细粒度 progress 只写 Redis，避免数据库写放大。
- started、generation_completed、execution_started、completed、failed 等关键节点写 PostgreSQL。
- 每次持久状态变更增加 `state_version`；Repository 使用条件更新，拒绝低版本或从 terminal 回退到 running。
- Redis payload 带同一版本。读取时若 Redis 版本落后于 PostgreSQL，重建 Redis 投影。
- 已经在 Worker 中运行的任务遇到 Redis 写失败时，不应失去永久历史；Worker 继续写 PostgreSQL milestone，并将实时能力标记为 degraded。但生产 API 在创建新异步任务前若发现 Redis 不可用，必须拒绝创建并返回 503。

### 10.3 执行完成

在一个 PostgreSQL 事务中：

1. 按幂等键写入/更新 TestCase。
2. 按 `idempotency_key` 写入 Execution，Celery retry 不得产生重复记录。
3. 写 Task `result_summary`、脱敏且受大小限制的 `result_payload`、`status=completed`、`progress=100`、`completed_at` 和新版本。
4. commit 后再写 Redis completed 状态与短期完整 result，并设置 TTL。

数据库 commit 必须先于 Redis terminal 更新，避免客户端看到 completed 但永久结果尚未落库。失败路径同样先持久化 Task failed/error，再更新 Redis。

### 10.4 读取、修复与对账

- 运行中 GET/WS 优先读 Redis，以获得实时状态。
- Redis key 不存在时，从 PostgreSQL 返回任务状态，并重建缓存。
- terminal 状态冲突时 PostgreSQL 优先。
- 增加可手动或定时运行的 reconciliation 命令：扫描长时间非终态 Task，对照 Redis/Celery 状态，重建缺失投影或标记 lost/failed。
- Phase 4A 不需要引入新的消息基础设施；通过 UUID、唯一约束、版本号、幂等 upsert 和修复命令处理双写窗口。

### 10.5 KnowledgeDocument 一致性

1. PostgreSQL 创建 `index_status=pending`。
2. 更新为 indexing，并向 Chroma upsert 文档和 embedding。
3. 成功后保存 `vector_document_id` 并更新 indexed；失败则记录 failed/error。
4. 重试复用同一稳定 vector id，避免 Chroma 重复文档。

删除或重建索引也采用显式状态转换。PostgreSQL 记录目录和处理状态，Chroma 仍是向量内容的权威存储。

## 11. 测试计划

Phase 4A 不使用 SQLite 替代关键集成测试，因为 PostgreSQL UUID、JSONB、部分索引和约束行为不同。测试使用独立 PostgreSQL database/schema，fixture 通过 transaction/savepoint 隔离数据。

### 11.1 Database Model Test

- 验证五张表、字段类型、默认值、relationship、FK、unique、check 和 on-delete 行为。
- 验证 UTC timestamp、UUID 与 JSONB round-trip。
- 验证 User 删除后 Task 保留，Task 删除后关联 TestCase/Execution 清理。

### 11.2 Repository Test

- 覆盖 create/get/list/update 和分页查询。
- 覆盖 email、case version、celery task id、execution idempotency 的唯一约束。
- 覆盖条件版本更新，旧事件不能覆盖新状态。

### 11.3 Task Persistence Test

- queued -> running -> completed/failed 生命周期。
- 最终事务同时保存 Task、TestCase、Execution。
- 重复 Celery retry 不产生重复记录。
- config、response excerpt 与 error 脱敏/截断。

### 11.4 Migration Test

- 对空 PostgreSQL 执行 `alembic upgrade head`。
- 使用 inspector 校验五张表、FK、索引与约束。
- 在 CI 临时数据库验证 downgrade/upgrade 往返；生产不自动 downgrade。
- 验证 migrations 与 ORM metadata 没有未提交 drift。

### 11.5 API Task Persistence Test

- Override `get_db()` 并 mock Celery 发布，调用 `POST /api/v1/tasks`。
- 断言响应 UUID、PostgreSQL Task、Redis 投影和 Celery 参数使用同一 task id。
- 覆盖数据库失败、Redis 降级、RabbitMQ 发布失败。
- GET 覆盖 Redis 命中、Redis 缺失回退、terminal 冲突数据库优先。

### 11.6 Worker 与跨存储测试

- 使用确定性 workflow result 验证 Worker milestone 和终态事务。
- 故障注入：Redis 暂时不可用、数据库 commit 失败、重复 delivery、过期 Redis key。
- 验证 422 `contract_mismatch` 可持久化到 `failure_category`。
- KnowledgeDocument 测试只检查 Chroma vector id 关联，不把 embedding 写入 PostgreSQL。
- 现有 API、Demo、HTTP Tool、Pytest、RAG、Failure Analysis 和 25 项回归测试必须继续通过。

## 12. Phase 4A 分步骤实施顺序

1. **配置与依赖**：增加依赖、统一 settings、DATABASE_URL 校验；不改变现有任务行为。
2. **数据库基础设施**：实现 Base、Engine、Session、FastAPI dependency 和 Worker session context。
3. **模型与 Migration**：实现五个模型和第一份 Alembic migration，在空 PostgreSQL 验证。
4. **Repository 层**：实现 CRUD、状态条件更新和幂等 upsert，并完成 Model/Repository tests。
5. **任务创建持久化**：API 先写 Task，再创建 Redis 投影并发布 Celery；增加失败补偿测试。
6. **Worker 生命周期持久化**：接入关键 milestone；完成时事务保存 TestCase、Execution 和 Task summary。
7. **读取与一致性**：实现 Redis-first/DB-fallback、版本比较、缓存重建和 reconciliation 命令。
8. **知识文档目录**：接入 KnowledgeDocument pending/indexed/failed，与 Chroma stable id 对齐。
9. **Docker 与 Migration 启动**：增加 Postgres、volume、healthcheck、一次性 migrate service 和 DATABASE_URL。
10. **质量门禁**：运行 migration、数据库集成、故障注入、完整 pytest 与现有端到端接口检查。
11. **文档与可回滚发布**：记录迁移、备份、恢复和降级运行方式，再进入人工验收。

每一步保持小范围可审查提交，不把认证、Admin 或其他后续阶段混入 Phase 4A。

## 13. 风险与回滚方案

| 风险 | 缓解措施 | 回滚方式 |
| --- | --- | --- |
| PostgreSQL/Redis 双写短暂不一致 | DB 优先、state_version、Redis 重建、reconciliation | 暂时关闭 Redis 投影写入，保留 DB 历史并重建缓存 |
| Celery retry 造成重复用例/执行 | 业务 Task UUID、唯一约束、execution idempotency key、upsert | 清理由 migration/repair script 明确识别的重复行，不人工盲删 |
| 发布成功但 celery_task_id 未落库 | Worker 用 `request.id` 自愈 | 从 Rabbit/Celery event 与 Task UUID 对账 |
| JSONB 结构随 contract 演进漂移 | Pydantic validation、schema_version/version 预留、Repository 封装 | 兼容读取旧 JSONB；通过向前 migration 修正，不直接破坏数据 |
| 数据库连接耗尽 | 受控 pool、短事务、每任务独立 Session、`pool_pre_ping` | 降低 worker concurrency/pool size，重启服务而不删除数据卷 |
| API Key 或响应秘密被持久化 | config allowlist、脱敏器、response 截断、测试断言 | 吊销泄露密钥，执行审计后的数据清理 migration |
| Migration 阻断启动 | CI 空库/升级库验证，一次性 migrate service，部署前备份 | 回滚应用镜像；保留向前兼容 schema，避免生产自动 downgrade |
| User 删除导致审计历史丢失 | User -> Task 使用 SET NULL | 恢复软删除/备份，不级联删除 Task |
| ORM 名称冲突或保留字 | `TestCaseORM` 别名；`document_metadata` 映射 DB `metadata` | 只调整 Python 映射，不改外部 API contract |
| Chroma 与 KnowledgeDocument 状态不一致 | pending/indexing/indexed 状态机、稳定 vector id、重试 | 从 PostgreSQL 目录重新索引，或从 Chroma 对账 vector id |

### 13.1 渐进启用

实现期可用 `PERSISTENCE_ENABLED` 作为短期 rollout/rollback 开关：先在测试环境双写并校验，再将 PostgreSQL 读取设为权威。该开关只用于迁移期，不改变最终 PostgreSQL Source of Truth 的目标。

### 13.2 数据与代码回滚

- UI 已有本地 checkpoint，可与 Phase 4A 数据层变更隔离。
- 第一阶段 schema 以新增表为主，不修改现有 Redis key 或 Chroma collection。
- 回滚应用时保留 PostgreSQL volume 和已写业务数据；旧版本仍可按原 Redis 流程运行。
- 生产 downgrade 前必须备份，优先使用向前修复 migration。
- 不在 Phase 4A 自动迁移、清空或覆盖现有 Chroma 向量数据。

## 14. 开源项目研究结论

### 14.1 FastAPI Full Stack Template

参考其后端分层、集中 settings、单 Engine/请求级 Session、FastAPI generator dependency、Alembic target metadata、数据库启动重试、测试 fixture，以及 Compose 中 PostgreSQL `pg_isready` 和 healthy dependency。模板使用 SQLModel 的实现细节不照搬，本项目将同样的边界翻译为纯 SQLAlchemy 2.x。

参考：

- [Database session](https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/core/db.py)
- [Configuration](https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/core/config.py)
- [FastAPI dependencies](https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/api/deps.py)
- [Alembic environment](https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/alembic/env.py)
- [Compose and PostgreSQL healthcheck](https://github.com/fastapi/full-stack-fastapi-template/blob/master/compose.yml)
- [Database readiness check](https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/tests_pre_start.py)

### 14.2 FastAPI Users

只借鉴其可扩展 User 表字段和“用户存储适配器、UserManager、认证策略相互分离”的边界。Phase 4A 只创建 User model，预留 `is_active`/`is_verified` 等兼容字段，不创建登录 route、JWT strategy 或 password flow。其示例使用异步 Session，本项目按已锁定决策改用同步 Session。

参考：

- [SQLAlchemy user database example](https://github.com/fastapi-users/fastapi-users/blob/master/examples/sqlalchemy/app/db.py)
- [User manager and authentication separation](https://github.com/fastapi-users/fastapi-users/blob/master/examples/sqlalchemy/app/users.py)
- [SQLAlchemy database guidance](https://github.com/fastapi-users/fastapi-users/blob/master/docs/configuration/databases/sqlalchemy.md)

### 14.3 SQLAdmin

未来 SQLAdmin 可直接接收标准 SQLAlchemy declarative model 和 sync Engine。为降低后续接入成本，模型应使用明确的 scalar UUID 主键、mapped columns、relationships 和可读的 `__str__`；避免不必要的复合主键与特殊映射。Phase 4A 不增加 Admin dependency、ModelView 或管理员权限逻辑。

参考：

- [SQLAdmin README](https://github.com/smithyhq/sqladmin/blob/main/README.md)
- [ModelView configuration](https://github.com/smithyhq/sqladmin/blob/main/docs/configurations.md)
