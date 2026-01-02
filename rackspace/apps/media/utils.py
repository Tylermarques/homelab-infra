import pulumi_kubernetes as k8s


def get_health_probes(port="http", path="/", initial_delay=30, liveness_delay=60):
    """Get default health probes for media applications"""
    return {
        "readiness_probe": k8s.core.v1.ProbeArgs(
            http_get=k8s.core.v1.HTTPGetActionArgs(
                path=path,
                port=port
            ),
            initial_delay_seconds=initial_delay,
            period_seconds=10
        ),
        "liveness_probe": k8s.core.v1.ProbeArgs(
            http_get=k8s.core.v1.HTTPGetActionArgs(
                path=path,
                port=port
            ),
            initial_delay_seconds=liveness_delay,
            period_seconds=30
        )
    }


def get_security_context(puid=1000, pgid=1000):
    """Get default security context for media applications"""
    return k8s.core.v1.PodSecurityContextArgs(
        run_as_user=puid,
        run_as_group=pgid,
        fs_group=pgid,
    )