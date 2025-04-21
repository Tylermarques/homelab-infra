import os
import pulumi
import pulumi_kubernetes as k8s


# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

u_the_bomb = k8s.yaml.ConfigFile(
    "u_the_bomb_com", os.path.join(current_dir, "u-the-bomb-com/argoApp.yaml")
)
