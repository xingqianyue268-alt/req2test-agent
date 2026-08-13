# Req2Test Agent 验收记录

最后一次本地集成验收：2026-08-14

## 验收环境

- macOS / Apple Silicon + Docker Desktop
- Python 3.11 容器
- PostgreSQL 16、Redis 7、RabbitMQ 3.13
- FastAPI、Celery Worker 与本地 ChromaDB

## 自动化回归

```text
131 passed
```

测试覆盖数据库 migration、认证与 RBAC、任务持久化和隔离、Celery retry 与幂等、Knowledge Base 生命周期、RAG 召回、HTTP Tool、Pytest Runner、Failure Analysis V2、WebSocket fallback 及主要页面契约。

## Knowledge Base

- 13 份内置 Markdown 写入 PostgreSQL `knowledge_documents`
- 39 个 chunks 写入统一 Chroma collection
- 重复 seed 不创建重复目录或向量
- 上传、重新索引、删除、全库重建与真实 top-k 搜索通过
- Workbench 召回与 Knowledge 页面使用同一知识库

## 可复现执行场景

| 场景 | HTTP 结果 | Failure Analysis V2 |
|---|---|---|
| PASS | 预期状态与实际状态一致 | 无失败诊断 |
| 422 | expected 200 / actual 422 | `contract_mismatch` |
| Timeout | 客户端 deadline 到期 | `timeout` |
| 401 | expected 200 / actual 401 | `authentication_error` |
| 500 | expected 200 / actual 500 | `upstream_api_error` |

诊断结果保留确定性证据、置信度、修复建议，并将 assertion/Pytest failure 作为辅助信号而非覆盖更具体的 API 根因。

## 基础设施与持久化

- `/health` 与 `/ready` 正常
- PostgreSQL、Redis、RabbitMQ、API 与 Worker 健康
- 任务、TestCase、Execution 和诊断证据可从 PostgreSQL 恢复
- Redis 中断不会改变 PostgreSQL 的长期数据权威地位
- 重复 Celery delivery 不重复执行或写入结果

以上是项目自身在指定本地环境中的可复现验收结果，不代表外部系统的质量或生产 SLA。
