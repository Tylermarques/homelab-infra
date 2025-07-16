import pulumi
import pulumi_kubernetes as k8s
from apps.volumes import create_nfs_pv_and_pvc
from textwrap import dedent

pv, pvc = create_nfs_pv_and_pvc(
    name="nfs-test",  # <- logical name; will create nfs-test-nfs-pv / -pvc
    namespace="monitoring",  # <- must match CronJob namespace
    server="proxmox-egress",
    share_path="/main/plex",
    storage_size="50Gi",
    storage_class_name="nfs-csi",
)

config_map = k8s.core.v1.ConfigMap(
    "nfs-bench-scripts",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="nfs-bench-scripts",
        namespace="monitoring",
    ),
    data={
        "run.sh": dedent(
            """\
            #!/bin/sh
            set -eu
            FIO_OUT=/tmp/fio.json
            METRICS=/tmp/metrics.txt
            MOUNT=/bench

            echo ">> Running fio"
            ###############################################################
            # 1. Run fio
            ###############################################################
            fio /scripts/job.fio --output-format=json --directory=$MOUNT > "$FIO_OUT"

            ###############################################################
            # 2. Extract numbers with jq
            ###############################################################
            # Throughput & IOPS
            r_bw=$(jq '.jobs[0].read.bw_bytes'  "$FIO_OUT")
            w_bw=$(jq '.jobs[0].write.bw_bytes' "$FIO_OUT")
            r_iops=$(jq '.jobs[0].read.iops'    "$FIO_OUT")
            w_iops=$(jq '.jobs[0].write.iops'   "$FIO_OUT")

            # Average latency (ns)
            r_lat_avg=$(jq '.jobs[0].read.lat_ns.mean'  "$FIO_OUT")
            w_lat_avg=$(jq '.jobs[0].write.lat_ns.mean' "$FIO_OUT")

            # P95 / P99 completion‑latency percentiles (ns)
            r_p95=$(jq '.jobs[0].read.clat_ns.percentile["95.000000"]'  "$FIO_OUT")
            w_p95=$(jq '.jobs[0].write.clat_ns.percentile["95.000000"]' "$FIO_OUT")
            r_p99=$(jq '.jobs[0].read.clat_ns.percentile["99.000000"]'  "$FIO_OUT")
            w_p99=$(jq '.jobs[0].write.clat_ns.percentile["99.000000"]' "$FIO_OUT")

            # Labels
            job_label=$(jq -r '.jobs[0].jobname' "$FIO_OUT")
            node_label=${NODE_NAME:-unknown}
            pv_label=${PV_TYPE:-unknown}

            ###############################################################
            # 3. Render Prometheus text format
            ###############################################################
            cat > "$METRICS" <<EOF
            # HELP nfs_bench_read_bw_bytes Aggregate read throughput in bytes/s
            # TYPE nfs_bench_read_bw_bytes gauge
            nfs_bench_read_bw_bytes{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${r_bw}
            # HELP nfs_bench_write_bw_bytes Aggregate write throughput in bytes/s
            # TYPE nfs_bench_write_bw_bytes gauge
            nfs_bench_write_bw_bytes{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${w_bw}

            # HELP nfs_bench_read_iops Read IOPS
            # TYPE nfs_bench_read_iops gauge
            nfs_bench_read_iops{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${r_iops}
            # HELP nfs_bench_write_iops Write IOPS
            # TYPE nfs_bench_write_iops gauge
            nfs_bench_write_iops{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${w_iops}

            # HELP nfs_bench_read_lat_ns_avg Average read latency (ns)
            # TYPE nfs_bench_read_lat_ns_avg gauge
            nfs_bench_read_lat_ns_avg{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${r_lat_avg}
            # HELP nfs_bench_write_lat_ns_avg Average write latency (ns)
            # TYPE nfs_bench_write_lat_ns_avg gauge
            nfs_bench_write_lat_ns_avg{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${w_lat_avg}

            # HELP nfs_bench_read_clat_ns_p95 95th‑percentile read completion latency (ns)
            # TYPE nfs_bench_read_clat_ns_p95 gauge
            nfs_bench_read_clat_ns_p95{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${r_p95}
            # HELP nfs_bench_write_clat_ns_p95 95th‑percentile write completion latency (ns)
            # TYPE nfs_bench_write_clat_ns_p95 gauge
            nfs_bench_write_clat_ns_p95{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${w_p95}

            # HELP nfs_bench_read_clat_ns_p99 99th‑percentile read completion latency (ns)
            # TYPE nfs_bench_read_clat_ns_p99 gauge
            nfs_bench_read_clat_ns_p99{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${r_p99}
            # HELP nfs_bench_write_clat_ns_p99 99th‑percentile write completion latency (ns)
            # TYPE nfs_bench_write_clat_ns_p99 gauge
            nfs_bench_write_clat_ns_p99{job="${job_label}",node="${node_label}",pv_type="${pv_label}"} ${w_p99}
            EOF

            ###############################################################
            # 4. Push to Pushgateway
            ###############################################################
            curl -s --data-binary "@${METRICS}" "${PUSHGATEWAY_URL}/metrics/job/nfs_bench"
            """
        ),
        "job.fio": dedent(
            """\
            [global]
            ioengine=libaio
            rw=randrw
            bs=4k
            iodepth=16
            direct=1
            time_based
            runtime=60
            size=500M
            norandommap
            [bench]
            """
        ),
    },
)

