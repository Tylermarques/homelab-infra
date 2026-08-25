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
