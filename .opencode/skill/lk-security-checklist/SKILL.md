---
name: lk-security-checklist
description: When reviewing or writing code, use this security checklist to identify common vulnerabilities and unsafe patterns. Invoke for security-focused code review, audit, or before finishing a feature.
license: MIT
compatibility: opencode
---

## What I do
Provide a structured security checklist covering input validation, authentication, data protection, error handling, dependencies, logging, business logic, and framework-specific concerns.

## When to use me
- Before marking a feature as complete
- During code review or security audit
- When handling user input, authentication, cryptography, or external dependencies
- When the issue involves security, privacy, or compliance requirements

## How to use me
Apply the checklist by category. Do not treat it as a pass/fail gate; use it to surface risks and decide whether to fix, document, or escalate.

### Input validation
- [ ] All user input is validated (allowlist over denylist)
- [ ] SQL queries use parameterization (prevents SQL injection)
- [ ] HTML output is escaped (prevents XSS)
- [ ] File paths do not accept user input (prevents path traversal)
- [ ] URL/redirect targets use an allowlist (prevents open redirect)
- [ ] Command execution does not accept concatenated user input (prevents command injection)
- [ ] Deserialization uses trusted formats (prevents deserialization vulnerabilities)

### Authentication & authorization
- [ ] Passwords are stored using bcrypt/argon2/scrypt (not plaintext, not MD5/SHA1)
- [ ] Session tokens are random and unpredictable (use `secrets` module, not `random`)
- [ ] Every endpoint has authorization checks (not just UI layer)
- [ ] JWT/session tokens have expiration (not long-lived)
- [ ] API keys/passwords are not present in code or logs
- [ ] Failed login attempts have rate limiting
- [ ] Password reset tokens are single-use and expire
- [ ] Multi-factor authentication is used for sensitive operations

### Data protection
- [ ] Sensitive data (PII / financial / health) is encrypted at rest
- [ ] All external communication uses HTTPS
- [ ] Database connections use TLS (not plaintext)
- [ ] Backups are encrypted and stored offline
- [ ] Key management uses dedicated services (AWS KMS / Vault / ...), not written in config files
- [ ] Logs do not print sensitive data (passwords, tokens, credit card numbers, SSNs)

### Error handling
- [ ] Error messages do not leak internal details (stack traces, internal paths, library versions)
- [ ] Exceptions are logged but not exposed to end users
- [ ] Failures default to secure (fail closed): authorization failure = deny, not allow
- [ ] Input validation failures do not return detailed errors (to prevent attackers probing the system)

### Dependencies & configuration
- [ ] Dependency versions are pinned (no ^/~, to avoid automatic upgrades introducing vulnerabilities)
- [ ] Regularly audit dependencies for vulnerabilities (`npm audit` / `pip-audit` / `cargo audit`)
- [ ] Configuration files are not in git (`.gitignore` secrets)
- [ ] Production environment does not enable debug mode (does not expose tracebacks)
- [ ] CORS configuration is strict (no wildcard allowing any origin)
- [ ] CSP headers are set (if applicable)

### Logging & monitoring
- [ ] Security events are auditable (logins, permission changes, sensitive operations)
- [ ] Anomalous logins trigger alerts (unusual locations, repeated failures)
- [ ] Logs do not contain PII (unless necessary and encrypted)
- [ ] Logs have a retention policy (do not retain sensitive data indefinitely)

### Business logic
- [ ] Financial/quantity operations are atomic (not partially committed)
- [ ] State machine transitions have validity checks (cannot jump from terminal back to initial)
- [ ] Critical operations have idempotency keys (prevent duplicate execution)
- [ ] Time window / timezone logic is explicit (avoid TOCTOU vulnerabilities)
- [ ] Sorting / priority logic does not expose internal information

### Framework / language specific
- Web: [ ] CSRF token, [ ] SameSite cookie, [ ] HttpOnly cookie
- SQL: [ ] Parameterization (see Input validation), [ ] Prefer ORM
- Containers: [ ] Non-root user, [ ] Minimal base image, [ ] Image scanning
- Kubernetes: [ ] RBAC, [ ] NetworkPolicy, [ ] Pod Security Standards
- AI/LLM: [ ] Input sanitization (prevents prompt injection), [ ] Output filtering (prevents info leakage), [ ] Token limits

## Output format
For each checklist item, provide a verdict:

- **✅ Pass**: Clear evidence that it is implemented
- **⚠️ Needs verification**: Requires more information or context
- **❌ Fail**: Clear vulnerability or anti-pattern found – must be fixed or escalated
- **⏭️ Not applicable**: Current changes do not involve this area

When you find ❌ or ⚠️, use the `inline-comments` skill to leave traceable notes at the relevant code or documentation locations.
```
