import pulumi
import pulumi_proxmoxve as proxmoxve
from config.settings import proxmox_settings, cluster_settings
from config.nodes import NodeSpec, CONTROL_PLANE_NODES, WORKER_NODES
from infrastructure.provider import proxmox_provider
from infrastructure.iso import talos_iso


def create_talos_vm(spec: NodeSpec) -> proxmoxve.vm.VirtualMachine:
    """
    Create a Talos Linux VM on Proxmox with the specified configuration.

    Talos-specific requirements:
    - CPU type must be 'host' or x86-64-v2-AES (not kvm64)
    - Memory hotplug must be disabled (floating=0)
    - QEMU guest agent should be enabled for VM lifecycle management
    - Boot order: cdrom first for initial install, then disk

    Args:
        spec: Node specification with CPU, memory, disk, and role

    Returns:
        The created VirtualMachine resource
    """
    vm = proxmoxve.vm.VirtualMachine(
        f"vm-{spec.name}",
        name=spec.name,
        node_name=proxmox_settings.node_name,
        vm_id=spec.vm_id,
        # Machine configuration
        bios="seabios",
        machine="q35",
        # CPU configuration - must be host or x86-64-v2-AES for Talos
        # Using 'host' for best compatibility and performance
        cpu=proxmoxve.vm.VirtualMachineCpuArgs(
            cores=spec.cpu_cores,
            sockets=1,
            type="host",
        ),
        # Memory - DO NOT enable hotplug for Talos (floating must be 0)
        memory=proxmoxve.vm.VirtualMachineMemoryArgs(
            dedicated=spec.memory_mb,
            floating=0,
        ),
        # QEMU guest agent for VM lifecycle management
        agent=proxmoxve.vm.VirtualMachineAgentArgs(
            enabled=True,
            type="virtio",
        ),
        # Boot from ISO initially using CD-ROM
        cdrom=proxmoxve.vm.VirtualMachineCdromArgs(
            file_id=talos_iso.id,
            interface="ide2",
        ),
        # Boot order: cdrom first for initial install, then disk
        boot_orders=["ide2", "scsi0"],
        # Disk configuration
        disks=[
            proxmoxve.vm.VirtualMachineDiskArgs(
                interface="scsi0",
                datastore_id=cluster_settings.storage_pool,
                size=spec.disk_gb,
                file_format="raw",
                iothread=True,
                ssd=True,
                discard="on",
            ),
        ],
        # Network configuration - DHCP will assign IPs
        network_devices=[
            proxmoxve.vm.VirtualMachineNetworkDeviceArgs(
                bridge=cluster_settings.network_bridge,
                model="virtio",
                firewall=False,
            ),
        ],
        # Operating system type - Linux 2.6+ kernel
        operating_system=proxmoxve.vm.VirtualMachineOperatingSystemArgs(
            type="l26",
        ),
        # SCSI controller
        scsi_hardware="virtio-scsi-single",
        # Start VM after creation
        started=True,
        on_boot=True,
        # Timeouts for creation
        timeout_create=300,
        timeout_clone=300,
        opts=pulumi.ResourceOptions(
            provider=proxmox_provider,
            depends_on=[talos_iso],
        ),
    )

    return vm


def create_all_vms() -> tuple[list[proxmoxve.vm.VirtualMachine], list[proxmoxve.vm.VirtualMachine]]:
    """
    Create all control plane and worker VMs.

    Returns:
        Tuple of (control_plane_vms, worker_vms)
    """
    control_plane_vms = [create_talos_vm(spec) for spec in CONTROL_PLANE_NODES]
    worker_vms = [create_talos_vm(spec) for spec in WORKER_NODES]
    return control_plane_vms, worker_vms
