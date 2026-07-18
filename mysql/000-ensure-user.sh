#!/bin/bash
#
# Ensure MySQL user has proper remote access permissions
# This script guarantees the user exists with correct permissions regardless of timing issues
#

set -euo pipefail

require_env() {
    local name="$1"
    local value="${!name:-}"
    if [ -z "$value" ]; then
        echo "Missing required environment variable: $name" >&2
        exit 1
    fi
}

escape_sql() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\'/\'\'}"
    printf "%s" "$value"
}

ensure_schema() {
    local schema="$1"
    local has_any_table=""
    local missing=()

    has_any_table="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${schema}' LIMIT 1" || true)"
    if [ -z "$has_any_table" ]; then
        echo "Guacamole schema is empty; importing schema into ${schema}..."
        mysql -u root -p"${MYSQL_ROOT_PASSWORD}" "${schema}" < /docker-entrypoint-initdb.d/001-create-schema.sql
        return 0
    fi

    for table in guacamole_entity guacamole_user guacamole_system_permission guacamole_user_permission; do
        exists="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${schema}' AND table_name='${table}' LIMIT 1" || true)"
        if [ "$exists" != "1" ]; then
            missing+=("$table")
        fi
    done

    if [ "${#missing[@]}" -ne 0 ]; then
        echo "Guacamole schema is incomplete (missing: ${missing[*]})."
        echo "Refusing to auto-import to avoid overwriting existing data."
        echo "Run /docker-entrypoint-initdb.d/001-create-schema.sql manually if this is a fresh install."
        return 1
    fi

    return 0
}

require_env "GUAC_ADMIN_USER"
require_env "GUAC_ADMIN_PASS"

reject_if_default() {
    local name="$1"
    local value="$2"
    local lower
    lower="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
    case "$lower" in
        guacadmin|changeme|change_me|password|test)
            echo "Refusing to use insecure ${name} value. Set a strong secret." >&2
            exit 1
            ;;
    esac
}

reject_if_default "GUAC_ADMIN_PASS" "$GUAC_ADMIN_PASS"
reject_if_default "MYSQL_ROOT_PASSWORD" "$MYSQL_ROOT_PASSWORD"
require_env "GUACAMOLE_MYSQL_USER"
require_env "GUACAMOLE_MYSQL_PASSWORD"
require_env "BLOCKCHAIN_MYSQL_USER"
require_env "BLOCKCHAIN_MYSQL_PASSWORD"
require_env "OPS_BACKEND_MYSQL_USER"
require_env "OPS_BACKEND_MYSQL_PASSWORD"
require_env "OPS_GUACAMOLE_MYSQL_USER"
require_env "OPS_GUACAMOLE_MYSQL_PASSWORD"

reject_if_default "GUACAMOLE_MYSQL_PASSWORD" "$GUACAMOLE_MYSQL_PASSWORD"
reject_if_default "BLOCKCHAIN_MYSQL_PASSWORD" "$BLOCKCHAIN_MYSQL_PASSWORD"
reject_if_default "OPS_BACKEND_MYSQL_PASSWORD" "$OPS_BACKEND_MYSQL_PASSWORD"
reject_if_default "OPS_GUACAMOLE_MYSQL_PASSWORD" "$OPS_GUACAMOLE_MYSQL_PASSWORD"

escaped_guacamole_mysql_user="$(escape_sql "$GUACAMOLE_MYSQL_USER")"
escaped_guacamole_mysql_password="$(escape_sql "$GUACAMOLE_MYSQL_PASSWORD")"
escaped_blockchain_mysql_user="$(escape_sql "$BLOCKCHAIN_MYSQL_USER")"
escaped_blockchain_mysql_password="$(escape_sql "$BLOCKCHAIN_MYSQL_PASSWORD")"
escaped_ops_backend_mysql_user="$(escape_sql "$OPS_BACKEND_MYSQL_USER")"
escaped_ops_backend_mysql_password="$(escape_sql "$OPS_BACKEND_MYSQL_PASSWORD")"
escaped_ops_guacamole_mysql_user="$(escape_sql "$OPS_GUACAMOLE_MYSQL_USER")"
escaped_ops_guacamole_mysql_password="$(escape_sql "$OPS_GUACAMOLE_MYSQL_PASSWORD")"
escaped_guac_admin_user="$(escape_sql "$GUAC_ADMIN_USER")"
escaped_guac_admin_pass="$(escape_sql "$GUAC_ADMIN_PASS")"
blockchain_db="${BLOCKCHAIN_MYSQL_DATABASE:-}"
escaped_mysql_database="$(escape_sql "$MYSQL_DATABASE")"
escaped_blockchain_db="$(escape_sql "$blockchain_db")"

