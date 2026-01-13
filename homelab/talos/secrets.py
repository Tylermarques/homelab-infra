import pulumiverse_talos as talos
from config.settings import cluster_settings


def generate_machine_secrets() -> talos.machine.Secrets:
    """
    Generate Talos machine secrets for the cluster.

    These secrets include:
    - PKI certificates for etcd, Kubernetes, and Talos OS
    - Bootstrap token for cluster initialization
    - Encryption keys for secrets at rest

    The secrets are generated once and reused across all node configurations.
    """
    secrets = talos.machine.Secrets(
        "talos-secrets",
        talos_version=cluster_settings.talos_version,
    )

    return secrets


# Singleton secrets instance - reused across all configurations
machine_secrets = generate_machine_secrets()
