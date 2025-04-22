import pulumi_kubernetes as k8s
import pulumi


def create_nfs_pv_and_pvc(
    name,
    namespace,
    server="proxmox-egress",
    share_path="/main/plex",
    storage_size="50Gi",
    storage_class_name="nfs-csi",
):
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
    )

    # Create Persistent Volume Claim
    pvc = k8s.core.v1.PersistentVolumeClaim(
        f"{name}-nfs-pvc",
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name=f"{name}-nfs-pvc", namespace=namespace
        ),
        spec=k8s.core.v1.PersistentVolumeClaimSpecArgs(
            access_modes=["ReadWriteMany"],
            resources=k8s.core.v1.ResourceRequirementsArgs(
                requests={"storage": storage_size}
            ),
            volume_name=pv.metadata.name,
            storage_class_name=storage_class_name,
        ),
    )

    return {"pv": pv, "pvc": pvc}
