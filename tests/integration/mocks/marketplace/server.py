"""Deterministic Marketplace authority for the demo vertical integration gate.

The real Marketplace remains covered by its Jest contract suites. This small
service supplies the cross-container boundary used by OpenResty so the Docker
gate can exercise publication, strict metadata sanitation, catalogue
discovery, and the eligibility response consumed by the Gateway.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

LAB_ID = "42"
LAB_OWNER = "0x1111111111111111111111111111111111111111"
published_metadata = None


def sanitize_metadata(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("demoEnabled"), bool):
        return None
    return {
        "name": str(payload.get("name") or "Vertical Demo Lab")[:200],
        "description": str(payload.get("description") or "")[:20000],
        "demoEnabled": payload["demoEnabled"],
        "attributes": payload.get("attributes") if isinstance(payload.get("attributes"), list) else [],
    }


def public_lab():
    return {
        "id": int(LAB_ID),
        "name": published_metadata["name"],
        "description": published_metadata["description"],
        "provider": LAB_OWNER,
        "resourceType": 0,
        "isListed": True,
        "demoEnabled": published_metadata["demoEnabled"],
        "accessURI": "https://gateway.example/guacamole",
    }


@app.get("/health")
def health():
    return jsonify({"status": "UP", "service": "marketplace-authority-mock"})


@app.post("/api/test/publish")
def publish():
    global published_metadata
    sanitized = sanitize_metadata(request.get_json(silent=True))
    if sanitized is None:
        return jsonify({"error": "demoEnabled must be a boolean"}), 422
    published_metadata = sanitized
    return jsonify({"metadata": published_metadata, "labId": LAB_ID}), 201


@app.get("/api/market/labs")
def catalogue():
    if published_metadata is None:
        return jsonify({"labs": [], "catalogueStatus": "fresh", "totalLabs": 0})
    return jsonify({
        "labs": [public_lab()],
        "catalogueStatus": "fresh",
        "totalLabs": 1,
        "returnedLabs": 1,
    })


@app.get("/api/demo/eligibility")
def eligibility():
    args = request.args
    lab_id = args.get("labId", "")
    start = args.get("start", "")
    end = args.get("end", "")
    try:
        start_value = int(start)
        end_value = int(end)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid eligibility parameters"}), 400

    if lab_id != LAB_ID or start_value < 1 or end_value <= start_value or end_value - start_value > 600:
        return jsonify({"eligible": False, "labId": lab_id, "start": start, "end": end}), 200

    return jsonify({
        "eligible": published_metadata is not None and published_metadata["demoEnabled"] is True,
        "labId": LAB_ID,
        "start": str(start_value),
        "end": str(end_value),
    })


@app.get("/api/test/state")
def state():
    return jsonify({
        "published": published_metadata is not None,
        "demoEnabled": published_metadata["demoEnabled"] if published_metadata else False,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
