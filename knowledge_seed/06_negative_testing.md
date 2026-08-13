---
title: 异常与负向测试
category: test_design
source: Req2Test testing practice synthesis
license: CC BY 4.0
version: 1.0
---
# 异常与负向测试

## 输入与依赖故障
负向测试覆盖缺失字段、错误类型、非法格式、冲突状态、权限不足、依赖超时和上游 5xx。预期应定义为明确的错误契约，而不是笼统的“失败”。

## 诊断质量
区分业务拒绝与基础设施异常。401 通常指向认证，403 指向授权，422 常提示契约或校验不一致，客户端 timeout 没有伪造的 HTTP 状态。保留请求阶段、耗时和响应摘要作为证据。
