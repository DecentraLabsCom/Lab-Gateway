#!/usr/bin/env python3
"""Deterministic Full control-plane fixture for the Full/Lite edge gate.

The fixture deliberately keeps the contract boundary explicit: access-code
delivery is rejected until the configured reservation status is
ACCESS_AUTHORIZED (2). JWTs are signed with a generated RSA key, so Lite
validates an actual remote issuer credential rather than a placeholder token.
"""

import base64
import json
import os
import ssl
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

import jwt
from cryptography.hazmat.primitives import serialization
from flask import Flask, jsonify, request


KEY_PATH = Path(os.getenv("JWT_PRIVATE_KEY_PATH", "/keys/private_key.pem"))
PRIVATE_KEY = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
PUBLIC_KEY = PRIVATE_KEY.public_key()
PUBLIC_KEY_PEM = PUBLIC_KEY.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")

DEFAULT_REDEEMERS = {"full.local": "full-redeemer", "lite.local": "lite-redeemer"}
DEFAULT_ISSUERS = {
    "full.local": "https://full.local/auth",
    "lite.local": "http://blockchain-services:8080/auth",
}


def json_env(name: str, default: dict[str, str]) -> dict[str, str]:
    raw = os.getenv(name, "")
    if not raw:
        return default
    try:
        value = json.loads(raw)
        return {str(key).lower(): str(item) for key, item in value.items()}
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid {name}") from exc


REDEEMERS = json_env("REDEEMER_CREDENTIALS_JSON", DEFAULT_REDEEMERS)
ISSUERS = json_env("ISSUER_BY_GATEWAY_JSON", DEFAULT_ISSUERS)
OBSERVER_SECRETS = json_env(
    "SESSION_OBSERVER_CREDENTIALS_JSON",
    {"lite.local": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"},
)
LITE_PROVISIONER_TOKEN = os.getenv("LITE_PROVISIONER_TOKEN", "lite-provisioner")
REDEMPTION_LEASE_SECONDS = max(1, int(os.getenv("REDEMPTION_LEASE_SECONDS", "30")))
REDEMPTION_PREPARE_DELAY_MS = max(0, int(os.getenv("REDEMPTION_PREPARE_DELAY_MS", "0")))

app = Flask(__name__)
contract_status = int(os.getenv("INITIAL_CONTRACT_STATUS", "1"))
access_codes: dict[str, dict] = {}
observations: list[dict] = []
access_codes_lock = threading.Lock()


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def status_name(value: int) -> str:
    return {
        0: "NONE",
        1: "CONFIRMED",
        2: "ACCESS_AUTHORIZED",
        3: "COLLECTED",
        4: "CANCELLED",
    }.get(value, "UNKNOWN")


def gateway_id(value: str | None) -> str:
    return (value or "").strip().lower()


def gateway_origin(value: str | None) -> str:
    origin = (value or "").strip().rstrip("/")
    if not origin:
        raise ValueError("gatewayOrigin is required")
    if not (origin.startswith("https://") or origin.startswith("http://")):
        raise ValueError("gatewayOrigin must be an absolute HTTP(S) origin")
    return origin


def json_response(payload: dict, status: int = 200, headers: dict[str, str] | None = None):
    response = jsonify(payload)
    response.status_code = status
    if headers:
        response.headers.update(headers)
    return response


def public_jwks() -> dict:
    numbers = PUBLIC_KEY.public_numbers()
    modulus = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    exponent = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {
        "keys": [{
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "kid": "full-lite-integration-key",
            "n": b64url(modulus),
            "e": b64url(exponent),
        }]
    }


def issue_access_token(record: dict) -> tuple[str, str]:
    now = int(time.time())
    jti = f"jti-{uuid.uuid4().hex}"
    username = f"dlabs-res-{record['gatewayId'].replace('.', '-')}-{uuid.uuid4().hex[:12]}"
    resource_type = record.get("resourceType", "lab")
    lab_url = (
        f"{record['gatewayOrigin']}/fmu/"
        if resource_type == "fmu"
        else f"{record['gatewayOrigin']}/guacamole/"
    )
    claims = {
        "iss": record["issuer"],
        "sub": username,
        "aud": lab_url.rstrip("/") if resource_type == "fmu" else f"{record['gatewayOrigin']}/guacamole",
        "jti": jti,
        "reservationKey": record["reservationKey"],
        "resourceType": "lab",
        "lab": record["labId"],
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
    }
    claims["resourceType"] = resource_type
    token = jwt.encode(
        claims,
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": "full-lite-integration-key"},
    )
    return token, lab_url


def authorized_redeemer(gateway: str) -> bool:
    provided = request.headers.get("X-Access-Code-Redeemer-Token", "")
    return bool(gateway and REDEEMERS.get(gateway) == provided)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "full-lite-control-plane"})


