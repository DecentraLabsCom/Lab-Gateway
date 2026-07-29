# Institutional Reservation Workflow

This document describes the current institutional reservation process from a user's SSO session through an on-chain reservation. It is intentionally limited to reservation creation, authorization, confirmation, cancellation, and the handoff to access. Check-in and session delivery are covered in [Institutional Check-in, Lab Access, and Session Workflow](institutional-check-in-access-sessions.md).

## Participants and sources of truth

| Participant | Responsibility |
| --- | --- |
| User | Starts the reservation and completes the institutional WebAuthn ceremony. |
| Marketplace | Validates the user session, prepares and signs an EIP-712 intent, registers it on chain, and orchestrates the authorization ceremony. |
| Consumer backend | Validates the SAML and WebAuthn evidence, persists the accepted intent, and executes the institutional transaction. |
| Provider backend | Observes pending reservation requests and accepts or denies them according to its configured reservation automation. |
| Smart contracts | Enforce intent consumption, reservation payload, price, state, and treasury rules. |

The chain is authoritative for the reservation lifecycle. Marketplace and Lab Gateway consume events and maintain operational projections for UI, notification, and laboratory preparation; these projections must not be used as a substitute for the on-chain state.

An intent registration is a separate, short-lived authorization record. If the
WebAuthn ceremony is cancelled or fails before backend authorization, the
Marketplace cancels the still-pending registration through its registered
signer. The lifecycle record is bound to the authorization session and is also
reconciled against the intent expiry; it must not be confused with a
reservation cancellation.

## Reservation states

| State | Meaning |
| --- | --- |
| `PENDING` | A request exists and awaits confirmation, denial, cancellation, or request expiry. |
| `CONFIRMED` | The reservation is active and the institutional treasury spend has succeeded. |
| `ACCESS_AUTHORIZED` | The payer institution has subsequently authorized access through check-in. |
| `SETTLED` | The reservation has reached terminal settlement/cleanup processing. |
| `CANCELLED` | The request or booking was cancelled or denied. |

`CONFIRMED` permits the later access check-in flow. It does not itself issue an access credential.

```mermaid
stateDiagram-v2
    [*] --> PENDING: external-lab request
    PENDING --> CONFIRMED: confirmation and treasury spend
    PENDING --> CANCELLED: denial, cancellation or expiry
    [*] --> CONFIRMED: direct booking
    CONFIRMED --> ACCESS_AUTHORIZED: payer check-in
    CONFIRMED --> CANCELLED: valid pre-start cancellation
    ACCESS_AUTHORIZED --> SETTLED
    CONFIRMED --> SETTLED
    SETTLED --> [*]
    CANCELLED --> [*]
```

## Inputs bound into a reservation intent

Marketplace requires an authenticated SSO session and a PUC. It validates a future start time, positive duration, laboratory identity, laboratory price, and the user's institutional affiliation. It computes:

- `pucHash`: hash of the normalized PUC;
- `assertionHash`: hash of the SAML assertion;
- `reservationKey`: `keccak256(abi.encodePacked(labId, start, pucHash))`;
- `price`: `pricePerSecond * (end - start)`;
- a request identifier, expiry, sequential intent nonce, executor, signer, action, and payload hash.

The resulting EIP-712 intent binds the reservation payload to the Marketplace administrative signer and to the institutional executor. The contract recomputes the reservation key and price and consumes the intent only when action, executor, payload hash, nonce, and expiry all match.

`pricePerSecond` and the resulting `price` are raw service-credit units. The
canonical scale is 7 decimals (`10,000,000` raw units per credit). Human
credit amounts must be converted at the UI/API boundary; neither the gateway
nor the backend should apply a legacy 5-decimal divisor.

## Preparation and WebAuthn authorization

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Marketplace
    participant Chain as Smart contracts
    participant Consumer as Consumer backend

    User->>Marketplace: Select lab and time window
    Marketplace->>Marketplace: Validate SSO, PUC, time, lab and price
    Marketplace->>Marketplace: Build and sign EIP-712 reservation intent
    par Intent registration
        Marketplace->>Chain: Submit intent registration
    and Authorization setup
        Marketplace->>Consumer: POST /intents/authorize with SAML-bound payload
    end
    Consumer-->>User: WebAuthn ceremony URL and session ID
    User->>Consumer: Complete WebAuthn assertion
    Consumer->>Consumer: Validate SAML, PUC, WebAuthn and intent signature
    Consumer->>Chain: Execute the accepted intent
    Chain-->>Consumer: Reservation event and transaction result
