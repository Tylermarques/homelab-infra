import pulumi
import pulumi_kubernetes as k8s
from ..volumes import create_nfs_pv_and_pvc
from .namespace import media_namespace
from ..dns import create_cloudflare_A_record, ALLOWED_DOMAINS, create_traefik_ingress

dns_record = create_cloudflare_A_record("jellyseerr", ALLOWED_DOMAINS.TM)


def create_jellyseerr_deployment(
    namespace=media_namespace.metadata.name,
    enabled=True,
    ingress_host="jellyseerr.local",
    puid=1000,
    pgid=1000,
    nfs_config={
        "server": "proxmox-egress",
        "share_path": "/main/plex",
        "storage_size": "10Gi",
        "storage_class_name": "nfs-csi",
    },
    # Within the /main/plex/ dir, use these sub directories
    sub_paths={
        "config": "config/jellyseerr",
        "cache": "config/jellyseerr/cache",
    },
    node_selector={},
    replica_count=1,
    # Using the preview-music-support tag for Lidarr support
    # See: https://github.com/Fallenbagel/jellyseerr/pull/1238
    # and: https://github.com/Fallenbagel/jellyseerr/pull/2132
    image="docker.io/fallenbagel/jellyseerr",
    tag="preview-music-support",
    port=5055,
    service_type="ClusterIP",
    resources={},
    use_tailscale=True,
):
    """
    Create a Jellyseerr deployment with Lidarr/music support.

    Jellyseerr is a media request management and discovery tool for Jellyfin, Plex, and Emby.
    This deployment uses the preview-music-support tag which includes Lidarr integration
    for music request management.

    Args:
        namespace: Kubernetes namespace for the deployment
        enabled: Whether to create the deployment
        ingress_host: Hostname for ingress (used for DNS)
        puid: Process user ID for file permissions
        pgid: Process group ID for file permissions
        nfs_config: NFS storage configuration
        sub_paths: Sub-paths within the NFS share for config and cache
        node_selector: Kubernetes node selector
        replica_count: Number of replicas
        image: Docker image to use
        tag: Docker image tag (default: preview-music-support for Lidarr support)
        port: Container port (default: 5055)
        service_type: Kubernetes service type
        resources: Resource requirements/limits
        use_tailscale: Whether to inject Tailscale sidecar

    Returns:
        Dictionary containing all created Kubernetes resources
    """
    if not enabled:
        return None

    # Create Labels
    app_labels = {"app": "jellyseerr"}

    # Create NFS PV and PVC
    pv, pvc = create_nfs_pv_and_pvc(
        name="jellyseerr",
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
        k8s.core.v1.EnvVarArgs(name="TZ", value="America/Toronto"),
        k8s.core.v1.EnvVarArgs(name="LOG_LEVEL", value="info"),
        k8s.core.v1.EnvVarArgs(name="PORT", value=str(port)),
    ]

    # Create volume mounts
    volume_mounts = [
        k8s.core.v1.VolumeMountArgs(
            name="nfs-data",
            mount_path="/app/config",
            sub_path=sub_paths["config"],
        ),
        # Cache mount for Lidarr music artwork caching
        k8s.core.v1.VolumeMountArgs(
            name="nfs-data",
            mount_path="/app/config/cache",
            sub_path=sub_paths["cache"],
        ),
    ]

    # Create pod spec with annotations when tailscale is enabled
    pod_metadata = k8s.meta.v1.ObjectMetaArgs(labels=app_labels)

    if use_tailscale:
        pod_metadata.annotations = {"tailscale.com/inject": "true"}

    # Create Deployment
    deployment = k8s.apps.v1.Deployment(
        "jellyseerr",
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
                            name="jellyseerr",
                            image=f"{image}:{tag}",
                            ports=[k8s.core.v1.ContainerPortArgs(container_port=port, name="http")],
                            env=env_vars,
                            volume_mounts=volume_mounts,
                            resources=k8s.core.v1.ResourceRequirementsArgs(**resources) if resources else None,
                        )
                    ],
                    volumes=[
                        k8s.core.v1.VolumeArgs(
                            name="nfs-data",
                            persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(claim_name=pvc.metadata.name),
                        )
                    ],
                ),
            ),
        ),
    )

    # Create Service
    service = k8s.core.v1.Service(
        "jellyseerr",
        metadata=k8s.meta.v1.ObjectMetaArgs(namespace=namespace, labels=app_labels),
        spec=k8s.core.v1.ServiceSpecArgs(
            type=service_type,
            ports=[k8s.core.v1.ServicePortArgs(port=port, target_port="http", name="http")],
            selector=app_labels,
        ),
    )

    ingress = create_traefik_ingress("jellyseerr", ALLOWED_DOMAINS.TM, port, namespace=namespace)

    return {
        "pv": pv,
        "pvc": pvc,
        "deployment": deployment,
        "service": service,
        "ingress": ingress,
    }


# Export the resources if this file is being run directly
jellyseerr = create_jellyseerr_deployment()
if jellyseerr:
    pulumi.export("jellyseerr-pv", jellyseerr["pv"].metadata.name)
    pulumi.export("jellyseerr-pvc", jellyseerr["pvc"].metadata.name)
    pulumi.export("jellyseerr-deployment", jellyseerr["deployment"].metadata.name)
    pulumi.export("jellyseerr-service", jellyseerr["service"].metadata.name)
