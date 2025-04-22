import pulumi
import pulumi_kubernetes as k8s
from dotenv import dotenv_values
from .namespace import namespace

from apps.volumes import create_nfs_pv_and_pvc

env_config = dotenv_values(".env")

nfs_storage = create_nfs_pv_and_pvc(
    name="grafana", namespace=namespace.metadata.name, share_path="/main/plex/grafana"
)

chart = k8s.helm.v3.Chart(
    "grafana",
    k8s.helm.v3.ChartOpts(
        chart="grafana",
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
                "existingClaim": nfs_storage["pvc"].metadata.name,
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
