# Req2Test Agent 验收记录

最后一次本地集成验收：2026-08-12

## 验收环境

- macOS / Apple Silicon
- Python 3.13 本地虚拟环境
- Docker Desktop（Linux aarch64 容器）
- Redis 7
- RabbitMQ 3.13 Management
- FastAPI + Celery Worker

## 自动化回归

```text
20 passed in 3.23s
```

覆盖内容包括：

- LangGraph 测试生成主流程
- Redis / 异步任务状态模型
- ChromaDB RAG 知识库
- HTTP API Tool 真实本机请求
- Pytest Runner 真实子进程执行
- 多行 HTTP 契约聚合解析
- 422 请求校验失败归因
- Demo Dashboard 关键展示元素

## RAG 验收

执行：

```bash
req2test-kb rebuild
req2test-kb stats
req2test-kb search --query "用户使用正确账号密码登录" --top-k 3
```

实际结果：

- Chroma backend 正常
- 15 条文档成功入库
- 登录查询首条召回历史用例 `case-HIST-001`

## Docker Compose 验收

已确认以下服务正常启动：

- Redis：Healthy
- RabbitMQ：Healthy
- FastAPI：Application startup complete
- Celery Worker：ready

## Demo A：全通过链路

输入两条显式 API 契约：

```text
GET /demo-target/health
预期状态码：200
响应包含：{"status":"ok"}

POST /demo-target/echo
请求体：{"message":"hello"}
预期状态码：200
响应包含：{"status":"ok"}
```

实际结果：

```text
HTTP 用例：2
HTTP 通过：2
HTTP 失败：0
Pytest：PASS
http_pass_rate：1.0
failure_analysis：[]
```

同时确认需求解析仅生成两个 Requirement，状态码、响应断言和请求体均保留在各自接口的 `acceptance_criteria` 中，没有被错误拆成独立需求。

## Demo B：失败归因链路

故意省略 POST 请求体：

```text
POST /demo-target/echo
预期状态码：200
```

实际结果：

```text
GET /demo-target/health：PASS，200 -> 200
POST /demo-target/echo：FAIL，200 -> 422
HTTP 用例：2
HTTP 通过：1
HTTP 失败：1
Pytest：FAIL
```

失败归因：

```text
API-002 · contract_mismatch
```

平台能够识别请求已到达接口，但请求体或参数未通过服务端契约校验，并提示核对必填字段、字段类型、请求格式与测试数据。

## 验收结论

第三阶段核心闭环已真实跑通：

```text
需求输入
→ RAG 检索
→ LangGraph 多 Agent 测试设计
→ Execution Planner
→ HTTP API Tool
→ Pytest Runner
→ 真实执行结果
→ Failure Analyzer
→ Dashboard / 原始 JSON
```

以上结果用于证明项目在本地演示环境中的可复现性，不代表任何外部生产系统的质量或 SLA。
