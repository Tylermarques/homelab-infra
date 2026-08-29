# Home Assistant ingress

`home-assistant.yaml` routes `hass.local.tylermarques.com` through the home
cluster's Traefik instance to the HAOS VM at `http://192.168.0.131:8123`.
Requests over plain HTTP receive a permanent redirect to HTTPS.

Home Assistant must trust the k3s pod network and every node that can run
Traefik. Home Assistant 2026.8 and newer manages HTTP settings in storage, not
`configuration.yaml`. Configure these trusted proxies through Home Assistant's
HTTP settings UI or WebSocket API:

```yaml
use_x_forwarded_for: true
trusted_proxies:
  - 10.42.0.0/16
  - 192.168.0.24/32
  - 192.168.0.113/32
  - 192.168.0.119/32
  - 192.168.0.240/32
  - 192.168.1.49/32
  - 192.168.1.111/32
  - 192.168.1.152/32
  - 192.168.1.153/32
  - 192.168.1.188/32
  - 192.168.1.226/32
```

The node addresses are required because k3s masquerades traffic from Traefik
to the external HAOS endpoint, so Home Assistant sees the k3s node's LAN
address. Keep this list synchronized with the cluster inventory.

Pi-hole must not point `hass.local.tylermarques.com` directly at the HAOS VM.
Remove that custom DNS record so the existing `*.local.tylermarques.com`
wildcard sends requests to Traefik instead.

## Dashboard

`home-control-dashboard.yaml` is the source-controlled configuration for the
storage-mode **Home Control** dashboard. It uses the native responsive Sections
layout and the existing Mushroom installation. The Rack Info and Map dashboards
remain separate.

## Authelia OIDC

Home Assistant uses `hass-oidc-auth` 1.2.1 with Authelia's public PKCE client:

```yaml
auth_oidc:
  client_id: homeassistant
  discovery_url: https://auth.local.tylermarques.com/.well-known/openid-configuration
  display_name: Authelia
  roles:
    admin: admins
    user: users
```

Local Home Assistant authentication remains available as a recovery path. To
link an existing Home Assistant user, temporarily add
`features.automatic_user_linking: true`, complete one OIDC login with the same
username, and then remove that option.
