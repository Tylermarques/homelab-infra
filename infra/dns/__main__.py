"""A Kubernetes Python Pulumi program"""

from dotenv import dotenv_values
import pulumi
import pulumi_cloudflare as cloudflare

env_config = dotenv_values(".env")


mcg_zone = cloudflare.get_zone(name="marquescg.com")

# Note that there are MX records present in CF that are not here. Mostly because they should never need changing.
# the content for all these domains is the same, so do it in a loop
MCG_DOMAINS = ["marquescg.com", "meeting-tools", "twenty"]
for domain in MCG_DOMAINS:
    _ = cloudflare.Record(
        "MCG_" + domain,
        zone_id=mcg_zone.id,
        name=domain,
        content=env_config["HOME_IP"],
        type="A",
        proxied=True,
        allow_overwrite=True,
    )
# Have www redirect to marquescg.com
_ = cloudflare.Record(
    "MCG_www",
    zone_id=mcg_zone.id,
    name="www",
    content="marquescg.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)


tylermarques_zone = cloudflare.get_zone(name="tylermarques.com")

TM_NOT_PROXIED_DOMAINS = ["hass", "plex", "immich", "photoprism"]
TM_PROXIED_DOMAINS = [
    "tylermarques.com",
    "issues",
    "mealie",
    "ntfy",
    "overseerr",
]
for domain in TM_PROXIED_DOMAINS:
    _ = cloudflare.Record(
        "TM_" + domain,
        zone_id=tylermarques_zone.id,
        name=domain,
        content=env_config["HOME_IP"],
        type="A",
        proxied=True,
    )
for domain in TM_NOT_PROXIED_DOMAINS:
    _ = cloudflare.Record(
        "TM_" + domain,
        zone_id=tylermarques_zone.id,
        name=domain,
        content=env_config["HOME_IP"],
        type="A",
        # Turn off proxying for these domains
        proxied=False,
    )
_ = cloudflare.Record(
    "TM_www",
    zone_id=tylermarques_zone.id,
    name="www",
    content="tylermarques.com",
    type="CNAME",
    proxied=True,
)
