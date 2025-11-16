
# DecentraLabs — Lab Gateway: Metadata, Quotes, and Reservation Confirmation
**Version:** 1.0 • **Date:** 2025‑09‑22  
**Author:** DecentraLabs (draft spec)

This document consolidates the three enhancements we agreed to implement in the **Lab Gateway** so that it becomes the operational source of truth while smart contracts provide the final cryptographic guarantees.

- **(1) Metadata from the Gateway** — Serve lab metadata (and optionally time slots) directly from the Lab Gateway, with integrity guarantees and resilient fallbacks.
- **(2) Real‑time Price Quotes (EIP‑712)** — The gateway computes price + time window and returns a signed quote that the user submits on‑chain, enabling dynamic pricing with anti‑front‑running.
- **(3) Reservation Confirmation by the Gateway** — The gateway makes the final approve/deny decision (based on real health/availability), using an EIP‑712 approval or directly sending the confirmation TX.

---

## 0) Scope & Principles

- **On‑chain is the source of guarantees** (confirmed reservations and paid price).  
- **Gateway is the source of reality** (actual readiness, live availability, pricing policy).  
- **Integrity & Replay‑safety** for any off‑chain payload: signatures (EIP‑712/191), nonces, and short expiries.  
- **Resilience:** IPFS/Gist fallbacks, caches, timeouts, and clear failure modes.  
- **Security by design:** key isolation (HSM/KMS/sidecar signer), rate‑limits, and minimal exposure.

---

## 1) Metadata from the Lab Gateway (with Integrity and Fallback)

### 1.1 Goals
- Freshness/coherence: the Gateway knows the real state of each lab.  
- Fewer dependencies per read: Marketplace fetches directly from provider’s Gateway.  
- Observability: access logs and abuse detection close to the source.

### 1.2 Endpoints
```
GET  /.well-known/decentralabs/<labId>/metadata.json
GET  /.well-known/decentralabs/<labId>/timeslots?from=<ISO8601|epoch>&to=<ISO8601|epoch>
```
**Headers (recommended):**
- `Content-Type: application/json`
- `ETag: "W/"<sha256>""`
- `Cache-Control: public, max-age=60, stale-while-revalidate=30`
- `Access-Control-Allow-Origin: https://<marketplace-domain>`
- Optional integrity header: `Content-Signature: ed25519=<base64_signature>`

**CORS:** allow only the Marketplace origin and only `GET`/`HEAD`.

### 1.3 Public JSON Structure (example)
```json
{
  "schema": "https://schemas.decentralabs.com/lab-metadata/v1",
  "version": "1.3.0",
  "labId": "0xABCDEF.../42",
  "name": "FPGA Intro Lab",
  "category": "electronics",
  "docsURI": "https://...",
  "images": ["https://.../img1.png"],
  "listedPrice": "0.05",
  "currency": "MATIC",
  "timeSlots": {
    "rangeStart": "2025-09-22T00:00:00Z",
    "rangeEnd": "2025-09-29T00:00:00Z",
    "slots": [
      {"start":"2025-09-23T10:00:00Z","end":"2025-09-23T11:00:00Z","status":"free"},
      {"start":"2025-09-23T11:00:00Z","end":"2025-09-23T12:00:00Z","status":"booked"}
    ],
    "slotsHash": "sha256:ab12…",
    "slotsSignature": {
      "algo": "ed25519",
      "signedAt": "2025-09-22T09:20:33Z",
      "nonce": "8f2c5b…",
      "sig": "base64…"
    }
  },
  "integrity": {
    "hash": "sha256:deadbeef…",
    "signature": {
      "algo": "ed25519",
      "keyId": "did:key:z6Mk…",
      "signedAt": "2025-09-22T09:20:33Z",
      "nonce": "f18c…",
      "sig": "base64…"
    }
  },
  "canonicalURI": "ipfs://bafy…",
  "fallbackURIs": ["ipfs://bafy…", "https://gist.github.com/user/..."],
  "updatedAt": "2025-09-22T09:20:30Z"
}
```

> **TokenURI strategy:**  
> - If `tokenURI = ipfs://CID`: integrity is intrinsic to the CID (hash). Sign only *dynamic* parts (e.g., `timeSlots`).  
> - If `tokenURI = https://…`: sign the JSON or anchor `metadataHash`/CID on‑chain; always sign dynamic endpoints.

### 1.4 Security & Hardening
- HTTPS + HSTS, automatic renewal (Let’s Encrypt).  
- Rate limiting (`limit_req` in OpenResty/nginx).  
- No secrets in public JSON (e.g., NEVER expose `accessKey`).  
- ETag and short caches to control load without losing freshness.  
- Multi‑URI (gateway primary + IPFS/Gist fallbacks).

