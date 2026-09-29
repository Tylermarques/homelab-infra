# DroppedNeedle

DroppedNeedle runs in the `default` namespace at
`https://droppedneedle.local.tylermarques.com`.

## Storage

- `/app/config` and `/app/cache` use the `droppedneedle-state` local-path claim.
  DroppedNeedle forces SQLite WAL mode, which is not safe on this NFS service.
- `/data` uses the retained `/main/plex/library` NFS volume.
- The music library is `/data/music`.
- SABnzbd completed downloads are `/data/downloads/completed`.
- `/app/imports` is backed by `/data/droppedneedle/imports` for purchase uploads
  and files that wait for a manual match.
- Plug-ins are in `/data/droppedneedle/plugins`.
- Verified state backups are in `/data/droppedneedle/backups`.

The `homecluster-apps` root Application picks up
`homecluster/app-of-apps/applications/droppedneedle.yaml`, which syncs
`manifests/`. Push to `main` to deploy; nothing is applied by hand.

The PersistentVolume and both claims in `manifests/persistence.yaml` carry
`Prune=false,Delete=false`. ArgoCD creates them but never removes them, and the
NFS volume uses the `Retain` reclaim policy.

## First Run

1. Wait until the `droppedneedle` Application is `Synced` and `Healthy`.
2. Open `https://droppedneedle.local.tylermarques.com` and create the first
   administrator.
3. Set the library path to `/data/music`.
4. Configure SABnzbd with URL `http://sabnzbd:8080/sabnzbd`, its full API key,
   and downloads mount
   `/data/downloads/completed`.
5. Do not use SABnzbd's add-only NZB key. DroppedNeedle needs the full key for
   queue, history, and delete operations.
6. Add the existing Prowlarr indexers as Newznab sources. Keep all API keys in
   the DroppedNeedle UI, not in Git.
7. Run a library scan before any download request.

## Lidarr Cutover

1. Import the current Lidarr configuration from `http://lidarr:8686`.
2. Compare DroppedNeedle album and track counts with Lidarr.
3. Test one controlled download and confirm that SABnzbd writes it under
   `/data/downloads/completed` and DroppedNeedle moves it into `/data/music`.
4. Disable Lidarr monitoring and imports. Do not let both applications manage
   the library at the same time.
5. Observe DroppedNeedle for one week.
6. Disable Lidarr in the `k8s-mediaserver` Helm release with
   `lidarr.enabled=false`.

## Backup Check

The backup CronJob runs at 03:17 America/Toronto. It uses SQLite's online backup
API and verifies the result before it publishes a snapshot. It keeps 14 recent
snapshots and up to 8 older weekly snapshots.

Run and inspect an initial backup after first-run setup:

```sh
kubectl create job --from=cronjob/droppedneedle-backup droppedneedle-backup-test
kubectl logs job/droppedneedle-backup-test
kubectl delete job droppedneedle-backup-test
```

Perform a restore test before DroppedNeedle becomes the authoritative library
manager. Restore `library.db` and the `config/` directory from one snapshot into
an unused claim, start a temporary pod, and confirm `PRAGMA integrity_check`
returns `ok`.

## Validation

```sh
kubectl kustomize homecluster/droppedneedle/manifests
kubectl apply --dry-run=server -f homecluster/droppedneedle/persistence.yaml
kubectl apply --dry-run=server -k homecluster/droppedneedle/manifests
```

After deployment, confirm that `/data/music`, `/data/downloads/completed`, and
`/data/droppedneedle/imports` report the same filesystem device. Confirm that
`/app/cache` is local storage and `PRAGMA journal_mode` reports `wal`.

## Rollback

1. Scale DroppedNeedle to zero.
2. Re-enable Lidarr and rescan `/music`.
3. Leave imported music files in place; both applications use normal media
   files and directory layouts.
4. Restore DroppedNeedle state from the latest verified NFS snapshot if needed.
