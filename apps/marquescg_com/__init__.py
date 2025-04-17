import os
import pulumi
import pulumi_kubernetes as k8s

from ..dns import create_cloudflare_A_record, create_traefik_ingress, ALLOWED_DOMAINS

dns_record = create_cloudflare_A_record("marquescg.com", ALLOWED_DOMAINS.MCG)
k8s_provider = k8s.Provider("prod")

namespace = "marquescg-com"

service = k8s.core.v1.Service.get(
    "marquescg-com",  # logical name inside Pulumi
    id="marquescg-com/prod-marquescg-com",  # <namespace>/<serviceName>
    opts=pulumi.ResourceOptions(provider=k8s_provider),
)

ingress = create_traefik_ingress(
    "marquescg.com",
    ALLOWED_DOMAINS.MCG,
    service.spec.ports[0].port,
    service_name="prod-marquescg-com",
    namespace=namespace,
    create_root=True,
)

current_dir = os.path.dirname(os.path.abspath(__file__))
# Argocd app to update based on github actions
marquescg_com = k8s.yaml.ConfigFile(
    "marquescg_com", os.path.join(current_dir, "argoApp.yaml")
)
