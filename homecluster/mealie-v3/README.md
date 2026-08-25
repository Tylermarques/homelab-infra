# Mealie v3 migration

This stack replaced the pre-v1 deployment in `default` on 2026-08-24. The v3
deployment owns `mealie.local.tylermarques.com`; the legacy deployments remain
scaled to zero during the observation period.

## Architecture

- Mealie `v3.23.1`, pinned to the linux/amd64 image digest
- one CloudNativePG PostgreSQL 17 instance on `local-path`
- a separate NFS volume for `/app/data`
- a dedicated certificate covering the staging and production local names

The legacy `mealie-claim` is not mounted or modified by this stack.

## Deploy

```sh
kubectl --context k3s-homelab apply -k homecluster/mealie-v3
kubectl --context k3s-homelab wait --for=condition=Ready cluster/mealie-db \
  -n mealie --timeout=5m
kubectl --context k3s-homelab rollout status deployment/mealie-v3 \
  -n mealie --timeout=5m
homecluster/mealie-v3/rotate-bootstrap-password.sh
```

The final command replaces Mealie's initial password with a random value stored
in the `mealie-v3-admin` Secret. Retrieve the credentials when needed:

```sh
kubectl --context k3s-homelab get secret mealie-v3-admin -n mealie \
  -o jsonpath='{.data.username}' | base64 -d
kubectl --context k3s-homelab get secret mealie-v3-admin -n mealie \
  -o jsonpath='{.data.password}' | base64 -d
```

## Rehearsal

1. Create a filesystem and SQLite backup of the legacy `/app/data` directory.
2. Use the legacy bulk recipe exporter for all recipe slugs. The admin site
   backup is not accepted by the v3 `mealie_alpha` migrator because it contains
   `database.json` instead of one JSON file per recipe.
3. Open `https://mealie-v3.local.tylermarques.com/group/migrations`.
4. Select the Mealie migration type and upload the bulk recipe export.
5. Review the report and compare every recipe slug with the legacy database.
6. Recreate users and unsupported records through the v3 API.
7. Check images, categories, tags, groups, meal plans, and shopping lists.

The migration assigns imported recipe ownership to the user that runs it. It
does not migrate users, group preferences, meal plans, shopping lists, or API
tokens. Legacy bcrypt hashes are compatible with v3, but verify compatibility
before transferring them.

### Rehearsal result

The 2026-08-24 rehearsal migrated:

- 19 of 19 recipe slugs
- all 16 recipes that have image directories
- three users with their existing bcrypt passwords and permissions
- the legacy household and group preferences
- one meal-plan entry
- one shopping list and its item

One recipe initially failed because its `Slow Cooker` tool had no group ID. A
single-recipe retry without that tool reference succeeded. Recreate the tool in
v3 if it is still wanted.

The bootstrap credential Secret was deleted after the legacy administrator
account replaced the bootstrap account. From then on, use the legacy Tyler
account and password.

## Backup gate

Do not retire the legacy instance until the PostgreSQL database has a tested,
off-host backup. Configure a CloudNativePG object-store backup to Garage or an
external S3-compatible target, run it once, and prove that it can create a new
temporary cluster. Proxmox ZFS snapshots are useful but are not off-host
protection because both the database VM disk and NFS data use that host.

## Final cutover

1. Log in to staging with the legacy Tyler email and password. Verify several
   recipes, their images, the meal plan, and the `Weekly` shopping list.
2. Stop writes and create a final legacy filesystem and SQLite backup.
3. If the legacy database changed after the rehearsal export, repeat the bulk
   recipe export and reconcile those changes before continuing.
4. Scale the legacy `mealie-api` and `mealie-frontend` deployments to zero.
5. Change `BASE_URL` and both Ingress hosts from `mealie-v3.local...` to
   `mealie.local...`.
6. Remove the legacy `mealie-ingress` and `mealie-http-redirect` routes before
   applying the v3 routes, so Traefik never has duplicate host rules.
7. Validate login, recipes, images, PostgreSQL health, TLS, and HTTP redirect.

## Rollback

Before new writes occur in v3, restore the legacy routes and scale its two
deployments back to one replica. Do not delete `mealie-claim` during the
observation period. After users write data to v3, rollback is not lossless;
preserve a v3 backup and fix forward instead.

The legacy, v3 application-data, and PostgreSQL PVs were changed to `Retain` at
cutover. After 7-14 days, remove the old workloads but keep the final migration
archive. Upgrade v3.23.1 to v3.24.0 as a separate tested change.
