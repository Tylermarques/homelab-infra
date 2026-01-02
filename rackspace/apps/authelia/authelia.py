"""
Authelia Authentication Server

This module deploys Authelia for SSO and MFA authentication.
It integrates with Traefik via ForwardAuth middleware.

Components:
- Authelia server (Helm chart)
- Redis for session storage
- PostgreSQL for user/config storage (via CloudNativePG)
- Traefik ForwardAuth middleware

Usage:
    To protect a service with Authelia, add the middleware to your IngressRoute:
    
    middlewares:
      - name: authelia-forwardauth
        namespace: authelia
"""

import pulumi
import pulumi_kubernetes as k8s
from pulumi import ResourceOptions
from dotenv import dotenv_values

from ..dns import create_traefik_ingress, create_cloudflare_A_record, ALLOWED_DOMAINS
from ..cloudnative_pg.cloudnative_pg import create_postgres_cluster
from ..volumes import create_cloud_voume

env_config = dotenv_values(".env")

# Create namespace for Authelia
namespace = k8s.core.v1.Namespace(
    "authelia",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia",
    ),
)

# ==================== PostgreSQL Database ====================
authelia_postgres = create_postgres_cluster(
    name="authelia-db",
    namespace=namespace.metadata.name,
    instances=1,
    storage_size="5Gi",
    database="authelia",
    owner="authelia",
)

# ==================== Redis for Session Storage ====================
redis_labels = {"app": "authelia", "component": "redis"}

redis_pvc = create_cloud_voume(
    name="authelia-redis",
    namespace=namespace.metadata.name,
    storage_size=5,
)

redis_deployment = k8s.apps.v1.Deployment(
    "authelia-redis",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-redis",
        namespace=namespace.metadata.name,
        labels=redis_labels,
    ),
    spec=k8s.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=redis_labels),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=k8s.meta.v1.ObjectMetaArgs(labels=redis_labels),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name="redis",
                        image="redis:7-alpine",
                        ports=[
                            k8s.core.v1.ContainerPortArgs(
                                container_port=6379,
                                name="redis",
                            )
                        ],
                        args=["--save", "60", "1", "--loglevel", "warning"],
                        volume_mounts=[
                            k8s.core.v1.VolumeMountArgs(
                                name="redis-data",
                                mount_path="/data",
                            )
                        ],
                        resources=k8s.core.v1.ResourceRequirementsArgs(
                            requests={"memory": "64Mi", "cpu": "50m"},
                            limits={"memory": "256Mi", "cpu": "200m"},
                        ),
                    )
                ],
                volumes=[
                    k8s.core.v1.VolumeArgs(
                        name="redis-data",
                        persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(
                            claim_name=redis_pvc.metadata.name
                        ),
                    )
                ],
            ),
        ),
    ),
)

redis_service = k8s.core.v1.Service(
    "authelia-redis",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-redis",
        namespace=namespace.metadata.name,
        labels=redis_labels,
    ),
    spec=k8s.core.v1.ServiceSpecArgs(
        type="ClusterIP",
        ports=[
            k8s.core.v1.ServicePortArgs(
                port=6379,
                target_port="redis",
                name="redis",
            )
        ],
        selector=redis_labels,
    ),
)

# ==================== Authelia Secrets ====================
# These secrets should be managed externally or via a secrets manager
# For now, we create placeholder secrets that should be updated

# JWT secret for token signing
authelia_jwt_secret = k8s.core.v1.Secret(
    "authelia-jwt-secret",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-jwt-secret",
        namespace=namespace.metadata.name,
    ),
    string_data={
        "JWT_SECRET": env_config.get("AUTHELIA_JWT_SECRET", "CHANGE_ME_GENERATE_RANDOM_SECRET"),
    },
)

# Session secret
authelia_session_secret = k8s.core.v1.Secret(
    "authelia-session-secret",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-session-secret",
        namespace=namespace.metadata.name,
    ),
    string_data={
        "SESSION_SECRET": env_config.get("AUTHELIA_SESSION_SECRET", "CHANGE_ME_GENERATE_RANDOM_SECRET"),
    },
)

# Storage encryption key
authelia_storage_secret = k8s.core.v1.Secret(
    "authelia-storage-secret",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-storage-secret",
        namespace=namespace.metadata.name,
    ),
    string_data={
        "STORAGE_ENCRYPTION_KEY": env_config.get("AUTHELIA_STORAGE_KEY", "CHANGE_ME_GENERATE_RANDOM_SECRET_MIN_20_CHARS"),
    },
)

