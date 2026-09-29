# slskd

[slskd](https://github.com/slskd/slskd) is a Soulseek client with a web UI. It
runs in the `default` namespace at `https://slskd.local.tylermarques.com` and is
the Soulseek download client for DroppedNeedle.

## Storage

Everything is on the retained `/main/plex/library` NFS export, through
slskd's own `slskd-media` volume (a PersistentVolume binds to one claim only,
so it cannot reuse DroppedNeedle's). Nothing is node-local, so the pod can run
on any node.

- `/app` is `/data/slskd/app`: logs and slskd's SQLite databases. The
  transfers database is what the per-user upload limits are counted from.
- Completed downloads go to `/data/downloads/slskd`, the path DroppedNeedle
  already reads (`SLSKD_DOWNLOADS_PATH`). Partial files go to
  `/data/downloads/slskd-incomplete`.
- `/data/music` is mounted read-only at `/music` and shared to the Soulseek
  network. Many peers refuse users with no shares.

The PersistentVolume and claim carry `Prune=false,Delete=false`, and the
volume uses the `Retain` reclaim policy.

slskd forces SQLite WAL mode, which SQLite does not support on network
filesystems, and this NFS service has already failed to checkpoint a WAL file
for DroppedNeedle. If slskd logs database errors, stop the pod and delete
`/data/slskd/app/data`. That loses transfer, search and message history and
resets the weekly upload counts; all configuration is in Git and the Secret.

## Configuration

Settings live in `manifests/slskd.yml`, mounted read-only at
`/config/slskd.yml` through a generated ConfigMap, so a change rolls the pod.
Directories and HTTPS are set by environment variables in the Deployment, and
credentials by the Secret. slskd loads the YAML after the environment, so
credentials must never go in the YAML.

Upload limits:

| Who | Priority | Slots | Speed | Per-user queue | Per-user daily | Per-user weekly |
| --- | --- | --- | --- | --- | --- | --- |
| Everyone (global cap) | | 10 | 2500 KiB/s | | | |
| Users who share files | 1 | up to 10 | up to 2500 KiB/s | 150 files / 1.5 GB | none | 1500 files / 15 GB, 150 failures |
| Leechers (no shares) | 99 | 1 | 100 KiB/s | 15 files / 150 MB | 30 files / 300 MB, 10 failures | 150 files / 1.5 GB, 30 failures |

Users with Soulseek privileges bypass the per-user limits but not the global
caps. The global speed cap is 2500 KiB/s, about 20 Mbit/s. Uploads must never
exceed 10% of the 3.5 Gbit/s uplink (about 42000 KiB/s). Downloads are not
capped.

## Secret

Credentials are deliberately not in git. Create the Secret by hand before the
first sync; the Deployment reads every key as an environment variable:

```sh
kubectl --context k3s-homelab create secret generic slskd-credentials \
  -n default \
  --from-literal=SLSKD_SLSK_USERNAME='<soulseek username>' \
  --from-literal=SLSKD_SLSK_PASSWORD='<soulseek password>' \
  --from-literal=SLSKD_USERNAME='<web ui username>' \
  --from-literal=SLSKD_PASSWORD='<web ui password>' \
  --from-literal=SLSKD_API_KEY="$(openssl rand -hex 32)" \
  --from-literal=SLSKD_JWT_KEY="$(openssl rand -hex 32)"
```

- The Soulseek account is created on first login if the username is free, so
  pick a unique name. Without these two keys slskd starts but never connects.
- Without the web credentials slskd falls back to `slskd` / `slskd`.
- `SLSKD_API_KEY` is the Administrator key DroppedNeedle uses.
- A fixed `SLSKD_JWT_KEY` keeps web sessions valid across restarts.

The Secret carries no ArgoCD tracking label, so `prune` leaves it alone. Rotate
by replacing it and restarting the Deployment.

## Incoming connections

Port 50300 is not forwarded from the internet, so slskd runs firewalled. Peers
with an open port can still download from us, because the Soulseek server asks
slskd to connect out to them instead. Transfers with other firewalled peers
fail in both directions. To remove that limit, add a LoadBalancer Service for
the `soulseek` container port and forward TCP 50300 on the router to the node
that runs the pod.

## Deploy

The `homecluster-apps` root Application picks up
`homecluster/app-of-apps/applications/slskd.yaml`, which syncs `manifests/`.
Create the Secret, then push to `main`; nothing is applied by hand.

```sh
kubectl --context k3s-homelab -n argocd get application slskd
kubectl --context k3s-homelab rollout status deployment/slskd --timeout=10m
```

## Connect DroppedNeedle

In DroppedNeedle's download client settings, add slskd with URL
`http://slskd:5030`, the `SLSKD_API_KEY` value from the Secret, and downloads
path `/data/downloads/slskd`.

## Validation

```sh
kubectl kustomize homecluster/slskd/manifests
kubectl apply --dry-run=server -k homecluster/slskd/manifests
```
