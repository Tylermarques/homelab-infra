from .tailscale import deploy_tailscale
from .syncthing import deploy_syncthing


def deploy_all_apps(k8s_provider):
    """Deploy all applications to the cluster using the provided Kubernetes provider."""
    tailscale_resources = deploy_tailscale(k8s_provider)
    syncthing_resources = deploy_syncthing(k8s_provider)
    return {
        "tailscale": tailscale_resources,
        "syncthing": syncthing_resources,
    }
