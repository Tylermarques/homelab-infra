# Immich

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
