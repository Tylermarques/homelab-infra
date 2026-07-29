# Homelab k3s Health Investigation

Investigation date: 2026-07-28

Scope: Read-only diagnostics only. No services were restarted, no Kubernetes resources were changed, and no remediation was executed.

## Executive Summary

The Kubernetes API failure is an embedded-etcd availability problem, not a Tailscale path problem. The three-member control plane effectively has only two reachable servers because `k3s-control-2` has been unreachable since 2025. The two remaining servers repeatedly restarted during the incident and showed rapid leader churn. Direct readiness checks alternated between control-1 being healthy and control-3 failing both `etcd` and `etcd-readiness`; 20 consecutive checks through the configured endpoint failed specifically on etcd.

Two likely destabilizers overlap: an automatic k3s upgrade plan is trying to jump from v1.32.3 to v1.36.2 and is blocked retrying the dead control-2 node, while expired control-plane certificates are reported on control-1 and control-3. At the same time, Proxmox is running a full `vzdump` to the same ZFS pool that stores all k3s VM disks. The host showed high load, significant I/O wait, and many ZFS/NFS threads blocked on I/O. This storage contention can make etcd miss its latency deadlines and aggravate restart/re-election behavior.

Paperless is a separate application configuration failure. Its container exits because `PAPERLESS_SECRET_KEY` is unset/default. NFS was responsive during testing and Paperless reached both its database and Redis before exiting.

## Symptoms

- `kubectl` using context `k3s-homelab` was slow and intermittently returned `ServiceUnavailable` or other server errors.
- Traefik continued to serve Immich while the control plane was unhealthy.
- Traefik returned HTTP 503 for `paperless.local.tylermarques.com`.
- Some Kubernetes reads briefly completed normally between periods of etcd failure.

## Evidence Gathered

### Client and network path

- `kubectl config view --minify --context k3s-homelab --raw=false` reports `server: https://192.168.1.49:6443`.
- `192.168.1.49` is `k3s-control-1`; the kubeconfig does not use Tailscale, a virtual IP, or a load balancer.
- `ip route get` selects LAN interface `enp8s0`, source `192.168.1.71`, for the k3s nodes and Proxmox/NFS host.
- Anonymous `/livez` requests reached control-1 in about 5 ms and returned HTTP 401, proving that TCP, TLS, and the API process itself were reachable.
- Port 6443 on `192.168.0.24` and `192.168.1.188` refused connections immediately. These are `k3s-worker-4` and `k3s-worker-2`, so this is expected; they are Traefik data-plane nodes, not API servers.

### API and etcd behavior

- One `kubectl get nodes -v=6` completed in 82 ms: discovery took 6-7 ms and the node list took 10 ms. This established that the failure was intermittent.
- A subsequent series of 20 authenticated `/livez` calls all failed in approximately 2.04 seconds. Every response showed `[-]etcd failed`; the other API health checks passed.
- Direct authenticated readiness on `k3s-control-1` (`192.168.1.49`) passed, including `etcd` and `etcd-readiness`.
- Direct authenticated readiness on `k3s-control-3` (`192.168.0.119`) failed on `etcd`, `etcd-readiness`, and the RBAC bootstrap hook.
- A direct TCP connection to `k3s-control-2` (`192.168.1.226`) port 6443 was refused.
- `k3s-control-2` has not renewed its node lease or posted a heartbeat since 2025-04-27. It remains represented as an etcd voter and is `NotReady`/unreachable.
- Kubernetes events recorded repeated `Starting`, kubelet startup, node registration, and leader-election events on control-1 and control-3 over roughly 45 minutes. Leadership moved between the two servers every few minutes.
- Certificate warnings on control-1 and control-3 report expired `k3s-controller` and `kube-proxy` client certificates, expired since 2025-08-23. The event explicitly says a controlled k3s restart is needed to trigger rotation.
- The cluster also contains stale/unhealthy nodes beyond the immediate control-plane issue, including `remote-k8s-worker`; node readiness changed during the investigation.

