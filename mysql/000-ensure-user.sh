#!/bin/bash
#
# Ensure MySQL user has proper remote access permissions
# This script guarantees the user exists with correct permissions regardless of timing issues
#

set -euo pipefail

echo "=== Ensuring MySQL user has proper remote access ==="

# Wait for MySQL to be ready
until mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; do
    echo "Waiting for MySQL to be ready..."
    sleep 2
done

echo "MySQL is ready. Configuring user permissions..."

# Reconcile the user definition on every run so we do not depend on init-only scripts
mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<-EOSQL
    -- Remove any users for this account regardless of host
    SET @drop_stmt = (
        SELECT GROUP_CONCAT(CONCAT('DROP USER IF EXISTS ''', user, '''@''', host, ''';') SEPARATOR ' ')
        FROM mysql.user
        WHERE user = '${MYSQL_USER}'
    );
    SET @drop_stmt = IFNULL(@drop_stmt, 'SELECT "No existing definitions to drop" AS info;');
    PREPARE drop_users FROM @drop_stmt;
    EXECUTE drop_users;
    DEALLOCATE PREPARE drop_users;
    
    -- Create the user with remote access and ensure credentials are up to date
    CREATE USER IF NOT EXISTS '${MYSQL_USER}'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';
    ALTER USER '${MYSQL_USER}'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';
    
    -- Grant all privileges on the database
    GRANT ALL PRIVILEGES ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_USER}'@'%';
    
    -- Ensure privileges are applied
    FLUSH PRIVILEGES;
    
    -- Verify the user was created correctly
    SELECT CONCAT('User ${MYSQL_USER} configured with host: ', host) AS status 
    FROM mysql.user 
    WHERE user = '${MYSQL_USER}';
EOSQL

echo "=== User configuration completed successfully ==="
