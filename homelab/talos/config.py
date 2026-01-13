import json
import pulumi
import pulumiverse_talos as talos
from config.settings import cluster_settings, tailscale_settings
from config.nodes import NodeSpec, CONTROL_PLANE_NODES
from talos.secrets import machine_secrets
from infrastructure.iso import get_talos_installer_image


def get_base_config_patches(node: NodeSpec) -> list[str]:
    """
    Generate base config patches applied to all nodes.

    Includes:
    - Install disk configuration
    - Hostname
    - DHCP networking (default)
    """
    patches = [
        # Install disk and installer image configuration
        json.dumps({
            "machine": {
                "install": {
                    "disk": "/dev/sda",
                    "image": get_talos_installer_image(cluster_settings.talos_version),
                    "bootloader": True,
                    "wipe": False,
                },
            },
        }),
        # Set hostname
        json.dumps({
            "machine": {
                "network": {
                    "hostname": node.name,
                },
            },
        }),
    ]

    return patches


def get_tailscale_config_patch(node: NodeSpec) -> str:
    """
    Generate Tailscale extension configuration patch.

    Configures the Tailscale extension to authenticate to the Tailnet
    using the provided auth key.
    """
    return json.dumps({
        "machine": {
            "files": [
                {
                    "content": f"""apiVersion: v1alpha1
kind: ExtensionServiceConfig
name: tailscale
environment:
  - TS_AUTHKEY={tailscale_settings.authkey}
  - TS_EXTRA_ARGS=--advertise-tags=tag:k8s-{node.role}
  - TS_HOSTNAME={node.name}
""",
                    "path": "/var/etc/tailscale/auth.env",
                    "op": "create",
                    "permissions": 0o600,
                },
            ],
        },
    })


def get_control_plane_config_patches(node: NodeSpec, is_first: bool = False) -> list[str]:
    """
    Generate config patches specific to control plane nodes.

    Args:
        node: Control plane node specification
        is_first: Whether this is the first control plane node (for VIP)
    """
    patches = get_base_config_patches(node)
    patches.append(get_tailscale_config_patch(node))

    # Control plane specific configuration
    # Enable VIP on all control plane nodes (Talos will coordinate)
    if cluster_settings.vip_hostname:
        # If a VIP hostname is configured, use it as the cluster endpoint
        # The VIP is managed by Talos across control plane nodes
        patches.append(json.dumps({
            "machine": {
                "network": {
                    "interfaces": [
                        {
                            "interface": "eth0",
                            "dhcp": True,
                            # VIP will float between control plane nodes
                            # This requires the Tailscale VIP to be pre-configured
                        },
                    ],
                },
            },
        }))

    return patches


def get_worker_config_patches(node: NodeSpec) -> list[str]:
    """
    Generate config patches specific to worker nodes.
    """
    patches = get_base_config_patches(node)
    patches.append(get_tailscale_config_patch(node))

    # Worker specific configuration
    patches.append(json.dumps({
        "machine": {
            "network": {
                "interfaces": [
                    {
                        "interface": "eth0",
                        "dhcp": True,
                    },
                ],
            },
        },
    }))

    return patches


def get_config_patches(node: NodeSpec) -> list[str]:
    """
    Get all config patches for a node based on its role.
    """
    if node.role == "controlplane":
        is_first = node == CONTROL_PLANE_NODES[0]
        return get_control_plane_config_patches(node, is_first)
    else:
        return get_worker_config_patches(node)


def generate_machine_configuration(node: NodeSpec) -> talos.machine.GetConfigurationResult:
    """
    Generate Talos machine configuration for a specific node.

    Args:
        node: Node specification

    Returns:
        Machine configuration result
    """
    # Determine the cluster endpoint
    # Use Tailscale VIP hostname if configured, otherwise use first control plane's Tailscale DNS
    if cluster_settings.vip_hostname:
        endpoint = f"https://{cluster_settings.vip_hostname}:6443"
    else:
        # Fallback to first control plane node's expected Tailscale DNS name
        first_cp = CONTROL_PLANE_NODES[0]
        endpoint = f"https://{first_cp.name}:6443"

    config = talos.machine.get_configuration_output(
        cluster_name=cluster_settings.name,
        cluster_endpoint=endpoint,
        machine_type=node.role,
        machine_secrets=machine_secrets.machine_secrets,
        talos_version=cluster_settings.talos_version,
        config_patches=get_config_patches(node),
        docs=False,
        examples=False,
    )

    return config