# ==================== Authelia ConfigMap ====================
authelia_config = k8s.core.v1.ConfigMap(
    "authelia-config",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-config",
        namespace=namespace.metadata.name,
    ),
    data={
        "configuration.yml": """
# Authelia Configuration
# See: https://www.authelia.com/configuration/

theme: auto

server:
  address: 'tcp://:9091'

log:
  level: info

totp:
  issuer: tylermarques.com
  period: 30
  skew: 1

authentication_backend:
  file:
    path: /config/users_database.yml
    password:
      algorithm: argon2id
      iterations: 3
      memory: 65536
      parallelism: 4
      key_length: 32
      salt_length: 16

access_control:
  default_policy: deny
  rules:
    # Public endpoints
    - domain: 'auth.tylermarques.com'
      policy: bypass
    # Default: require two-factor for all other domains
    - domain: '*.tylermarques.com'
      policy: two_factor

session:
  name: authelia_session
  same_site: lax
  expiration: 1h
  inactivity: 5m
  remember_me: 1M
  cookies:
    - domain: tylermarques.com
      authelia_url: https://auth.tylermarques.com
      default_redirection_url: https://tylermarques.com

  redis:
    host: authelia-redis
    port: 6379

regulation:
  max_retries: 3
  find_time: 2m
  ban_time: 5m

storage:
  postgres:
    address: 'tcp://authelia-db-rw:5432'
    database: authelia
    username: authelia
    timeout: 5s

notifier:
  disable_startup_check: false
  filesystem:
    filename: /config/notification.txt
"""
    },
)

# Users database ConfigMap (for file-based auth backend)
# In production, consider using LDAP or OIDC
authelia_users_config = k8s.core.v1.ConfigMap(
    "authelia-users-config",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-users-config",
        namespace=namespace.metadata.name,
    ),
    data={
        "users_database.yml": """
# Users database for Authelia
# Generate password hashes with: docker run --rm authelia/authelia:latest authelia crypto hash generate argon2
users:
  admin:
    disabled: false
    displayname: "Admin User"
    # Default password: changeme (CHANGE THIS!)
    # Generate new hash: docker run --rm authelia/authelia:latest authelia crypto hash generate argon2
    password: "$argon2id$v=19$m=65536,t=3,p=4$placeholder$placeholder"
    email: admin@tylermarques.com
    groups:
      - admins
      - users
"""
    },
)

# ==================== Authelia Deployment ====================
authelia_labels = {"app": "authelia", "component": "server"}

authelia_deployment = k8s.apps.v1.Deployment(
    "authelia",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia",
        namespace=namespace.metadata.name,
        labels=authelia_labels,
    ),
    spec=k8s.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=authelia_labels),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=k8s.meta.v1.ObjectMetaArgs(labels=authelia_labels),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name="authelia",
                        image="authelia/authelia:4.38",
                        ports=[
                            k8s.core.v1.ContainerPortArgs(
                                container_port=9091,
                                name="http",
                            )
                        ],
                        env=[
                            k8s.core.v1.EnvVarArgs(name="TZ", value="America/Toronto"),
                            k8s.core.v1.EnvVarArgs(
                                name="AUTHELIA_JWT_SECRET_FILE",
                                value="/secrets/jwt/JWT_SECRET",
                            ),
                            k8s.core.v1.EnvVarArgs(
                                name="AUTHELIA_SESSION_SECRET_FILE",
                                value="/secrets/session/SESSION_SECRET",
                            ),
                            k8s.core.v1.EnvVarArgs(
                                name="AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE",
                                value="/secrets/storage/STORAGE_ENCRYPTION_KEY",
                            ),
                            k8s.core.v1.EnvVarArgs(
                                name="AUTHELIA_STORAGE_POSTGRES_PASSWORD_FILE",
                                value="/secrets/postgres/password",
                            ),
                        ],
                        volume_mounts=[
                            k8s.core.v1.VolumeMountArgs(
                                name="config",
                                mount_path="/config/configuration.yml",
                                sub_path="configuration.yml",
                            ),
                            k8s.core.v1.VolumeMountArgs(
                                name="users",
                                mount_path="/config/users_database.yml",
                                sub_path="users_database.yml",
                            ),
                            k8s.core.v1.VolumeMountArgs(
                                name="jwt-secret",
                                mount_path="/secrets/jwt",
                                read_only=True,
                            ),
                            k8s.core.v1.VolumeMountArgs(
                                name="session-secret",
                                mount_path="/secrets/session",
                                read_only=True,
                            ),
                            k8s.core.v1.VolumeMountArgs(
                                name="storage-secret",
                                mount_path="/secrets/storage",
                                read_only=True,
                            ),
                            k8s.core.v1.VolumeMountArgs(
                                name="postgres-secret",
                                mount_path="/secrets/postgres",
                                read_only=True,
                            ),
                        ],
                        resources=k8s.core.v1.ResourceRequirementsArgs(
                            requests={"memory": "128Mi", "cpu": "100m"},
                            limits={"memory": "512Mi", "cpu": "500m"},
                        ),
                        liveness_probe=k8s.core.v1.ProbeArgs(
                            http_get=k8s.core.v1.HTTPGetActionArgs(
                                path="/api/health",
                                port="http",
                            ),
                            initial_delay_seconds=30,
                            period_seconds=10,
                        ),
                        readiness_probe=k8s.core.v1.ProbeArgs(
                            http_get=k8s.core.v1.HTTPGetActionArgs(
                                path="/api/health",
                                port="http",
                            ),
                            initial_delay_seconds=5,
                            period_seconds=5,
                        ),
                    )
                ],
                volumes=[
                    k8s.core.v1.VolumeArgs(
                        name="config",
                        config_map=k8s.core.v1.ConfigMapVolumeSourceArgs(
                            name=authelia_config.metadata.name,
                        ),
                    ),
                    k8s.core.v1.VolumeArgs(
                        name="users",
                        config_map=k8s.core.v1.ConfigMapVolumeSourceArgs(
                            name=authelia_users_config.metadata.name,
                        ),
                    ),
                    k8s.core.v1.VolumeArgs(
                        name="jwt-secret",
                        secret=k8s.core.v1.SecretVolumeSourceArgs(
                            secret_name=authelia_jwt_secret.metadata.name,
                        ),
                    ),
                    k8s.core.v1.VolumeArgs(
                        name="session-secret",
                        secret=k8s.core.v1.SecretVolumeSourceArgs(
                            secret_name=authelia_session_secret.metadata.name,
                        ),
                    ),
                    k8s.core.v1.VolumeArgs(
                        name="storage-secret",
                        secret=k8s.core.v1.SecretVolumeSourceArgs(
                            secret_name=authelia_storage_secret.metadata.name,
                        ),
                    ),
                    k8s.core.v1.VolumeArgs(
                        name="postgres-secret",
                        secret=k8s.core.v1.SecretVolumeSourceArgs(
                            secret_name="authelia-db-app",  # Auto-generated by CloudNativePG
                        ),
                    ),
                ],
            ),
        ),
    ),
    opts=ResourceOptions(depends_on=[authelia_postgres, redis_deployment]),
)

