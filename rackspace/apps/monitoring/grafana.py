import pulumi_kubernetes as k8s
from dotenv import dotenv_values
from pulumi_kubernetes import meta
from pulumi_kubernetes.core.v1 import ServiceSpecArgs

from apps.dns import ALLOWED_DOMAINS, create_cloudflare_A_record
from .namespace import namespace

from apps.volumes import create_nfs_pv_and_pvc
from apps.dns import create_traefik_ingress

env_config = dotenv_values(".env")

pv, pvc = create_nfs_pv_and_pvc(name="grafana", namespace=namespace.metadata.name, share_path="/main/plex/grafana")

chart = k8s.helm.v3.Chart(
    "grafana",
    k8s.helm.v3.ChartOpts(
        chart="grafana",
        version="v8.14.1",
        fetch_opts=k8s.helm.v3.FetchOpts(
            repo="https://grafana.github.io/helm-charts",
        ),
        namespace=namespace.metadata.name,
        values={
            "adminUser": "admin",
            "adminPassword": env_config["GRAFANA_PASSWORD"],
            "service": {"type": "ClusterIP"},
            "persistence": {
                "enabled": True,
                "existingClaim": pvc.metadata.name,
            },
            "datasources": {
                "datasources.yaml": {
                    "apiVersion": 1,
                    "datasources": [
                        {
                            "name": "Prometheus",
                            "type": "prometheus",
                            "url": "http://prometheus-server",
                            "access": "proxy",
                            "isDefault": True,
                        }
                    ],
                }
            },
            # ⇣ optional ingress / dashboards
            # ⇣ optional ingress / dashboards
        },
    ),
)

tailscale_service = k8s.core.v1.Service(
    "traefik-tailscale", metadata={"name": "traefik-tailscale"}, spec=ServiceSpecArgs(type="LoadBalancer", load_balancer_class="tailscale", ports=[{"name": "https", "port": 443}])
)

create_traefik_ingress(
    "grafana.local",
    ALLOWED_DOMAINS.TM,
    80,
    namespace=namespace.metadata.name,
    service_name="grafana",
    tailnet_only=True,
)
create_cloudflare_A_record("grafana.local", ALLOWED_DOMAINS.TM, proxied=False, ip="100.123.5.67")
