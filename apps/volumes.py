from enum import Enum
from pulumi import ResourceOptions
import pulumi_kubernetes as k8s
from typing import Tuple

from pulumi_kubernetes.core.v1 import VolumeResourceRequirementsArgs


def create_nfs_pv_and_pvc(
    name,
    namespace,
    server="proxmox-egress",
    share_path="/main/plex",
    storage_size="50Gi",
    storage_class_name="nfs-csi",
) -> Tuple[k8s.core.v1.PersistentVolume, k8s.core.v1.PersistentVolumeClaim]:
    """Create a Persistent Volume and Persistent Volume Claim for NFS storage"""

    # Create Persistent Volume
    pv = k8s.core.v1.PersistentVolume(
        f"{name}-nfs-pv",
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name=f"{name}-nfs-pv",
            annotations={"pv.kubernetes.io/provisioned-by": "nfs.csi.k8s.io"},
        ),
        spec=k8s.core.v1.PersistentVolumeSpecArgs(
            capacity={"storage": storage_size},
            access_modes=["ReadWriteMany"],
            persistent_volume_reclaim_policy="Retain",
            storage_class_name=storage_class_name,
            mount_options=["nfsvers=4.1"],
            csi=k8s.core.v1.CSIPersistentVolumeSourceArgs(
                driver="nfs.csi.k8s.io",
                volume_handle=f"{server}#{share_path}##{name}",
                volume_attributes={"server": server, "share": share_path},
            ),
        ),
        # Remove this before replacing it.
        opts=ResourceOptions(delete_before_replace=True),
    )

    # Create Persistent Volume Claim
    pvc = k8s.core.v1.PersistentVolumeClaim(
        f"{name}-nfs-pvc",
        metadata=k8s.meta.v1.ObjectMetaArgs(name=f"{name}-nfs-pvc", namespace=namespace),
        spec=k8s.core.v1.PersistentVolumeClaimSpecArgs(
            access_modes=["ReadWriteMany"],
            resources=k8s.core.v1.VolumeResourceRequirementsArgs(requests={"storage": storage_size}),
            volume_name=pv.metadata.name,
            storage_class_name=storage_class_name,
        ),
        # Remove this before replacing it.
        opts=ResourceOptions(delete_before_replace=True),
    )

    return (pv, pvc)


class StorageClass(Enum):
    SSD = "ssd"
    SSD_LARGE = "ssd-large"
    SATA = "sata"
    SATA_LARGE = "sata-large"


def create_cloud_voume(
    name: str,
    namespace: str,
    storage_size: int,
    storage_class: StorageClass = StorageClass.SSD,
) -> k8s.core.v1.PersistentVolumeClaim:
    assert isinstance(storage_class, StorageClass), "Invalid value for storage_class, expected Type StorageClass"
    assert storage_class != "nfs", "Cannot create storage class with nfs type, please use the dedicated function for creating nfs volumes"
    assert storage_class in StorageClass, f"Invalid storage class type {storage_class}, accepted values are {[i for i in StorageClass]}"

    # Validate that the storage requested is of the correct size.
    if storage_class in [StorageClass.SATA_LARGE, StorageClass.SSD_LARGE] and storage_size < 50:
        raise Exception(f"When using the {storage_class.value} storage_class, volumes must be 50Gi or larger. You requested {storage_size}Gi")
    if storage_class in [StorageClass.SATA, StorageClass.SSD] and not 5 <= storage_size <= 20:
        raise Exception(f"When using the {storage_class.value} storage_class, volumes must be between 5Gi and 20Gi. You requested {storage_size}Gi")

    # Create Persistent Volume Claim
    pvc = k8s.core.v1.PersistentVolumeClaim(
        f"{name}-{storage_class.value}-pvc",
        metadata=k8s.meta.v1.ObjectMetaArgs(name=f"{name}-{storage_class.value}-pvc", namespace=namespace),
        spec=k8s.core.v1.PersistentVolumeClaimSpecArgs(
            access_modes=["ReadWriteOnce"],
            resources=VolumeResourceRequirementsArgs(requests={"storage": f"{storage_size}Gi"}),
            storage_class_name=storage_class.value,
        ),
        # Don't accidently delete this resource. That would remove your data.
        opts=ResourceOptions(retain_on_delete=True),
    )
    return pvc
