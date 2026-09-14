# Media server stack

Sonarr, Radarr, Lidarr, Prowlarr and SABnzbd in the `default` namespace, all
served from <https://media.local.tylermarques.com> under a path prefix per app
(`/sonarr`, `/radarr`, `/lidarr`, `/prowlarr`, `/sabnzbd`). Each app has its
URL base set to the same prefix, so Traefik forwards the path untouched.

Managed by the `k8s-mediaserver` ArgoCD Application in
`homecluster/app-of-apps/applications/mediaserver.yaml`.

## Where these manifests came from

These objects were created in 2023 by the `k8s-mediaserver` Helm release
(chart `k8s-mediaserver-0.7.0` from the kubealex/k8s-mediaserver-operator
repository, which used to be a git submodule of this repo). The manifests here
are the output of `helm get manifest k8s-mediaserver -n default` with three
changes:

- Helm bookkeeping labels removed (`helm.sh/chart`,
  `app.kubernetes.io/managed-by`, `app.kubernetes.io/version`).
- Homepage annotations and `ingressClassName: traefik` added to every Ingress.
  Lidarr's Ingress already had the class set by hand; the others now match it.
- Jackett dropped. Prowlarr replaced it.

The Deployment selector (`app.kubernetes.io/name` and
`app.kubernetes.io/instance`, both `k8s-mediaserver`) is identical across all
five Deployments and is immutable, so keep it as is. Pods are told apart by the
`app=<name>` label, which is what the Services and Homepage select on.

Because of that shared selector, `kubectl exec deploy/sonarr` (or any
`deploy/<name>`) resolves to an arbitrary pod from the whole stack, not the one
you named. Always pick the pod by label instead:

```sh
kubectl --context k3s-homelab -n default exec -it \
  "$(kubectl --context k3s-homelab -n default get pod -l app=sonarr -o name)" -- bash
```

Config, downloads and libraries live on the NFS export `192.168.0.71:/main/plex`
under `config/<app>` and `library/...`. The init container only seeds a config
file when none exists, so redeploying never overwrites app settings.

## Adoption and cleanup

The Helm release record is still stored in `default` as
`sh.helm.release.v1.k8s-mediaserver.v*` Secrets. Once ArgoCD reports the
Application Synced and Healthy, remove them so a stray `helm uninstall` cannot
delete the adopted objects:

```sh
kubectl --context k3s-homelab -n default delete secret \
  -l name=k8s-mediaserver,owner=helm
```

The Jackett Deployment, Services, ConfigMaps and Ingress are pruned by ArgoCD
on the first sync. Its config directory on NFS (`config/jackett`) is not
touched.

## Homepage

Each Ingress carries the Homepage annotations described in
`homecluster/homepage/README.md`. Because all five share one host, each sets an
explicit `gethomepage.dev/href` pointing at its path, and `pod-selector` is
`app=<name>` because the pods share every other label.

Widgets read each app's API over the cluster network
(`http://<app>.default.svc.cluster.local:<port>/<app>`). The API keys are
referenced as `{{HOMEPAGE_VAR_<APP>_KEY}}` and come from the
`homepage-widget-keys` Secret in the `homepage` namespace; see the Homepage
README for how to create it.

## Authentication

Every app Ingress is bound to `websecure` with the wildcard
`star-local-tylermarques-prod-tls` certificate and carries the Authelia
ForwardAuth middleware. `http-redirect.yaml` sends plain http to https.

Access is decided in the Authelia Application's `access_control` rules for
`media.local.tylermarques.com`: members of the `admins` group get in with one
factor, every other Authelia user is denied, and the API paths
(`/<app>/api`, `/<app>/feed`, `/sabnzbd/api`) bypass Authelia so API-key
clients keep working. None of these apps support OIDC, so this is the only
single-sign-on option they have.

Because Authelia is the gate, each *arr app runs with **Authentication
Method: External** (Settings > General > Security) and SABnzbd runs with its
web login disabled (`html_login = 0`). The API key is still required on API
paths in every app regardless of that setting. Never set External on an app
that is reachable by a route without the middleware.

## Known debts

- Images float on `latest` (`develop` for Prowlarr) with `imagePullPolicy:
  Always`, so any pod restart can upgrade an app.
- The init containers use `docker.io/ubuntu:groovy`, an EOL release.