### Automatic upgrade activity

- All observed nodes report `v1.32.3+k3s1`.
- The `system-upgrade/server-plan` follows the unpinned `stable` channel, currently resolving to `v1.36.2-k3s1`, with concurrency 1 and cordoning enabled.
- Plan status says it is applying to unreachable `k3s-control-2`.
- The control-2 upgrade job repeatedly exceeded its 15-minute active deadline and could not schedule because the target node was unreachable.
- This creates a risky four-minor-version jump and upgrade/restart activity while the etcd cluster already lacks one reachable voter. Host journals could not be obtained to prove whether every observed restart was initiated by the upgrade controller, certificate handling, or a k3s crash.

### Proxmox and ZFS

- Read-only root SSH to `192.168.0.71` succeeded. SSH to the k3s guests as both `root` and `tyler` failed public-key authentication, so guest `journalctl -u k3s` and guest disk/memory measurements were unavailable.
- Proxmox load averages were approximately `22/30/30` on a 48-CPU host.
- Memory was not exhausted: about 45 GiB remained available and swap usage was zero.
- `vmstat` showed 11-15 blocked tasks and 17-23% I/O wait during samples, with bursts above 100 MiB/s reads.
- Process state showed many ZFS write/zvol workers blocked in uninterruptible `D` state on request-queue waits, plus blocked `nfsd` threads.
- `zpool status` reports pool `main` ONLINE, every device ONLINE, zero read/write/checksum errors, and no known data errors. The last scrub repaired 0 bytes with 0 errors.
- Capacity is healthy: pool `main` has about 10.6 TiB available. This is a latency/contention condition, not pool exhaustion or detected corruption.
- An active all-VM `vzdump` snapshot backup started at 21:00:10 host time and writes a zstd archive under `/main/backups`. Its process was still running nearly an hour later.
- All k3s control and worker VMs run on this Proxmox host and their virtual disks are ZFS volumes under `main/vm-storage`, so backup reads/writes and etcd VM I/O share the same physical pool.

### NFS

- `timeout 10 showmount -e 192.168.0.71` returned promptly with `/main/plex (everyone)`.
- `rpcinfo -p 192.168.0.71` returned the expected portmapper, mountd, NFS v3/v4, ACL, status, and lock-manager services.
- The ZFS pool hosting `/main/plex` is ONLINE and has ample free space.
- These checks prove NFS control-plane responsiveness, but do not rule out transient data-path latency during heavy ZFS activity. Blocked `nfsd` threads indicate contention was present.

### Data plane

- HTTPS requests with correct SNI and host routing to Traefik on `192.168.1.49`, `192.168.0.24`, and `192.168.1.188` all returned HTTP 200 for Immich in 16-22 ms.
- HTTP requests to each of those nodes returned HTTP 503 for Paperless in about 2 ms.
- This confirms that Traefik and established workload routing continue independently of current API/etcd health.

### Paperless

- The Paperless pod was in `CrashLoopBackOff`, not ready, with 1,387 restarts at the initial snapshot.
- Its previous and current logs both terminate with `django.core.exceptions.ImproperlyConfigured: PAPERLESS_SECRET_KEY is not set or is the default 'change-me' value`.
- Before exiting, initialization reported that the database was ready and Redis was connected and ready.
- Both NFS volumes were mounted into the pod. There were no mount-failure events.
- The Service's EndpointSlice contained pod IP `10.42.7.43` but explicitly marked it `ready: false` and `serving: false`; the legacy Endpoints object had no usable address. This directly explains Traefik's 503.
- The deployment uses `ghcr.io/paperless-ngx/paperless-ngx:latest` with `imagePullPolicy: Always`. An upstream image change requiring a non-default secret key is the likely trigger for the five-day crash loop.
- A concurrent Paperless rollout/config edit appeared during this read-only investigation. No changes to it were made by this investigation.

