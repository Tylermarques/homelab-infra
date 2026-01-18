from pulumi import ResourceOptions
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
from pulumi_kubernetes.core.v1 import Namespace

from config.settings import tailscale_operator_settings

CLUSTER_NAME = "Homelab"


def deploy_tailscale(k8s_provider):
    """Deploy Tailscale operator to the cluster."""
    opts = ResourceOptions(provider=k8s_provider)

    namespace = Namespace(
        "tailscale-operator-namespace",
        metadata={"name": "tailscale"},
        opts=opts,
    )

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
                    "hostnamePrefix": f"{CLUSTER_NAME}-",
                    "tags": [f"tag:cluster-{CLUSTER_NAME}"],
                },
            },
        ),
        opts=opts,
    )

    return {
        "namespace": namespace,
        "operator": tailscale_operator,
    }
