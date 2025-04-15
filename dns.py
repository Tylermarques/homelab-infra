from dotenv import dotenv_values
import pulumi
import pulumi_cloudflare as cloudflare


env_config = dotenv_values(".env")
mcg_zone = cloudflare.get_zone(name="marquescg.com")
tylermarques_zone = cloudflare.get_zone(name="tylermarques.com")
uthebomb_zone = cloudflare.get_zone(name="u-the-bomb.com")

rackspace_ip = env_config["RACKSPACE_IP"]
home_ip = env_config["HOME_IP"]

MCG_DOMAINS = {
    "marquescg.com": {
        "proxied": True,
        "content": home_ip,
    },
}
TM_DOMAINS = {
    "hass": {"proxied": False, "content": home_ip},
    "plex": {"proxied": False, "content": home_ip},
    "immich": {"proxied": False, "content": home_ip},
    "tylermarques.com": {"proxied": True, "content": home_ip},
    "overseerr": {"proxied": True, "content": home_ip},
    "mealie": {"proxied": True, "content": home_ip},
    "ntfy": {"proxied": True, "content": home_ip},
    "sftp": {"proxied": True, "content": home_ip},
    "terraria": {"proxied": False, "content": rackspace_ip},
}

BOMB_DOMAINS = {
    "u-the-bomb.com": {"proxied": True, "content": rackspace_ip},
}

# Note that there are MX records present in CF that are not here. Mostly because they should never need changing.
# the content for all these domains is the same, so do it in a loop
for prefix, domain_block, zone in [
    ("MCG", MCG_DOMAINS, mcg_zone),
    ("TM", TM_DOMAINS, tylermarques_zone),
    ("BOMB", BOMB_DOMAINS, uthebomb_zone),
]:
    for domain, options in domain_block.items():
        _ = cloudflare.Record(
            f"{prefix}_" + domain,
            zone_id=zone.id,
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
_ = cloudflare.Record(
    "TM_www",
    zone_id=tylermarques_zone.id,
    name="www",
    content="tylermarques.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)
_ = cloudflare.Record(
    "uthebomb_www",
    zone_id=uthebomb_zone.id,
    name="www",
    content="u-the-bomb.com",
    type="CNAME",
    proxied=True,
    allow_overwrite=True,
)
