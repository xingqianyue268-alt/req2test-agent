---
title: 等价类划分
category: test_design
source: ISTQB equivalence partitioning concepts
license: Original paraphrased guidance; terminology attributed to ISTQB
version: 1.0
---
# 等价类划分

## 设计方法
把输入域划分为系统预期以相同方式处理的集合，每个有效和无效等价类至少选择一个代表值。划分维度可包括类型、格式、权限、业务状态和组合约束，避免只按数值范围划分。

## 示例
年龄允许 18 至 60 时，有效类是区间内整数；无效类包括小于 18、大于 60、非整数、空值和错误类型。若接口还要求实名认证，应将认证状态作为独立分区考虑。
