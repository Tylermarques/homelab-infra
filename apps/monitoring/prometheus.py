import os
import pulumi
import pulumi_kubernetes as k8s
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
from .namespace import namespace

from apps.volumes import create_nfs_pv_and_pvc


nfs_storage = create_nfs_pv_and_pvc(
    name="prometheus",
    namespace=namespace.metadata.name,
    share_path="/main/plex/prometheus",
)
prometheus = Chart(
    "prometheus",
    k8s.helm.v3.ChartOpts(
        chart="prometheus",
        fetch_opts=k8s.helm.v3.FetchOpts(
            repo="https://prometheus-community.github.io/helm-charts",
        ),
        namespace=namespace.metadata.name,
        values={
            "server": {
                "persistentVolume": {
                    "enabled": True,
                    "size": "8Gi",
                    "existingClaim": nfs_storage["pvc"].metadata.name,
                    "access_modes": ["ReadWriteMany"],
                },
                "service": {"type": "ClusterIP"},
                "securityContext": {
                    "runAsUser": 65534,
                    "runAsGroup": 65534,
                    "fsGroup": None,
                    "fsGroupChangePolicy": "OnRootMismatch",
                },
                # optional: quiet Kubernetes warnings about missing fsGroup
                "podSecurityContext": {
                    "fsGroupChangePolicy": "OnRootMismatch",
                },
            },
            "alertmanager": {
                # Install this separately as the default helm chart has no control over the placement of the pv
                "enabled": False,
            },
        },
    ),
)