# ---------------------------------------------------------------------------
# 4.  CronJob that runs the benchmark hourly and pushes to Pushgateway
# ---------------------------------------------------------------------------
bench_labels = {"app": "nfs-bench"}
cron_job = k8s.batch.v1.CronJob(
    "nfs-bench",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="nfs-bench",
        namespace="monitoring",
        labels=bench_labels,
    ),
    spec=k8s.batch.v1.CronJobSpecArgs(
        schedule="0 * * * *",  # at :00 every hour
        concurrency_policy="Forbid",
        successful_jobs_history_limit=1,
        failed_jobs_history_limit=3,
        job_template=k8s.batch.v1.JobTemplateSpecArgs(
            spec=k8s.batch.v1.JobSpecArgs(
                backoff_limit=0,
                active_deadline_seconds=600,
                template=k8s.core.v1.PodTemplateSpecArgs(
                    metadata=k8s.meta.v1.ObjectMetaArgs(labels=bench_labels),
                    spec=k8s.core.v1.PodSpecArgs(
                        restart_policy="Never",
                        volumes=[
                            k8s.core.v1.VolumeArgs(
                                name="nfs",
                                persistent_volume_claim=k8s.core.v1.PersistentVolumeClaimVolumeSourceArgs(claim_name=pvc.metadata.name),
                            ),
                            k8s.core.v1.VolumeArgs(
                                name="scripts",
                                config_map=k8s.core.v1.ConfigMapVolumeSourceArgs(
                                    name=config_map.metadata.name,
                                    default_mode=0o755,
                                ),
                            ),
                        ],
                        containers=[
                            k8s.core.v1.ContainerArgs(
                                name="bench",
                                # Public Alpine‑based fio image
                                image="xridge/fio:3.13-r1",
                                # One‑liner: add jq, then run our script
                                command=[
                                    "/bin/sh",
                                    "-c",
                                    "apk add --no-cache jq curl && /scripts/run.sh",
                                ],
                                env=[
                                    k8s.core.v1.EnvVarArgs(
                                        name="PUSHGATEWAY_URL",
                                        value="http://prometheus-prometheus-pushgateway.monitoring:9091",
                                    ),
                                    k8s.core.v1.EnvVarArgs(
                                        name="NODE_NAME",
                                        value_from=k8s.core.v1.EnvVarSourceArgs(field_ref=k8s.core.v1.ObjectFieldSelectorArgs(field_path="spec.nodeName")),
                                    ),
                                    # ‑‑‑ PV type – set once here for easy labelling
                                    k8s.core.v1.EnvVarArgs(
                                        name="PV_TYPE",
                                        value="nfs",
                                    ),
                                ],
                                volume_mounts=[
                                    k8s.core.v1.VolumeMountArgs(
                                        name="nfs",
                                        mount_path="/bench",
                                    ),
                                    k8s.core.v1.VolumeMountArgs(
                                        name="scripts",
                                        mount_path="/scripts",
                                    ),
                                ],
                                resources=k8s.core.v1.ResourceRequirementsArgs(limits={"cpu": "500m", "memory": "1Gi"}),
                            )
                        ],
                    ),
                ),
            )
        ),
    ),
)

# ---------------------------------------------------------------------------
# 5.  Export a handy Grafana / Prometheus hint
# ---------------------------------------------------------------------------
pulumi.export(
    "pushgateway_url",
    pulumi.Output.concat("http://prometheus-prometheus-pushgateway.monitoring.svc.cluster.local:9091"),
)
