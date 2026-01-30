import pulumi
import pulumiverse_talos as talos
import pulumi_proxmoxve as proxmoxve
from config.settings import cluster_settings
from config.nodes import NodeSpec, CONTROL_PLANE_NODES, WORKER_NODES
from talos.secrets import machine_secrets
from talos.config import generate_machine_configuration
from infrastructure.reachability import create_reachability_check


def extract_vm_ip(ipv4_addresses: list[list[str]]) -> str:
    """
    Extract the primary non-loopback IP from Proxmox VM ipv4_addresses.

    The ipv4_addresses is a list of lists, where each inner list contains
    the IP addresses for a network interface. We need to find the first
    non-loopback address.

    Args:
        ipv4_addresses: List of IP address lists from QEMU guest agent

    Returns:
        The first non-loopback IP address, or empty string if none found
    """
    if not ipv4_addresses:
        return ""

    for interface_ips in ipv4_addresses:
        for ip in interface_ips:
            # Skip loopback addresses
            if not ip.startswith("127."):
                return ip

    return ""


def apply_configuration_to_node(
    node: NodeSpec,
    vm: proxmoxve.vm.VirtualMachine,
    depends_on: list[pulumi.Resource],
) -> talos.machine.ConfigurationApply:
    """
    Apply Talos configuration to a specific node.

    IMPORTANT: Since nodes use DHCP, we need to discover the IP from Proxmox
    after the VM boots. The VM's ipv4_addresses output is populated by the
    QEMU guest agent once the VM is running.

    This function first checks that the node is reachable via ping before
    attempting to apply configuration.

    Args:
        node: Node specification
        vm: The Proxmox VM resource
        depends_on: Resources this depends on

    Returns:
        ConfigurationApply resource
    """
    # Generate machine configuration for this node
    config = generate_machine_configuration(node)

    # Get the primary IPv4 address from the VM's guest agent
    # This is populated after the VM boots and the guest agent reports IPs
    node_ip = vm.ipv4_addresses.apply(extract_vm_ip)

    # Wait for the node to be reachable before applying configuration
    reachability_check = create_reachability_check(
        f"reachability-{node.name}",
        host=node_ip,
        timeout=5,  # 5 seconds - VMs should respond immediately
        interval=1,
        opts=pulumi.ResourceOptions(
            depends_on=depends_on + [vm],
        ),
    )

    return talos.machine.ConfigurationApply(
        f"config-apply-{node.name}",
        client_configuration={
            "ca_certificate": machine_secrets.client_configuration.ca_certificate,
            "client_certificate": machine_secrets.client_configuration.client_certificate,
            "client_key": machine_secrets.client_configuration.client_key,
        },
        machine_configuration_input=config.machine_configuration,
        node=node_ip,
        apply_mode="reboot",
        timeouts={
            "create": "15m",
            "update": "15m",
        },
        opts=pulumi.ResourceOptions(
            depends_on=[reachability_check],
        ),
    )


def bootstrap_cluster(
    control_plane_vms: list[proxmoxve.vm.VirtualMachine],
    worker_vms: list[proxmoxve.vm.VirtualMachine],
) -> tuple[list[talos.machine.ConfigurationApply], talos.machine.Bootstrap]:
    """
    Orchestrate the full Talos cluster bootstrap process.

    Steps:
    1. Apply configuration to all control plane nodes
    2. Apply configuration to all worker nodes
    3. Bootstrap the cluster on the first control plane node

    IMPORTANT: This process requires the QEMU guest agent to report VM IPs.
    The VMs must boot fully and the guest agent must be running before
    configuration can be applied.

    Returns:
        Tuple of (all config applies, bootstrap resource)
    """
    config_applies: list[talos.machine.ConfigurationApply] = []

    # Step 1: Apply configuration to control plane nodes
    for i, node in enumerate(CONTROL_PLANE_NODES):
        vm = control_plane_vms[i]
        apply = apply_configuration_to_node(
            node=node,
            vm=vm,
            depends_on=[],
        )
        config_applies.append(apply)

    # Step 2: Apply configuration to worker nodes
    # Workers depend on control plane being configured
    for i, node in enumerate(WORKER_NODES):
        vm = worker_vms[i]
        apply = apply_configuration_to_node(
            node=node,
            vm=vm,
            depends_on=config_applies[:len(CONTROL_PLANE_NODES)],
        )
        config_applies.append(apply)

    # Step 3: Bootstrap cluster on first control plane node
    first_control_plane = CONTROL_PLANE_NODES[0]
    first_control_plane_apply = config_applies[0]
    first_vm = control_plane_vms[0]

    # Get the first control plane's IP for bootstrap
    first_node_ip = first_vm.ipv4_addresses.apply(extract_vm_ip)

    bootstrap = talos.machine.Bootstrap(
        "talos-bootstrap",
        node=first_node_ip,
        client_configuration={
            "ca_certificate": machine_secrets.client_configuration.ca_certificate,
            "client_certificate": machine_secrets.client_configuration.client_certificate,
            "client_key": machine_secrets.client_configuration.client_key,
        },
        timeouts={
            "create": "15m",
        },
        opts=pulumi.ResourceOptions(
            depends_on=[first_control_plane_apply],
        ),
    )

    return config_applies, bootstrap


def get_kubeconfig(
    bootstrap: talos.machine.Bootstrap,
    first_vm: proxmoxve.vm.VirtualMachine,
) -> talos.cluster.Kubeconfig:
    """
    Retrieve the kubeconfig for the Talos cluster after bootstrap.

    Args:
        bootstrap: The bootstrap resource (to ensure proper ordering)
        first_vm: The first control plane VM (to get its IP)

    Returns:
        Kubeconfig resource
    """
    # Get the first control plane's IP
    node_ip = first_vm.ipv4_addresses.apply(extract_vm_ip)

    kubeconfig = talos.cluster.Kubeconfig(
        "talos-kubeconfig",
        node=node_ip,
        client_configuration={
            "ca_certificate": machine_secrets.client_configuration.ca_certificate,
            "client_certificate": machine_secrets.client_configuration.client_certificate,
            "client_key": machine_secrets.client_configuration.client_key,
        },
        opts=pulumi.ResourceOptions(depends_on=[bootstrap]),
    )

    return kubeconfig


def get_talosconfig() -> pulumi.Output[str]:
    """
    Generate talosconfig for use with talosctl.

    This allows direct interaction with Talos nodes using the CLI.
    """
    return pulumi.Output.all(
        machine_secrets.client_configuration.ca_certificate,
        machine_secrets.client_configuration.client_certificate,
        machine_secrets.client_configuration.client_key,
    ).apply(
        lambda args: f"""context: {cluster_settings.name}
contexts:
  {cluster_settings.name}:
    endpoints:
      - {CONTROL_PLANE_NODES[0].name}
    nodes:
      - {CONTROL_PLANE_NODES[0].name}
    ca: {args[0]}
    crt: {args[1]}
    key: {args[2]}
"""
    )