---

## 2) Real‑Time Price Quotes (EIP‑712)

### 2.1 Purpose
- **Dynamic pricing without gas** for list updates.  
- **Anti front‑running:** bind the quote to `renter`.  
- **Immediate response:** Gateway decides price+availability in ~ms and signs a quote.

### 2.2 Data Types

**EIP‑712 Domain:**
```
EIP712Domain(
  name    = "DecentraLabs Reservations",
  version = "1",
  chainId,
  verifyingContract = <ReservationFacet>
)
```

**Typed struct — `PriceQuote`:**
```
PriceQuote(
  address provider,
  address renter,        // bind to user; or 0x0 for public (then contract enforces msg.sender)
  uint256 labId,
  uint64  start,
  uint64  end,
  address paymentToken,  // 0x0 for native
  uint256 price,         // wei/units
  uint64  expiry,        // short (+5–15 min)
  uint256 nonce          // unique per provider
)
```

### 2.3 Gateway Endpoint
```
POST /.well-known/decentralabs/quote
Body: { labId, start, end, paymentToken, renter }
Resp: { quote: PriceQuote, signature: 0x<r||s||v> }
```

### 2.4 Gateway Algorithm (fast path)
1. **Validate** input (ranges, allowed token, address format).  
2. **Availability (fast)**: local cache of confirmed on‑chain reservations + near‑term slot plan.  
3. **Optimistic Lock**: per `{labId,start,end}` with TTL 15–30 s (Redis/KV) to avoid double quotes.  
4. **Price**: deterministically from policy (base ± peak/discounts/institution).  
5. **Nonce**: monotonic per `provider` (KV).  
6. **Expiry**: now + 10 min (configurable).  
7. **Sign** the EIP‑712 struct with the provider’s signer (HSM/KMS/sidecar).  
8. **Respond** `{quote, signature}` (latency target: <100 ms).

> If you prefer maximum throughput, you may release the lock right after issuing the quote; the effective guard is on‑chain (no overlap + nonce usage).

### 2.5 Contract Responsibilities
- Rebuild EIP‑712 digest and `ecrecover` to `provider`.  
- Validate `expiry` and `nonce` (consume it).  
- Enforce **no overlap** with confirmed reservations.  
- Collect funds (native/`transferFrom`) and **persist** the reservation with the **effective price**.  
- Emit `ReservationCreated(...)` with `price` and time window.

### 2.6 Frontend (ethers v6 — gist)
```ts
const domain = { name: "DecentraLabs Reservations", version: "1", chainId, verifyingContract };
const types  = { PriceQuote: [ /* fields as defined */ ] };
const { quote, signature } = await fetch("/.well-known/decentralabs/quote", { method:"POST", body: JSON.stringify(req) }).then(r=>r.json());
await contract.createReservation(quote, signature, { value: quote.paymentToken === ZeroAddress ? quote.price : 0n });
```

---

## 3) Reservation Confirmation by the Lab Gateway

The gateway is best positioned to **approve/deny** a reservation based on **real machine state** (health, readiness, occupancy), not only metadata.

### 3.1 Option A — Two‑Step with EIP‑712 Approval (recommended to start)
Flow:
1. **User** → contract: `requestReservation(...)` ⇒ state `pending`.  
2. **Gateway** listens `ReservationRequested`, checks **health/availability/policy**, then signs an **Approval**.  
3. **Relayer/Marketplace** → contract: `confirmReservationRequest(approval, sig)`.

**Typed struct — `Approval`:**
```
Approval(
  address provider,
  uint256 reservationId,
  uint64  approvedAt,
  uint64  expiry,
  uint256 nonce
)
```

**Contract checks:** signature → `provider`, `expiry`, `nonce` unused, lab/provider match, then confirm + emit event.

### 3.2 Option B — One‑Step (Quote + Approve) for Instant UX
- Gateway returns **two signatures**:
  - `PriceQuote` (see §2).  
  - `ApproveForQuote( provider, quoteHash, expiry, nonce )`.
- Frontend calls `createAndConfirm(quote, sigQuote, approve, sigApprove)`; contract validates both, then confirms directly.

### 3.3 Option C — Gateway Sends the TX
- Gateway signs **and submits** `confirmReservationRequest` using a provider role key with gas.  
- Simplest operationally; ensure HSM/KMS, IP allowlists, and throttling.

### 3.4 Gateway Checks before Approval
- **Real availability:** no overlapping sessions, no zombie processes.  
- **Health:** Guacamole/Tomcat up, latency thresholds, CPU/GPU/memory ok, required services running.  
- **Policy:** maintenance windows, KYC/affiliation caps, institutional priority.  
- **Coherence:** matches the quote (labId, time, token, price).  
- **Race control:** short TTL lock on the slot while producing the approval.

