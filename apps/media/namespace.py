import pulumi
import pulumi_kubernetes as k8s

# Create a new Pulumi namespace called "media"
media_namespace = k8s.core.v1.Namespace("media_namespace", metadata={"name": "media"})
