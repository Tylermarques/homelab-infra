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

Do not annotate HTTP redirect routes, TCP routes, backend-only APIs, or storage
endpoints. Removing `gethomepage.dev/enabled` removes the service from the
dashboard without a Homepage deployment change.

Widget credentials must not be stored in route annotations. Store them in a
Kubernetes Secret and add the widget through Homepage configuration instead.