---

## 4) Security, Operations & Observability

### 4.1 Keys & Signing
- Prefer **HSM/KMS** or a **sidecar signer** process that holds the provider private key in RAM.  
- Restrict signer API (localhost, mTLS), strict rate limits, and audit logging.  
- Version **EIP‑712 domains** (`name`, `version`) and rotate if needed.

### 4.2 Concurrency & Caching
- Redis or embedded KV (SQLite WAL / Badger / LMDB) for:  
  - `lock:slot:<labId>:<start>:<end>` (PX 30_000)  
  - `nonce:provider:<address>` counters  
  - recent `ReservationCreated` to warm availability cache

### 4.3 Time & Expiries
- NTP sync on gateway hosts; treat `expiry` in epoch seconds.  
- Expiries short: Quotes 5–15 min; Approvals 3–10 min.

### 4.4 Rate Limits & Abuse
- Per‑IP and per‑lab request ceilings, bursts; block clearly abusive patterns.  
- Return `409 locked` when a slot lock exists; `429` on rate excess.

### 4.5 Observability
- Metrics: P50/P95 latency of `/quote`, approval rate, 409 lock rate, quote→reservation conversion, errors by cause.  
- Logs: reasoned deny (health/overlap/policy), reservation digests, nonces.  
- Alerts: gateway down, signer failures, unusual rejection spikes.

### 4.6 Fallbacks
- If the gateway is down, providers may **opt‑in** to allow **marketplace auto‑confirm** using metadata policy (as a **temporary** fallback).  
- Always prefer to fail **closed** if policy demands real‑time health verification.

---

## 5) Migration Plan (Minimal Disruption)

1. **Phase 1 — Metadata**  
   - Add the endpoints, signatures/hashes, caching headers, and fallbacks.  
   - Marketplace verifies integrity and starts preferring gateway URIs.

2. **Phase 2 — Quotes**  
   - Implement `/quote` and the on‑chain verification path.  
   - Keep on‑chain listedPrice (optional) for transparency; effective price lives in the reservation.

3. **Phase 3 — Confirmation**  
   - Start with **Option A** (EIP‑712 Approval).  
   - Once stable, consider **Option B** for instant UX.

4. **Phase 4 — Hardening & Observability**  
   - Add dashboards, alerts, KMS integration, and DR runbooks.

---

## 6) Solidity Sketches

> Use OpenZeppelin `EIP712` + `ECDSA` to reduce boilerplate and avoid subtle hashing mistakes.

### 6.1 Quote Verification (createReservation)
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract ReservationFacet is EIP712 {
    bytes32 private constant PRICEQUOTE_TYPEHASH =
        keccak256("PriceQuote(address provider,address renter,uint256 labId,uint64 start,uint64 end,address paymentToken,uint256 price,uint64 expiry,uint256 nonce)");

    struct PriceQuote {
        address provider;
        address renter;
        uint256 labId;
        uint64  start;
        uint64  end;
        address paymentToken;
        uint256 price;
        uint64  expiry;
        uint256 nonce;
    }

    mapping(address => mapping(uint256 => bool)) public usedNonce;

    constructor() EIP712("DecentraLabs Reservations", "1") {}

    function _hashQuote(PriceQuote memory q) internal view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(
            PRICEQUOTE_TYPEHASH,
            q.provider, q.renter, q.labId, q.start, q.end,
            q.paymentToken, q.price, q.expiry, q.nonce
        )));
    }

    function createReservation(PriceQuote calldata q, bytes calldata sig) external payable {
        address renter = q.renter == address(0) ? msg.sender : q.renter;
        require(renter == msg.sender, "not renter");
        require(block.timestamp <= q.expiry, "expired");
        require(!usedNonce[q.provider][q.nonce], "nonce used");

        address signer = ECDSA.recover(_hashQuote(q), sig);
        require(_isProviderOf(q.labId, signer), "bad signer");

        _assertTimeslotFree(q.labId, q.start, q.end);

        if (q.paymentToken == address(0)) {
            require(msg.value == q.price, "bad value");
        } else {
            require(msg.value == 0, "native not expected");
            require(IERC20(q.paymentToken).transferFrom(renter, _treasury(), q.price), "erc20 xfer fail");
        }

        usedNonce[q.provider][q.nonce] = true;
        _storeReservation(q.labId, renter, signer, q.start, q.end, q.paymentToken, q.price);
        emit ReservationCreated(q.labId, renter, signer, q.start, q.end, q.paymentToken, q.price);
    }

    // --- hooks (implement) ---
    function _isProviderOf(uint256 labId, address signer) internal view returns (bool) {}
    function _assertTimeslotFree(uint256 labId, uint64 start, uint64 end) internal view {}
    function _storeReservation(uint256 labId, address renter, address provider, uint64 start, uint64 end, address paymentToken, uint256 price) internal {}
    function _treasury() internal view returns (address payable) { return payable(address(this)); }

    event ReservationCreated(uint256 indexed labId, address indexed renter, address indexed provider,
        uint64 start, uint64 end, address paymentToken, uint256 price);
}
```

### 6.2 Approval Verification (confirmReservationRequest)
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

contract ReservationApprovalFacet is EIP712 {
    bytes32 private constant APPROVAL_TYPEHASH =
        keccak256("Approval(address provider,uint256 reservationId,uint64 approvedAt,uint64 expiry,uint256 nonce)");

    struct Approval {
        address provider;
        uint256 reservationId;
        uint64  approvedAt;
        uint64  expiry;
        uint256 nonce;
    }

    mapping(address => mapping(uint256 => bool)) public usedApprovalNonce;

    constructor() EIP712("DecentraLabs Reservations", "1") {}

    function _hashApproval(Approval memory a) internal view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(
            APPROVAL_TYPEHASH, a.provider, a.reservationId, a.approvedAt, a.expiry, a.nonce
        )));
    }

    function confirmReservationRequest(Approval calldata a, bytes calldata sig) external {
        require(block.timestamp <= a.expiry, "approval expired");
        require(!usedApprovalNonce[a.provider][a.nonce], "nonce used");

        address signer = ECDSA.recover(_hashApproval(a), sig);
        require(_isProviderOfReservation(a.reservationId, signer), "not provider");

        usedApprovalNonce[a.provider][a.nonce] = true;
        _confirmReservation(a.reservationId);
        emit ReservationConfirmed(a.reservationId, signer);
    }

    // --- hooks (implement) ---
    function _isProviderOfReservation(uint256 reservationId, address signer) internal view returns (bool) {}
    function _confirmReservation(uint256 reservationId) internal {}

    event ReservationConfirmed(uint256 indexed reservationId, address provider);
}
```

