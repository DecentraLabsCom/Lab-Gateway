"""
Mock ops-worker server for integration testing.
Simulates the lab station operations service.
"""

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
    return jsonify({"events": demo_events, "sessions": demo_sessions})


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
    print("Starting mock ops-worker server on port 5001...")
    app.run(host='0.0.0.0', port=5001)
