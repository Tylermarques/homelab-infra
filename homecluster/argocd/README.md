# Argo CD

Argo CD v2.11 was installed by hand from the upstream `install.yaml` into the
`argocd` namespace, and that install is not in Git. This directory holds only
its configuration and its route, applied by the `argocd-config` Application
(`homecluster/app-of-apps/applications/argocd-config.yaml`):

- `manifests/argocd-cm.yaml`: external URL and OIDC.
- `manifests/argocd-rbac-cm.yaml`: RBAC policy.
- `manifests/ingress.yaml`: the `argocd-server` IngressRoute for
  `argocd.local.tylermarques.com`, which also carries the annotations that
  list Argo CD on the Homepage dashboard.
- `manifests/certificate.yaml`: the TLS certificate for that route.

The Application does not prune, so nothing else in the namespace is touched.
The IngressRoute was hand-applied before it was added here; the Application
adopts it in place. Its old TLS Secret, `argocd-local-tylermarques-com`, is no
longer referenced and can be deleted once `argocd-local-tls` is issued.

## Single sign-on

Argo CD uses Authelia at `https://auth.local.tylermarques.com` as its OIDC
provider. The client definitions are in the Authelia Application; see
`homecluster/authelia/README.md`.

The client secret is not in Git. `argocd-cm` refers to it as
`$argocd-oidc:clientSecret`, which Argo CD resolves from the `argocd-oidc`
Secret in this namespace (it must carry the label
`app.kubernetes.io/part-of: argocd`). Create it, together with the digest that
Authelia stores, with:

```sh
homecluster/authelia/bootstrap-argocd-oidc-secrets.sh
```

The Authelia `admins` group maps to `role:admin`. There is no `policy.default`,
and Authelia refuses non-admins for these clients in the first place.

CLI login:

```sh
argocd login argocd.local.tylermarques.com --sso --grpc-web
```

## Recovery

The local `admin` account stays enabled as a fallback for when Authelia is
down. Its password is whatever was last set; the original is in
`argocd-initial-admin-secret` if it was never changed.
