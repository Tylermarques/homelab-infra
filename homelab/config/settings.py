from pydantic_settings import BaseSettings
from pydantic import Field
import pulumi


class ProxmoxSettings(BaseSettings):
    """Proxmox VE API configuration loaded from environment variables."""

    endpoint: str = Field(alias="PROXMOX_VE_ENDPOINT")
    username: str = Field(alias="PROXMOX_VE_USERNAME")
    password: str = Field(alias="PROXMOX_VE_PASSWORD")
    insecure: bool = Field(default=True, alias="PROXMOX_VE_INSECURE")
    node_name: str = Field(default="proxmox")

    class Config:
        env_file = ".env"
        extra = "ignore"


class ClusterSettings(BaseSettings):
    """Cluster configuration loaded from environment and Pulumi config."""

    name: str = Field(default="homelab")
    talos_version: str = Field(default="v1.9.0")
    storage_pool: str = Field(default="local-lvm")
    network_bridge: str = Field(default="vmbr0")
    vip_hostname: str = Field(default="", alias="CLUSTER_VIP_HOSTNAME")

    class Config:
        env_file = ".env"
        env_prefix = "CLUSTER_"
        extra = "ignore"


class TailscaleSettings(BaseSettings):
    """Tailscale configuration for node networking."""

    authkey: str = Field(alias="TAILSCALE_AUTHKEY")

    class Config:
        env_file = ".env"
        extra = "ignore"


class TailscaleOperatorSettings(BaseSettings):
    """Tailscale operator OAuth credentials for Kubernetes."""

    client_id: str = Field(alias="TAILSCALE_OPERATOR_CLIENT_ID")
    client_secret: str = Field(alias="TAILSCALE_OPERATOR_CLIENT_SECRET")

    class Config:
        env_file = ".env"
        extra = "ignore"


# Load Pulumi config to override defaults
config = pulumi.Config("homelab-talos")

# Initialize settings instances
proxmox_settings = ProxmoxSettings()
proxmox_settings.node_name = config.get("proxmox_node") or proxmox_settings.node_name

cluster_settings = ClusterSettings()
cluster_settings.name = config.get("cluster_name") or cluster_settings.name
cluster_settings.talos_version = config.get("talos_version") or cluster_settings.talos_version
cluster_settings.storage_pool = config.get("storage_pool") or cluster_settings.storage_pool
cluster_settings.network_bridge = config.get("network_bridge") or cluster_settings.network_bridge

tailscale_settings = TailscaleSettings()
tailscale_operator_settings = TailscaleOperatorSettings()
