from dotenv import dotenv_values
import pulumi
import pulumi_kubernetes as kubernetes

env_config = dotenv_values(".env")

# FIXME: This is a gross hack and I hate it. Anyway it's going in Prod
for ns in ["marquescg-com", "tylermarques-com", "argocd", "u-the-bomb-com"]:
    gchrio_cred = kubernetes.core.v1.Secret(
        "gchrio_cred_" + ns,
        metadata={"name": "gchrio-cred", "namespace": ns},
        data={
            ".dockerconfigjson": env_config["GCHRIO_CRED"],
        },
        type="kubernetes.io/dockerconfigjson",
    )
