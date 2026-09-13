#!/bin/sh
# JWT key overlap and refresh watchers for init-ssl.sh.
# The caller defines the JWT paths, mode, timing values, atomic_copy and
# is_valid_public_key before sourcing this file. This file only defines
# functions; the caller controls when each background watcher is launched.

retire_previous_jwt_key() {
    issued_ts="$(cat "$JWT_PREVIOUS_ISSUED_MARKER" 2>/dev/null || echo 0)"
    now_ts="$(date +%s)"
    case "$issued_ts" in
        ''|*[!0-9]*) return 1 ;;
    esac
    if [ "$issued_ts" -gt 0 ] && [ $((now_ts - issued_ts)) -ge "$JWT_KEY_OVERLAP_SECONDS" ]; then
        rm -f "$JWT_PREVIOUS_PUBLIC_KEY" "$JWT_PREVIOUS_ISSUED_MARKER"
        echo "Expired previous JWT public key overlap"
        return 0
    fi
    return 1
}

# blockchain-services rotates the Full-mode key in-place. Keep the last
# complete key in the writable cert volume and reload only after the new PEM
# validates, giving OpenResty a bounded current/previous overlap window.
watch_full_jwt_public_key() {
    if [ "$jwt_key_sync_mode" != "local" ]; then
        return
    fi
    while true; do
        sleep 60
        if retire_previous_jwt_key; then
            /usr/local/openresty/bin/openresty -s reload || true
        fi
        if ! is_valid_public_key "$FULL_JWT_PUBLIC_KEY"; then
            echo "WARNING: Full-mode JWT public key is missing or invalid; retaining current key"
            continue
        fi
        if [ ! -f "$JWT_ACTIVE_SNAPSHOT" ]; then
            atomic_copy "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"
            echo "Full-mode JWT public key became available; reloading OpenResty"
            /usr/local/openresty/bin/openresty -s reload || true
            continue
        fi
        if ! cmp -s "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"; then
            if ! atomic_copy "$JWT_ACTIVE_SNAPSHOT" "$JWT_PREVIOUS_PUBLIC_KEY"; then
                echo "WARNING: Could not preserve previous JWT key; deferring rotation"
                continue
            fi
            date +%s > "$JWT_PREVIOUS_ISSUED_MARKER" 2>/dev/null || true
            if ! atomic_copy "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"; then
                echo "WARNING: Could not snapshot new JWT key; deferring rotation"
                continue
            fi
            echo "Full-mode JWT public key changed; reloading OpenResty with overlap key"
            /usr/local/openresty/bin/openresty -s reload || true
        fi
    done
}

auto_refresh_jwt_public_key() {
    if [ "$jwt_key_sync_mode" != "remote" ]; then
        return
    fi
    while true; do
        sleep "$JWT_KEY_REFRESH_INTERVAL_SECONDS"
        if retire_previous_jwt_key; then
            /usr/local/openresty/bin/openresty -s reload || true
        fi
        sync_jwt_public_key_from_issuer "$EFFECTIVE_ISSUER"
        sync_result=$?
        if [ $sync_result -eq 10 ]; then
            echo "JWT public key changed - reloading OpenResty"
            /usr/local/openresty/bin/openresty -s reload || true
        elif [ $sync_result -ne 0 ]; then
            echo "WARNING: JWT public key refresh failed; will retry every hour until it succeeds"
            # Retry loop: attempt once per hour until the remote is reachable again
            retry_interval=3600
            while true; do
                sleep $retry_interval
                sync_jwt_public_key_from_issuer "$EFFECTIVE_ISSUER"
                retry_result=$?
                if [ $retry_result -eq 0 ] || [ $retry_result -eq 10 ]; then
                    if [ $retry_result -eq 10 ]; then
                        echo "JWT public key updated on retry - reloading OpenResty"
                        /usr/local/openresty/bin/openresty -s reload || true
                    else
                        echo "JWT public key confirmed up-to-date after retry"
                    fi
                    break  # success - return to 24h cycle
                fi
                echo "WARNING: JWT public key refresh retry failed; will try again in ${retry_interval}s"
            done
        fi
    done
}
