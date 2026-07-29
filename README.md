# Tyler's Homelab

## DNS for local services (`*.local.tylermarques.com`)

Local services resolve for both home-LAN and tailnet clients via public DNS:

- A wildcard A record `*.local.tylermarques.com` (in `rackspace/apps/dns.py`,
  controlled by `HOME_LAN_INGRESS_IP` in `rackspace/.env`) points at the home
  cluster's Traefik LAN IP. It is unproxied — anyone can resolve it, but only
  clients on the LAN or tailnet can route to it.
- A Tailscale `Connector` (subnet router) deployed by the `homelab/` Pulumi
  project advertises the LAN subnet (`HOME_LAN_SUBNET`) to the tailnet, so
  tailnet clients can reach that LAN IP. The route must be approved once in
  the Tailscale admin console (or auto-approved via ACL `autoApprovers`).
- TLS comes from the existing `*.local.tylermarques.com` wildcard cert
  (cert-manager DNS-01, `rackspace/apps/cert_manager/`).

Gotcha: some routers/resolvers drop public DNS answers containing private IPs
(rebind protection). If LAN clients can't resolve `*.local.tylermarques.com`,
whitelist the domain in the router's rebind-protection settings.

## TODOs

- [x] Move most of services to RackspaceSpot
- Implement secret manager
- Speed tests for the NFS - is it feasible to have the nfs at home?
- Dashboard with appropriate auto discovery
- Move the existing services over to pulumi

### Service migration List

- [] dashy
- [] freshrss
- [x] prometheus
- [x] grafana
- [] immich
- [] loki
- [] paperless-ngx
- [] overseer
- [] immich
- [] mealie
- [] ntfy
