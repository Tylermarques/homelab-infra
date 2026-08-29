# Authelia

Authelia is the home cluster's central authentication portal and Traefik
ForwardAuth provider. It is available only on the LAN or tailnet at
`https://auth.local.tylermarques.com`.

## Deployment

The app-of-apps parent is `homecluster/app-of-apps/root.yaml`. It discovers the
child Application in `homecluster/app-of-apps/applications/` after these files
are committed and pushed to `main`.

Secrets are deliberately not stored in Git. Bootstrap them once before syncing
the child Application:

```sh
homecluster/authelia/bootstrap-secrets.sh
kubectl --context k3s-homelab apply \
  -f homecluster/app-of-apps/applications/authelia.yaml
```

Retrieve the initial login without printing it in repository files:

```sh
kubectl --context k3s-homelab get secret authelia-bootstrap-credentials \
  -n authelia -o jsonpath='{.data.username}' | base64 -d
kubectl --context k3s-homelab get secret authelia-bootstrap-credentials \
  -n authelia -o jsonpath='{.data.password}' | base64 -d
```

The bootstrap script refuses to overwrite `authelia-secrets` because rotating
the storage encryption key makes stored TOTP and WebAuthn credentials unusable.

## Mealie OIDC

Create the separate Authelia and Mealie OIDC secrets before applying the
updated applications:

```sh
homecluster/authelia/bootstrap-oidc-secrets.sh
```

The script is idempotent. It does not modify `authelia-secrets`, and it refuses
to replace an existing OIDC secret or rotate a client credential. Authelia
stores only the client-secret digest. Mealie stores the matching plaintext in
its namespace. Neither value is stored in Git.

Mealie uses its native OIDC support. Do not add the Authelia ForwardAuth
middleware to the Mealie ingress because that would cause two authentication
flows. The Mealie login form remains available as a fallback.

## Home Assistant OIDC

Home Assistant uses the `hass-oidc-auth` HACS integration and a public PKCE
client. No client secret is required. Its callback is:

```text
https://hass.local.tylermarques.com/auth/oidc/callback
```

The integration maps the Authelia `admins` group to Home Assistant
administrators and `users` to regular users. Keep Home Assistant's local login
available as a recovery path.

## User management

Authelia is not a user directory and has no admin user-management UI for the
current file authentication backend. The `authelia-users` Secret contains the
complete user database, so do not replace it with a single-user file when you
add or update an account. Generate password hashes without printing passwords,
merge the change into the full database, and retain a backup before applying
the Secret.

Use LLDAP as the preferred future authentication backend if administrators
need a web UI for users, groups, and password changes. Authelia can then use
LDAP for authentication while it continues to provide OIDC and ForwardAuth.

## Protecting services

For a Traefik `IngressRoute`, add this middleware:

```yaml
middlewares:
  - name: authelia-forwardauth
    namespace: authelia
```

For a standard `Ingress`, add this annotation:

```yaml
traefik.ingress.kubernetes.io/router.middlewares: authelia-authelia-forwardauth@kubernetescrd
```

The initial access policy is one-factor authentication for
`*.local.tylermarques.com`. Enroll TOTP or WebAuthn before changing protected
applications to a two-factor policy.

## Storage

CloudNativePG stores durable authentication state in PostgreSQL on a 10 GiB
`local-path` PVC. A dedicated password-protected Redis holds sessions. The chart
uses a separate 1 GiB `local-path` PVC for filesystem notifications and other
configuration state. All components are pinned to `k3s-worker-1`.

Back up PostgreSQL and the Authelia PVC before changing the storage encryption
key or moving the workload to another node. Both live PersistentVolumes use the
`Retain` reclaim policy.
