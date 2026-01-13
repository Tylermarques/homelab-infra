from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
from pulumi_kubernetes.core.v1 import Namespace

from config.settings import tailscale_operator_settings

cluster_name = "Homelab"

namespace = Namespace("tailscale-operator-namespace", metadata={"name": "tailscale"})

tailscale_operator = Chart(
    "tailscale-operator",
    ChartOpts(
        chart="tailscale-operator",
        version="1.82.0",
        namespace=namespace.metadata["name"],
        fetch_opts=FetchOpts(repo="https://pkgs.tailscale.com/helmcharts"),
        values={
            "oauth": {
                "clientId": tailscale_operator_settings.client_id,
                "clientSecret": tailscale_operator_settings.client_secret,
            },
            "operator": {
                "hostnamePrefix": f"{cluster_name}-",
                "tags": [f"tag:cluster-{cluster_name}"],
            },
        },
    ),
)
