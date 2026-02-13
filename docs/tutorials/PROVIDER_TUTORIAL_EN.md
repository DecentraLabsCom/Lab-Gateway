# Lab Provider Tutorial (English)

This tutorial explains how a lab provider can publish and operate a remote lab with DecentraLabs Gateway.

## 1. Prerequisites

- Gateway deployed and healthy (`/health` and `/gateway/health`).
- Access to Guacamole admin credentials.
- Valid token for protected routes (`SECURITY_ACCESS_TOKEN` and optional `LAB_MANAGER_TOKEN`).
- Lab station host data configured for ops-worker if remote power/session control is required.

## 2. Configure Guacamole Connections

1. Open `https://<gateway-domain>/guacamole`.
2. Sign in with `GUAC_ADMIN_USER` and `GUAC_ADMIN_PASS`.
3. Create required protocols (RDP/VNC/SSH) for each lab station.
4. Verify test login to each connection.

Reference: `configuring-lab-connections/guacamole-connections.md`.

## 3. Prepare Authentication/Wallet Layer

1. Open `https://<gateway-domain>/wallet-dashboard`.
2. Configure/import the institutional wallet when needed.
3. Validate auth endpoints:
   - `/.well-known/openid-configuration`
   - `/auth/jwks`
4. Confirm reservation-aware access is enabled in your policy.

## 4. Configure Ops Worker (Optional but Recommended)

1. Edit hosts file for lab station inventory.
2. Provide WinRM credentials through environment variables.
3. Set `MYSQL_DSN` and enable reservation automation if required.
4. Verify:
   - `GET /ops/health`
   - `POST /ops/api/wol`
   - `POST /ops/api/winrm`

## 5. Publish and Validate End-to-End Flow

1. Simulate or create a reservation.
2. Authenticate with wallet/SSO path.
3. Confirm access to Guacamole session.
4. Verify logs in OpenResty, blockchain-services, and ops-worker.

## 6. Operational Checklist

- Rotate admin and database credentials.
- Monitor cert expiration and renewals.
- Keep submodule and container versions updated.
- Run integration/smoke tests before production updates.
