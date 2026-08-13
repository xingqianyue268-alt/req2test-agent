---
title: API 测试设计
category: api_testing
source: OpenAPI Specification and Schemathesis concepts
license: Original paraphrased guidance; OpenAPI and Schemathesis licenses apply
version: 1.0
---
# API 测试设计

## 契约层
根据 OpenAPI 验证 method、path、参数位置、required、类型、枚举、格式、状态码与响应 schema。既验证有效示例，也生成违反单个约束的最小反例，便于定位 contract mismatch。

## 行为层
契约正确之外，还要验证鉴权、幂等、分页、排序、并发、持久化副作用与错误语义。Schemathesis 一类 schema 驱动方法适合扩大输入覆盖，但关键业务不变量仍需显式断言。
