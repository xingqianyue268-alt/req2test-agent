# Security notes

Req2Test validates the current user and role from PostgreSQL for every protected request;
JWT role claims are not authoritative. Knowledge mutations and all Admin APIs enforce
server-side RBAC.

## Phase Security TODO

Cookie-authenticated state-changing endpoints currently rely on `SameSite=Lax`. A later
security phase must add CSRF tokens and/or strict `Origin` validation for HttpOnly-cookie
mutation requests. This TODO is intentionally recorded here; CSRF is outside Phase 4C/4D.
