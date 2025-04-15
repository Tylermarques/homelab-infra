import pulumi_kubernetes as k8s
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts

# Configuration for NFS CSI Driver
nfs_csi_driver = Chart(
    "csi-driver-nfs",
    ChartOpts(
        chart="csi-driver-nfs",
        version="4.11.0",  # Using the version mentioned in the documentation
        fetch_opts=k8s.helm.v3.FetchOpts(
            repo="https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/master/charts"
        ),
        namespace="kube-system",
        values={
            # Default configuration based on the documentation
            "driver": {
                "name": "nfs.csi.k8s.io",
                "mountPermissions": 0,  # Default mount permissions
            },
            "feature": {
                "enableFSGroupPolicy": True,
                "enableInlineVolume": False,
                "propagateHostMountOptions": False,
            },
            "controller": {
                "replicas": 1,
                "runOnControlPlane": False,
                "dnsPolicy": "ClusterFirstWithHostNet",
                "defaultOnDeletePolicy": "delete",
                "logLevel": 5,
                "workingMountDir": "/tmp",
            },
            "node": {
                "dnsPolicy": "ClusterFirstWithHostNet",
                "maxUnavailable": 1,
                "logLevel": 5,
            },
            # Enable storage class creation
            "storageClass": {
                "create": True,
                "name": "nfs-csi",
                "defaultClass": False,
                "reclaimPolicy": "Retain",
                "parameters": {
                    "server": "proxmox-egress",  # Using the Kubernetes service name for Proxmox
                    "share": "/main/plex/",  # Using the same path as in the test
                },
                "mountOptions": ["nfsvers=4.1"],
            },
        },
    ),
)
