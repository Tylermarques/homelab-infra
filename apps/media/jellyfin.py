import pulumi
import pulumi_kubernetes as k8s
from .volumes import create_nfs_pv_and_pvc
from .namespace import media_namespace
from ..dns import create_cloudflare_A_record, ALLOWED_DOMAINS, create_traefik_ingress

dns_record = create_cloudflare_A_record("jellyfin", ALLOWED_DOMAINS.TM)


def create_jellyfin_deployment(
    namespace=media_namespace.metadata.name,
    enabled=True,
    ingress_host="jellyfin.local",
    puid=1000,
    pgid=1000,
    nfs_config={
        "server": "proxmox-egress",
        "share_path": "/main/plex",
        "storage_size": "50Gi",
        "storage_class_name": "nfs-csi",
    },
    # Within the /main/plex/ dir, use these sub directories
    sub_paths={
        "config": "config/jellyfin",
        "movies": "library/movies",
        "tv": "library/tv",
    },
    node_selector={},
    replica_count=1,
    image="docker.io/linuxserver/jellyfin",
    tag="latest",
    port=8096,
    service_type="ClusterIP",
    ingress_enabled=True,
    ingress_class_name="",
    ingress_annotations={},
    ingress_tls_enabled=False,
    ingress_tls_secret_name="",
    resources={},
    use_tailscale=True,
):
    if not enabled:
        return None

    # Create Labels
    app_labels = {"app": "jellyfin"}

    # Create NFS PV and PVC
    nfs_storage = create_nfs_pv_and_pvc(
        name="jellyfin",
        namespace=namespace,
        server=nfs_config["server"],
        share_path=nfs_config["share_path"],
        storage_size=nfs_config["storage_size"],
        storage_class_name=nfs_config["storage_class_name"],
    )

    # Create Container environment variables
    env_vars = [
        k8s.core.v1.EnvVarArgs(name="PUID", value=str(puid)),
        k8s.core.v1.EnvVarArgs(name="PGID", value=str(pgid)),
        k8s.core.v1.EnvVarArgs(name="TZ", value="UTC"),
    ]

    # Create volume mounts
    volume_mounts = [
        k8s.core.v1.VolumeMountArgs(
            name="nfs-data",
            mount_path="/config",
            sub_path=sub_paths["config"],
        ),
        k8s.core.v1.VolumeMountArgs(
            name="nfs-data",
            mount_path="/data/movies",
            sub_path=sub_paths["movies"],
        ),
        k8s.core.v1.VolumeMountArgs(
            name="nfs-data",
            mount_path="/data/tvshows",
            sub_path=sub_paths["tv"],
        ),
    ]

    # Create pod spec with annotations when tailscale is enabled
    pod_metadata = k8s.meta.v1.ObjectMetaArgs(labels=app_labels)

    if use_tailscale:
        pod_metadata.annotations = {"tailscale.com/inject": "true"}

    # Create Deployment
    deployment = k8s.apps.v1.Deployment(
        "jellyfin",
        metadata=k8s.meta.v1.ObjectMetaArgs(namespace=namespace, labels=app_labels),
        spec=k8s.apps.v1.DeploymentSpecArgs(
            replicas=replica_count,
            selector=k8s.meta.v1.LabelSelectorArgs(match_labels=app_labels),
            template=k8s.core.v1.PodTemplateSpecArgs(
                metadata=pod_metadata,
                spec=k8s.core.v1.PodSpecArgs(
                    node_selector=node_selector,
                    containers=[
                        k8s.core.v1.ContainerArgs(
                            name="jellyfin",
                            image=f"{image}:{tag}",
                            ports=[
                                k8s.core.v1.ContainerPortArgs(
                                    container_port=port, name="http"
                                )
                            ],
                            env=env_vars,
                            volume_mounts=volume_mounts,
                            resources=k8s.core.v1.ResourceRequirementsArgs(**resources)
                            if resources
                            else None,
                        )
                    ],
                    volumes=[
                        k8s.core.v1.VolumeArgs(
                            name="nfs-data",
                            persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(
                                claim_name=nfs_storage["pvc"].metadata.name
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    # Create Service
    service = k8s.core.v1.Service(
        "jellyfin",
        metadata=k8s.meta.v1.ObjectMetaArgs(namespace=namespace, labels=app_labels),
        spec=k8s.core.v1.ServiceSpecArgs(
            type=service_type,
            ports=[
                k8s.core.v1.ServicePortArgs(port=port, target_port="http", name="http")
            ],
            selector=app_labels,
        ),
    )

    ingress = create_traefik_ingress(
        "jellyfin", ALLOWED_DOMAINS.TM, port, namespace=namespace
    )

    return {
        "pv": nfs_storage["pv"],
        "pvc": nfs_storage["pvc"],
        "deployment": deployment,
        "service": service,
        "ingress": ingress,
    }


# Export the resources if this file is being run directly
jellyfin = create_jellyfin_deployment()
if jellyfin:
    pulumi.export("jellyfin-pv", jellyfin["pv"].metadata.name)
    pulumi.export("jellyfin-pvc", jellyfin["pvc"].metadata.name)
    pulumi.export("jellyfin-deployment", jellyfin["deployment"].metadata.name)
    pulumi.export("jellyfin-service", jellyfin["service"].metadata.name)
    # if jellyfin["ingress"]:
    #     pulumi.export("jellyfin-ingress", jellyfin["ingress"].metadata.name)
