# eduGAIN Integration Guide (Technical)

This document covers the technical preparation for federation onboarding with eduGAIN/NREN channels.

## 1. Scope

The gateway itself does not register automatically in eduGAIN. Registration is an external federation process that requires:

- institutional ownership of metadata
- NREN federation workflow (for example RedIRIS in Spain)
- operational contacts and support procedures

## 2. Required Inputs

1. Public service URL and TLS certificate chain.
2. EntityID and federation metadata URL decisions.
3. Signing keys and rollover policy.
4. Attribute release policy (nameID, ePPN, mail, scoped affiliation).
5. Incident/security contact and service support contact.

## 3. Gateway-side Technical Checklist

1. OpenID/OAuth endpoints reachable through OpenResty:
   - `/.well-known/openid-configuration`
   - `/auth/jwks`
2. Stable issuer URL derived from `SERVER_NAME` and `HTTPS_PORT`.
3. Token validation and audience checks aligned with federated identity assumptions.
4. CORS and callback URLs aligned with final public domains.
5. Monitoring and logs enabled for auth paths.

## 4. NREN Submission Checklist

1. Prepare metadata package requested by the NREN.
2. Submit service endpoints and certificates.
3. Validate test federation login flow.
4. Resolve metadata validation comments.
5. Request propagation to eduGAIN aggregate.

## 5. Evidence to Store in Repository

When external steps are completed, add references under `docs/pilots/`:

- registration ticket IDs
- federation validation reports
- date of publication in federation metadata
- known limitations/open issues

## 6. Security Notes

- Keep private signing keys out of git.
- Document rotation procedures and emergency revocation path.
- Keep clear owner contacts for federation trust incidents.
