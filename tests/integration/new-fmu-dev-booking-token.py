import argparse
import hashlib
import time
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a dev FMU booking JWT signed with the local Lab Gateway keypair."
    )
    parser.add_argument("--private-key", default=r"c:\Repos\Lab Gateway\certs\private_key.pem")
    parser.add_argument("--audience", default="https://localhost:8443")
    parser.add_argument("--issuer", default="https://localhost:8443/auth")
    parser.add_argument("--subject", default="dev-user")
    parser.add_argument("--lab-id", default="lab-1")
    parser.add_argument("--reservation-key", default="reservation-1")
    parser.add_argument("--access-key", default="BouncingBall.fmu")
    parser.add_argument("--expires-in-seconds", type=int, default=900)
    parser.add_argument("--nbf-skew-seconds", type=int, default=60)
    return parser.parse_args()


def load_private_key(path: Path):
    payload = path.read_bytes()
    return serialization.load_pem_private_key(payload, password=None)


def compute_kid(private_key) -> str:
    numbers = private_key.public_key().public_numbers()
    modulus_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    if modulus_bytes and (modulus_bytes[0] & 0x80):
        modulus_bytes = b"\x00" + modulus_bytes
    return hashlib.sha256(modulus_bytes).hexdigest()


def main() -> int:
    args = parse_args()
    key_path = Path(args.private_key)
    if not key_path.is_file():
        raise SystemExit(f"Private key not found: {key_path}")

    private_key = load_private_key(key_path)
    kid = compute_kid(private_key)
    now = int(time.time())

    claims = {
        "iss": args.issuer,
        "aud": args.audience,
        "sub": args.subject,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "nbf": now - max(0, args.nbf_skew_seconds),
        "exp": now + max(1, args.expires_in_seconds),
        "resourceType": "fmu",
        "labId": args.lab_id,
        "reservationKey": args.reservation_key,
        "accessKey": args.access_key,
    }

    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"typ": "JWT", "kid": kid},
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
