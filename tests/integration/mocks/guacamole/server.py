"""
Mock Guacamole server for integration testing.
Simulates the Apache Guacamole API endpoints.
"""

import secrets
from flask import Flask, jsonify, request

app = Flask(__name__)

# Simulated connections
connections = {
    "test-conn-1": {
        "identifier": "test-conn-1",
        "name": "Test RDP Connection",
        "protocol": "rdp",
        "parentIdentifier": "ROOT",
        "parameters": {
            "hostname": "192.168.1.100",
            "port": "3389",
            "username": "testuser"
        }
    },
    "test-conn-2": {
        "identifier": "test-conn-2",
        "name": "Test VNC Connection",
        "protocol": "vnc",
        "parentIdentifier": "ROOT",
        "parameters": {
            "hostname": "192.168.1.101",
            "port": "5900"
        }
    }
}

# Simulated active sessions
active_sessions = {}


@app.route('/', methods=['GET'])
def root():
    """Root endpoint."""
    return jsonify({"service": "guacamole-mock", "version": "1.5.5-test"})


@app.route('/api/session/data/mysql/connections', methods=['GET'])
def list_connections():
    """List all connections."""
    return jsonify(connections)


@app.route('/api/session/data/mysql/connections/<conn_id>', methods=['GET'])
def get_connection(conn_id):
    """Get specific connection details."""
    if conn_id in connections:
        return jsonify(connections[conn_id])
    return jsonify({"message": "Connection not found", "type": "NOT_FOUND"}), 404


@app.route('/api/tokens', methods=['POST'])
def create_token():
    """Simulate Guacamole authentication token creation."""
    data = request.form
    username = data.get('username', '')
    password = data.get('password', '')
    
    # For testing, accept any credentials
    if username and password:
        token = secrets.token_hex(32)
        return jsonify({
            "authToken": token,
            "username": username,
            "dataSource": "mysql",
            "availableDataSources": ["mysql"]
        })
    
    return jsonify({"message": "Invalid credentials", "type": "INVALID_CREDENTIALS"}), 403


@app.route('/api/session', methods=['GET'])
def get_session():
    """Get current session info."""
    auth_header = request.headers.get('Guacamole-Token', '')
    if auth_header:
        return jsonify({
            "username": "testuser",
            "dataSource": "mysql",
            "availableDataSources": ["mysql"]
        })
    return jsonify({"message": "Unauthorized"}), 401


@app.route('/api/session/data/mysql/activeConnections', methods=['GET'])
def get_active_connections():
    """Get active connection sessions."""
    return jsonify(active_sessions)


@app.route('/api/session/data/mysql/connections/<conn_id>/activeSessions', methods=['GET'])
def get_connection_sessions(conn_id):
    """Get active sessions for a specific connection."""
    if conn_id not in connections:
        return jsonify({"message": "Connection not found"}), 404
    
    conn_sessions = {k: v for k, v in active_sessions.items() if v.get("connectionIdentifier") == conn_id}
    return jsonify(conn_sessions)


@app.route('/api/ext/saml/callback', methods=['POST'])
def saml_callback():
    """Mock SAML callback for JWT-based auth testing."""
    # This simulates the SAML extension callback
    return jsonify({
        "authToken": secrets.token_hex(32),
        "username": "jwt-user@test.com",
        "dataSource": "mysql"
    })


# Health check endpoint for Docker
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "guacamole-mock"
    })


if __name__ == '__main__':
    print("Starting mock Guacamole server on port 8080...")
    app.run(host='0.0.0.0', port=8080)
