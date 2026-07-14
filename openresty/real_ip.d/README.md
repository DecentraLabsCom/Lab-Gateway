# Trusted real-IP snippets

The gateway overwrites `X-Forwarded-For` before proxying. Do not add a
`real_ip` snippet unless the public edge is behind a reverse proxy whose
source ranges are controlled and maintained by the deployment operator.

For Cloudflare, create a local `10-cloudflare.conf` containing the current
published Cloudflare ranges and use its canonical header:

```nginx
set_real_ip_from <current-cloudflare-cidr>;
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
```

For another trusted proxy, use its published CIDRs and the header it
normalizes. Never use `0.0.0.0/0`, trust arbitrary client-supplied headers, or
commit provider-specific ranges without an update process.
