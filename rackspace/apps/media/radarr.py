import pulumi
import pulumi_kubernetes as k8s
from ..volumes import create_nfs_pv_and_pvc
from .namespace import media_namespace


def create_radarr_deployment(
    namespace=media_namespace.metadata.name,
    enabled=True,
    ingress_host="radarr.local",
    puid=1000,
    pgid=1000,
    nfs_config={
        "server": "proxmox-egress",
        "share_path": "/main/plex",
        "storage_size": "50Gi",
        "storage_class_name": "nfs-csi",
    },
    sub_paths={
        "config": "config/radarr",
        "movies": "library/movies",
        "downloads": "library/downloads",
    },
    node_selector={},
    replica_count=1,
    image="docker.io/linuxserver/radarr",
    tag="latest",
    port=7878,
    service_type="ClusterIP",
    resources={},
    use_tailscale=True,
):
    if not enabled:
        return None

    # Create Labels
    app_labels = {"app": "radarr"}

    # Create NFS PV and PVC
    pv, pvc = create_nfs_pv_and_pvc(
        name="radarr",
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
            mount_path="/movies",
            sub_path=sub_paths["movies"],
        ),
        k8s.core.v1.VolumeMountArgs(
            name="nfs-data",
            mount_path="/downloads",
            sub_path=sub_paths["downloads"],
        ),
    ]

    # Create pod spec with annotations when tailscale is enabled
    pod_metadata = k8s.meta.v1.ObjectMetaArgs(labels=app_labels)

    if use_tailscale:
        pod_metadata.annotations = {"tailscale.com/inject": "true"}

    # Create Deployment
    deployment = k8s.apps.v1.Deployment(
        "radarr",
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
                            name="radarr",
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
        "radarr",
        metadata=k8s.meta.v1.ObjectMetaArgs(namespace=namespace, labels=app_labels),
        spec=k8s.core.v1.ServiceSpecArgs(
            type=service_type,
            ports=[k8s.core.v1.ServicePortArgs(port=port, target_port="http", name="http")],
            selector=app_labels,
        ),
    )

    # Radarr is local-only, no ingress needed
    ingress = None

    return {
        "pv": pv,
        "pvc": pvc,
        "deployment": deployment,
        "service": service,
        "ingress": ingress,
    }


# Export the resources if this file is being run directly
radarr = create_radarr_deployment()
if radarr:
    pulumi.export("radarr-pv", radarr["pv"].metadata.name)
    pulumi.export("radarr-pvc", radarr["pvc"].metadata.name)
    pulumi.export("radarr-deployment", radarr["deployment"].metadata.name)
    pulumi.export("radarr-service", radarr["service"].metadata.name)
