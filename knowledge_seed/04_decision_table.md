---
title: 判定表测试
category: test_design
source: ISTQB decision table testing concepts
license: Original paraphrased guidance; terminology attributed to ISTQB
version: 1.0
---
# 判定表测试

## 条件与动作
当结果取决于多个条件组合时，列出条件、可能取值、规则列和预期动作。合并确实不会改变结果的规则，但不要用直觉删除罕见组合。优先覆盖高风险规则和互斥条件。

## 认证示例
登录决策可包含账号存在、密码正确、账号启用、二次验证通过。预期动作不仅是允许或拒绝，还包括返回状态、审计记录、失败计数和是否泄露账号存在性。