drop_user_definitions() {
    local escaped_user="$1"
    [ -n "$escaped_user" ] || return 0
    mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<-EOSQL
        SET @drop_stmt = (
            SELECT GROUP_CONCAT(CONCAT('DROP USER IF EXISTS ''', user, '''@''', host, ''';') SEPARATOR ' ')
            FROM mysql.user
            WHERE user = '${escaped_user}'
        );
        SET @drop_stmt = IFNULL(@drop_stmt, 'SELECT "No existing definitions to drop";');
        PREPARE drop_users FROM @drop_stmt;
        EXECUTE drop_users;
        DEALLOCATE PREPARE drop_users;
EOSQL
}

grant_guacamole_worker_tables() {
    local table
    for table in guacamole_entity guacamole_user guacamole_connection_permission guacamole_connection guacamole_connection_parameter; do
        exists="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${MYSQL_DATABASE}' AND table_name='${table}' LIMIT 1" || true)"
        if [ "$exists" = "1" ]; then
            mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "GRANT SELECT, INSERT, UPDATE, DELETE ON \`${escaped_mysql_database}\`.\`${table}\` TO '${escaped_ops_guacamole_mysql_user}'@'%';"
        fi
    done

    # History is evidence only; the worker must never mutate it.
    exists="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${MYSQL_DATABASE}' AND table_name='guacamole_connection_history' LIMIT 1" || true)"
    if [ "$exists" = "1" ]; then
        mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "GRANT SELECT ON \`${escaped_mysql_database}\`.\`guacamole_connection_history\` TO '${escaped_ops_guacamole_mysql_user}'@'%';"
    fi
}

echo "=== Ensuring MySQL user has proper remote access ==="

# Wait for MySQL to be ready
until mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; do
    echo "Waiting for MySQL to be ready..."
    sleep 2
done

echo "MySQL is ready. Configuring user permissions..."

# Reconcile each principal on every run so grants are deterministic.
for user in \
    "$GUACAMOLE_MYSQL_USER" \
    "$BLOCKCHAIN_MYSQL_USER" \
    "$OPS_BACKEND_MYSQL_USER" \
    "$OPS_GUACAMOLE_MYSQL_USER"; do
    drop_user_definitions "$(escape_sql "$user")"
done

mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<-EOSQL
    CREATE DATABASE IF NOT EXISTS \`${escaped_mysql_database}\`;
    CREATE DATABASE IF NOT EXISTS \`${escaped_blockchain_db}\`;

    CREATE USER '${escaped_guacamole_mysql_user}'@'%' IDENTIFIED BY '${escaped_guacamole_mysql_password}';
    CREATE USER '${escaped_blockchain_mysql_user}'@'%' IDENTIFIED BY '${escaped_blockchain_mysql_password}';
    CREATE USER '${escaped_ops_backend_mysql_user}'@'%' IDENTIFIED BY '${escaped_ops_backend_mysql_password}';
    CREATE USER '${escaped_ops_guacamole_mysql_user}'@'%' IDENTIFIED BY '${escaped_ops_guacamole_mysql_password}';

    -- Application principals are scoped to their own schema.
    GRANT ALL PRIVILEGES ON \`${escaped_mysql_database}\`.* TO '${escaped_guacamole_mysql_user}'@'%';
    GRANT ALL PRIVILEGES ON \`${escaped_blockchain_db}\`.* TO '${escaped_blockchain_mysql_user}'@'%';

    -- Ops backend requires DML for scheduler/outbox/reservation tables but
    -- never DDL, GRANT, or access to the Guacamole schema.
    GRANT SELECT, INSERT, UPDATE, DELETE ON \`${escaped_blockchain_db}\`.* TO '${escaped_ops_backend_mysql_user}'@'%';
    FLUSH PRIVILEGES;
EOSQL

waited=0
max_wait=60
while true; do
    missing_tables=()
    for table in guacamole_entity guacamole_user guacamole_system_permission guacamole_user_permission; do
        exists="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${MYSQL_DATABASE}' AND table_name='${table}' LIMIT 1" || true)"
        if [ "$exists" != "1" ]; then
            missing_tables+=("$table")
        fi
    done

    if [ "${#missing_tables[@]}" -eq 0 ]; then
        break
    fi

    if [ "$waited" -ge "$max_wait" ]; then
        echo "Guacamole schema not ready after ${max_wait}s (missing: ${missing_tables[*]}); attempting auto-import."
        if ensure_schema "${MYSQL_DATABASE}"; then
            missing_tables=()
            for table in guacamole_entity guacamole_user guacamole_system_permission guacamole_user_permission; do
                exists="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${MYSQL_DATABASE}' AND table_name='${table}' LIMIT 1" || true)"
                if [ "$exists" != "1" ]; then
                    missing_tables+=("$table")
                fi
            done
            if [ "${#missing_tables[@]}" -eq 0 ]; then
                break
            fi
        fi
        echo "Guacamole schema not ready after ${max_wait}s (missing: ${missing_tables[*]}); skipping admin sync."
        echo "=== User configuration completed successfully ==="
        exit 0
    fi

    echo "Guacamole schema not ready (missing: ${missing_tables[*]}); waiting..."
    sleep 2
    waited=$((waited + 2))
done

# Apply table-level grants after the Guacamole schema exists. Missing optional
# tables (for example on an older Guacamole image) are skipped safely.
grant_guacamole_worker_tables

mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<-EOSQL
    -- Ensure Guacamole admin user matches configured credentials
    USE \`${MYSQL_DATABASE}\`;
    SET @guac_admin_user = '${escaped_guac_admin_user}';
    SET @guac_admin_pass = '${escaped_guac_admin_pass}';
    SET @guac_salt = UNHEX(SHA2(UUID(), 256));

    INSERT INTO guacamole_entity (name, type)
    VALUES (@guac_admin_user, 'USER')
    ON DUPLICATE KEY UPDATE name = VALUES(name), type = VALUES(type);

    INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date)
    SELECT
        entity_id,
        UNHEX(SHA2(CONCAT(@guac_admin_pass, HEX(@guac_salt)), 256)),
        @guac_salt,
        NOW()
    FROM guacamole_entity WHERE name = @guac_admin_user
    ON DUPLICATE KEY UPDATE
        password_hash = VALUES(password_hash),
        password_salt = VALUES(password_salt),
        password_date = VALUES(password_date);

    INSERT IGNORE INTO guacamole_system_permission (entity_id, permission)
    SELECT entity_id, permission
    FROM (
              SELECT @guac_admin_user AS username, 'CREATE_CONNECTION'       AS permission
        UNION SELECT @guac_admin_user AS username, 'CREATE_CONNECTION_GROUP' AS permission
        UNION SELECT @guac_admin_user AS username, 'CREATE_SHARING_PROFILE'  AS permission
        UNION SELECT @guac_admin_user AS username, 'CREATE_USER'             AS permission
        UNION SELECT @guac_admin_user AS username, 'CREATE_USER_GROUP'       AS permission
        UNION SELECT @guac_admin_user AS username, 'ADMINISTER'              AS permission
    ) permissions
    JOIN guacamole_entity ON permissions.username = guacamole_entity.name AND guacamole_entity.type = 'USER';

    INSERT IGNORE INTO guacamole_user_permission (entity_id, affected_user_id, permission)
    SELECT guacamole_entity.entity_id, guacamole_user.user_id, permission
    FROM (
              SELECT @guac_admin_user AS username, @guac_admin_user AS affected_username, 'READ'       AS permission
        UNION SELECT @guac_admin_user AS username, @guac_admin_user AS affected_username, 'UPDATE'     AS permission
        UNION SELECT @guac_admin_user AS username, @guac_admin_user AS affected_username, 'ADMINISTER' AS permission
    ) permissions
    JOIN guacamole_entity          ON permissions.username = guacamole_entity.name AND guacamole_entity.type = 'USER'
    JOIN guacamole_entity affected ON permissions.affected_username = affected.name AND guacamole_entity.type = 'USER'
    JOIN guacamole_user            ON guacamole_user.entity_id = affected.entity_id;

    -- Disable the bundled default account if a different admin is configured
    SET @default_admin = 'guacadmin';
    SET @default_salt = UNHEX(SHA2(UUID(), 256));
    UPDATE guacamole_user u
    JOIN guacamole_entity e ON e.entity_id = u.entity_id
    SET u.password_hash = UNHEX(SHA2(CONCAT(UUID(), @default_salt), 256)),
        u.password_salt = @default_salt,
        u.password_date = NOW()
    WHERE e.name = @default_admin AND @guac_admin_user <> @default_admin;
EOSQL

# ── Demo Guacamole user (header-auth only, password login disabled) ──────────
# The user is pre-created so the lab admin only needs to assign a connection.
# Connection assignment is intentionally NOT automated here.
DEMO_GUAC_USER="${DEMO_USER:-demo}"
escaped_demo_user="$(escape_sql "$DEMO_GUAC_USER")"
echo "Ensuring demo Guacamole user: ${DEMO_GUAC_USER}"

mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<-EOSQL
    USE \`${MYSQL_DATABASE}\`;

    -- Random, non-guessable hash and salt so password login is effectively impossible.
    -- Authentication happens via the Authorization header set by OpenResty.
    SET @demo_salt = UNHEX(SHA2(CONCAT('demo-salt-', UUID()), 256));
    SET @demo_hash = UNHEX(SHA2(CONCAT('demo-hash-', UUID()), 256));

    INSERT IGNORE INTO guacamole_entity (name, type)
    VALUES ('${escaped_demo_user}', 'USER');

    INSERT IGNORE INTO guacamole_user (entity_id, password_hash, password_salt, password_date)
    SELECT entity_id, @demo_hash, @demo_salt, NOW()
    FROM guacamole_entity
    WHERE name = '${escaped_demo_user}' AND type = 'USER';
EOSQL

echo "=== User configuration completed successfully ==="
