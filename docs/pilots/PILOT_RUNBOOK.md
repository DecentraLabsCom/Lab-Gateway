# Pilot Runbook

Use this runbook to execute institutional pilots and capture evidence for MoU deliverables.

## 1. Pilot Scope

- Validate end-to-end reservation + auth + remote session flow.
- Validate operational reliability (health checks, logs, recoverability).
- Capture user/admin feedback and map issues to remediation.

## 2. Minimum Test Matrix

1. Gateway health (`/health`, `/gateway/health`).
2. Auth metadata (`/.well-known/openid-configuration`, `/auth/jwks`).
3. Guacamole session launch after authenticated flow.
4. Ops endpoints with valid/invalid token.
5. Reservation automation behavior (if enabled).
6. TLS and CORS behavior from external clients.

## 3. Evidence Collection

- Deployment commit/branch references.
- Configuration fingerprint (non-secret values only).
- Logs for success and failure scenarios.
- Screenshots of user journeys.
- Performance notes (latency, startup times).
- Known issues and mitigations.

## 4. Completion Criteria

- All critical tests pass.
- At least one real lab station session validated.
- Institutional operators confirm maintainability and onboarding clarity.
- Findings documented in pilot report template and linked in repo.

## 5. Report Templates

- `docs/pilots/UNED_PILOT_REPORT_TEMPLATE.md`
- `docs/pilots/PARTNER_PILOT_REPORT_TEMPLATE.md`