@app.get("/.well-known/public-key.pem")
def public_key():
    return app.response_class(PUBLIC_KEY_PEM, status=200, mimetype="text/plain")


@app.get("/auth/jwks")
def jwks():
    return jsonify(public_jwks())


@app.get("/.well-known/openid-configuration")
def openid_configuration():
    return jsonify({
        "issuer": "https://full.local/auth",
        "authorization_endpoint": "https://full.local/auth/authorize-and-issue",
        "jwks_uri": "https://full.local/auth/jwks",
    })


@app.get("/auth/message")
def auth_message():
    return jsonify({"message": "integration-auth-message", "timestamp": str(int(time.time() * 1000))})


@app.post("/auth/access-credential")
def access_credential():
    global contract_status
    body = request.get_json(silent=True) or {}
    gateway = gateway_id(body.get("gatewayId"))
    try:
        origin = gateway_origin(body.get("gatewayOrigin"))
    except ValueError:
        return json_response({"error": "invalid gateway origin"}, 400)

    if body.get("marketplaceToken") != "integration-marketplace-token":
        return json_response({"error": "invalid marketplace token"}, 401)
    if contract_status in (3, 4):
        return json_response({
            "error": "ACCESS_AUTHORIZATION_REJECTED",
            "reservationStatus": status_name(contract_status),
            "retryable": False,
        }, 409)
    if contract_status != 2:
        return json_response({
            "error": "ACCESS_AUTHORIZATION_PENDING",
            "reservationStatus": status_name(contract_status),
            "retryable": True,
        }, 503, {"Retry-After": "1"})
    if not gateway or gateway not in REDEEMERS:
        return json_response({"error": "unknown gateway"}, 403)

    resource_type = str(body.get("resourceType") or "lab").strip().lower()
    if resource_type not in {"lab", "fmu"}:
        return json_response({"error": "unsupported resourceType"}, 400)
    reservation_key = str(body.get("reservationKey") or "").strip()
    lab_id = str(body.get("labId") or "").strip()
    if not reservation_key or not lab_id:
        return json_response({"error": "reservationKey and labId are required"}, 400)

    code = f"access-code-{gateway}-{uuid.uuid4().hex[:12]}"
    access_codes[code] = {
        "gatewayId": gateway,
        "gatewayOrigin": origin,
        "issuer": ISSUERS.get(gateway, ISSUERS.get("lite.local")),
        "reservationKey": reservation_key,
        "labId": lab_id,
        "resourceType": resource_type,
        "prepared": False,
        "committed": False,
    }
    resource_url = f"{origin}/fmu/" if resource_type == "fmu" else f"{origin}/guacamole/"
    return json_response({"accessCode": code, "labURL": resource_url, "resourceType": resource_type})


@app.post("/auth/access-code/redeem")
def redeem_access_code():
    body = request.get_json(silent=True) or {}
    gateway = gateway_id(request.headers.get("X-Gateway-ID"))
    if not authorized_redeemer(gateway):
        return jsonify({"error": "invalid redeemer credential"}), 403
    with access_codes_lock:
        record = access_codes.get(str(body.get("accessCode") or ""))
        if not record or record["gatewayId"] != gateway or record["committed"]:
            return jsonify({"error": "invalid or expired access code"}), 401
        if record["prepared"] and time.time() >= record.get("leaseExpiresAt", 0):
            record["prepared"] = False
            record.pop("redemptionHandle", None)
            record.pop("token", None)
        if record["prepared"]:
            return jsonify({"error": "access code redemption is already in progress"}), 409
        if REDEMPTION_PREPARE_DELAY_MS:
            time.sleep(REDEMPTION_PREPARE_DELAY_MS / 1000)
        token, lab_url = issue_access_token(record)
        record["prepared"] = True
        record["leaseExpiresAt"] = time.time() + REDEMPTION_LEASE_SECONDS
        record["redemptionHandle"] = f"handle-{uuid.uuid4().hex}"
        record["token"] = token
    return jsonify({
        "token": token,
        "labURL": lab_url,
        "resourceType": record["resourceType"],
        "redemptionHandle": record["redemptionHandle"],
    })


