---
title: Pytest 自动化基础
category: automation
source: pytest documentation concepts
license: Original paraphrased guidance; pytest MIT license applies
version: 1.0
---
# Pytest 自动化基础

## 测试结构
测试名称表达行为，Arrange、Act、Assert 保持清楚。fixture 管理可复用前置条件并用最小 scope 隔离状态；parametrize 表达等价输入集合；marker 用于选择而非隐藏不稳定测试。

## 可靠性
断言应包含有诊断价值的差异。避免依赖执行顺序、共享可变数据和固定 sleep。外部依赖用明确边界替身，端到端测试则保留真实协议与持久化证据。
