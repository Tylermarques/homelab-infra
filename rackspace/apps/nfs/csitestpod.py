import pulumi
import pulumi_kubernetes as k8s

# Create a sample PVC using the NFS storage class
sample_pvc = k8s.core.v1.PersistentVolumeClaim(
    "sample-nfs-pvc",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="sample-nfs-pvc",
        namespace="default",
    ),
    spec=k8s.core.v1.PersistentVolumeClaimSpecArgs(
        access_modes=["ReadWriteMany"],
        storage_class_name="nfs-csi",
        resources=k8s.core.v1.ResourceRequirementsArgs(
            requests={
                "storage": "1Gi",
            },
        ),
    ),
    opts=pulumi.ResourceOptions(depends_on=[nfs_csi_driver]),
)

# Create a test pod that uses the PVC
nfs_test_pod = k8s.core.v1.Pod(
    "nfs-csi-test-pod",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="nfs-csi-test-pod",
        namespace="default",
    ),
    spec=k8s.core.v1.PodSpecArgs(
        containers=[
            k8s.core.v1.ContainerArgs(
                name="busybox",
                image="busybox",
                command=[
                    "/bin/sh",
                    "-c",
                    "echo 'Testing NFS CSI volume...'; "
                    "ls -la /mnt/nfs; "
                    "echo 'Writing test file...'; "
                    "echo 'Hello from CSI driver' > /mnt/nfs/test-csi.txt; "
                    "echo 'Test complete'; "
                    "sleep 3600",  # Keep the pod running for investigation
                ],
                volume_mounts=[
                    k8s.core.v1.VolumeMountArgs(
                        name="nfs-csi-volume",
                        mount_path="/mnt/nfs",
                    )
                ],
            )
        ],
        volumes=[
            k8s.core.v1.VolumeArgs(
                name="nfs-csi-volume",
                persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(
                    claim_name=sample_pvc.metadata.name,
                ),
            )
        ],
        restart_policy="Never",
    ),
    opts=pulumi.ResourceOptions(depends_on=[sample_pvc]),
)

# Export useful information
pulumi.export("csi_driver_name", "csi-driver-nfs")
pulumi.export("storage_class_name", "nfs-csi")
pulumi.export("sample_pvc_name", sample_pvc.metadata.name)
pulumi.export("test_pod_name", nfs_test_pod.metadata.name)
pulumi.export(
    "check_logs_command",
    pulumi.Output.concat("kubectl logs -n default ", nfs_test_pod.metadata.name),
)
pulumi.export(
    "exec_into_pod_command",
    pulumi.Output.concat(
        "kubectl exec -it -n default ",
        nfs_test_pod.metadata.name,
        " -- /bin/sh",
    ),
)
