# Home kiosk

`https://floorplan.local.tylermarques.com` is a wall-panel version of the
illustrated Home Assistant floor plan, built for the old iPad (iPad 4, iOS
12.5.8). As of 2026.10, Home Assistant's own frontend fails on iOS 12. Its
legacy `frontend_es5` build ships BigInt literals (`0n`), which Safari only
supports from version 14. The companion app shows "Unable to connect to Home
Assistant" because it renders that same frontend.

This service serves a plain ES5 page and proxies a fixed slice of the HA REST
API:

- `GET /api/state` returns the sun, the kitchen and living room lights, the
  three room temperature/humidity sensors and `weather.forecast_home`.
- `POST /api/toggle/<kitchen|living_room>` calls `light.toggle`.

Nothing else in HA can be reached through it. The HA token stays in the
cluster. The page has no login, so anyone on the LAN who can resolve
`*.local.tylermarques.com` can toggle those two lights.

ArgoCD syncs `manifests/` through the `home-kiosk` Application in
`homecluster/app-of-apps/applications/`. That Application uses server-side
apply because the image ConfigMaps are larger than the 256 KiB
`last-applied-configuration` annotation that client-side apply writes.

## HA token

The Deployment reads a long-lived access token from the `home-kiosk-ha-token`
Secret. It is created out of band and is not stored in git:

```sh
kubectl --context k3s-homelab -n default create secret generic home-kiosk-ha-token \
  --from-literal=token=<long-lived access token>
```

Create the token in HA under Profile → Security → Long-lived access tokens.
After rotating it, run `kubectl rollout restart deployment/home-kiosk`.

## Artwork

`manifests/images/*.jpg` are 2048×1536 4:3 crops (x 2%–77%) of the 16:9 panel
art from `~/Documents/1089 Wilson/ha-floorplan/ha`. They are pre-composited
because iOS 12 cannot decode WebP. The variants are `day` and `night`, plus
`night-kitchen`, `night-living` and `night-both` with the light overlays applied.
Element positions in `app/index.html` are percentages of that crop. The server
adds a content hash to the image URLs, so the iPad picks up new art without
waiting for its one-day cache to expire.

## iPad setup

1. In Safari, open `https://floorplan.local.tylermarques.com` and choose
   Share → Add to Home Screen. Launched from there, it runs full screen.
2. Set Settings → Display & Brightness → Auto-Lock to Never.
3. Optionally, lock the iPad to the page with Settings → General →
   Accessibility → Guided Access.
