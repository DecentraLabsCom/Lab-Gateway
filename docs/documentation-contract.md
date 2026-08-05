# Documentation contract

This file defines which document owns each DecentraLabs concept. It prevents
the installation guides, audience guides and the embedded backend reference
from becoming competing protocol specifications.

## Authority order

When two descriptions disagree, use this order:

1. Deployed Smart-Contracts ABI, selector manifest and on-chain state.
2. Executable configuration and migrations in
   `Lab Gateway/blockchain-services` plus the OpenResty/Lab Gateway
   implementation.
3. The canonical workflow and service guides listed below.
4. Marketplace audience guides, tutorials and translations.

Audience documents explain the user journey. They must link to the canonical
workflow or API reference instead of redefining endpoint payloads, TTLs,
security boundaries or state transitions.

## Ownership matrix

| Subject | Canonical source | Audience/supporting sources |
| --- | --- | --- |
| Full/Lite topology, issuer and gateway trust | [Deployment architectures](deployment-architectures.md) | `Lab Gateway/README.md`, installation guides |
| Environment names and Compose profiles | [Configuration reference](reference/configuration.md), `.env.example` | English/Spanish installation guides |
| Reservation, intent and on-chain lifecycle | [Institutional reservation workflow](workflows/institutional-reservation-workflow.md) | Marketplace reservation and provider guides |
| Check-in, access-code redemption and session evidence | [Institutional check-in, access and sessions](workflows/institutional-check-in-access-sessions.md) | Guacamole policy, eduGAIN guide, Marketplace access guides |
| Backend roles and endpoint contracts | [`blockchain-services` API reference](../blockchain-services/docs/reference/API_REFERENCE.md) and [authentication guide](../blockchain-services/docs/services/authentication/AUTH.md) | Backend `README.md`, Marketplace integration notes |
| Gateway session policy | [Guacamole session policy](guacamole-session-policy.md) | Tutorials and operations guide |
| Smart-contract behavior | Deployed contract, ABI and [Smart-Contracts docs](../../Smart-Contracts/docs/README.md) | Marketplace catalogue/reservation guides |

## Current access-code invariant

The access-code protocol is two-phase. `POST /auth/access-code/redeem`
reserves a short-lived `redemptionHandle`; the gateway validates the returned
JWT and local destination/state; `/commit` consumes the code, while `/release`
or lease expiry leaves it redeemable. No document may describe the prepare call
alone as the irreversible consumption step.
The state sequence is `REDEMPTION_PREPARED` → `LOCAL_VALIDATED` → `CONSUMED`;
the redemption lease is 30 seconds and may end in `RELEASED` on failure.

The reservation and session workflows are separate: a confirmed reservation
does not itself create a session, and `SessionStarted` is durable economic
evidence rather than a synonym for accepting an access request.

External reservation timing is a separate invariant: the on-chain pending
request TTL is 5 minutes and the minimum creation lead is 10 minutes. The
canonical provider listener keeps its confirmation/canonicality gate and uses
short polling/retry intervals; a request that misses the deadline expires
without confirmation or credit capture. Do not document a late confirmation as
an availability fallback.

## Variants and translations

`Lab Gateway/blockchain-services` is the canonical backend and embedded
production target. The root `Blockchain-Services/` directory is a parallel
standalone variant with its own implementation and documentation; it is not a
second source for the embedded contract. Changes that intentionally target
that variant must say so explicitly and must not be copied into the canonical
flow by implication.

The Spanish installation and tutorial files are translations of the English
guides. Update the English source and its Spanish counterpart in the same
change, preserving protocol names, endpoint paths, environment names and
numeric values exactly.

## Change checklist

When changing a cross-project flow:

- update the owning canonical workflow/API document;
- update the relevant index (`Lab Gateway/docs/README.md` or
  `blockchain-services/SUMMARY.md`);
- update affected Marketplace audience text and translations;
- search both canonical repositories for the old endpoint, state or numeric
  value;
- run the narrow documentation checks plus the module tests appropriate to the
  change.
