#!/bin/sh

# Certbot deploy hook for the Compose-managed Lab Gateway.
# Certbot stores its lineage below /etc/letsencrypt/live, while OpenResty
# reads the stable files at /etc/letsencrypt/fullchain.pem and
# /etc/letsencrypt/privkey.pem through the shared certs/ bind mount.

set -eu

lineage="${RENEWED_LINEAGE:-}"
target_dir="${CERTBOT_TARGET_DIR:-/etc/letsencrypt}"
target_cert="$target_dir/fullchain.pem"
target_key="$target_dir/privkey.pem"
source_cert="$lineage/fullchain.pem"
source_key="$lineage/privkey.pem"

if [ -z "$lineage" ]; then
    echo "Certbot deploy hook requires RENEWED_LINEAGE" >&2
    exit 1
fi

if [ ! -s "$source_cert" ] || [ ! -s "$source_key" ]; then
    echo "Renewed certificate pair is missing under $lineage" >&2
    exit 1
fi

if ! openssl x509 -in "$source_cert" -checkend 0 -noout >/dev/null 2>&1; then
    echo "Renewed certificate is invalid or expired: $source_cert" >&2
    exit 1
fi

if ! openssl pkey -in "$source_key" -noout >/dev/null 2>&1; then
    echo "Renewed private key is invalid: $source_key" >&2
    exit 1
fi

certificate_hostname="${TLS_CERT_HOSTNAME:-}"
if [ -n "$certificate_hostname" ] && [ "$certificate_hostname" != "localhost" ]; then
    case "$certificate_hostname" in
        *:*)
            if ! openssl x509 -in "$source_cert" -checkip "$certificate_hostname" -noout >/dev/null 2>&1; then
                echo "Renewed certificate does not cover $certificate_hostname" >&2
                exit 1
            fi
            ;;
        *)
            if ! openssl x509 -in "$source_cert" -checkhost "$certificate_hostname" -noout >/dev/null 2>&1; then
                echo "Renewed certificate does not cover $certificate_hostname" >&2
                exit 1
            fi
            ;;
    esac
fi

mkdir -p "$target_dir"

cert_public_tmp="$(mktemp "$target_dir/.fullchain-public.XXXXXX")"
key_public_tmp="$(mktemp "$target_dir/.privkey-public.XXXXXX")"
cert_target_tmp="$(mktemp "$target_dir/.fullchain.XXXXXX")"
key_target_tmp="$(mktemp "$target_dir/.privkey.XXXXXX")"

cleanup() {
    rm -f "$cert_public_tmp" "$key_public_tmp" "$cert_target_tmp" "$key_target_tmp"
}

trap cleanup EXIT
trap 'exit 1' HUP INT TERM

if ! openssl x509 -in "$source_cert" -pubkey -noout |
    openssl pkey -pubin -outform DER > "$cert_public_tmp"; then
    echo "Could not read the renewed certificate public key" >&2
    exit 1
fi

if ! openssl pkey -in "$source_key" -pubout -outform DER > "$key_public_tmp"; then
    echo "Could not read the renewed private key public key" >&2
    exit 1
fi

if ! cmp -s "$cert_public_tmp" "$key_public_tmp"; then
    echo "Renewed certificate and private key do not match" >&2
    exit 1
fi

cp "$source_cert" "$cert_target_tmp"
cp "$source_key" "$key_target_tmp"
chmod 0644 "$cert_target_tmp"
chmod 0640 "$key_target_tmp"

cert_uid="${TLS_CERT_UID:-}"
cert_gid="${TLS_CERT_GID:-}"
case "$cert_uid:$cert_gid" in
    :|*[!0-9:]*|*:)
        echo "TLS_CERT_UID and TLS_CERT_GID must be numeric when configured" >&2
        exit 1
        ;;
    *)
        chown "$cert_uid:$cert_gid" "$cert_target_tmp" "$key_target_tmp"
        # Keep the current Certbot lineage readable by the OpenResty UID too.
        # Certbot normally creates archive private keys as root:root 0600;
        # without this, startup fallback cannot recover a missing canonical
        # pair from certs/live after a host-side file loss.
        chown "$cert_uid:$cert_gid" "$source_cert" "$source_key"
        chmod 0644 "$source_cert"
        chmod 0640 "$source_key"
        ;;
esac

# The two replacements are protected by OpenResty's pair validation. If its
# watcher observes the short interval between them, it defers reload until
# both files form a valid matching pair.
mv -f "$cert_target_tmp" "$target_cert"
mv -f "$key_target_tmp" "$target_key"

echo "Installed renewed TLS certificate from $lineage"
