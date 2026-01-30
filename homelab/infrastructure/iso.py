from functools import lru_cache
from pathlib import Path

import httpx
import pulumi
import pulumi_proxmoxve as proxmoxve
from config.settings import proxmox_settings, cluster_settings
from infrastructure.provider import proxmox_provider

# Talos Image Factory API endpoint
TALOS_FACTORY_API = "https://factory.talos.dev/schematics"

# Path to the schematic.yaml file
SCHEMATIC_FILE = Path(__file__).parent / "schematic.yaml"


@lru_cache(maxsize=1)
def get_schematic_id() -> str:
    """
    Get the schematic ID from the Talos Image Factory.

    Reads the local schematic.yaml file and POSTs it to the Image Factory API
    to get the corresponding schematic ID. The result is cached for the
    duration of the Pulumi run.

    Returns:
        The schematic ID string from the Image Factory

    Raises:
        FileNotFoundError: If schematic.yaml doesn't exist
        httpx.HTTPError: If the API request fails
    """
    schematic_content = SCHEMATIC_FILE.read_bytes()

    response = httpx.post(
        TALOS_FACTORY_API,
        content=schematic_content,
        headers={"Content-Type": "application/yaml"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["id"]


def get_talos_iso_url(version: str) -> str:
    """
    Generate the Talos Image Factory URL for downloading an ISO.

    Args:
        version: Talos version (e.g., "v1.9.0")

    Returns:
        URL to download the ISO
    """
    schematic_id = get_schematic_id()
    return f"https://factory.talos.dev/image/{schematic_id}/{version}/nocloud-amd64.iso"


def get_talos_installer_image(version: str) -> str:
    """
    Get the Talos installer image reference for machine configuration.

    Args:
        version: Talos version (e.g., "v1.9.0")

    Returns:
        Installer image reference
    """
    schematic_id = get_schematic_id()
    return f"factory.talos.dev/installer/{schematic_id}:{version}"


def download_talos_iso() -> proxmoxve.download.File:
    """
    Download Talos Linux ISO to Proxmox storage.

    Uses the Talos Image Factory to get an ISO with extensions defined
    in schematic.yaml (qemu-guest-agent, nfs-utils).
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
