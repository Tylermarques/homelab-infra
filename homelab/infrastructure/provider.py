import pulumi_proxmoxve as proxmoxve
from config.settings import proxmox_settings


def create_proxmox_provider() -> proxmoxve.Provider:
    """
    Create and configure the Proxmox VE provider.

    Authentication uses API token from environment variables.
    The token format should be: user@realm!token-id=secret
    """
    return proxmoxve.Provider(
        "proxmox-provider",
        endpoint=proxmox_settings.endpoint,
        username=proxmox_settings.username,
        password=proxmox_settings.password,
        insecure=proxmox_settings.insecure,
    )


# Singleton provider instance
proxmox_provider = create_proxmox_provider()
