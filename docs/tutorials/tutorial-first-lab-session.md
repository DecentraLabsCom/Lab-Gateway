# Tutorial: From Zero to First Authenticated Lab Session

This tutorial walks a new institution administrator through the complete end-to-end flow:
deploying the gateway, connecting a physical lab computer, and watching a user reach an
authenticated remote-desktop session.

**Estimated time:** 60–90 minutes for a first deployment on a fresh server.

**Prerequisites:** you have completed one of the installation guides and all containers are
running (`docker compose ps` shows every service as `Up`).

---

## Overview

```
Institution server                  Lab computer (Windows)
┌──────────────────┐                ┌─────────────────────┐
│  Lab Gateway     │  internal RDP  │  Lab Station + app  │
│  ├ OpenResty     │◄──────────────►│  (physical or VM)   │
│  ├ Guacamole     │                └─────────────────────┘
│  └ blockchain-   │
│    services      │
└────────┬─────────┘
         │ HTTPS
         ▼
    User browser
    (Marketplace)
```

The gateway receives the user, validates their blockchain reservation, issues a session
token, and opens an authenticated Guacamole window pointing at your lab computer.

---

## Part 1 — Register the institution as a lab provider

Provider registration follows a two-system handshake: the **Marketplace** generates a
signed provisioning token, and the **Lab Gateway** applies it to complete both local
configuration and on-chain registration in a single step.

> **Precondition:** this tutorial assumes you deployed Lab Gateway in **provider+consumer mode**
> by following one of the [installation guides](../install/). If you installed in consumer-only
> mode, provider registration and lab publishing are not available.

### 1.1 Log into the Marketplace with institutional SSO credentials

Open `https://marketplace-decentralabs.vercel.app` and sign in using your institution's
**eduGAIN / SSO credentials** (university username and password). You must have the
**institution admin** role. If you do not yet have that role, contact the Marketplace
platform administrator.

### 1.2 Generate a provisioning token in the Marketplace

1. Go to your **user dashboard** and find the **Institutional Provisioning Token** card.
2. Select token type **Provider**.
3. Enter the **public base URL of your Lab Gateway** (e.g. `https://lab.your-institution.edu`).
   This is the URL the Marketplace will use to reach your gateway's auth endpoints.
4. Click **Generate Provisioning Token**.
5. **Copy the token** — it is short-lived (typically 15–30 minutes) and single-use.

The token is a signed JWT issued by the Marketplace that encodes your institution name,
email, country, organisation domain, and gateway URL. It also authorises the Marketplace
to complete the on-chain provider registration on your behalf.

### 1.3 Apply the token in the wallet dashboard

1. Open `https://lab.your-institution.edu/wallet-dashboard`.
2. Enter your `ADMIN_ACCESS_TOKEN` when prompted.
3. Find the **Apply Provisioning Token** section and paste the token you copied.
4. Click **Apply**.

What happens next (automatically):

- `blockchain-services` validates the token signature against the Marketplace JWKS.
- Configuration fields (institution name, email, country, organisation, gateway URL) are
  saved and locked to the values encoded in the token.
- `blockchain-services` calls back to the Marketplace to trigger on-chain registration:
  wallet address receives `PROVIDER_ROLE` and `INSTITUTION_ROLE`, and the gateway's
  auth endpoint is recorded in the smart contract.
- The dashboard shows **Provider Token Applied** once the blockchain transaction confirms.

> If the dashboard shows **Provider Token Saved** (not Applied), the on-chain step did
> not complete yet. Use the **Retry registration** button after verifying your
> institutional wallet has been created (Step 5 / Section "Institutional Wallet Setup"
> in the installation guide).

---

## Part 2 — Connect the lab computer

### 2.1 Check network reachability

The gateway must be able to reach the lab computer on port 3389 (RDP). Test from the
gateway host:

```bash
# Replace 192.168.1.100 with your lab computer's IP
nc -zv 192.168.1.100 3389
```

If using a separate network interface or VLAN, verify the routing is in place.

### 2.2 Prepare the lab computer (Windows)

1. Enable Remote Desktop: **Settings → System → Remote Desktop → Enable**.
2. Create a dedicated Windows user account for lab sessions (avoid using administrator
   accounts for day-to-day lab access).
3. Note the exact path of the Lab Station `AppControl.exe` and the window class name
   of the lab application. See the [Lab Station README](../../Lab%20Station/README.md)
   for instructions on how to find the window class.

### 2.3 Add a Guacamole connection

1. Open `https://lab.your-institution.edu/guacamole`.
2. Log in with the Guacamole admin credentials set during installation.
3. Go to **Settings → Connections → New Connection**.
4. Fill in:
   - **Name:** any descriptive name (e.g., `Electronics Lab 1`)
   - **Protocol:** RDP
   - **Hostname:** lab computer's IP address
   - **Port:** 3389
   - **Username:** Windows account username
   - **Password:** Windows account password
   - **Security mode:** Any
   - **Ignore server certificate:** checked
5. Under **Remote App:**
   - **Program:** `AppControl.exe` (or the full path if needed)
   - **Working directory:** path to the Lab Station folder on the Windows machine
   - **Parameters:** window class and lab application path — see Lab Station docs for details
