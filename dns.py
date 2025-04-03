from dotenv import dotenv_values
import pulumi
import pulumi_cloudflare as cloudflare


env_config = dotenv_values(".env")
mcg_zone = cloudflare.get_zone(name="marquescg.com")
tylermarques_zone = cloudflare.get_zone(name="tylermarques.com")

MCG_DOMAINS = {
    "marquescg.com": {
        "proxied": True,
        "content": env_config["RACKSPACE_IP"],
    },
}
TM_DOMAINS = {
    "hass": {"proxied": False, "content": env_config["HOME_IP"]},
    "plex": {"proxied": False, "content": env_config["HOME_IP"]},
    "immich": {"proxied": False, "content": env_config["HOME_IP"]},
    "tylermarques.com": {"proxied": True, "content": env_config["HOME_IP"]},
    "overseerr": {"proxied": True, "content": env_config["HOME_IP"]},
    "mealie": {"proxied": True, "content": env_config["HOME_IP"]},
    "ntfy": {"proxied": True, "content": env_config["HOME_IP"]},
}
# Note that there are MX records present in CF that are not here. Mostly because they should never need changing.
# the content for all these domains is the same, so do it in a loop
for domain, options in MCG_DOMAINS.items():
    _ = cloudflare.Record(
        "MCG_" + domain,
        zone_id=mcg_zone.id,
        name=domain,
        content=options["content"],
        type="A",
        proxied=options["proxied"],
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
for domain, options in TM_DOMAINS.items():
    _ = cloudflare.Record(
        "TM_" + domain,
        zone_id=tylermarques_zone.id,
        name=domain,
        content=options["content"],
        type="A",
        proxied=options["proxied"],
        allow_overwrite=True,
    )
_ = cloudflare.Record(
    "TM_www",
    zone_id=tylermarques_zone.id,
    name="www",
    content="tylermarques.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)
