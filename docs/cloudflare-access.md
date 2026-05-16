# Cloudflare access plan for the Summerhouse Agent

Recommended setup: keep the Flask app private inside Docker and expose it via a named Cloudflare Tunnel protected by Cloudflare Access.

## Target architecture

Browser/family -> Cloudflare Access login -> Cloudflare Tunnel -> `http://127.0.0.1:8080` inside the Hermes container -> Summerhouse Agent Flask app.

No inbound port needs to be opened on the server.

## Prerequisites

- A Cloudflare account.
- A domain on Cloudflare, e.g. `yourdomain.dk`.
- A chosen hostname, e.g. `summerhouse.yourdomain.dk`.
- Family member emails for the Access allowlist.

## App command

From `/opt/data/repos/summerhouse-agent`:

```bash
scripts/start_dashboard.sh
```

By default it binds only to `127.0.0.1:8080`, which is appropriate when `cloudflared` runs in the same container.

If `cloudflared` runs as a separate container on the same Docker network, start the app with:

```bash
SUMMERHOUSE_HOST=0.0.0.0 SUMMERHOUSE_PORT=8080 scripts/start_dashboard.sh
```

## Cloudflare Tunnel setup options

### Option A — Token-based tunnel, simplest in Docker

1. In Cloudflare Zero Trust, create a tunnel.
2. Add public hostname:
   - Hostname: `summerhouse.yourdomain.dk`
   - Service: `http://127.0.0.1:8080` if same container, or `http://summerhouse-agent:8080` if separate container.
3. Copy the tunnel token.
4. Run cloudflared with:

```bash
cloudflared tunnel run --token '<TOKEN_FROM_CLOUDFLARE>'
```

### Option B — Config-file tunnel

Example `/etc/cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL-UUID>
credentials-file: /etc/cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: summerhouse.yourdomain.dk
    service: http://127.0.0.1:8080
  - service: http_status:404
```

Run:

```bash
cloudflared tunnel run <TUNNEL-NAME>
```

## Cloudflare Access policy

Protect the hostname with Cloudflare Access:

- Application type: Self-hosted
- Domain: `summerhouse.yourdomain.dk`
- Policy: Allow only selected emails, e.g. family members
- Optional: require one-time PIN login by email

This is important because the dashboard can trigger scraping, edit preferences, and manipulate watchlists.

## Suggested next hardening inside the app

Even with Cloudflare Access, add a simple app-level shared password later. Defense-in-depth helps if the tunnel hostname is ever misconfigured.

## Verification

Inside Docker:

```bash
curl -I http://127.0.0.1:8080/
```

From outside:

```text
https://summerhouse.yourdomain.dk
```

Expected: Cloudflare Access login first, then the dashboard.
