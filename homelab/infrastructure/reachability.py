"""
Host reachability check using pulumi-command.

This module provides a way to ensure a host is reachable (via ping) before
proceeding with dependent resources like Talos configuration apply.
"""

import pulumi
import pulumi_command as command


def create_reachability_check(
    name: str,
    host: pulumi.Input[str],
    timeout: int = 5,
    interval: int = 1,
    opts: pulumi.ResourceOptions | None = None,
) -> command.local.Command:
    """
    Create a reachability check that waits for a host to become pingable.

    Uses a bash script that retries ping until the host responds or timeout.

    Args:
        name: Resource name
        host: The IP address or hostname to check
        timeout: Maximum time to wait for host to become reachable (seconds)
        interval: Time between ping attempts (seconds)
        opts: Pulumi resource options

    Returns:
        A Command resource that completes when the host is reachable
    """
    # Bash script that waits for host to be reachable
    # Uses a loop with timeout to retry ping
    check_script = pulumi.Output.from_input(host).apply(
        lambda h: f'''
set -e

HOST="{h}"
TIMEOUT={timeout}
INTERVAL={interval}

if [ -z "$HOST" ]; then
    echo "ERROR: Host IP is empty - cannot check reachability" >&2
    exit 1
fi

if [[ "$HOST" == 127.* ]]; then
    echo "ERROR: Host IP is a loopback address ($HOST) - this is likely incorrect" >&2
    exit 1
fi

echo "Waiting for host $HOST to become reachable (timeout: ${{TIMEOUT}}s)..." >&2

START_TIME=$(date +%s)
while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))

    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "ERROR: Host $HOST is not reachable after ${{TIMEOUT}} seconds" >&2
        echo "Ensure the VM has booted and has network connectivity." >&2
        exit 1
    fi

    if ping -c 1 -W 2 "$HOST" > /dev/null 2>&1; then
        echo "Host $HOST is reachable (took ${{ELAPSED}}s)" >&2
        echo "$HOST"
        exit 0
    fi

    sleep $INTERVAL
done
'''
    )

    return command.local.Command(
        name,
        create=check_script,
        # Re-run the check on updates by using the host as a trigger
        triggers=[host],
        opts=opts,
    )
