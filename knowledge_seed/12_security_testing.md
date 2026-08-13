---
title: Web 与 API 安全测试
category: security_testing
source: OWASP Web Security Testing Guide
license: Original paraphrased checklist; OWASP content is CC BY-SA 4.0
version: 1.0
---
# Web 与 API 安全测试

## 输入与输出
对注入、路径穿越、恶意文件名、超大 payload 和内容类型混淆进行测试。服务端应采用允许列表、参数化查询、大小限制和上下文输出编码，日志不得记录 secret。

## 安全边界
验证 TLS 与 cookie 属性、CORS、CSRF、防缓存策略、速率限制和错误信息。安全测试应记录可复现请求、影响范围和修复建议，但测试数据不得包含真实凭证或生产个人信息。
