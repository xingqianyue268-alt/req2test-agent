# Security notes

Req2Test validates the current user and role from PostgreSQL for every protected request;
JWT role claims are not authoritative. Knowledge mutations and all Admin APIs enforce
server-side RBAC.

## Known limitation

Cookie-authenticated state-changing endpoints currently rely on `SameSite=Lax`. A later
release should add CSRF tokens and/or strict `Origin` validation for HttpOnly-cookie
mutation requests. Deployments should keep `SameSite=Lax`, use HTTPS, and avoid exposing
the service to untrusted origins until that protection is added.
