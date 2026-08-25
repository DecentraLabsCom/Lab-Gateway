"""
Mock ops-worker server for integration testing.
Simulates the lab station operations service.
"""

import os
import secrets
from flask import Flask, jsonify, request

app = Flask(__name__)

# Simulated lab stations state
lab_stations = {
    "lab-station-1": {
        "id": "lab-station-1",
        "name": "Test Lab Station 1",
        "mac": "00:11:22:33:44:55",
        "ip": "192.168.1.100",
        "status": "online",
        "last_seen": "2025-01-15T10:00:00Z"
    },
    "lab-station-2": {
        "id": "lab-station-2",
        "name": "Test Lab Station 2",
        "mac": "00:11:22:33:44:66",
        "ip": "192.168.1.101",
        "status": "offline",
        "last_seen": "2025-01-14T15:30:00Z"
    }
}

# Simulated job tracking
jobs = {}
demo_events = []
demo_sessions = {}
DEMO_LAB_ID = "42"
DEMO_CONNECTION_ID = "1"
INTERNAL_TOKEN = "integration-ops-internal-secret"
PROVISIONER_TOKEN = os.getenv("GUACAMOLE_PROVISIONER_TOKEN", "integration-test-secret")
OBSERVATION_TOKEN = os.getenv("SESSION_OBSERVATION_INGEST_TOKEN", "integration-observation-token")
provisioner_events = []
session_observations = []
guacamole_revocations = []
station_available = True


def demo_response(demo_id, lab_id, event, success=True, **extra):
    if lab_id != DEMO_LAB_ID or not demo_id.startswith("demo:"):
        return {"success": False, "error": "invalid demo binding"}
    entry = {"demoId": demo_id, "labId": lab_id, "event": event}
    demo_events.append(entry)
    if event == "start":
        demo_sessions[demo_id] = {"labId": lab_id, "status": "prepared"}
    elif event == "connected":
        demo_sessions.setdefault(demo_id, {"labId": lab_id})["status"] = "active"
    elif event == "end":
        demo_sessions.setdefault(demo_id, {"labId": lab_id})["status"] = "released"
    return {"success": success, "operationId": demo_id, "event": event, **extra}


def require_internal_token():
    return request.headers.get("X-Ops-Internal-Token") == INTERNAL_TOKEN


def require_observation_token():
    return request.headers.get("X-Gateway-Observation-Token") == OBSERVATION_TOKEN


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "ops-worker-mock",
        "version": "1.0.0-test",
        "db": True,
        "guacamole_schema": True,
        "demo": {
            "status": "ready",
            "labId": DEMO_LAB_ID,
            "connectionId": DEMO_CONNECTION_ID,
            "checks": {
                "connection": True,
                "principal": True,
                "permission": True,
                "physical_host": True,
            },
        },
    })


