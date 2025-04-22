import pulumi
import pulumi_kubernetes as k8s
from apps.media.volumes import create_nfs_pv_and_pvc

from .namespace import namespace

nfs_storage = create_nfs_pv_and_pvc(name="tempo", namespace=namespace.metadata.name)


def deploy_tempo(namespace: str, opts=None):
    cfg = pulumi.Config("tempo")
    chart = k8s.helm.v3.Chart(
        "tempo",
        k8s.helm.v3.ChartOpts(
            chart="tempo",
            fetch_opts=k8s.helm.v3.FetchOpts(
                repo="https://grafana.github.io/helm-charts",
            ),
            namespace=namespace,
            values={
                "mode": "monolithic",
                "persistence": {
                    "enabled": True,
                    "size": "10Gi",
                    "existingClaim": nfs_storage["pvc"].metadata.name,
                },
                "tempo": {
                    "searchEnabled": True,
                },
            },
        ),
        opts=opts,
    )
    return chart
