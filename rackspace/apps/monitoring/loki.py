# components/loki.py
import pulumi_kubernetes as k8s
from dotenv import dotenv_values

from .namespace import namespace

env_config = dotenv_values(".env")

"""
Deploy Grafana Loki in *Distributed* mode with the exact settings
recommended by the upstream docs (schema v13, S3 storage via Garage,
three‑replica quorum, etc.).

Loki connects to Garage S3 storage deployed in the home cluster.
Credentials are loaded from environment variables:
  - GARAGE_LOKI_ACCESS_KEY
  - GARAGE_LOKI_SECRET_KEY
"""

chart = k8s.helm.v3.Chart(
    "loki",
    k8s.helm.v3.ChartOpts(
        chart="loki",
        fetch_opts=k8s.helm.v3.FetchOpts(
            repo="https://grafana.github.io/helm-charts",
        ),
        namespace=namespace.metadata.name,
        #
        # ───────────────────────────── values.yaml ─────────────────────────────
        #
        values={
            # Top‑level deployment mode
            "deploymentMode": "Distributed",
            # ── Core Loki config ────────────────────────────────────────────
            "loki": {
                "schemaConfig": {
                    "configs": [
                        {
                            "from": "2024-04-01",
                            "store": "tsdb",
                            "object_store": "s3",
                            "schema": "v13",
                            "index": {
                                "prefix": "loki_index_",
                                "period": "24h",
                            },
                        }
                    ]
                },
                # ── Garage S3 Storage Configuration ────────────────────────
                "storage": {
                    "type": "s3",
                    "s3": {
                        "endpoint": "http://garage-s3.garage.svc.cluster.local:3900",
                        "bucketnames": "loki",
                        "access_key_id": env_config.get("GARAGE_LOKI_ACCESS_KEY", ""),
                        "secret_access_key": env_config.get("GARAGE_LOKI_SECRET_KEY", ""),
                        "s3forcepathstyle": True,
                        "insecure": True,
                    },
                },
                "ingester": {
                    "chunk_encoding": "snappy",
                },
                "querier": {
                    "max_concurrent": 4,
                },
                "pattern_ingester": {
                    "enabled": True,
                },
                "limits_config": {
                    "allow_structured_metadata": True,
                    "volume_enabled": True,
                },
            },
            # ── Per‑component replica counts / disruption budgets ───────────
            "ingester": {
                "replicas": 3,
                "zoneAwareReplication": {"enabled": False},
            },
            "querier": {
                "replicas": 3,
                "maxUnavailable": 2,
            },
            "queryFrontend": {
                "replicas": 2,
                "maxUnavailable": 1,
            },
            "queryScheduler": {
                "replicas": 2,
            },
            "distributor": {
                "replicas": 3,
                "maxUnavailable": 2,
            },
            "compactor": {
                "replicas": 1,
            },
            "indexGateway": {
                "replicas": 2,
                "maxUnavailable": 1,
            },
            # Disable unused bloom‑filter and read/write split components
            "bloomPlanner": {"replicas": 0},
            "bloomBuilder": {"replicas": 0},
            "bloomGateway": {"replicas": 0},
            "backend": {"replicas": 0},
            "read": {"replicas": 0},
            "write": {"replicas": 0},
            "singleBinary": {"replicas": 0},
            # ── External access ─────────────────────────────────────────────
            "gateway": {
                "service": {"type": "LoadBalancer"},
            },
            # ── Built‑in MinIO (quick‑start, NOT FOR PROD) ─────────────────
            #     • 10 Gi PVC by default
            #     • AWS‑style env vars injected into Loki components
            "minio": {
                "enabled": False,
            },
        },
    ),
)