@app.post('/api/demo/start')
def demo_start():
    if not require_internal_token():
        return jsonify({"success": False, "error": "internal authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    demo_id = str(payload.get("demoId") or "")
    lab_id = str(payload.get("labId") or "")
    if not station_available:
        return jsonify({
            "success": False,
            "error": "station unavailable",
            "operationId": demo_id,
            "event": "start",
        }), 503
    return jsonify(demo_response(
        demo_id,
        lab_id,
        "start",
        steps=[{"action": "wake", "status": "completed"}, {"action": "prepare", "status": "completed"}],
    ))


@app.post('/api/demo/event')
def demo_event():
    if not require_internal_token():
        return jsonify({"success": False, "error": "internal authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    return jsonify(demo_response(
        str(payload.get("demoId") or ""),
        str(payload.get("labId") or ""),
        str(payload.get("event") or "connected"),
    ))


@app.post('/api/demo/end')
def demo_end():
    if not require_internal_token():
        return jsonify({"success": False, "error": "internal authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    demo_id = str(payload.get("demoId") or "")
    lab_id = str(payload.get("labId") or "")
    if demo_id in demo_sessions and demo_sessions[demo_id].get("status") == "released":
        return jsonify({"success": True, "alreadyReleased": True, "operationId": demo_id})
    return jsonify(demo_response(
        demo_id,
        lab_id,
        "end",
        reason=str(payload.get("reason") or "disconnected"),
        steps=[{"action": "release", "status": "completed"}],
    ))


@app.get('/api/demo/state')
def demo_state():
    return jsonify({"events": demo_events, "sessions": demo_sessions, "stationAvailable": station_available})


@app.post('/api/test/station')
def set_station_state():
    """Test-only station outage switch for deterministic reconnect checks."""
    global station_available
    payload = request.get_json(silent=True) or {}
    station_available = bool(payload.get("available"))
    return jsonify({"available": station_available})


@app.post('/internal/guacamole/provision')
def provision_guacamole_user():
    if request.headers.get("X-Guacamole-Provisioner-Token") != PROVISIONER_TOKEN:
        return jsonify({"success": False, "error": "provisioner authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    selector = str(payload.get("selector") or "")
    session_id = str(payload.get("sessionId") or "")
    if not selector.startswith("guac:id:") or not session_id:
        return jsonify({"success": False, "error": "invalid provisioning request"}), 400
    event = {"selector": selector, "sessionId": session_id, "activate": bool(payload.get("activate"))}
    provisioner_events.append(event)
    return jsonify({
        "success": True,
        "sessionId": session_id,
        "username": f"dlabs-res-{session_id}",
        "connection": {
            "id": 7,
            "selector": selector,
            "name": "Remote provisioned connection",
            "protocol": "rdp",
            "hostname": "192.0.2.7",
            "port": "3389",
        },
    })


@app.delete('/internal/guacamole/provision/<session_id>')
def release_guacamole_user(session_id):
    if request.headers.get("X-Guacamole-Provisioner-Token") != PROVISIONER_TOKEN:
        return jsonify({"success": False, "error": "provisioner authentication required"}), 401
    provisioner_events.append({"sessionId": session_id, "released": True})
    return jsonify({"success": True, "sessionId": session_id})


@app.get('/internal/guacamole/connections')
def list_provisionable_connections():
    if request.headers.get("X-Guacamole-Provisioner-Token") != PROVISIONER_TOKEN:
        return jsonify({"success": False, "error": "provisioner authentication required"}), 401
    return jsonify({"success": True, "connections": [{"id": 7, "selector": "guac:id:7"}]})


@app.post('/internal/session-observations')
def ingest_session_observation():
    if not require_observation_token():
        return jsonify({"success": False, "error": "observation authentication required"}), 401
    session_observations.append(request.get_json(silent=True) or {})
    return jsonify({"recorded": True}), 202


@app.post('/internal/guacamole-token-revocations')
def ingest_guacamole_revocation():
    if not require_observation_token():
        return jsonify({"success": False, "error": "observation authentication required"}), 401
    guacamole_revocations.append(request.get_json(silent=True) or {})
    return jsonify({"recorded": True}), 202


@app.get('/api/integration/state')
def integration_state():
    return jsonify({
        "provisionerEvents": provisioner_events,
        "sessionObservations": session_observations,
        "guacamoleRevocations": guacamole_revocations,
    })


@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint."""
    return jsonify({
        "ready": True,
        "service": "ops-worker-mock"
    })


@app.route('/api/stations', methods=['GET'])
def list_stations():
    """List all lab stations."""
    return jsonify({
        "stations": list(lab_stations.values())
    })


@app.route('/api/stations/<station_id>', methods=['GET'])
def get_station(station_id):
    """Get specific lab station status."""
    if station_id in lab_stations:
        return jsonify(lab_stations[station_id])
    return jsonify({"error": "Station not found"}), 404


@app.route('/api/stations/<station_id>/wol', methods=['POST'])
def wake_station(station_id):
    """Simulate Wake-on-LAN for a station."""
    if station_id not in lab_stations:
        return jsonify({"error": "Station not found"}), 404
    
    job_id = secrets.token_hex(8)
    jobs[job_id] = {
        "id": job_id,
        "station_id": station_id,
        "type": "wol",
        "status": "completed",
        "message": f"WoL magic packet sent to {lab_stations[station_id]['mac']}"
    }
    
    # Simulate station coming online
    lab_stations[station_id]["status"] = "online"
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "Wake-on-LAN packet sent"
    })


@app.route('/api/stations/<station_id>/command', methods=['POST'])
def execute_command(station_id):
    """Simulate WinRM command execution."""
    if station_id not in lab_stations:
        return jsonify({"error": "Station not found"}), 404
    
    if lab_stations[station_id]["status"] != "online":
        return jsonify({"error": "Station is offline"}), 503
    
    data = request.get_json() or {}
    command = data.get("command", "")
    
    job_id = secrets.token_hex(8)
    
    # Simulate different command responses
    if "shutdown" in command.lower():
        jobs[job_id] = {
            "id": job_id,
            "station_id": station_id,
            "type": "command",
            "status": "completed",
            "output": "System shutdown initiated",
            "exit_code": 0
        }
        lab_stations[station_id]["status"] = "offline"
    else:
        jobs[job_id] = {
            "id": job_id,
            "station_id": station_id,
            "type": "command",
            "status": "completed",
            "output": f"Mock execution of: {command}",
            "exit_code": 0
        }
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "output": jobs[job_id]["output"]
    })


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """Get job status."""
    if job_id in jobs:
        return jsonify(jobs[job_id])
    return jsonify({"error": "Job not found"}), 404


@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    """Get aggregated telemetry from all stations."""
    return jsonify({
        "total_stations": len(lab_stations),
        "online_stations": sum(1 for s in lab_stations.values() if s["status"] == "online"),
        "offline_stations": sum(1 for s in lab_stations.values() if s["status"] == "offline"),
        "stations": [
            {
                "id": s["id"],
                "status": s["status"],
                "cpu_usage": 45.2 if s["status"] == "online" else None,
                "memory_usage": 62.8 if s["status"] == "online" else None
            }
            for s in lab_stations.values()
        ]
    })


if __name__ == '__main__':
    port = int(os.getenv("PORT", "5001"))
    print(f"Starting mock ops-worker server on port {port}...")
    app.run(host='0.0.0.0', port=port)
