from dotenv import dotenv_values
import pulumi_kubernetes as k8s
import pulumi_cloudflare as cloudflare
from enum import Enum
from typing import Optional

from pulumi_kubernetes.apiextensions import CustomResource


class ALLOWED_DOMAINS(Enum):
    TM = "tylermarques.com"
    MCG = "marquescg.com"
    BOMB = "u-the-bomb.com"


env_config = dotenv_values(".env")
mcg_zone = cloudflare.get_zone(name="marquescg.com")
tylermarques_zone = cloudflare.get_zone(name="tylermarques.com")
uthebomb_zone = cloudflare.get_zone(name="u-the-bomb.com")

# TODO: This can be changed from an env value to a lookup of the 'traefik' svc in the 'traefik' namespace
rackspace_ip = env_config["RACKSPACE_IP"]
home_ip = env_config["HOME_IP"]

# Middleware that limits traffic to only coming from the tailnet.
tailnet_allow_middleware = CustomResource(
    "tailnet-allow",
    api_version="traefik.io/v1alpha1",
    kind="Middleware",
    metadata={
        "name": "tailnet-allow",
        "namespace": "monitoring",
    },
    spec={
        "ipAllowList": {
            "sourceRange": ["100.64.0.0/10"],
        }
    },
)


def create_traefik_ingress(
    subdomain: str,
    host_domain: ALLOWED_DOMAINS,
    service_port: int,
    name: Optional[str] = None,
    namespace: Optional[str] = None,
    service_name: Optional[str] = None,
    path: Optional[str] = "/",
    tls_enabled: bool = True,
    cert_issuer: str = "letsencrypt-prod-cloudissuer",
    create_root: bool = False,
    tailnet_only: bool = False,
) -> k8s.apiextensions.CustomResource:
    """
    Create a Traefik IngressRoute CustomResource for a given service. Name, Namespace, and Service_Name are all derived from the subdomain,
    ensuring a consistent pattern.

    Args:
        subdomain: Subdomain to use (e.g., "app" for app.tylermarques.com)
        host_domain: Domain enum from ALLOWED_DOMAINS
        service_port: Port on the service to route traffic to
        name: Name for the IngressRoute resource
        namespace: Kubernetes namespace where the IngressRoute should be created
        service_name: Name of the service to route traffic to
        path: URL path to match (default: "/")
        tls_enabled: Whether to enable TLS (default: True)
        cert_issuer: The cert-manager ClusterIssuer to use (default: "letsencrypt-prod")
        create_root: Whether this record if for the route of the domain
        tailnet_only: Whether to apply the tailnet only middleware, which only allows traffic from within the tailnet to access the ingress

    Returns:
        The created Traefik IngressRoute CustomResource
    """
    if name is None:
        name = subdomain
    if namespace is None:
        namespace = subdomain
    if service_name is None:
        service_name = subdomain

    # Construct the full hostname
    hostname = f"{subdomain}.{host_domain.value}"
    if create_root:
        hostname = host_domain.value

    route = {"match": f"Host(`{hostname}`) && PathPrefix(`{path}`)", "kind": "Rule", "services": [{"name": service_name, "port": service_port}], "middlewares": []}
    if create_root:
        if name != host_domain.value:
            raise ValueError("You provided a name that was not the host_domain, but also create_root. The name cannot be used")
        route["match"] = f"Host(`{host_domain.value}`) || Host(`www.{host_domain.value}`)"

    # Create the route spec
    if tailnet_only:
        route["middlewares"].append({"name": "tailnet-allow", "namespace": namespace})

    # Create the IngressRoute spec
    ingress_route_spec = {"entryPoints": ["websecure"], "routes": [route]}

    # Add TLS if enabled
    if tls_enabled:
        # Secret name for the TLS certificate
        secret_name = f"{name}-tls"
        ingress_route_spec["tls"] = {"secretName": secret_name}
        hosts = [hostname, f"www.{hostname}"] if create_root else [hostname]
        certificate = k8s.apiextensions.CustomResource(
            f"{name}-certificate",
            api_version="cert-manager.io/v1",
            kind="Certificate",
            metadata={
                "name": name,
                "namespace": namespace,
            },
            spec={
                "secretName": secret_name,
                "issuerRef": {
                    "name": cert_issuer,
                    "kind": "ClusterIssuer",
                },
                "dnsNames": hosts,
            },
        )

    # Create the IngressRoute custom resource
    ingress_route = k8s.apiextensions.CustomResource(
        f"{name}-ingressroute",
        api_version="traefik.io/v1alpha1",
        kind="IngressRoute",
        metadata={
            "name": name,
            "namespace": namespace,
        },
        spec=ingress_route_spec,
    )

    return ingress_route


# TODO: This file is in a halfway state. New deployments are having their records placed within their directory,
# old ones are at the bottom of this page.
def create_cloudflare_A_record(subdomain: str, domain: ALLOWED_DOMAINS, ip=rackspace_ip, proxied=True):
    """
    Create a DNS record for a subdomain under a specified domain.
    """
    if domain.value not in [d.value for d in ALLOWED_DOMAINS]:
        raise ValueError(f"Domain {domain.value} is not in allowed domains: {[d.value for d in ALLOWED_DOMAINS]}")
    zone = cloudflare.get_zone(name=domain.value)

    _ = cloudflare.Record(
        f"{subdomain}_" + domain.value,
        zone_id=zone.id,
        name=subdomain,
        content=ip,
        type="A",
        proxied=proxied,
        allow_overwrite=True,
    )


TM_DOMAINS = {
    "hass": {"proxied": False, "content": home_ip},
    "plex": {"proxied": False, "content": home_ip},
    "immich": {"proxied": False, "content": home_ip},
    "tylermarques.com": {"proxied": True, "content": home_ip},
    "overseerr": {"proxied": True, "content": home_ip},
    "mealie": {"proxied": True, "content": home_ip},
    "ntfy": {"proxied": True, "content": home_ip},
    "sftp": {"proxied": True, "content": home_ip},
    "terraria": {"proxied": False, "content": rackspace_ip},
}

BOMB_DOMAINS = {
    "u-the-bomb.com": {"proxied": True, "content": rackspace_ip},
}

# Note that there are MX records present in CF that are not here. Mostly because they should never need changing.
# the content for all these domains is the same, so do it in a loop
for prefix, domain_block, zone in [
    ("TM", TM_DOMAINS, tylermarques_zone),
    ("BOMB", BOMB_DOMAINS, uthebomb_zone),
]:
    for domain, options in domain_block.items():
        _ = cloudflare.Record(
            f"{prefix}_" + domain,
            zone_id=zone.id,
            name=domain,
            content=options["content"],
            type="A",
            proxied=options["proxied"],
            allow_overwrite=True,
        )
# Have www redirect to marquescg.com
_ = cloudflare.Record(
    "MCG_www",
    zone_id=mcg_zone.id,
    name="www",
    content="marquescg.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)
_ = cloudflare.Record(
    "TM_www",
    zone_id=tylermarques_zone.id,
    name="www",
    content="tylermarques.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)
_ = cloudflare.Record(
    "uthebomb_www",
    zone_id=uthebomb_zone.id,
    name="www",
    content="u-the-bomb.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)