## Root Cause Hypotheses Ranked by Likelihood

1. **Confirmed immediate cause: intermittent loss or severe degradation of embedded-etcd quorum.** Twenty consecutive health checks failed specifically on etcd, control-3 directly failed etcd readiness, and control-2 is unreachable. With only control-1 and control-3 reachable in a nominal three-voter cluster, either remaining member restarting or becoming I/O-stalled removes quorum.
2. **Very likely trigger/amplifier: ZFS contention from the full Proxmox backup on the shared VM-storage pool.** The backup timing overlaps the incident, and host evidence shows high I/O wait plus many blocked ZFS/zvol/NFS tasks. Etcd is highly sensitive to disk fsync latency.
3. **Very likely control-plane destabilizer: unsafe/stalled automatic upgrade and expired certificates.** The unpinned stable plan wants to jump v1.32.3 to v1.36.2, is blocked on a long-dead control node, and overlaps repeated server starts and leader elections. Expired internal client certificates add another reason for failed/repeated startup. Host k3s logs are needed to distinguish the exact restart initiator.
4. **Availability design weakness: kubeconfig is pinned to control-1.** Even with healthy etcd, restarting or losing control-1 makes clients fail rather than using control-3. This worsens the observed availability but does not cause the etcd failures.
5. **Confirmed separate Paperless cause: missing `PAPERLESS_SECRET_KEY`.** The 503 is caused by an unready crash-looping application, not by absent NFS mounts. NFS contention may affect performance but is not the startup failure shown in logs.

## Recommended Remediation Steps (Not Executed)

1. Pause or disable the automatic `stable` channel upgrade before any further control-plane work. Pin a reviewed target and plan supported incremental upgrades instead of jumping directly from v1.32 to v1.36.
2. Do not restart control-1 or control-3 while control-2 remains absent. First take/verify an etcd snapshot and determine actual member health with `k3s etcd-snapshot`/`etcdctl` diagnostics from a control node.
3. Restore control-2 if its datastore is intact, or replace/remove its stale etcd member using the documented k3s quorum-recovery procedure. Preserve a verified snapshot and ensure two healthy voters throughout; do not blindly delete the node or etcd member.
4. After quorum is stable, inspect `journalctl -u k3s` and `k3s certificate check` on each server. Rotate expired certificates with controlled, one-server-at-a-time restarts, confirming etcd health after each action.
5. Reschedule or throttle Proxmox backups so they do not saturate the pool hosting etcd VMs. Consider separate backup storage, per-job bandwidth limits, and moving control-plane VM disks to low-latency SSD-backed storage. Monitor disk latency, not only pool health/capacity.
6. Once all control planes are healthy, put kubeconfig behind a tested LAN VIP/load balancer spanning control-1 and control-3 (and restored control-2). Health-check `/readyz`; do not send clients to merely open port 6443.
7. Add `PAPERLESS_SECRET_KEY` from a Kubernetes Secret and complete a controlled Paperless rollout. Pin the Paperless image to a tested version/digest instead of `latest`.
8. Move existing Paperless administrative and Redis credentials out of plaintext manifests/environment definitions and rotate them, since they are currently exposed through deployment configuration.
9. Validate Paperless's ready endpoint and Traefik response after the application fix. NFS remediation is not currently indicated, but measure mount/file-operation latency during backups if application stalls continue.
10. Remove or repair stale node records and review system-upgrade scheduling only after etcd is stable; avoid combining quorum repair, certificate rotation, version upgrades, and storage-heavy backups in one maintenance window.

## Investigation Limitations

- SSH authentication to k3s guests was unavailable, so k3s service logs and guest-level disk latency could not be collected.
- NFS was tested through RPC discovery only; no filesystem was mounted and no data was written because the investigation was strictly read-only.
- Concurrent Paperless changes occurred during evidence collection, so Paperless observations describe the initial failing pod and endpoint snapshot.
