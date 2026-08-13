---
title: 边界值分析
category: test_design
source: ISTQB boundary value analysis concepts
license: Original paraphrased guidance; terminology attributed to ISTQB
version: 1.0
---
# 边界值分析

## 边界集合
对闭区间最小值与最大值验证边界本身、边界内相邻值和边界外相邻值。长度、数量、时间、分页、金额、速率限制都存在边界；空集合与单元素集合也应视为结构边界。

## API 注意点
边界测试需同时观察 HTTP 状态码、响应 schema 和副作用。拒绝越界输入时不应产生部分写入；最大分页或最大 payload 场景还应记录耗时与资源限制。
