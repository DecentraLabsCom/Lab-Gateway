---
description: >-
  Authentication and authorization service connecting your lab access control
  system to the blockchain
---

# Auth Service

<figure><img src=".gitbook/assets/image (1).png" alt=""><figcaption></figcaption></figure>

This microservice provides web3-based JWT tokens and offers a bridge between institutional access control systems (like the **Lab Gateway** in the figure above) with the blockchain-based smart contracts.

It can work just as an authentication service (checking the user actually is the owner of a certain wallet address), or as an authentication + authorization service (checking against the corresponding smart contract whether the owner of the wallet has certain permissions). In the latter case, the permissions are related to whether valid bookings on remote laboratories exist or not.

This microservice is built with Java Spring Boot and prepared to be deployed in a matter of seconds as a Maven (.war) package running on Apache Tomcat (at least v. 9) with Java (at least v. 17).

It provides the following endpoints when the war package is deployed into Tomcat as auth.war:

```
- /auth/.well-known/openid-configuration: To expose endpoints for OpenID Connect.
- /auth/jwks: Offers the public key in JWKS format (OpenID Connect).
- /auth/message: Generates a message for the client to sign with their wallet.
- /auth/auth: Provides authentication by checking the signature of the message above.
- /auth/auth2: Provides authentication + authorization by additionaly consulting the corresponding smart contract.
```

There is a running example of this microservice in sarlab.dia.uned.es/auth2, but users can use this code as an inspiration to implement their own auth service or just deploy it themselves as it is for their own purposes.

The following image shows the sequence diagram that illustrates the process for authenticating and authorizing a (wallet-logged in) user in the lab provider infrastructure through DecentraLabs.

```mermaid
sequenceDiagram
    autonumber
    participant U as User Browser
    participant D as Marketplace
    participant W as Wallet
    participant AS as Auth Service
    participant SC as Smart Contracts
    participant PG as Lab Gateway

    U->>D: Open lab page and connect wallet
    D->>W: Request wallet connection
    W-->>D: Return wallet address

    D->>AS: Ask for signable challenge for address
    AS-->>D: Send challenge with address and time data

    D->>W: Prompt user to sign challenge
    W-->>D: Return signature

    D->>AS: Submit address and signature
    AS->>AS: Verify signature against address
    AS->>SC: Query active reservation for address
    SC-->>AS: Return reservation data lab id access uri access key start end

    AS->>AS: Create JWT with iss iat jti aud sub nbf exp labId
    AS-->>D: Return JWT to dApp

    D->>U: Redirect user to provider access uri with jwt parameter
    U->>PG: Request guacamole path carrying jwt
    Note over PG: Gateway starts its own verification flow
```

The process for authenticating and authorizing an SSO-logged in user will be added and described here when this feature is fully implemented.