```

Marketplace currently submits on-chain intent registration and requests the WebAuthn authorization session concurrently. The initial response reports registration as `submitted`; after mining, Marketplace signals the consumer backend that registration is available. This lets the user complete WebAuthn without waiting for a block while preserving the contract's final intent-consumption gate.

If the authorization window closes, the Marketplace sends a session-bound
cleanup request. The server verifies the session/request/institution binding,
serializes signer access, and calls `cancelIntent` while the intent is still
`Pending`. Expired records are reconciled with `expireIntent`; an already
executed or cancelled intent is removed from the lifecycle store without a
second transaction.

The consumer backend accepts an intent only after validating its shape, SAML assertion and assertion-hash binding, replay rules, WebAuthn assertion, expiry, EIP-712 signature, and trusted-signer policy. Accepted intents are persisted and move through `QUEUED`, `AUTHORIZED_PENDING_REGISTRATION`, `IN_PROGRESS`, `EXECUTED`, `FAILED`, or `REJECTED` as applicable.

## Booking branches

### Direct booking: institution owns the laboratory

If the payer institution is also the current owner of the lab, Marketplace selects `DIRECT_BOOKING`. The institution wallet or its registered backend may execute the intent; the contract resolves the owner as the payer/provider identity. `institutionalDirectBookingWithIntent` consumes the intent, creates the institutional reservation, and confirms it in one transaction. There is no externally visible pending-confirmation interval.

### Reservation request: external provider laboratory

For an external lab, Marketplace selects `REQUEST_BOOKING`. The institution wallet or its registered backend executes the intent; the contract resolves the payer from the registered `schacHomeOrganization`, rather than treating the backend as a separate institution. `institutionalReservationRequestWithIntent` consumes the intent and creates a `PENDING` reservation. The request contains the payer institution, PUC hash, lab, start/end window, and computed reservation key.

Confirmation verifies that the reservation is pending, the institution and PUC hash match the reservation, the provider/lab is eligible, the request period remains valid, and the payer's institutional treasury can spend the computed price. On success it captures the spend, reserves the physical-lab calendar interval where applicable, sets `CONFIRMED`, and emits `ReservationConfirmed`.

The confirmation contract accepts external requests only from the current
provider/lab owner or its registered backend, provided the supplied institution
and PUC match the reservation. The payer's treasury is charged by this
provider-authorized confirmation. The same provider-side authority is required
to deny a pending request. The payer remains authorized to create and cancel
its request/booking according to policy, but cannot confirm or deny an external
request. `DIRECT_BOOKING` is the separate payer-authorized path for a lab the
institution currently owns.

## Cancellation and expiry

The `REQUEST_BOOKING` branch has two independent operational actors: the payer
institution requests the booking, while the provider/lab owner (or its
registered backend) may confirm or deny the pending request under the contract
rules. A confirmed institutional booking may be cancelled before its start
time by the authorized payer institution/backend with the matching PUC hash;
the provider backend is not assumed to be available for that cancellation
path. The contract applies the cancellation fee and institutional refund rules.

Before a cancellation is submitted, the Marketplace preview exposes the
on-chain status, cancellation cutoff, total fee, minimum-fee flag, provider
fee, spending period, source credit lots and destination account. The preview
is informational; the contract and institutional backend validate the final
amount again. Legacy reservations without recorded source lots are labelled as
legacy rather than being presented as a fully traceable lot allocation.

For physical laboratories, an eligible payer cancellation before the start
retains 10% of the reservation price: 6% is provider receivable and 4% is the
implicit Marketplace margin. Simulation reservations refund 100% on this path.
If a physical reservation reaches its end without `SessionStarted`, the
post-attestation no-show settlement retains 25%: 15% goes to the provider and
10% remains the implicit Marketplace margin; the payer receives the remaining
75%. A simulation still receives a full refund. Provider-initiated
cancellation is always a full refund, but it affects lab reputation: -1 with
at least 24 hours' notice, -2 with less than 24 hours' notice, and -3 for an
explicit service failure after the provider did not deliver the confirmed
service. The service-failure path requires no `SessionStarted` evidence and
remains available only through the attestation grace period, so a payer no-show
is not automatically blamed on the provider. Technical denial of a pending
request remains unpenalized.

The chain may also cancel or settle reservations during expiry/release processing. UI labels such as "active" or "completed" are operational views and must not be treated as aliases for the on-chain states above.

## Listing, deletion and settlement boundaries

Listing is performed through the current `listLab`/`unlistLab` contract
surface. The Marketplace and Gateway perform a metadata health preflight before
listing; the atomic `addAndList` path applies the same gate before submitting
the transaction. Legacy `listToken`/`unlistToken` selectors are not part of
the effective Diamond allowlist.

Deleting a lab does not cancel reservations or erase settlement history. The
contract guards deletion while active reservations or receivables remain, and
the provider UI reports that existing reservations are not cancelled
automatically. Settlement claims require a non-zero unique claim ID,
reservations reference and invoice reference; the backend persists and
deduplicates the corresponding invoice/payment references.

## Operational behavior

Contract event listeners can persist reservation events and notify users. Before
loading laboratory metadata, provider-side reservation automation resolves the
local wallet's on-chain role: only the current lab owner/backend may confirm or
deny an external request, and only when provider features are enabled. Payer
and unrelated listeners remain informational and do not submit confirmation or
denial transactions. Executing the payer's request intent does not trigger a
confirmation postflight; the provider must process the resulting event.

The reservation key is derived from `(labId, start, pucHash)`. This keeps exclusive
physical-lab scheduling keyed by its calendar interval while allowing distinct FMU
users to reserve the same start instant. FMU capacity remains provider-side policy:
the provider counts active overlapping reservations and evaluates
`maxConcurrentUsers` from the lab metadata together with the calendar, hours and
maintenance rules before confirming the request.

Intent nonces are sequential per signer on chain. Any horizontally scaled component that prepares or registers intents must serialize nonce assignment per signer; a transaction carrying a nonce other than the next expected value is rejected by the contract.

## Handoff to access

After a reservation reaches `CONFIRMED` and its time window is valid, the user can start the separate check-in process. The consumer institution submits `AccessAuthorized`; only after the provider observes `ACCESS_AUTHORIZED` does it activate laboratory access. See [Institutional Check-in, Lab Access, and Session Workflow](institutional-check-in-access-sessions.md).

## Related implementation surfaces

- Reservation preparation: `Marketplace/src/app/api/backend/intents/reservations/prepare/route.js`
- Intent construction: `Marketplace/src/utils/intents/signInstitutionalReservationIntent.js`
- Intent API: `blockchain-services/.../controller/intent/IntentController.java`
- Intent execution: `blockchain-services/.../service/intent/IntentOnChainExecutor.java`
- Contract entry points: `Smart-Contracts/contracts/facets/reservation/ReservationIntentFacet.sol`
- Confirmation rules: `Smart-Contracts/contracts/libraries/LibInstitutionalReservationConfirmation.sol`
