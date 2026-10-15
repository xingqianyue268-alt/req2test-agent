# Security notes

Req2Test validates the current user and role from PostgreSQL for every protected request;
JWT role claims are not authoritative. Knowledge mutations and all Admin APIs enforce
server-side RBAC.

## Execution targets

HTTP Tool, Pytest Runner (including direct calls and generated modules) and the shared
execution entry point use the same target policy. Only HTTP(S) base URLs with an allowed
hostname are accepted. Embedded credentials, base queries/fragments and malformed ports
are rejected. Both clients disable automatic redirects: a 30x response is tested as-is,
including redirects to an otherwise allowed host. Use the final authorized URL if needed.

`REQ2TEST_EXECUTION_ALLOWED_HOSTS` defaults to `localhost,127.0.0.1,::1,api`.
`REQ2TEST_ALLOW_REMOTE_EXECUTION=true` is an explicit administrator override, not a safe
multi-tenant default. This is hostname authorization, not DNS pinning, port isolation or
an OS network sandbox. Only fixed HTTP test templates are generated; arbitrary Python
is not accepted by the public API.

## Browser Cookie and Origin policy

Set `REQ2TEST_TRUSTED_ORIGINS` to a comma-separated list of exact browser origins, e.g.
`https://req2test.example.com`. Include scheme and non-default port, without a path,
trailing slash or wildcard. Defaults cover only `http://localhost:8000` and
`http://127.0.0.1:8000`. A custom port/domain or reverse proxy needs explicit configuration.
The application never derives trusted origins from `Host` or `Forwarded` headers.

State-changing requests authenticated by the HttpOnly Cookie require a trusted Origin;
missing, `null`, duplicate and foreign origins fail closed with 403. Cookie WebSocket
connections require the same proof (4403 otherwise). Keep HTTPS, HttpOnly and SameSite=Lax.
A test client simulating a browser must supply its configured Origin, just as a browser does.

Bearer-only API requests need no Origin. On ordinary protected endpoints, a nonempty
Bearer credential is authoritative even if a Cookie is also present; invalid Bearer tokens
cannot fall back to Cookie authentication. Malformed/empty authorization headers cannot
bypass the Cookie guard. Login, registration and logout change browser sessions: if an
Origin or session Cookie is present, these routes require a trusted Origin even with Bearer.
Non-browser credential login without Origin or Cookie remains supported.

## Sensitive output

`security/redaction.py` is shared by execution reports, evidence, task/error persistence,
Redis reads/writes, WebSocket projections, exports, evaluation output and LLM prompts.
It recognizes structured and textual JSON, Python dict representations, credential headers,
URL userinfo/query parameters, validation input echoes and configured sensitive fields.
Redaction precedes truncation. Assertion diagnostics omit raw compared values. Existing
stored task output is sanitized when read, but this change does not erase old stored data.

Worker exceptions, final/dead-letter results, retry tracebacks and queue argument display
metadata are sanitized. HTTPX information logs are sanitized; HTTPCore/OpenAI SDK debug
payloads are suppressed because they can contain raw bodies and byte-pair headers.
Use `REQ2TEST_REDACT_FIELDS` to add comma-separated field names specific to your data.

Execution inputs and assertions remain unchanged in memory. The broker still transports
actual execution arguments; it must remain access-controlled. Model client credentials,
login responses and authorized identity fields are intentionally usable. Knowledge source
content remains application data; diagnostics and model prompts derived from it are sanitized.
Redaction is field-based, not a universal detector for unlabelled secrets, arbitrary encodings
or personal data in prose. Do not enable raw SQL parameter logging, external tracing or
third-party request capture without separately securing those sinks.

See [the P0 acceptance report](docs/security-hardening-report.md) for evidence, tested scope,
unverified areas and rollback instructions. No schema migration is introduced by this patch.
