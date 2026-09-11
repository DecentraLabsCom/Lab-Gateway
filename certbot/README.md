# Certbot (ACME automation for OpenResty)

This folder is used as the webroot for HTTP-01 challenges. Certbot keeps its
lineage under `certs/live/<primary-domain>/`; the deploy hook validates each
renewed certificate/key pair and installs it into the stable files consumed by
OpenResty:

```text
certs/fullchain.pem
certs/privkey.pem
```

The certificate must be reachable from the public Internet on HTTP port 80 and
`SERVER_NAME` must match the primary domain in `CERTBOT_DOMAINS`.

## One-time setup and automatic renewal

Set these values in `.env`:

```env
SERVER_NAME=lab.example.edu
CERTBOT_DOMAINS=lab.example.edu
CERTBOT_EMAIL=admin@example.edu
CERTBOT_STAGING=0
```

Then start the initialization and renewal services:

```sh
docker compose --profile certbot up -d certbot-init certbot-renew
```

`certbot-init` obtains the first certificate when no valid Certbot lineage is
present. `certbot-renew` checks twice per day. After a successful renewal, the
deploy hook replaces each stable file after checking expiration, hostname, and
certificate/private-key matching. OpenResty's watcher validates the pair and
reloads OpenResty within `TLS_RELOAD_INTERVAL_SECONDS` (60 seconds by default).

Check the initial issuance and renewal service:

```sh
docker compose logs certbot-init certbot-renew
```

To test the renewal path without issuing a production certificate:

```sh
docker compose run --rm --profile certbot certbot renew --dry-run \
  --deploy-hook "sh /usr/local/bin/deploy-hook.sh"
```

The dry run validates the renewal configuration but does not replace the
currently installed certificate.

## Manual issuance

If you prefer to issue the first certificate manually, run:

```sh
docker compose run --rm --profile certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d lab.example.edu \
  --email admin@example.edu \
  --agree-tos --no-eff-email \
  --deploy-hook "sh /usr/local/bin/deploy-hook.sh"
```

Volumes:
- `./certs` mounts to `/etc/letsencrypt` (Certbot lineage and stable TLS files).
- `./certbot/www` mounts to `/var/www/certbot` (ACME challenge webroot).

If a valid certificate/key pair already exists in `certs/fullchain.pem` and
`certs/privkey.pem`, OpenResty keeps using it at startup. The Certbot profile is
an explicit migration to Let's Encrypt: its first successful issuance runs the
deploy hook and replaces those stable files.

If you omit `CERTBOT_DOMAINS`/`CERTBOT_EMAIL`, the stack falls back to
self-signed localhost certificates for local development. If HTTP-01 cannot be
served on port 80, use an external DNS-01 workflow and install its result into
the two stable files above; the automatic service in this directory currently
implements HTTP-01 only.
