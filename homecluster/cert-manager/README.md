# cert-manager (home k3s cluster)

Helm-managed release, upgraded from v1.11.0 to v1.21.1 (2026-07-29) because
v1.11's Cloudflare DNS-01 solver broke when Cloudflare removed `zone_id` from
DNS-record API responses (renewals silently failed from ~April 2025).

Upgrade with:

    helm repo update jetstack
    helm --kube-context k3s-homelab upgrade cert-manager jetstack/cert-manager \
      -n cert-manager --version <target> -f values.yaml

The Cloudflare API token lives in the `cloudflare-token-secret` Secret in the
cert-manager namespace (not in git). Public recursive nameservers are pinned
in values.yaml because pihole serves split-horizon answers for
local.tylermarques.com, which breaks cert-manager's zone resolution.
