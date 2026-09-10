# Req2Test Agent 验收记录

历史完整平台验收：2026-08-14

Evaluation Center v1 验收：2026-09-10

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

## Evaluation Center v1 验收范围

- 公开 `golden-demo-v1` JSONL 可加载，版本混用、重复 ID、越界文件和非法结构被拒绝。
- 六项指标统一输出 0–100 `score`、`reason`、`evidence`。
- Coverage、Completeness、Redundancy 只走确定性评估器。
- Executability、Expected Result Quality、Groundedness 在 Judge 失败或 Demo 模式下确定性降级。
- Judge 输出严格校验，Prompt version/digest 与非敏感模型参数被保存。
- EvaluationRun、EvaluationCaseResult、EvaluationComparison 可通过 Alembic migration 持久化。
- 普通用户只能读取自己的 Run/Comparison，Admin 可查看全部；响应不返回 API Key。
- A/B 固定同一个 dataset snapshot，并输出各指标、总分、延迟、修订次数及 B-A delta。
- `/evaluations` 覆盖 Dataset、创建 Run、详情/evidence 与 A/B 结果。
- GitHub Actions 在原有 pytest 后执行完全离线的 80 分 regression gate。

确定性 smoke gate：

```bash
python scripts/run_eval.py --dataset evals/golden_demo.jsonl --mode demo --min-score 80
```

基线 `golden-demo-v1` 当前总分为 `98.45/100`。此分数来自 Demo 生成与规则降级，CI 不需要
OpenAI API Key 或 Ollama 服务。2026-09-10 在真实 PostgreSQL/Redis/RabbitMQ/Celery
组合环境中执行 `pytest -q`：`162 passed, 0 skipped, 0 failed`。最终发布数字以本次
收尾后的重新运行结果为准。

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
