# Paperless-ngx

Paperless-ngx is available at <https://paperless.local.tylermarques.com>.

## Authelia OIDC

Create the matching OIDC secrets before deploying the updated Authelia and
Paperless manifests:

```sh
homecluster/authelia/bootstrap-paperless-oidc-secrets.sh
```

The script is idempotent and refuses to rotate or replace an existing client
credential. Authelia stores only the client-secret digest. Paperless stores the
provider configuration and matching plaintext client secret in a Kubernetes
Secret. Neither credential is stored in Git.

The callback URI is:

```text
https://paperless.local.tylermarques.com/accounts/oidc/authelia/login/callback/
```

Paperless trusts Authelia's verified email claim to connect an OIDC identity to
an existing local account with the same email. Confirm that the Paperless and
Authelia account email addresses match before the first OIDC login. Local
username and password login remains enabled as a recovery path.
