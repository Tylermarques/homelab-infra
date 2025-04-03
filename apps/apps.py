import os
import pulumi
import pulumi_kubernetes as k8s


# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

tylermarques_com = k8s.yaml.ConfigFile(
    "tylermarques_com", os.path.join(current_dir, "tylermarques-com/argoApp.yaml")
)
marquescg_com = k8s.yaml.ConfigFile(
    "marquescg_com", os.path.join(current_dir, "marquescg-com/argoApp.yaml")
)

u_the_bomb = k8s.yaml.ConfigFile(
    "u_the_bomb_com", os.path.join(current_dir, "u-the-bomb-com/argoApp.yaml")
)
