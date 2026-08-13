---
title: 测试用例设计基础
category: test_design
source: ISTQB testing principles and Req2Test editorial synthesis
license: Original summary; terminology attributed to ISTQB
version: 1.0
---
# 测试用例设计基础

## 可追溯性
每个测试用例应关联明确的需求或风险。标题描述行为，前置条件只保留执行所需状态，步骤应可复现，预期结果必须可观察。一个用例不应同时验证多个无关目标，否则失败后难以定位根因。

## 优先级与覆盖
优先级由业务影响、发生概率和检测成本共同决定。正向路径证明能力可用，异常与边界路径揭示防御能力。评审时检查需求、用例、执行证据三者是否能形成闭环。
