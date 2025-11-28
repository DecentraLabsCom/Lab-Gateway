#!/bin/bash
# =================================================================
# Guacamole Docker Entrypoint
# Generates guacamole.properties from environment variables
# =================================================================

set -e

GUAC_HOME="/etc/guacamole"
PROPERTIES_FILE="${GUAC_HOME}/guacamole.properties"

echo "=== Guacamole Configuration ==="

# Generate guacamole.properties from environment variables
cat > "${PROPERTIES_FILE}" << EOF
# Guacamole properties file (auto-generated)

guacamole.context-path: /guacamole

# MySQL database connection settings
mysql-hostname: ${MYSQL_HOSTNAME:-mysql}
mysql-port: ${MYSQL_PORT:-3306}
mysql-database: ${MYSQL_DATABASE:-guacamole_db}
mysql-username: ${MYSQL_USER:-guacamole_user}
mysql-password: ${MYSQL_PASSWORD}
mysql-server-timezone: ${MYSQL_TIMEZONE:-Europe/Madrid}

# HTTP header authentication
http-auth-header: Authorization

extension-priority: header, mysql

# Guacd connection
guacd-hostname: ${GUACD_HOSTNAME:-guacd}
guacd-port: ${GUACD_PORT:-4822}

# Session timeout (minutes)
api-session-timeout: ${API_SESSION_TIMEOUT:-1}
EOF

echo "✔ Generated ${PROPERTIES_FILE}"
echo "  Database: ${MYSQL_HOSTNAME:-mysql}:${MYSQL_PORT:-3306}/${MYSQL_DATABASE:-guacamole_db}"
echo "  User: ${MYSQL_USER:-guacamole_user}"

# Start Tomcat
echo "=== Starting Tomcat ==="
exec catalina.sh run
