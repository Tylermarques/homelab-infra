import os
import pulumi
import pulumi_kubernetes as k8s

from pulumi_kubernetes.core.v1 import ServicePortArgs, ServiceSpecArgs, Namespace
from pulumi_kubernetes.meta.v1 import ObjectMetaArgs, LabelSelectorArgs
from ..dns import create_cloudflare_A_record, create_traefik_ingress, ALLOWED_DOMAINS

dns_record = create_cloudflare_A_record("marquescg.com", ALLOWED_DOMAINS.MCG)


namespace = Namespace("marquescgcom", metadata=ObjectMetaArgs(name="marquescgcom"))
service = k8s.core.v1.Service(
    "marquescgcom-Service",
    metadata=ObjectMetaArgs(name="marquescgcom", namespace=namespace.metadata.name),
    spec=ServiceSpecArgs(
        selector={"app": "marquescgcom"},
        ports=[ServicePortArgs(port=3000, target_port=3000, name="marquescgcom")],
        type="ClusterIP",
    ),
)

ingress = create_traefik_ingress(
    "marquescg.com",
    ALLOWED_DOMAINS.MCG,
    service.spec.ports[0].port,
    service_name=service.metadata.name,
    namespace=namespace,
    create_root=True,
)

current_dir = os.path.dirname(os.path.abspath(__file__))
# Argocd app to update based on github actions
marquescg_com = k8s.yaml.ConfigFile("marquescg_com", os.path.join(current_dir, "argoApp.yaml"))
