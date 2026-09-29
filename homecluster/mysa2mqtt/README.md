# mysa2mqtt

Bridges the three Mysa baseboard thermostats into Home Assistant over MQTT
auto-discovery. Added 2026-09-29.

## Why this and not the HACS integration

Mysa exposes no local API, so every integration option is cloud-based: an AWS
Cognito login with the Mysa account password, then `app-prod.mysa.cloud` for
REST and AWS IoT MQTT-over-WebSocket for real-time state.

The HomeKit route is not available. The thermostats advertise no `_hap._tcp`
service and have no TCP port open at all, so `homekit_controller` has nothing to
pair with.

The alternative, the `kgelinas/Mysa_HA` HACS integration, exposes more
Mysa-specific settings but had no maintainer commit between 2026-03-22 and this
deployment, with open bugs that hit exactly this setup: telemetry freezing at
startup values on legacy baseboards, and dropped commands when controlling
several thermostats. mysa2mqtt was on a weekly release cadence instead.

It is a single-maintainer project against an unsanctioned API, and it went quiet
for four months in early 2026 while the maintainer was ill. Mysa can break it
without warning.

## Layout

- Runs in its own namespace with no Service. It only makes outbound
  connections: Mysa's cloud, and the `mosquitto` broker in `default`.
- The image is pinned to a digest, as elsewhere in this repo.
- Both probes read the heartbeat file that mysa2mqtt touches on every successful
  cloud contact, since the process serves no HTTP endpoint.
- The broker runs `allow_anonymous true`, so no MQTT credentials are set.

## Secret

The Mysa account credentials are deliberately not in git. Create the Secret by
hand before the first apply:

```sh
kubectl --context k3s-homelab create secret generic mysa-account \
  -n mysa2mqtt \
  --from-literal=username='you@example.com' \
  --from-literal=password='...'
```

Rotate by replacing the Secret and restarting the Deployment. The same
credentials are used by the Mysa phone app; changing the password there requires
updating this Secret.

Note that mysa2mqtt's Cognito login implements no MFA or social-login path, so
the Mysa account must use plain email and password.

## Deploy

ArgoCD owns this directory through
`homecluster/app-of-apps/applications/mysa2mqtt.yaml`, so deploying means
merging to `main`. The root `homecluster-apps` Application picks up the new
child Application, which then syncs this path with `prune` and `selfHeal`
enabled.

The hand-created `mysa-account` Secret carries no ArgoCD tracking label, so
`prune` leaves it alone.

Once synced, the thermostats appear in Home Assistant under Settings → Devices &
Services → MQTT, each with a climate entity plus temperature and humidity
sensors.

To watch a sync or force one early:

```sh
kubectl --context k3s-homelab -n argocd get application mysa2mqtt
kubectl --context k3s-homelab rollout status deployment/mysa2mqtt \
  -n mysa2mqtt --timeout=5m
```

## Observed behaviour

All three units are `BB-V2-0` on firmware `3.17.5.13`. On this fleet the AWS IoT
real-time socket never connects — every attempt fails with
`AWS_ERROR_MQTT_UNEXPECTED_HANGUP`, which is the known upstream behaviour on V2
and Lite baseboards (mysa2mqtt issue #125). The bridge retries in the
background and falls back to the REST poll, so state is never more than 60s
stale, and commands still work because those go over REST.

Expect those retry errors in the logs continuously. They are noisy but not
fatal. The heartbeat file is touched by the successful polls, so the liveness
probe stays green.

## Power sensors

V2 and Lite baseboards report no real current draw. To get an estimated power
sensor, set `M2M_HEATER_WATTS` on the Deployment to the heaters' wattage, either
globally or per device:

```yaml
- name: M2M_HEATER_WATTS
  value: "Living Room=1500,Bedroom=750"
```

The estimate is duty cycle multiplied by that wattage, so it swings between zero
and full watts rather than tracking real draw. It integrates into a reasonable
daily energy figure but is coarse instantaneously.