authelia_service = k8s.core.v1.Service(
    "authelia",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia",
        namespace=namespace.metadata.name,
        labels=authelia_labels,
    ),
    spec=k8s.core.v1.ServiceSpecArgs(
        type="ClusterIP",
        ports=[
            k8s.core.v1.ServicePortArgs(
                port=9091,
                target_port="http",
                name="http",
            )
        ],
        selector=authelia_labels,
    ),
)

# ==================== Traefik ForwardAuth Middleware ====================
# This middleware can be referenced by other IngressRoutes to protect services
authelia_forwardauth_middleware = k8s.apiextensions.CustomResource(
    "authelia-forwardauth",
    api_version="traefik.io/v1alpha1",
    kind="Middleware",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-forwardauth",
        namespace=namespace.metadata.name,
    ),
    spec={
        "forwardAuth": {
            "address": "http://authelia.authelia.svc.cluster.local:9091/api/authz/forward-auth",
            "trustForwardHeader": True,
            "authResponseHeaders": [
                "Remote-User",
                "Remote-Groups",
                "Remote-Email",
                "Remote-Name",
            ],
        },
    },
)

# Basic auth middleware (simpler, no MFA)
authelia_basic_middleware = k8s.apiextensions.CustomResource(
    "authelia-basic",
    api_version="traefik.io/v1alpha1",
    kind="Middleware",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="authelia-basic",
        namespace=namespace.metadata.name,
    ),
    spec={
        "forwardAuth": {
            "address": "http://authelia.authelia.svc.cluster.local:9091/api/authz/forward-auth/basic",
            "trustForwardHeader": True,
            "authResponseHeaders": [
                "Remote-User",
                "Remote-Groups",
                "Remote-Email",
                "Remote-Name",
            ],
        },
    },
)

# ==================== Ingress & DNS ====================
# Create DNS record for auth subdomain
create_cloudflare_A_record("auth", ALLOWED_DOMAINS.TM)

# Create ingress for Authelia
authelia_ingress = create_traefik_ingress(
    subdomain="auth",
    host_domain=ALLOWED_DOMAINS.TM,
    service_port=9091,
    namespace=namespace.metadata.name,
    service_name="authelia",
)

# Export resources
pulumi.export("authelia-namespace", namespace.metadata.name)
pulumi.export("authelia-postgres-cluster", authelia_postgres.metadata.name)
pulumi.export("authelia-redis-service", redis_service.metadata.name)
pulumi.export("authelia-deployment", authelia_deployment.metadata.name)
pulumi.export("authelia-service", authelia_service.metadata.name)
pulumi.export("authelia-forwardauth-middleware", authelia_forwardauth_middleware.metadata["name"])
