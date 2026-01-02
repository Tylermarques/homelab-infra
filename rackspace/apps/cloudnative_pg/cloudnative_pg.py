"""
CloudNativePG Operator Installation

This module installs the CloudNativePG operator via Helm chart.
The operator manages PostgreSQL clusters in Kubernetes using the Cluster custom resource.

Usage:
    After installing, create PostgreSQL clusters using the postgresql.cnpg.io/v1 Cluster CR.
    Connection services are automatically created:
    - <cluster-name>-rw.<namespace>.svc - Read-Write (primary)
    - <cluster-name>-ro.<namespace>.svc - Read-Only (replicas)
    - <cluster-name>-r.<namespace>.svc - Read (all instances)

    Credentials are stored in secrets:
    - <cluster-name>-app - Application credentials (username, password, uri, etc.)
    - <cluster-name>-superuser - Superuser credentials (if enabled)
"""

import pulumi
import pulumi_kubernetes as k8s

# Create namespace for CloudNativePG operator
cnpg_namespace = k8s.core.v1.Namespace(
    "cnpg-system",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="cnpg-system",
    ),
)

# Install CloudNativePG operator via Helm
cnpg_operator = k8s.helm.v3.Chart(
    "cloudnative-pg",
    k8s.helm.v3.ChartOpts(
        chart="cloudnative-pg",
        version="0.23.0",  # Stable version
        fetch_opts=k8s.helm.v3.FetchOpts(
            repo="https://cloudnative-pg.github.io/charts",
        ),
        namespace=cnpg_namespace.metadata.name,
        values={
            "replicaCount": 1,
            "monitoring": {
                "podMonitorEnabled": False,  # Enable if using Prometheus Operator
            },
        },
    ),
)


def create_postgres_cluster(
    name: str,
    namespace: str,
    instances: int = 1,
    storage_size: str = "10Gi",
    storage_class: str = "nfs-csi",
    database: str = "app",
    owner: str = "app",
    enable_superuser: bool = False,
    postgres_version: str = "17",
    resources: dict = None,
) -> k8s.apiextensions.CustomResource:
    """
    Create a CloudNativePG PostgreSQL Cluster.

    Args:
        name: Name of the cluster
        namespace: Kubernetes namespace
        instances: Number of PostgreSQL instances (1 for single, 3 for HA)
        storage_size: Size of persistent storage per instance
        storage_class: Kubernetes storage class to use
        database: Name of the application database to create
        owner: Owner of the application database
        enable_superuser: Whether to enable superuser access
        postgres_version: PostgreSQL major version
        resources: Resource requests/limits dict

    Returns:
        The created Cluster CustomResource

    Connection Info:
        - Service: {name}-rw.{namespace}.svc:5432
        - Secret: {name}-app (contains: username, password, uri, jdbc-uri, etc.)
    """
    cluster_spec = {
        "instances": instances,
        "imageName": f"ghcr.io/cloudnative-pg/postgresql:{postgres_version}",
        "storage": {
            "storageClass": storage_class,
            "size": storage_size,
        },
        "bootstrap": {
            "initdb": {
                "database": database,
                "owner": owner,
            },
        },
        "enableSuperuserAccess": enable_superuser,
        "postgresql": {
            "parameters": {
                "max_connections": "100",
                "shared_buffers": "256MB",
            },
        },
    }

    if resources:
        cluster_spec["resources"] = resources

    cluster = k8s.apiextensions.CustomResource(
        f"{name}-postgres-cluster",
        api_version="postgresql.cnpg.io/v1",
        kind="Cluster",
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name=name,
            namespace=namespace,
        ),
        spec=cluster_spec,
        opts=pulumi.ResourceOptions(
            depends_on=[cnpg_operator],
        ),
    )

    return cluster


# Export operator namespace
pulumi.export("cnpg-namespace", cnpg_namespace.metadata.name)
