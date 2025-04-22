from pulumi_kubernetes.core.v1 import Namespace

namespace = Namespace(
    "monitoring",
    metadata={"name": "monitoring"},
)
