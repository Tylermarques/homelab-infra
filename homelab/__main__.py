"""
Homelab Talos Linux Kubernetes Cluster on Proxmox

This Pulumi program creates a 6-node Talos Linux Kubernetes cluster:
- 3 control plane nodes (4 CPU, 8GB RAM, 50GB disk)
- 3 worker nodes (4 CPU, 16GB RAM, 100GB disk)

The cluster is fully automated including:
1. Talos ISO download to Proxmox (with qemu-guest-agent and tailscale extensions)
2. VM creation with proper specs
3. Talos machine configuration generation
4. Configuration application to all nodes
5. Cluster bootstrap
6. Kubeconfig export

Prerequisites:
- Proxmox API access (set PROXMOX_VE_ENDPOINT, PROXMOX_VE_API_TOKEN in .env)
- Tailscale auth key (set TAILSCALE_AUTHKEY in .env)
- Copy .env.example to .env and fill in your values

Usage:
    pulumi up    # Create/update the cluster
    pulumi destroy  # Tear down the cluster

After deployment:
    pulumi stack output kubeconfig --show-secrets > ~/.kube/homelab
    pulumi stack output talosconfig --show-secrets > ~/.talos/config
"""
import pulumi
import pulumi_kubernetes as k8s

# Import infrastructure components
from infrastructure.iso import talos_iso
from infrastructure.vms import create_all_vms

# Import Talos components
from talos.secrets import machine_secrets
from talos.bootstrap import bootstrap_cluster, get_kubeconfig, get_talosconfig

# Import configuration
from config.nodes import CONTROL_PLANE_NODES, WORKER_NODES


def main() -> None:
    """Main entry point for the Pulumi program."""

    # Phase 1: Create all VMs
    # VMs boot from the Talos ISO into maintenance mode
    control_plane_vms, worker_vms = create_all_vms()

    # Phase 2: Bootstrap the Talos cluster
    # This applies configuration to each node and bootstraps the cluster
    config_applies, bootstrap = bootstrap_cluster(control_plane_vms, worker_vms)

    # Phase 3: Get kubeconfig after bootstrap
    kubeconfig = get_kubeconfig(bootstrap, control_plane_vms[0])

    # Export outputs
    pulumi.export("talos_iso_id", talos_iso.id)

    pulumi.export("control_plane_vm_ids", [vm.vm_id for vm in control_plane_vms])
    pulumi.export("worker_vm_ids", [vm.vm_id for vm in worker_vms])

    pulumi.export("control_plane_names", [node.name for node in CONTROL_PLANE_NODES])
    pulumi.export("worker_names", [node.name for node in WORKER_NODES])

    # Export VM IPs (useful for debugging)
    pulumi.export("control_plane_ips", [
        vm.ipv4_addresses.apply(
            lambda addrs: addrs[1][0] if addrs and len(addrs) > 1 and addrs[1] else addrs[0][0] if addrs and addrs[0] else "pending"
        )
        for vm in control_plane_vms
    ])
    pulumi.export("worker_ips", [
        vm.ipv4_addresses.apply(
            lambda addrs: addrs[1][0] if addrs and len(addrs) > 1 and addrs[1] else addrs[0][0] if addrs and addrs[0] else "pending"
        )
        for vm in worker_vms
    ])

    # Export kubeconfig and talosconfig
    pulumi.export("kubeconfig", kubeconfig.kubeconfig_raw)
    pulumi.export("talosconfig", get_talosconfig())

    # Export client configuration for talosctl
    pulumi.export("talos_client_ca", machine_secrets.client_configuration.ca_certificate)
    pulumi.export("talos_client_cert", machine_secrets.client_configuration.client_certificate)
    pulumi.export("talos_client_key", machine_secrets.client_configuration.client_key)

    # Phase 4: Deploy applications to the cluster
    # Create Kubernetes provider using the kubeconfig from Talos bootstrap
    k8s_provider = k8s.Provider(
        "homelab-k8s",
        kubeconfig=kubeconfig.kubeconfig_raw,
    )

    # Deploy all apps to the cluster with the provider
    from apps import deploy_all_apps
    deploy_all_apps(k8s_provider)


# Run main
main()
