import os
import pulumi
from pulumi_kubernetes.core.v1 import ServicePortArgs, ServiceSpecArgs, Namespace
from pulumi_kubernetes.meta.v1 import ObjectMetaArgs, LabelSelectorArgs
from pulumi_kubernetes.apps.v1 import DeploymentSpecArgs, DeploymentArgs, DeploymentStrategyArgs, RollingUpdateDeploymentArgs
import pulumi_kubernetes as k8s

from ..dns import create_cloudflare_A_record, create_traefik_ingress, ALLOWED_DOMAINS

dns_record = create_cloudflare_A_record("tylermarques.com", ALLOWED_DOMAINS.TM)


namespace = Namespace(
    "tylermarquescom", metadata=ObjectMetaArgs(name="tylermarquescom")
)

service = k8s.core.v1.Service(
    "tylermarquescom-Service",
    metadata=ObjectMetaArgs(name="tylermarquescom", namespace=namespace.metadata.name),
    spec=ServiceSpecArgs(
        selector={"app": "tylermarquescom"},
        ports=[ServicePortArgs(port=3000, target_port=3000, name="tylermarquescom")],
        type="ClusterIP",
    ),
)
ingress = create_traefik_ingress(
    "tylermarques.com",
    ALLOWED_DOMAINS.TM,
    service.spec.ports[0].port,
    service_name="tylermarquescom",
    namespace=namespace.metadata.name,
    create_root=True,
)

deployment = k8s.apps.v1.Deployment(
    "tylermarques-com-deployment",
    metadata=ObjectMetaArgs(
        name="tylermarques-com",
        namespace=namespace.metadata.name,
        labels={"app": "tylermarquescom"}
    ),
    spec=DeploymentSpecArgs(
        selector=LabelSelectorArgs(
            match_labels={"app": "tylermarquescom"}
        ),
        replicas=1,
        strategy=DeploymentStrategyArgs(
            type="RollingUpdate",
            rolling_update=RollingUpdateDeploymentArgs(
                max_surge="25%",
                max_unavailable="25%"
            )
        ),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=ObjectMetaArgs(
                labels={"app": "tylermarquescom"},
                annotations={
                    "kubectl.kubernetes.io/default-container": "tylermarquescom"
                }
            ),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name="tylermarquescom",
                        image="ghcr.io/tylermarques/tylermarques-com:6b90eec228bc38a8b8b5613530fe53a3e93a58cb",
                        image_pull_policy="Always",
                        ports=[
                            k8s.core.v1.ContainerPortArgs(
                                container_port=3000,
                                name="http",
                                protocol="TCP"
                            )
                        ]
                    )
                ],
                image_pull_secrets=[
                    k8s.core.v1.LocalObjectReferenceArgs(
                        name="gchrio-cred"
                    )
                ]
            )
        )
    )
)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Argocd app to update based on github actions
marquescg_com = k8s.yaml.ConfigFile(
    "tylermarquescom", os.path.join(current_dir, "argoApp.yaml")
)
