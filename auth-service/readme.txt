This microservice provides web3-based JWT tokens.

It can serve just as an authentication service (checking the user is the owner of a wallet),
or as an authentication + authorization service (checking against the corresponding smart 
contract whether the owner of the wallet has certain permissions). In this case, the
permissions are related to whether valid bookings on remote laboratories exist or not.

This microservice is built with Spring Boot and prepared to be deployed in a matter of seconds
as a Maven (.war) package running on Apache Tomcat 9 with Java 17.

It provides the following endpoints when the war package is deployed into Tomcat as auth.war:

    - /auth/.well-known/openid-configuration: To expose endpoints for OpenID Connect
    - /auth/jwks: Offers the public key in JWKS format (OpenID Connect)
    - /auth/message: Generates a message for the client to sign with their wallet.
    - /auth/auth: Provides authentication by checking the signature of the message above.
    - /auth/auth2: Provides authentication + authorization by additionaly consulting the
    corresponding smart contract.

There is a running example of this microservice in sarlab.dia.uned.es/auth, but users can 
use this code as an inspiration to implement their own auth service or just deploy it
themselves as it is for their own purposes.