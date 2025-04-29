import os
from dotenv import dotenv_values
from pulumi_kubernetes.apiextensions import CustomResource
import pulumi
from pulumi_kubernetes.helm.v3 import RepositoryOptsArgs
from pulumi_kubernetes.core.v1 import Namespace, Secret
from pulumi_kubernetes_cert_manager import CertManager, ReleaseArgs

env_config = dotenv_values(".env")

current_dir = os.path.dirname(os.path.abspath(__file__))

cert_manager_ns = Namespace("cert-manager-namespace", metadata={"name": "cert-manager"})

cert_manager = CertManager(
    "certmanager",
    install_crds=True,
    helm_options=ReleaseArgs(
        chart="cert-manager",
        version="v1.17.1",
        namespace="cert-manager",
        value_yaml_files=[pulumi.FileAsset(current_dir + "/values.yaml")],
        repository_opts=RepositoryOptsArgs(
            repo="https://charts.jetstack.io",
        ),
    ),
    opts=pulumi.ResourceOptions(depends_on=cert_manager_ns),
)

if env_config["CLOUDFARE_TOKEN"] is None:
    raise ValueError("CLOUDFARE_TOKEN Cannot be None")

cloudflare_token = Secret(
    "cloudflare-token",
    string_data={"cloudflare-token": env_config["CLOUDFARE_TOKEN"]},
    metadata={
        "name": "cloudflare-token-secret",
        "namespace": cert_manager_ns.metadata["name"],
    },
)

issuer = CustomResource(
    "letsencrypt-prod-cloudissuer",
    api_version="cert-manager.io/v1",
    kind="ClusterIssuer",
    spec={
        "acme": {
            "email": "me@tylermarques.com",
            "server": "https://acme-v02.api.letsencrypt.org/directory",
            "privateKeySecretRef": {"name": "letsencrypt-prod"},
            "solvers": [
                {
                    "dns01": {
                        "cloudflare": {
                            "email": "me@tylermarques.com",
                            "apiTokenSecretRef": {
                                "name": "cloudflare-token-secret",
                                "key": "cloudflare-token",
                            },
                        }
                    },
                    "selector": {
                        "dnsZones": [
                            "tylermarques.com",
                            "marquescg.com",
                            "u-the-bomb.com",
                        ]
                    },
                }
            ],
        }
    },
    opts=pulumi.ResourceOptions(depends_on=cert_manager),
)
pulumi.export("cert_manager_status", cert_manager.status)
