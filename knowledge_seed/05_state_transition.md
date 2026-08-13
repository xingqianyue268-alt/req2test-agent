---
title: 状态迁移测试
category: test_design
source: ISTQB state transition testing concepts
license: Original paraphrased guidance; terminology attributed to ISTQB
version: 1.0
---
# 状态迁移测试

## 模型
识别稳定状态、触发事件、守卫条件、动作与目标状态。至少覆盖每条有效迁移，并验证禁止迁移不会改变数据。对任务系统可建模为 pending、running、retrying、completed 与 failed。

## 序列风险
单步正确不代表序列正确。测试重复提交、乱序事件、终态后再次投递、超时恢复和并发更新。验证幂等键或版本号能阻止旧状态覆盖新状态。
