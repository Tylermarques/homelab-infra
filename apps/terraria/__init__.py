import pulumi
from pulumi_kubernetes.apiextensions import CustomResource
from pulumi_kubernetes.core.v1 import (
    NFSVolumeSourceArgs,
    Namespace,
    PersistentVolumeClaimSpecArgs,
    PersistentVolumeSpecArgs,
    Service,
    ContainerArgs,
    PodSpecArgs,
    PodTemplateSpecArgs,
    ContainerPortArgs,
    ServicePortArgs,
    VolumeArgs,
    VolumeMountArgs,
    PersistentVolume,
    PersistentVolumeClaim,
    PersistentVolumeClaimVolumeSourceArgs,
    VolumeResourceRequirementsArgs,
    SecurityContextArgs,
)
from pulumi_kubernetes.apps.v1 import Deployment, DeploymentSpecArgs
from pulumi_kubernetes.meta.v1 import ObjectMetaArgs

from dotenv import dotenv_values


env_config = dotenv_values(".env")
# Create a namespace for Terraria
terraria_namespace = Namespace("terraria", metadata=ObjectMetaArgs(name="terraria"))

# NFS server configuration
nfs_server = "proxmox-egress"  # NFS server hostname or IP
nfs_path = "/main/plex/terraria"  # Path on the NFS server for Terraria data

# Create a PersistentVolume for NFS
# nfs_persistent_volume = PersistentVolume(
#     "terraria-pv",
#     metadata=ObjectMetaArgs(
#         name="terraria-nfs", namespace=terraria_namespace.metadata.name
#     ),
#     spec=PersistentVolumeSpecArgs(
#         capacity={"storage": "10Gi"},
#         access_modes=["ReadWriteOnce"],
#         nfs=NFSVolumeSourceArgs(server=nfs_server, path=nfs_path),
#         mount_options=["vers=4"],
#         storage_class_name="",
#     ),
# )
nfs_pvc = PersistentVolumeClaim(
    "terraria-pvc",
    metadata=ObjectMetaArgs(namespace=terraria_namespace.metadata.name),
    spec=PersistentVolumeClaimSpecArgs(
        resources=VolumeResourceRequirementsArgs(requests={"storage": "10Gi"}),
        access_modes=["ReadWriteOnce"],
        storage_class_name="nfs-csi",
    ),
)
#
# expensive_persistent_volume = PersistentVolume(
#     "terraria-pv-rackspace",
#     metadata=ObjectMetaArgs(name="terraria-nfs-rackspace"),
#     spec={
#         "capacity": {"storage": "10Gi"},
#         "accessModes": ["ReadWriteOnce"],
#     },
# )
# terraria_pvc = PersistentVolumeClaim(
#     "terraria-pvc",
#     metadata=ObjectMetaArgs(
#         name="terraria-data-pvc", namespace=terraria_namespace.metadata.name
#     ),
#     spec={
#         "accessModes": ["ReadWriteOnce"],
#         "resources": {"requests": {"storage": "10Gi"}},
#     },
# )
# Create Terraria deployment
terraria_deployment = Deployment(
    "terraria",
    metadata=ObjectMetaArgs(
        name="terraria", namespace=terraria_namespace.metadata.name
    ),
    spec=DeploymentSpecArgs(
        selector={"matchLabels": {"app": "terraria"}},
        replicas=1,
        template=PodTemplateSpecArgs(
            metadata=ObjectMetaArgs(labels={"app": "terraria"}),
            spec=PodSpecArgs(
                init_containers=[
                    ContainerArgs(
                        name="init-permissions",
                        image="busybox",
                        command=[
                            "sh",
                            "-c",
                            "chown -R 1000:1000 /data && chmod -R 755 /data",
                        ],
                        volume_mounts=[
                            VolumeMountArgs(
                                name="nfs-mount",
                                mount_path="/data",
                            )
                        ],
                        security_context={
                            "runAsUser": 0,  # Run as root to change permissions
                            "allowPrivilegeEscalation": True,
                        },
                    )
                ],
                containers=[
                    ContainerArgs(
                        name="terraria",
                        image="hexlo/terraria-tmodloader-server:latest",
                        # command=["sh", "-c", "while sleep 3600; do :; done"],
                        command=[
                            "/hom/tml/manage-tModLoaderServer.sh start --folder=/home/tml/.local/share/Terraria/tModLoader"
                        ],
                        # command=[
                        #     "/home/tml/.local/share/Terraria/tModLoader/Scripts/entrypoint.sh"
                        # ],
                        ports=[ContainerPortArgs(container_port=7777, name="terraria")],
                        env=[
                            {"name": "WORLD_FILENAME", "value": "MyTerrariaWorld"},
                            {"name": "WORLD_SIZE", "value": "3"},  # Large world
                            {"name": "DIFFICULTY", "value": "1"},  # HardMode difficulty
                            {"name": "MAX_PLAYERS", "value": "8"},
                            {"name": "AUTOCREATE", "value": "3"},
                            {
                                "name": "PASSWORD",
                                "value": env_config["TERRARIA_WORLD_PASSWORD"],
                            },  # No password
                            {
                                "name": "MOTD",
                                "value": "Welcome to Terraria with tModLoader, Tyler is great!",
                            },
                        ],
                        volume_mounts=[
                            VolumeMountArgs(
                                name="nfs-mount",
                                mount_path="/home/tml/.local/share/Terraria/tModLoader/",
                            )
                        ],
                        security_context={
                            "runAsUser": 1000,  # Assuming the container runs as UID 1000
                            "runAsGroup": 1000,
                            "fsGroup": 1000,
                        },
                        stdin=True,
                        tty=True,
                    )
                ],
                volumes=[
                    VolumeArgs(
                        name="nfs-mount",
                        persistent_volume_claim=PersistentVolumeClaimVolumeSourceArgs(
                            claim_name=nfs_pvc.metadata.name
                        ),
                    )
                ],
            ),
        ),
    ),
)
# # Create Terraria service
terraria_service = Service(
    "terraria",
    metadata=ObjectMetaArgs(
        name="terraria", namespace=terraria_namespace.metadata.name
    ),
    spec={
        "selector": {"app": "terraria"},
        "ports": [ServicePortArgs(port=7777, target_port=7777, name="terraria")],
        "type": "ClusterIP",
    },
)

# Create IngressRoute for Terraria
terraria_ingress = CustomResource(
    "terraria_ingress_route",
    api_version="traefik.io/v1alpha1",
    kind="IngressRoute",
    metadata=ObjectMetaArgs(
        name="terraria", namespace=terraria_namespace.metadata.name
    ),
    spec={
        "entryPoints": ["web"],
        "routes": [
            {
                "match": "Host(`terraria.tylermarques.com`)",
                "kind": "Rule",
                "services": [{"name": terraria_service.metadata.name, "port": 7777}],
            }
        ],
    },
)

# Export the Terraria service endpoint
pulumi.export("terraria_service", terraria_service.metadata.name)
pulumi.export("terraria_namespace", terraria_namespace.metadata.name)