6. Click **Save**.

### 2.4 Test the connection manually

Still in Guacamole admin view, click the connection name to open a direct session and
confirm the desktop appears and the lab application launches.

---

## Part 3 — Publish the lab on the Marketplace

Lab publishing can be done from either the **Marketplace** or the local **Lab Manager**.
Use Marketplace publishing when the provider has eduGAIN/SSO access. Use Lab Manager
publishing when the provider was onboarded with a Marketplace invitation token but does
not have an eduGAIN IdP.

### 3.0 Publish from Lab Manager

1. Open `https://lab.your-institution.edu/lab-manager`.
2. Enter your `LAB_MANAGER_TOKEN` when prompted.
3. In **Labs**, select an existing Guacamole connection or FMU discovered from the
   Gateway inventory.
4. Choose **Full Setup** to generate metadata and upload images/documents locally, or
   **Quick Setup** to reference an externally hosted metadata JSON.
5. Click **Publish Lab**. The Gateway stores generated metadata/assets under its
   persistent lab-content volume, exposes them at `/lab-content/...`, and signs the
   on-chain transaction with the institutional provider wallet.

### 3.1 Open the provider dashboard

1. Log into `https://marketplace-decentralabs.vercel.app` with your institutional SSO credentials.
2. Navigate to **Lab Panel** in the navbar. The lab management section is only visible to
   registered providers.
3. Click **Add New Lab**. A modal opens with two setup modes.

### 3.2 Choose a setup mode

#### Option A — Full Setup (recommended)

Fill in all lab details directly in the Marketplace form. No external files needed.

- **Basic Information:** lab name, description, keywords, category.
- **Pricing and availability:** hourly rate in service credits, available time slots,
  opening and closing dates.
- **Access information:** gateway access URI (your Lab Gateway URL) and access key.
- **Media:** upload images and documentation (up to 5 MB per file).

When you submit, the Marketplace sends a blockchain transaction that mints the lab
on-chain and automatically stores the metadata. The lab is immediately bookable once
the transaction confirms.

#### Option B — Quick Setup (advanced)

Use this mode if you already maintain a JSON metadata file hosted externally
(IPFS, Arweave, GitHub Gist, your own server, etc.) and want to reference it
directly rather than re-entering data in the form.

1. Host your JSON metadata file at a publicly accessible HTTPS URL.
2. In the **Quick Setup** tab, fill in the minimal on-chain fields (hourly rate,
   access URI, access key).
3. Paste the public URL to your JSON file in the **Metadata URL** field.
4. Submit — only the URL and on-chain fields are written to the contract.

> The JSON file is **optional in Full Setup** — the Marketplace generates and manages
> metadata storage automatically. It is only required in Quick Setup.

### 3.3 Confirm the lab appears in the Marketplace

After the transaction confirms, your lab should be listed when any user searches for
your institution on `https://marketplace-decentralabs.vercel.app` and available for booking.

---

## Part 4 — End-to-end user flow

### 4.1 User makes a reservation

A user visits the Marketplace, finds your lab, and books a time slot. The smart contract
records the reservation and assigns a `reservationKey`.

### 4.2 User authenticates at the gateway

At their booked start time, the user follows the **Access lab** link. This initiates the
authentication flow:

1. The Marketplace sends the user's wallet signature and reservation key to the gateway.
2. `blockchain-services` validates the signature against the on-chain reservation.
3. If valid, a signed JWT is issued and a Guacamole session cookie is set.
4. The browser is redirected to the Guacamole viewer, already authenticated.

### 4.3 User reaches the lab desktop

The Guacamole window opens and shows the Windows desktop of the lab computer with the
Lab Station application running. The user interacts with the remote lab in real time.

---

## Part 5 — Health and monitoring

### Check all services are running

```bash
docker compose ps
```

### Check gateway health

```bash
curl -k https://lab.your-institution.edu/health
```

### Check OIDC / JWKS metadata (Full mode only)

```bash
curl -k https://lab.your-institution.edu/auth/.well-known/openid-configuration
curl -k https://lab.your-institution.edu/auth/jwks
```

### Tail logs for a service

```bash
docker compose logs -f blockchain-services
docker compose logs -f openresty
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| User lands on Guacamole login screen instead of session | JWT not accepted by Guacamole | Check `ISSUER` in `.env` matches the blockchain-services issuer shown at `/auth/.well-known/openid-configuration`. |
| Reservation validation fails with 401 | Contract address mismatch | Verify `CONTRACT_ADDRESS` in `blockchain-services/.env` matches the deployed contract. |
| Guacamole shows "connection failed" | Lab computer unreachable | Check network path and Windows firewall on the lab computer. |
| RDP session opens but Lab Station app does not start | Wrong Remote App parameters | Double-check the window class and path in the Guacamole connection settings. |
| Wallet dashboard returns CORS error | Missing origin in allowlist | Add the gateway URL to `CORS_ALLOWED_ORIGINS` in `.env` and `ALLOWED_ORIGINS` in `blockchain-services/.env`. |

---

## Next steps

- [eduGAIN federation guide](../edugain/edugain-federation.md) — let institutional users log in with their university credentials
- [Installation guides](../install/) — other deployment modes