---

## 7) API Contracts (Gateway)

### 7.1 `GET /.well-known/decentralabs/<labId>/metadata.json`
- **200** `{ ...metadata schema... }` + integrity headers/signatures.  
- **404** if lab unknown.  
- **503** if gateway degrades (fallback to IPFS/Gist).

### 7.2 `GET /.well-known/decentralabs/<labId>/timeslots?from=&to=`
- **200** `{ timeSlots: { rangeStart, rangeEnd, slots[], slotsHash, slotsSignature } }`.  
- **400** invalid ranges.  
- **409** if calculation is locked (try again).

### 7.3 `POST /.well-known/decentralabs/quote`
- **Req:** `{ labId, start, end, paymentToken, renter }`  
- **200:** `{ quote, signature }`  
- **409:** `slot_pending_or_locked` or `slot_unavailable`  
- **429:** rate‑limited

### 7.4 (Option A) `POST /.well-known/decentralabs/approve`
- **Req:** `{ reservationId }` (gateway fetches details from cache/chain)  
- **200:** `{ approval, signature }`  
- **409/423:** health/unavailable windows / maintenance  
- **429:** rate‑limited

---

## 8) Redis/KV Key Scheme (suggested)

- Slot locks: `lock:slot:<labId>:<start>:<end>  -> <reqId>` (PX 30000)  
- Nonces: `nonce:provider:<address> -> int64`  
- Cache of reservations: `resv:<labId>:<start>:<end> -> reservationId`  
- Health signals: `health:<labId> -> {ready:bool, latency_ms:int, updatedAt:ts}`

---

## 9) Error Handling & UX

- Show *pending* only if using Option A (two‑step). Timeout after N seconds with “We’re waiting for lab confirmation… retry / pick another slot”.  
- If quote expires before the user signs the on‑chain TX, ask for a new quote.  
- Provide explicit errors for overlap/locks and suggest nearby slots.

---

## 10) Security Checklist

- [ ] All gateway endpoints behind HTTPS + HSTS  
- [ ] CORS restricted to Marketplace domain(s)  
- [ ] Rate‑limits per IP and per lab  
- [ ] Signer isolated (KMS/HSM/sidecar), no PK on disk  
- [ ] Short expiries + nonces (quotes, approvals)  
- [ ] Integrity verification (IPFS/CID for static; signatures for dynamic)  
- [ ] NTP sync on all hosts  
- [ ] Audit logs with reasoned deny/approve

---

## 11) Change Log
- v1.0 — First complete draft of Lab Gateway spec for metadata, quotes, and confirmation flows.

---

**End of document.**
