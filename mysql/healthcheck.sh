#!/usr/bin/env bash
set -euo pipefail

read_secret() {
  local path="$1"
  local value

  if [[ ! -r "$path" ]]; then
    echo "Required MySQL healthcheck secret is not readable: $path" >&2
    return 1
  fi

  value="$(cat "$path")"
  if [[ -z "$value" ]]; then
    echo "Required MySQL healthcheck secret is empty: $path" >&2
    return 1
  fi

  printf '%s' "$value"
}

root_password="$(read_secret /run/secrets/mysql_root_password)"
blockchain_password="$(read_secret /run/secrets/blockchain_mysql_password)"

: "${BLOCKCHAIN_MYSQL_USER:?BLOCKCHAIN_MYSQL_USER must be configured}"
: "${BLOCKCHAIN_MYSQL_DATABASE:?BLOCKCHAIN_MYSQL_DATABASE must be configured}"

mysqladmin ping \
  -h localhost \
  -u root \
  -p"$root_password"

mysql \
  -h localhost \
  -u"$BLOCKCHAIN_MYSQL_USER" \
  -p"$blockchain_password" \
  "$BLOCKCHAIN_MYSQL_DATABASE" \
  -e "SELECT 1"
