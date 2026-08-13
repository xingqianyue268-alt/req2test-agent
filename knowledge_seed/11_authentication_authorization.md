---
title: Authentication 与 Authorization 测试
category: security_testing
source: OWASP WSTG authentication and authorization guidance
license: Original paraphrased checklist; OWASP content is CC BY-SA 4.0
version: 1.0
---
# Authentication 与 Authorization 测试

## Authentication
验证无凭证、无效凭证、过期 token、撤销状态、暴力尝试限制和会话结束。401 响应不应泄露密码、token 或可利用的账号枚举差异。JWT 测试需覆盖签名、算法、issuer、audience 和时间声明。

## Authorization
以资源所有权和角色矩阵验证水平与垂直越权。只隐藏 UI 不构成权限控制；每个敏感 API 都应在服务端拒绝未授权访问。检查 ID 替换、批量接口和间接对象引用。
