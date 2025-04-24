import pulumi
import pulumi_kubernetes as k8s

# Configuration
nfs_server = "proxmox-egress"  # Replace with your NFS server IP or hostname
nfs_path = "/main/plex/"  # Replace with your NFS exported path

# Create a pod to test NFS connectivity
nfs_test_pod = k8s.core.v1.Pod(
    "nfs-test-pod",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="nfs-test-pod",
        namespace="terraria",
        annotations={"tailscale.com/inject": "true"},
    ),
    spec=k8s.core.v1.PodSpecArgs(
        containers=[
            k8s.core.v1.ContainerArgs(
                name="busybox",
                image="busybox",
                command=[
                    "/bin/sh",
                    "-c",
                    "echo 'Mounting NFS...'; "
                    "mkdir -p /mnt/nfs; "
                    "mount -t nfs -o vers=4 ${NFS_SERVER}:${NFS_PATH} /mnt/nfs; "
                    "echo 'Mount result: $?'; "
                    "ls -la /mnt/nfs; "
                    "echo 'Test complete'; "
                    "sleep 3600",  # Keep the pod running for investigation
                ],
                env=[
                    k8s.core.v1.EnvVarArgs(name="NFS_SERVER", value=nfs_server),
                    k8s.core.v1.EnvVarArgs(name="NFS_PATH", value=nfs_path),
                ],
                security_context=k8s.core.v1.SecurityContextArgs(
                    privileged=True  # Required for mount operations
                ),
                volume_mounts=[k8s.core.v1.VolumeMountArgs(name="nfs-test-volume", mount_path="/mnt/nfs")],
            )
        ],
        volumes=[
            k8s.core.v1.VolumeArgs(
                name="nfs-csi-volume",
                persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(claim_name="terraria-pvc"),
            )
        ],
        restart_policy="Never",
    ),
)

# Export the pod name
pulumi.export("pod_name", nfs_test_pod.metadata.name)
pulumi.export("namespace", namespace.metadata.name)
pulumi.export(
    "check_logs_command",
    pulumi.Output.concat("kubectl logs -n ", namespace.metadata.name, " ", nfs_test_pod.metadata.name),
)
pulumi.export(
    "exec_into_pod_command",
    pulumi.Output.concat(
        "kubectl exec -it -n ",
        namespace.metadata.name,
        " ",
        nfs_test_pod.metadata.name,
        " -- /bin/sh",
    ),
)
