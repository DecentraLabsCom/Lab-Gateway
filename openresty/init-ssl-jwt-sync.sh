#!/bin/sh
# Lite-mode issuer URL and JWT public-key synchronization helpers.
# The caller defines trim, atomic_copy and the JWT path variables before
# sourcing this file. Full-mode key rotation remains in init-ssl.sh.

build_key_url_from_issuer() {
    issuer_raw="$(trim "$1")"
    issuer_no_slash="$(echo "$issuer_raw" | sed 's:/*$::')"
    origin="$(echo "$issuer_no_slash" | sed -n 's#^\(https\?://[^/]*\).*$#\1#p')"
    if [ -z "$origin" ]; then
        return 1
    fi
    echo "${origin}/.well-known/public-key.pem"
}

sync_jwt_public_key_from_issuer() {
    target_issuer="$1"
    key_url="$(build_key_url_from_issuer "$target_issuer" 2>/dev/null || true)"
    if [ -z "$key_url" ]; then
        echo "Invalid issuer URL for key sync: '$target_issuer'"
        return 1
    fi

    tmp_key="${JWT_PUBLIC_KEY}.download"
    echo "Syncing JWT public key from: $key_url"
    if ! curl -fsSL --connect-timeout 10 --max-time 20 "$key_url" -o "$tmp_key"; then
        echo "Failed to download JWT public key from $key_url"
        rm -f "$tmp_key"
        return 1
    fi

    if ! grep -q "BEGIN PUBLIC KEY" "$tmp_key"; then
        echo "Downloaded file is not a PEM public key"
        rm -f "$tmp_key"
        return 1
    fi

    if ! openssl pkey -pubin -in "$tmp_key" -noout >/dev/null 2>&1; then
        echo "Downloaded PEM public key is invalid"
        rm -f "$tmp_key"
        return 1
    fi

    if [ -f "$JWT_PUBLIC_KEY" ] && cmp -s "$tmp_key" "$JWT_PUBLIC_KEY"; then
        rm -f "$tmp_key"
        echo "JWT public key already up-to-date"
        return 0
    fi

    if [ -f "$JWT_PUBLIC_KEY" ]; then
        atomic_copy "$JWT_PUBLIC_KEY" "$JWT_PREVIOUS_PUBLIC_KEY"
        date +%s > "$JWT_PREVIOUS_ISSUED_MARKER" 2>/dev/null || true
    fi
    mv "$tmp_key" "$JWT_PUBLIC_KEY"
    chmod 644 "$JWT_PUBLIC_KEY"
    atomic_copy "$JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"
    echo "JWT public key updated from issuer"
    return 10
}