def finish_access_code(commit: bool):
    body = request.get_json(silent=True) or {}
    gateway = gateway_id(request.headers.get("X-Gateway-ID"))
    if not authorized_redeemer(gateway):
        return jsonify({"error": "invalid redeemer credential"}), 403
    with access_codes_lock:
        record = access_codes.get(str(body.get("accessCode") or ""))
        if not record or record["gatewayId"] != gateway or body.get("redemptionHandle") != record.get("redemptionHandle"):
            return jsonify({"error": "invalid redemption"}), 401
        if record.get("prepared") and time.time() >= record.get("leaseExpiresAt", 0):
            record["prepared"] = False
            record.pop("redemptionHandle", None)
            record.pop("token", None)
            return jsonify({"error": "invalid or expired redemption lease"}), 401
        if commit:
            if not record["prepared"]:
                return jsonify({"error": "redemption was not prepared"}), 401
            record["committed"] = True
        record["prepared"] = False
    return ("", 204)


@app.post("/auth/access-code/redeem/commit")
def commit_access_code():
    return finish_access_code(True)


@app.post("/auth/access-code/redeem/release")
def release_access_code():
    return finish_access_code(False)


@app.post("/test/contract-state")
def set_contract_state():
    global contract_status
    body = request.get_json(silent=True) or {}
    try:
        contract_status = int(body.get("status"))
    except (TypeError, ValueError):
        return jsonify({"error": "status must be an integer"}), 400
    return jsonify({"status": contract_status, "statusName": status_name(contract_status)})


@app.get("/test/contract-state")
def get_contract_state():
    return jsonify({"status": contract_status, "statusName": status_name(contract_status)})


@app.get("/test/state")
def state():
    return jsonify({"contractStatus": status_name(contract_status), "accessCodes": len(access_codes), "observations": observations})


@app.get("/test/observer-token")
def observer_token():
    gateway = gateway_id(request.args.get("gatewayId"))
    secret = OBSERVER_SECRETS.get(gateway)
    if not secret:
        return jsonify({"error": "unknown observer gateway"}), 404
    now = int(time.time())
    token = jwt.encode({
        "iss": gateway,
        "sub": gateway,
        "aud": ["session-observation"],
        "scope": "session-observation:submit",
        "iat": now,
        "exp": now + 120,
    }, base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4)), algorithm="HS256")
    return jsonify({"token": token})


@app.post("/access-audit/internal/session-observed")
def session_observed():
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return jsonify({"error": "unauthorized"}), 401
    token = authorization[len("Bearer "):].strip()
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        gateway = gateway_id(unverified.get("iss"))
        secret = OBSERVER_SECRETS[gateway]
        claims = jwt.decode(
            token,
            base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4)),
            algorithms=["HS256"],
            audience="session-observation",
            issuer=gateway,
        )
        if claims.get("sub") != gateway or claims.get("scope") != "session-observation:submit":
            raise ValueError("invalid observer scope")
    except (KeyError, ValueError, jwt.PyJWTError, UnicodeError):
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    if body.get("gatewayId", gateway).lower() != gateway or not body.get("reservationKey"):
        return jsonify({"error": "gatewayId mismatch or missing reservationKey"}), 403
    observations.append({**body, "gatewayId": gateway})
    return jsonify({"recorded": True, "auditRecorded": True, "attestationRecorded": False})


@app.post("/test/provision-lite")
def provision_lite():
    """Act as the remote Full backend and call the Lite provisioner route."""
    body = request.get_json(silent=True) or {}
    request_body = json.dumps({
        "selector": body.get("selector", "guac:id:7"),
        "sessionId": body.get("sessionId", "reservation-session-1"),
        "validUntilEpochSeconds": int(time.time()) + 300,
        "activate": True,
    }).encode("utf-8")
    target = "https://lite-gateway/gateway-provisioner/guacamole/provision"
    req = Request(target, data=request_body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Guacamole-Provisioner-Token": LITE_PROVISIONER_TOKEN,
    })
    try:
        with urlopen(req, context=ssl._create_unverified_context(), timeout=10) as response:
            payload = response.read().decode("utf-8")
            return app.response_class(payload, status=response.status, mimetype="application/json")
    except Exception:
        return json_response({"success": False, "error": "Lite provisioning failed"}, 502)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
