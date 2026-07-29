from pulumi import ResourceOptions
from pulumi_kubernetes.apiextensions import CustomResource
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
from pulumi_kubernetes.core.v1 import Namespace

from config.settings import cluster_settings, tailscale_operator_settings

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

    # Subnet router: lets tailnet clients reach LAN IPs, e.g. the records under
    # *.local.tylermarques.com that point at Traefik's LAN address. The
    # advertised route must be approved in the Tailscale admin console (or
    # auto-approved via an ACL autoApprovers rule for this tag).
    subnet_router = CustomResource(
        "tailscale-subnet-router",
        api_version="tailscale.com/v1alpha1",
        kind="Connector",
        metadata={"name": "home-lan"},
        spec={
            "hostname": f"{CLUSTER_NAME}-subnet-router",
            "subnetRouter": {
                "advertiseRoutes": [cluster_settings.lan_subnet],
            },
            "tags": [f"tag:cluster-{CLUSTER_NAME}"],
        },
        opts=ResourceOptions(provider=k8s_provider, depends_on=[tailscale_operator]),
    )

    return {
        "namespace": namespace,
        "operator": tailscale_operator,
        "subnet_router": subnet_router,
    }
