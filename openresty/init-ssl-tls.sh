#!/bin/sh
# TLS pair validation and atomic installation helpers for init-ssl.sh.
# The caller defines SSL_DIR, CERT_FILE, KEY_FILE, TEMP_SSL_DIR,
# SERVER_NAME and set_ssl_permissions before sourcing this file.

atomic_tls_copy() {
    source_path="$1"
    target_path="$2"
    mode="$3"
    target_tmp="${target_path}.tmp.$$"
    if ! cp "$source_path" "$target_tmp"; then
        rm -f "$target_tmp"
        return 1
    fi
    chmod "$mode" "$target_tmp" 2>/dev/null || true
    mv -f "$target_tmp" "$target_path"
}

cert_pair_is_usable() {
    cert_path="$1"
    key_path="$2"

    [ -s "$cert_path" ] && [ -s "$key_path" ] || return 1
    openssl x509 -in "$cert_path" -noout >/dev/null 2>&1 || return 1
    openssl x509 -in "$cert_path" -checkend 0 -noout >/dev/null 2>&1 || return 1
    openssl pkey -in "$key_path" -noout >/dev/null 2>&1 || return 1

    if [ -n "${SERVER_NAME:-}" ] && [ "$SERVER_NAME" != "localhost" ]; then
        case "$SERVER_NAME" in
            *:*)
                openssl x509 -in "$cert_path" -checkip "$SERVER_NAME" -noout >/dev/null 2>&1 || return 1
                ;;
            *)
                openssl x509 -in "$cert_path" -checkhost "$SERVER_NAME" -noout >/dev/null 2>&1 || return 1
                ;;
        esac
    fi

    mkdir -p "$TEMP_SSL_DIR"
    cert_public_tmp="$TEMP_SSL_DIR/cert-public.$$"
    key_public_tmp="$TEMP_SSL_DIR/key-public.$$"

    if ! openssl x509 -in "$cert_path" -pubkey -noout |
        openssl pkey -pubin -outform DER > "$cert_public_tmp"; then
        rm -f "$cert_public_tmp" "$key_public_tmp"
        return 1
    fi
    if ! openssl pkey -in "$key_path" -pubout -outform DER > "$key_public_tmp"; then
        rm -f "$cert_public_tmp" "$key_public_tmp"
        return 1
    fi

    cmp -s "$cert_public_tmp" "$key_public_tmp"
    result=$?
    rm -f "$cert_public_tmp" "$key_public_tmp"
    return "$result"
}

install_tls_pair() {
    source_cert="$1"
    source_key="$2"
    if ! atomic_tls_copy "$source_cert" "$CERT_FILE" 0644; then
        return 1
    fi
    if ! atomic_tls_copy "$source_key" "$KEY_FILE" 0640; then
        return 1
    fi
    set_ssl_permissions
    return 0
}
