# Immich sharing

`https://share.local.tylermarques.com` publishes an Immich album to the
internet for a limited time. You give the share a name, an album and an expiry
date. The page then shows a public link,
`https://share.taildff07.ts.net/share/<key>`, that anyone can open without
being on the tailnet. When the expiry passes, the service deletes the Immich
shared link. The page also has a "Revoke now" button.

## How it works

- `immich-public-proxy` (IPP) serves only shared-link pages and their
  assets. Visitors never reach the Immich login page or API.
- `share-funnel` (`manifests/funnel-ingress.yaml`) is a Tailscale Ingress in
  front of IPP. It is a single permanent tailnet device, `share`, so the
  hostname and its HTTPS certificate stay the same from share to share.
- `immich-share` (`manifests/app/server.py`) is the web page plus a loop that
  runs every 60 seconds:
  - Creating a share creates an Immich shared link with that `expiresAt` and
    records the share in the `immich-share-state` ConfigMap.
  - The loop deletes the Immich link of each share whose expiry has passed,
    or whose link was deleted in Immich itself, and drops its record.
  - Funnel follows the share list. The service sets
    `tailscale.com/funnel: "true"` on `share-funnel` while at least one share
    is active and removes it once none are. With Funnel off, the device is
    reachable only from the tailnet and the name does not resolve publicly.
- Immich itself also refuses a link after `expiresAt`, so each share ends on
  time even if this service is down. The funnel is then switched off on the
  first loop after the service starts again.
- While shares overlap, Funnel stays on until the last one ends. Expired
  links on the same host still fail, because Immich refuses them.

Argo CD does not manage the funnel annotation. The immich-share Application
ignores it (`ignoreDifferences` + `RespectIgnoreDifferences`), so a sync never
switches Funnel on or off. `immich-share-state` is created by the service and
has no Argo CD tracking label, so Argo CD neither prunes nor resets it. To see
the share list:

```sh
kubectl --context k3s-homelab -n immich-share get configmap immich-share-state -o yaml
```

Expiries are limited to 30 days (`MAX_DAYS` in `manifests/share-manager.yaml`).

ArgoCD syncs `manifests/` through the `immich-share` Application in
`homecluster/app-of-apps/applications/`. Authelia limits
`share.local.tylermarques.com` to `group:admins`.

## One-time setup

### Tailnet policy

The funnel device is tagged `tag:k8s-funnel`. Only this tag gets the
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

- Funnel needs the Tailscale operator at 1.80 or later. The hand-installed
  v1.76.6 proxies never got a public DNS record: those clients cannot send
  `Hostinfo.IngressEnabled`, which newer control servers appear to require.
- After Funnel turns on, the public DNS record can take a minute or two to
  appear. A visitor who looks the name up before that may have the
  "not found" answer cached for up to 5 minutes.
- IPP config is `manifests/ipp-config.json`, the v4.0.0 default with two
  changes: `allowDownload: 1` (follow each share's "Allow downloads" box) and
  `showHomePage: false`. IPP caches assets for 30 days in the visitor's
  browser, so someone who already opened a photo may still see it from their
  own cache after expiry.
- `PUBLIC_BASE_URL` is set on IPP so link previews (`og:image`) use the
  public `https://` address. Without it IPP builds an `http://` URL, because
  the funnel forwards plain HTTP to it.
- Funnel traffic is relayed through Tailscale, so large videos can load slowly.
