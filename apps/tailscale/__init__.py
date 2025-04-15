import os
from dotenv import dotenv_values
import pulumi
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
from pulumi_kubernetes.core.v1 import Namespace


env_config = dotenv_values(".env")

cluster_name = "Rackspace"

current_dir = os.path.dirname(os.path.abspath(__file__))
namespace = Namespace(
    "tailscale-operator-namespace",
    metadata={"name": "tailscale"},
)
tailscale_operator = Chart(
    "tailscale-operator",
    ChartOpts(
        chart="tailscale-operator",
        version="1.82.0",  # Change this to the correct version if needed
        namespace=namespace.metadata["name"],
        fetch_opts=FetchOpts(
            repo="https://pkgs.tailscale.com/helmcharts",
        ),
        values={
            "oauth": {
                "clientId": env_config["TAILSCALE_OPERATOR_CLIENT_ID"],
                "clientSecret": env_config["TAILSCALE_OPERATOR_CLIENT_SECRET"],
            },
            # Configure operator to use cluster-specific naming
            "operator": {
                # Prefix all Tailscale resources with the cluster name
                "hostnamePrefix": f"{cluster_name}-",
                # Add cluster-specific tags to all Tailscale resources
                "tags": [f"tag:cluster-{cluster_name}"],
            },
        },
    ),
)


pulumi.export("tailscale_namespace", namespace.metadata["name"])
pulumi.export("tailscale_cluster_name", cluster_name)
