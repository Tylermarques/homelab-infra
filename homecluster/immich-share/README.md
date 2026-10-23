# Immich sharing

`https://share.local.tylermarques.com` publishes an Immich album to the
internet for a limited time. You give the share a name, an album and an expiry
date. The page then shows a public link like
`https://photos-grandmas-visit-3f9a.<tailnet>.ts.net/share/<key>` that anyone
can open without being on the tailnet. When the expiry passes, the service
deletes the Immich shared link and the funnel, and the address stops
resolving. The page also has a "Revoke now" button.

## How it works

- `immich-public-proxy` (IPP) serves only shared-link pages and their
  assets. Visitors never reach the Immich login page or API.
- `immich-share` (`manifests/app/server.py`) is the web page plus an expiry
  loop. To create a share it:
  1. creates an Immich shared link for the album, with the same `expiresAt`,
  2. creates a Tailscale `Ingress` in this namespace with
     `tailscale.com/funnel: "true"`, pointing at IPP.
- Each share has its own Ingress, and so its own funnel device and hostname.
  The Ingress is the only record of the share: its
  `immich-share.tylermarques.com/*` annotations hold the name, album, Immich
  link ID and expiry. No database is needed.
- Every 60 seconds the loop removes shares whose expiry has passed. It also
  removes shares whose Immich link was deleted in Immich itself. Deleting an
  Ingress makes the Tailscale operator delete the funnel proxy and its
  tailnet device.
- Immich itself also refuses the link after `expiresAt`, so access ends on
  time even if this service is down. The funnel is then removed on the
  first loop after the service starts again.

The funnel Ingresses are created by the service, not by Argo CD. They carry
`app.kubernetes.io/managed-by: immich-share` and no Argo CD tracking label,
so Argo CD neither prunes nor shows them. List them with:

```sh
kubectl --context k3s-homelab -n immich-share get ingress -l app.kubernetes.io/managed-by=immich-share
```

Expiries are limited to 30 days (`MAX_DAYS` in `manifests/share-manager.yaml`).

ArgoCD syncs `manifests/` through the `immich-share` Application in
`homecluster/app-of-apps/applications/`. Authelia limits
`share.local.tylermarques.com` to `group:admins`.

## One-time setup

### Tailnet policy

The funnel proxies are tagged `tag:k8s-funnel`. Only these devices get the
`funnel` attribute, so no other operator proxy can be put on the internet. In
the Tailscale admin console's access controls, add:

```jsonc
"tagOwners": {
  // The operator applies this tag to the proxies it creates.
  "tag:k8s-funnel": ["tag:k8s-operator"],
},
"nodeAttrs": [
  { "target": ["tag:k8s-funnel"], "attr": ["funnel"] },
],
```

Merge these into the existing `tagOwners` and `nodeAttrs` sections. The
tailnet also needs MagicDNS and HTTPS certificates turned on (DNS page of the
admin console).

### Immich API key

In Immich, open Account Settings → API Keys and create a key named
`immich-share` with these permissions: `album.read`, `sharedLink.create`,
`sharedLink.read` and `sharedLink.delete`. Shares are created as the user who
owns the key, so only that user's albums (and albums shared with them) can be
picked.

```sh
kubectl --context k3s-homelab create namespace immich-share  # if Argo CD has not created it yet
kubectl --context k3s-homelab -n immich-share create secret generic immich-share-api-key \
  --from-literal=api-key=<key>
```

After rotating the key, run
`kubectl --context k3s-homelab -n immich-share rollout restart deployment/immich-share`.

## Notes

- Hostnames of funnel devices appear in public certificate-transparency
  logs, so the share name (the `photos-<name>-<random>` part) is effectively
  public. The `/share/<key>` part is what grants access.
- IPP config is `manifests/ipp-config.json`, the v4.0.0 default with two
  changes: `allowDownload: 1` (follow each share's "Allow downloads" box) and
  `showHomePage: false`. IPP caches assets for 30 days in the visitor's
  browser, so someone who already opened a photo may still see it from their
  own cache after expiry.
- Link previews (for example in iMessage) may show no image. IPP builds the
  `og:image` URL from the request scheme, and the funnel forwards plain HTTP
  to it, so the URL starts with `http://`, which the funnel does not serve.
- Funnel traffic is relayed through Tailscale, so large videos can load slowly.
