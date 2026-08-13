---
title: Failure Analysis 证据化诊断
category: failure_analysis
source: Req2Test Failure Analysis V2 taxonomy
license: Project original
version: 2.0
---
# Failure Analysis 证据化诊断

## 根因优先级
优先呈现最具体且由确定性证据支持的根因。实际 422 与 schema 校验信息可归为 contract_mismatch；客户端连接超过配置 deadline 归为 timeout；实际 401 归为 authentication_error；真实上游 500 归为 upstream_api_error。

## 主因与辅助信号
pytest assertion_failure 是执行信号，不应覆盖更具体的 API 根因。证据至少包含 expected 与 actual、请求 method/path、duration、响应摘要或异常类型。建议必须对应证据，不能凭空推断服务内部实现。
