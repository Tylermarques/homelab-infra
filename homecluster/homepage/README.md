# Homepage

Homepage is the service catalog for the home cluster. It discovers opted-in
Kubernetes `Ingress` and Traefik `IngressRoute` resources and is available at
<https://home.local.tylermarques.com>.

## Publish a service

Add these annotations to the user-facing HTTPS route:

```yaml
metadata:
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: Example
    gethomepage.dev/group: Tools
    gethomepage.dev/icon: example.png
```

For a Traefik `IngressRoute`, also set the full URL because Homepage cannot
reliably derive it from a Traefik match expression:

```yaml
    gethomepage.dev/href: https://example.local.tylermarques.com
```

Also set `href` on a plain `Ingress` that has no `spec.tls` block (Homepage
would otherwise build an `http://` link) or that shares its host with other
apps under path prefixes, as the media stack does:

```yaml
    gethomepage.dev/href: https://media.local.tylermarques.com/sonarr
```

If the route's pods are not the only pods matching the app's default selector,
add `gethomepage.dev/pod-selector` so the status dot tracks the right pods.

Do not annotate HTTP redirect routes, TCP routes, backend-only APIs, or storage
endpoints. Removing `gethomepage.dev/enabled` removes the service from the
dashboard without a Homepage deployment change.

## Widgets

Service widgets are declared on the same route with `widget.*` annotations.
Credentials must never appear in the annotation itself. Reference an
environment variable instead; Homepage substitutes `{{HOMEPAGE_VAR_<NAME>}}`
in annotation values at discovery time:

```yaml
    gethomepage.dev/widget.type: sonarr
    gethomepage.dev/widget.url: http://sonarr.default.svc.cluster.local:8989/sonarr
    gethomepage.dev/widget.key: "{{HOMEPAGE_VAR_SONARR_KEY}}"
```

Use the in-cluster Service URL, including the app's URL base if it has one, so
widgets do not depend on LAN DNS or TLS.

The variables come from the `homepage-widget-keys` Secret in the `homepage`
namespace, which `deployment.yaml` loads with `envFrom`. Each Secret key must
be the full variable name. The Secret is created by hand and never committed.
Find the keys under Settings > General in Sonarr, Radarr, Lidarr and Prowlarr,
and under Config > General in SABnzbd, then:

```sh
kubectl --context k3s-homelab -n homepage create secret generic homepage-widget-keys \
  --from-literal=HOMEPAGE_VAR_SONARR_KEY=... \
  --from-literal=HOMEPAGE_VAR_RADARR_KEY=... \
  --from-literal=HOMEPAGE_VAR_LIDARR_KEY=... \
  --from-literal=HOMEPAGE_VAR_PROWLARR_KEY=... \
  --from-literal=HOMEPAGE_VAR_SABNZBD_KEY=...
kubectl --context k3s-homelab -n homepage rollout restart deployment/homepage
```

The restart is required because `envFrom` is read at container start. The
Secret is marked optional, so Homepage runs without it; the widgets just show
an error until it exists. To add or rotate a key, edit the Secret and restart
the Deployment again.
