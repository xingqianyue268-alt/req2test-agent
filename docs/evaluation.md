# AI Evaluation Center v1

## 定位与边界

Evaluation Center 用于离线评测、回归门禁和模型/Prompt 实验。它复用现有生成工作流，但与
工作流内部 Review Agent 职责分离：Review Agent 在生成期间自动发现问题并修订，Evaluation
Center 对最终产物做独立、可比较的测量。本版本不包含 RAGAS、RAG Eval、Agent Eval、Red
Team、流量回放或新的编排基础设施。

## Golden Dataset

Golden Dataset 是 UTF-8 JSONL，每行是一条严格校验的数据：

```json
{
  "id": "demo-login-001",
  "requirement_text": "用户使用有效账号和密码登录后，应进入首页。",
  "expected_requirements": [
    {"id": "login-success", "text": "有效凭据登录成功", "keywords": ["有效", "登录"]}
  ],
  "expected_constraints": [],
  "tags": ["demo", "authentication"],
  "dataset_version": "golden-demo-v1"
}
```

Loader 拒绝空文件、超过 5 MB 的文件、非法 JSON、重复 case ID、混合 dataset version 和不符合
Pydantic 严格契约的记录。运行同时保存声明版本和完整文件 SHA-256 digest，因此只改版本号不能
伪装相同快照。仓库中的 `evals/golden_demo.jsonl` 全部为虚构、可公开数据。

## 指标与聚合

所有结果使用同一契约：`score`（0–100）、`reason`、`evidence`、`evaluator` 和
`evaluator_version`。

| Metric | 首选评估器 | 默认权重 | 含义 |
|---|---|---:|---|
| `requirement_coverage` | deterministic | 25% | Golden expectation 是否被 Requirement 与 trace 覆盖 |
| `case_completeness` | deterministic | 15% | 用例结构、trace 和配置要求的类型是否完整 |
| `executability` | LLM Judge | 20% | 步骤是否具体、可按顺序执行 |
| `expected_result_quality` | LLM Judge | 15% | 预期结果是否可观察、可判定 |
| `requirement_groundedness` | LLM Judge | 20% | 用例是否由需求支撑、是否产生无依据功能 |
| `redundancy` | deterministic | 5% | 归一化标题/步骤指纹后的重复程度；分数越高冗余越少 |

前三个确定性指标中的 Coverage、Completeness、Redundancy 永远不会再次交给 LLM。后三个主观
指标在 Demo 模式下完全离线计算；在线 Judge 调用、JSON 解析或严格校验失败时也使用相同降级。
总分是版本化权重的加权平均，单 case 和 run aggregate 均标准化为 0–100。

## LLM-as-a-Judge

Judge 复用 `LLMSettings` 与 OpenAI-compatible 客户端；Ollama 使用兼容 endpoint。Prompt 常量
有独立 `judge-v1` 版本和 SHA-256 digest，响应必须精确包含三个主观指标，未知字段、缺项、重复项
或越界分数会触发 deterministic fallback。

发送给 Judge 的 payload 是明确白名单，只包含 Golden requirement/expectation/constraint 和生成的
Requirement/TestCase。API Key、认证 Header、Cookie、ExecutionReport 与响应正文不会进入 Judge
payload。持久化 metadata 只有 provider、model、temperature、seed、Prompt version/digest 和降级
原因；错误文本会做凭据模式脱敏与长度限制。Case result 也只持久化生成的
Requirement、TestCase、Review 和修订次数，不保存 RAG 原始上下文、认证信息或原始模型错误。

## 可复现性定义

每个 Eval Run 保存：

- dataset name、version、SHA-256 digest；
- workflow prompt version、SHA-256 digest；
- generation model/provider、temperature、provider 支持时的 seed；
- 完整 `GenerationConfig`；
- Judge model/provider/temperature/seed 与 Judge Prompt version/digest；
- knowledge base identifier 与内容/catalog digest；
- aggregation/evaluator version、起止时间、latency、修订次数和失败原因。

这些字段让输入和配置可审计、可重新运行。在线托管模型的服务端版本、采样实现和基础设施可能
变化，因此即使元数据一致，也不宣称 bit-for-bit 完全复现。Demo 模式不访问模型服务，适合稳定
CI regression。

## 持久化与异步执行

Migration `20260909_0005_evaluation_center` 新增：

- `evaluation_runs`：不可变输入快照、运行状态、聚合分数和运行 metadata；
- `evaluation_case_results`：每条 Golden case 的六项完整评分、evidence、Judge metadata 与产物；
- `evaluation_comparisons`：同一 dataset snapshot 的 A/B run 引用和 delta summary。

FastAPI 创建记录后提交事务，再将 run ID 与快照 metadata 交给现有 RabbitMQ/Celery。Worker 在
执行前检查 dataset 和 knowledge digest，逐 case 失败不会抹掉其他结果；两个 A/B run 都终态后
自动生成 comparison summary。

## API 与 UI

所有 Evaluation API 都要求现有 JWT 登录，资源按 owner 隔离，Admin 沿用现有 RBAC 查看全部。
浏览器入口为 `/evaluations`。API：

```text
GET  /api/v1/evaluations/datasets
POST /api/v1/evaluations/runs
GET  /api/v1/evaluations/runs
GET  /api/v1/evaluations/runs/{run_id}
POST /api/v1/evaluations/comparisons
GET  /api/v1/evaluations/comparisons
GET  /api/v1/evaluations/comparisons/{comparison_id}
```

## 离线 regression gate

```bash
python scripts/run_eval.py \
  --dataset evals/golden_demo.jsonl \
  --mode demo \
  --min-score 80
```

命令输出 dataset/prompt digest、配置、六项指标和总分。低于阈值时返回 1，
dataset 无效或执行错误时返回 2。`--output`
可选保存完整报告；Demo 模式不会读取 API Key，也不要求 Ollama、PostgreSQL、Redis 或 RabbitMQ。

## 已知限制

- 托管的在线模型只保证输入与运行 metadata 可追溯，不保证 bit-for-bit 输出相同。
- `golden-demo-v1` 只是小型公开演示集；确定性词法/结构指标是稳定回归信号，不等同于人工领域评审。
- v1 从受控的服务端 JSONL 注册目录发现 dataset，尚不提供在线编辑/发布 dataset 的 UI。
- Compose 会以只读卷挂载 `evals/`；脱离 Compose 部署镜像时，运行方需设置
  `REQ2TEST_EVAL_DATASET_DIR` 并挂载受信任的 dataset 目录。
- 在线 Judge 需要可用的 OpenAI-compatible/Ollama endpoint；CI 仅验证完全离线降级路径。
