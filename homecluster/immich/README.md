# Immich

## Deployment

- Immich server and machine learning: `v3.1.0`
- Helm chart: `0.13.1` from the signed OCI registry
- PostgreSQL: `15.18` with pgvector `0.8.0` and VectorChord `1.1.1`
- Queue: persistent Valkey `9.1`
- Media: `immich-library`, a retained 250 GiB NFS PVC mounted at `/data`
- Upload folder: `immich-uploads`, a static read-only NFS PV for
  `192.168.0.71:/main/plex/immich-uploads`, mounted at `/mnt/immich-uploads`
- Database: `immich-db-1`, a retained 10 GiB local PVC on `k3s-worker-4`

Deploy the application with:

```sh
helm upgrade --install immich \
  oci://ghcr.io/immich-app/immich-charts/immich \
  --version 0.13.1 \
  --namespace immich \
  --values homecluster/immich/values.yaml \
  --wait
```

Apply `storage.yaml` before the Helm upgrade, because the server needs the
`immich-uploads` PVC.

## Upload folder

Copy photos from a computer or camera into `/main/plex/immich-uploads` on the
Proxmox NFS export. From a Mac, connect to `smb://192.168.0.71/immich-uploads`.
The `[immich-uploads]` Samba share is defined in `/etc/samba/smb.conf` on the
Proxmox host, not in this repository. Immich reads this folder as the External Library
"Immich uploads", with the import path `/mnt/immich-uploads`. The mount is read-only: Immich does not
move or delete these files, and deleting an asset in Immich does not remove
the file.

Immich cannot see NFS writes from other machines through file watching. A
periodic library scan imports new files. The scan runs every 15 minutes
(`*/15 * * * *`, set in Administration > Settings > External Library).

`immich-cluster` is the pre-migration PostgreSQL cluster on the retained mixed
NFS volume. Keep it and its PV until a v3 restore test and observation period
are complete. Do not point Immich back to it without also restoring a matching
pre-VectorChord application and database state.

## Database credentials

The Immich deployment reads `DB_USERNAME` and `DB_PASSWORD` from
`secret/immich-postgres-userpass`. CloudNativePG also uses this Secret for the
managed `immich` role. Create it before applying `postgres.yaml`; never put the
password in Helm values.

For an existing cluster, do not replace or rotate this Secret without changing
the PostgreSQL role password in the same operation.

## Authelia OIDC

Run the idempotent bootstrap before deploying the Authelia client:

```sh
homecluster/immich/bootstrap-oidc.sh
```

The script creates a confidential client credential, stores its digest in
`secret/authelia-oidc`, and stores the matching plaintext only in Immich's
database-backed system configuration. Password login stays enabled. Automatic
OIDC registration stays disabled, so an existing Immich user must have the same
email address as the Authelia account.

Registered callbacks:

```text
https://immich.local.tylermarques.com/auth/login
https://immich.local.tylermarques.com/user-settings
app.immich:///oauth-callback
```

## Recovery points

Database dumps are stored under `/main/plex/backups` on the Proxmox ZFS pool:

- `immich-v1.119.0-pre-migration.dump`
- `immich-v1.132.3-pre-vectorchord.dump`
- `immich-v1.133.1-post-vectorchord.dump`
- `immich-v1.144.1-pre-v2.dump`
- `immich-v2.7.5-pre-v3.dump`
- `immich-v3.1.0-final.dump`

Matched filesystem snapshots are `main/plex@pre-immich-v3-migration-20260902`,
`main/plex@immich-storage-cutover-20260902`, and
`main/plex@immich-v3.1.0-final-20260902`.
