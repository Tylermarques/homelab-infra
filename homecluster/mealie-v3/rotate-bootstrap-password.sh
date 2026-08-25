#!/usr/bin/env bash

set -euo pipefail

context="${KUBE_CONTEXT:-k3s-homelab}"
namespace="mealie"
base_url="https://mealie.local.tylermarques.com"
username="changeme@example.com"
default_password="MyPassword"
new_password="$(openssl rand -hex 24)"

response="$(
  curl -fsS -X POST "${base_url}/api/auth/token" \
    --data-urlencode "username=${username}" \
    --data-urlencode "password=${default_password}"
)"
token="$(jq -r '.access_token // .accessToken // empty' <<<"${response}")"
test -n "${token}"

payload="$(
  jq -nc \
    --arg current "${default_password}" \
    --arg new "${new_password}" \
    '{currentPassword:$current,newPassword:$new}'
)"
curl -fsS -X PUT "${base_url}/api/users/password" \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  --data "${payload}" >/dev/null

kubectl --context "${context}" create secret generic mealie-v3-admin \
  --namespace "${namespace}" \
  --from-literal="username=${username}" \
  --from-literal="password=${new_password}" \
  --dry-run=client \
  -o yaml | kubectl --context "${context}" apply -f -

echo "Rotated the bootstrap password and stored it in secret/${namespace}/mealie-v3-admin."
