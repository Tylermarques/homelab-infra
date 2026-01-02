import pulumi
import pulumi_kubernetes as k8s
from ..volumes import create_nfs_pv_and_pvc
from ..dns import create_traefik_ingress, ALLOWED_DOMAINS
from ..cloudnative_pg.cloudnative_pg import create_postgres_cluster

# Create namespace for mealie
namespace = k8s.core.v1.Namespace("mealie", metadata={"name": "mealie"})

# Create NFS PV and PVC for shared data (still needed for uploads/media)
pv, pvc = create_nfs_pv_and_pvc(
    name="mealie",
    namespace=namespace.metadata.name,
    share_path="/main/plex/mealie",
    storage_size="10Gi",
)

# ==================== PostgreSQL Database ====================
# Create PostgreSQL cluster for mealie using CloudNativePG
mealie_postgres = create_postgres_cluster(
    name="mealie-db",
    namespace=namespace.metadata.name,
    instances=1,  # Single instance for mealie
    storage_size="5Gi",
    database="mealie",
    owner="mealie",
)

# Common labels
api_labels = {"app": "mealie", "component": "api"}
frontend_labels = {"app": "mealie", "component": "frontend"}

# ==================== API Deployment ====================
# Database connection uses the auto-generated secret from CloudNativePG
# Secret name: mealie-db-app (contains: username, password, host, port, dbname, uri)
api_env_vars = [
    k8s.core.v1.EnvVarArgs(name="ALLOW_SIGNUP", value="true"),
    k8s.core.v1.EnvVarArgs(name="BASE_URL", value="https://mealie.tylermarques.com"),
    k8s.core.v1.EnvVarArgs(name="MAX_WORKERS", value="1"),
    k8s.core.v1.EnvVarArgs(name="PGID", value="911"),
    k8s.core.v1.EnvVarArgs(name="PUID", value="911"),
    k8s.core.v1.EnvVarArgs(name="TZ", value="America/Toronto"),
    k8s.core.v1.EnvVarArgs(name="WEB_CONCURRENCY", value="1"),
    k8s.core.v1.EnvVarArgs(name="API_PORT", value="9000"),
    # PostgreSQL configuration
    k8s.core.v1.EnvVarArgs(name="DB_ENGINE", value="postgres"),
    k8s.core.v1.EnvVarArgs(
        name="POSTGRES_USER",
        value_from=k8s.core.v1.EnvVarSourceArgs(
            secret_key_ref=k8s.core.v1.SecretKeySelectorArgs(
                name="mealie-db-app",
                key="username",
            )
        ),
    ),
    k8s.core.v1.EnvVarArgs(
        name="POSTGRES_PASSWORD",
        value_from=k8s.core.v1.EnvVarSourceArgs(
            secret_key_ref=k8s.core.v1.SecretKeySelectorArgs(
                name="mealie-db-app",
                key="password",
            )
        ),
    ),
    k8s.core.v1.EnvVarArgs(name="POSTGRES_SERVER", value="mealie-db-rw"),
    k8s.core.v1.EnvVarArgs(name="POSTGRES_PORT", value="5432"),
    k8s.core.v1.EnvVarArgs(name="POSTGRES_DB", value="mealie"),
]

api_deployment = k8s.apps.v1.Deployment(
    "mealie-api",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="mealie-api",
        namespace=namespace.metadata.name,
        labels=api_labels,
    ),
    spec=k8s.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=api_labels),
        strategy=k8s.apps.v1.DeploymentStrategyArgs(type="Recreate"),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=k8s.meta.v1.ObjectMetaArgs(labels=api_labels),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name="mealie-api",
                        image="hkotel/mealie:api-v1.0.0beta-5",
                        env=api_env_vars,
                        ports=[
                            k8s.core.v1.ContainerPortArgs(
                                container_port=9000,
                                name="api",
                            )
                        ],
                        volume_mounts=[
                            k8s.core.v1.VolumeMountArgs(
                                name="mealie-data",
                                mount_path="/app/data/",
                            )
                        ],
                        resources=k8s.core.v1.ResourceRequirementsArgs(
                            limits={"memory": "1000Mi"},
                        ),
                    )
                ],
                volumes=[
                    k8s.core.v1.VolumeArgs(
                        name="mealie-data",
                        persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(claim_name=pvc.metadata.name),
                    )
                ],
            ),
        ),
    ),
    opts=pulumi.ResourceOptions(depends_on=[mealie_postgres]),
)

api_service = k8s.core.v1.Service(
    "mealie-api",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="mealie-api",
        namespace=namespace.metadata.name,
        labels=api_labels,
    ),
    spec=k8s.core.v1.ServiceSpecArgs(
        type="ClusterIP",
        ports=[
            k8s.core.v1.ServicePortArgs(
                port=9000,
                target_port="api",
                name="api",
            )
        ],
        selector=api_labels,
    ),
)

# ==================== Frontend Deployment ====================
frontend_env_vars = [
    k8s.core.v1.EnvVarArgs(name="API_URL", value="http://mealie-api:9000"),
    k8s.core.v1.EnvVarArgs(name="TZ", value="America/Toronto"),
]

frontend_deployment = k8s.apps.v1.Deployment(
    "mealie-frontend",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="mealie-frontend",
        namespace=namespace.metadata.name,
        labels=frontend_labels,
    ),
    spec=k8s.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=frontend_labels),
        strategy=k8s.apps.v1.DeploymentStrategyArgs(type="Recreate"),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=k8s.meta.v1.ObjectMetaArgs(labels=frontend_labels),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name="mealie-frontend",
                        image="hkotel/mealie:frontend-v1.0.0beta-5",
                        env=frontend_env_vars,
                        ports=[
                            k8s.core.v1.ContainerPortArgs(
                                container_port=3000,
                                name="http",
                            )
                        ],
                        volume_mounts=[
                            k8s.core.v1.VolumeMountArgs(
                                name="mealie-data",
                                mount_path="/app/data/",
                            )
                        ],
                    )
                ],
                volumes=[
                    k8s.core.v1.VolumeArgs(
                        name="mealie-data",
                        persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(claim_name=pvc.metadata.name),
                    )
                ],
            ),
        ),
    ),
)

frontend_service = k8s.core.v1.Service(
    "mealie-frontend",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="mealie-frontend",
        namespace=namespace.metadata.name,
        labels=frontend_labels,
    ),
    spec=k8s.core.v1.ServiceSpecArgs(
        type="ClusterIP",
        ports=[
            k8s.core.v1.ServicePortArgs(
                port=3000,
                target_port="http",
                name="http",
            )
        ],
        selector=frontend_labels,
    ),
)

# ==================== Ingress ====================
ingress = create_traefik_ingress(
    subdomain="mealie",
    host_domain=ALLOWED_DOMAINS.TM,
    service_port=3000,
    namespace=namespace.metadata.name,
    service_name="mealie-frontend",
)
