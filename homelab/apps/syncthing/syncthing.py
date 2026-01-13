import pulumi_kubernetes as k8s
from ..volumes import create_nfs_pv_and_pvc

# Create namespace for syncthing
namespace = k8s.core.v1.Namespace("syncthing", metadata={"name": "syncthing"})

# Create NFS PV/PVC for config
config_pv, config_pvc = create_nfs_pv_and_pvc(
    name="syncthing-config",
    namespace=namespace.metadata.name,
    share_path="/main/plex/syncthing/config",
    storage_size="1Gi",
)

# Create NFS PV/PVC for data
data_pv, data_pvc = create_nfs_pv_and_pvc(
    name="syncthing-data",
    namespace=namespace.metadata.name,
    share_path="/main/plex/syncthing/data",
    storage_size="50Gi",
)

# Common labels
labels = {"app": "syncthing"}

# StatefulSet for Syncthing
statefulset = k8s.apps.v1.StatefulSet(
    "syncthing",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="syncthing",
        namespace=namespace.metadata.name,
        labels=labels,
    ),
    spec=k8s.apps.v1.StatefulSetSpecArgs(
        replicas=1,
        service_name="syncthing",
        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=labels),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=k8s.meta.v1.ObjectMetaArgs(labels=labels),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name="syncthing",
                        image="syncthing/syncthing:latest",
                        env=[
                            k8s.core.v1.EnvVarArgs(name="TZ", value="America/Toronto"),
                        ],
                        ports=[
                            k8s.core.v1.ContainerPortArgs(container_port=8384, name="web-ui"),
                            k8s.core.v1.ContainerPortArgs(container_port=22000, name="sync-tcp"),
                            k8s.core.v1.ContainerPortArgs(container_port=22000, name="sync-udp", protocol="UDP"),
                            k8s.core.v1.ContainerPortArgs(container_port=21027, name="discovery", protocol="UDP"),
                        ],
                        volume_mounts=[
                            k8s.core.v1.VolumeMountArgs(name="config", mount_path="/var/syncthing/config"),
                            k8s.core.v1.VolumeMountArgs(name="data", mount_path="/var/syncthing/data"),
                        ],
                        liveness_probe=k8s.core.v1.ProbeArgs(
                            http_get=k8s.core.v1.HTTPGetActionArgs(path="/rest/noauth/health", port=8384),
                            initial_delay_seconds=30,
                            period_seconds=60,
                        ),
                        readiness_probe=k8s.core.v1.ProbeArgs(
                            http_get=k8s.core.v1.HTTPGetActionArgs(path="/rest/noauth/health", port=8384),
                            initial_delay_seconds=10,
                            period_seconds=10,
                        ),
                    )
                ],
                volumes=[
                    k8s.core.v1.VolumeArgs(
                        name="config",
                        persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(
                            claim_name=config_pvc.metadata.name
                        ),
                    ),
                    k8s.core.v1.VolumeArgs(
                        name="data",
                        persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(
                            claim_name=data_pvc.metadata.name
                        ),
                    ),
                ],
            ),
        ),
    ),
)

# Tailscale LoadBalancer Service
service = k8s.core.v1.Service(
    "syncthing",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="syncthing",
        namespace=namespace.metadata.name,
        labels=labels,
        annotations={
            "tailscale.com/expose": "true",
            "tailscale.com/hostname": "syncthing",
        },
    ),
    spec=k8s.core.v1.ServiceSpecArgs(
        type="LoadBalancer",
        load_balancer_class="tailscale",
        selector=labels,
        ports=[
            k8s.core.v1.ServicePortArgs(name="web-ui", port=8384, target_port="web-ui"),
            k8s.core.v1.ServicePortArgs(name="sync-tcp", port=22000, target_port="sync-tcp"),
        ],
    ),
)
