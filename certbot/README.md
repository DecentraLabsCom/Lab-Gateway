# Certbot (manual ACME for OpenResty)

This folder is used as the webroot for HTTP-01 challenges. To issue/renew certificates with Let's Encrypt (or any ACME CA), run:

```sh
# Replace your.domain and email with real values
docker compose run --rm --profile certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d your.domain \
  --email you@example.com \
  --agree-tos --no-eff-email
```

Volumes:
- `./certs` mounts to `/etc/letsencrypt` (certs/keys will be stored here and used by OpenResty).
- `./certbot/www` mounts to `/var/www/certbot` (ACME challenge webroot).

Automation:
- Provide `CERTBOT_DOMAINS` (comma-separated) and `CERTBOT_EMAIL` in your `.env`.
- Run `docker compose up -d --profile certbot certbot-init certbot-renew` once. `certbot-init` will issue if missing; `certbot-renew` will renew every 12h and OpenResty will auto-reload when cert files change.
- If you skip `CERTBOT_DOMAINS`/`CERTBOT_EMAIL`, the stack falls back to self-signed localhost certs that rotate automatically every ~87 days inside the OpenResty container (good for local/dev only).

If you prefer manual control, skip the services above and run certbot commands as needed, then `docker compose restart openresty`.
