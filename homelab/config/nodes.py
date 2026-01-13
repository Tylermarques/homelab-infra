from dataclasses import dataclass
from typing import Literal


@dataclass
class NodeSpec:
    """Specification for a Talos Linux node VM."""

    name: str
    vm_id: int
    cpu_cores: int
    memory_mb: int
    disk_gb: int
    role: Literal["controlplane", "worker"]


# Control Plane Nodes: 4 CPU, 8GB RAM, 50GB disk
CONTROL_PLANE_NODES: list[NodeSpec] = [
    NodeSpec(name="k8s-control-0", vm_id=200, cpu_cores=4, memory_mb=8192, disk_gb=50, role="controlplane"),
    NodeSpec(name="k8s-control-1", vm_id=201, cpu_cores=4, memory_mb=8192, disk_gb=50, role="controlplane"),
    NodeSpec(name="k8s-control-2", vm_id=202, cpu_cores=4, memory_mb=8192, disk_gb=50, role="controlplane"),
]

# Worker Nodes: 4 CPU, 16GB RAM, 100GB disk
WORKER_NODES: list[NodeSpec] = [
    NodeSpec(name="k8s-worker-0", vm_id=210, cpu_cores=4, memory_mb=16384, disk_gb=100, role="worker"),
    NodeSpec(name="k8s-worker-1", vm_id=211, cpu_cores=4, memory_mb=16384, disk_gb=100, role="worker"),
    NodeSpec(name="k8s-worker-2", vm_id=212, cpu_cores=4, memory_mb=16384, disk_gb=100, role="worker"),
]

ALL_NODES = CONTROL_PLANE_NODES + WORKER_NODES
