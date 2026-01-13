import pulumi
import pulumi_proxmoxve as proxmoxve
from config.settings import proxmox_settings, cluster_settings
from infrastructure.provider import proxmox_provider

# Talos Image Factory schematic configuration
# This schematic includes the following extensions:
#   - siderolabs/qemu-guest-agent (for Proxmox VM lifecycle management)
#   - siderolabs/tailscale (for Tailscale VPN networking)
#
# To regenerate this schematic ID, create a file 'schematic.yaml' with:
#   customization:
#     systemExtensions:
#       officialExtensions:
#         - siderolabs/qemu-guest-agent
#         - siderolabs/tailscale
#
# Then run:
#   curl -X POST --data-binary @schematic.yaml https://factory.talos.dev/schematics
#
# The response will contain the new schematic ID.
#
# See: https://factory.talos.dev

# Schematic ID for qemu-guest-agent + tailscale extensions
# Generated from the Image Factory with the above configuration
TALOS_SCHEMATIC_ID = "7d4c31cbd96db9f90c874990697c523482b2bae27fb4631d5583dcd9c281b1ff"


def get_talos_iso_url(version: str, schematic_id: str = TALOS_SCHEMATIC_ID) -> str:
    """
    Generate the Talos Image Factory URL for downloading an ISO.

    Args:
        version: Talos version (e.g., "v1.9.0")
        schematic_id: Image Factory schematic ID

    Returns:
        URL to download the ISO
    """
    return f"https://factory.talos.dev/image/{schematic_id}/{version}/metal-amd64.iso"


def get_talos_installer_image(version: str, schematic_id: str = TALOS_SCHEMATIC_ID) -> str:
    """
    Get the Talos installer image reference for machine configuration.

    Args:
        version: Talos version (e.g., "v1.9.0")
        schematic_id: Image Factory schematic ID

    Returns:
        Installer image reference
    """
    return f"factory.talos.dev/installer/{schematic_id}:{version}"


def download_talos_iso() -> proxmoxve.download.File:
    """
    Download Talos Linux ISO to Proxmox storage.

    Uses the Talos Image Factory to get an ISO with:
    - QEMU guest agent extension (required for Proxmox VM management)
    - Tailscale extension (for VPN networking)
    """
    version = cluster_settings.talos_version
    iso_url = get_talos_iso_url(version)

    talos_iso = proxmoxve.download.File(
        "talos-iso",
        content_type="iso",
        datastore_id="local",
        node_name=proxmox_settings.node_name,
        url=iso_url,
        file_name=f"talos-{version}-amd64.iso",
        overwrite=False,
        upload_timeout=600,
        verify=True,
        opts=pulumi.ResourceOptions(provider=proxmox_provider),
    )

    return talos_iso


# Export the ISO resource
talos_iso = download_talos_iso()
