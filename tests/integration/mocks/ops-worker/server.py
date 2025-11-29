"""
Mock ops-worker server for integration testing.
Simulates the lab station operations service.
"""

import json
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


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "ops-worker-mock",
        "version": "1.0.0-test"
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
    print("Starting mock ops-worker server on port 5001...")
    app.run(host='0.0.0.0', port=5001)
