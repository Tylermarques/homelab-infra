#!/usr/bin/env bash

set -euo pipefail

context="${KUBE_CONTEXT:-k3s-homelab}"
authelia_namespace="authelia"
immich_namespace="immich"
authelia_secret="authelia-oidc"
digest_key="immich-client-secret-digest.txt"
client_id="immich"
issuer_url="https://auth.local.tylermarques.com/.well-known/openid-configuration"
external_domain="https://immich.local.tylermarques.com"

read_digest() {
  kubectl --context "${context}" get secret "${authelia_secret}" \
    --namespace "${authelia_namespace}" \
    -o go-template="{{if index .data \"${digest_key}\"}}{{index .data \"${digest_key}\" | base64decode}}{{end}}"
}

read_client_secret() {
  kubectl --context "${context}" exec --namespace "${immich_namespace}" \
    immich-cluster-1 -- psql -U postgres -d immich -Atc \
    "SELECT value #>> '{oauth,clientSecret}' FROM system_metadata WHERE key = 'system-config';"
}

digest="$(read_digest 2>/dev/null || true)"
client_secret="$(read_client_secret)"

if [[ -n "${digest}" || -n "${client_secret}" ]]; then
  if [[ -z "${digest}" || -z "${client_secret}" ]]; then
    echo "Immich and Authelia OIDC credentials are incomplete; refusing to rotate them." >&2
    exit 1
  fi

  kubectl --context "${context}" exec --namespace "${authelia_namespace}" \
    deployment/authelia -- authelia crypto hash validate \
    --password "${client_secret}" -- "${digest}" >/dev/null
  echo "Immich OIDC credentials already exist and match; no changes made."
  exit 0
fi

client_secret="$(openssl rand -hex 32)"
hash_output="$(kubectl --context "${context}" exec \
  --namespace "${authelia_namespace}" deployment/authelia -- \
  authelia crypto hash generate pbkdf2 --password "${client_secret}")"
digest="${hash_output#Digest: }"

patch="$(jq -nc --arg key "${digest_key}" --arg digest "${digest}" \
  '{stringData: {($key): $digest}}')"
kubectl --context "${context}" patch secret "${authelia_secret}" \
  --namespace "${authelia_namespace}" --type merge --patch "${patch}" >/dev/null

oauth_json="$(jq -nc \
  --arg client_id "${client_id}" \
  --arg client_secret "${client_secret}" \
  --arg issuer_url "${issuer_url}" \
  '{
    enabled: true,
    issuerUrl: $issuer_url,
    clientId: $client_id,
    clientSecret: $client_secret,
    scope: "openid profile email",
    buttonText: "Login with Authelia",
    autoRegister: false,
    autoLaunch: false,
    signingAlgorithm: "RS256",
    profileSigningAlgorithm: "none",
    mobileOverrideEnabled: false,
    mobileRedirectUri: ""
  }')"
server_json="$(jq -nc --arg external_domain "${external_domain}" \
  '{externalDomain: $external_domain}')"
oauth_base64="$(printf '%s' "${oauth_json}" | base64 --wrap=0)"
server_base64="$(printf '%s' "${server_json}" | base64 --wrap=0)"

sql="UPDATE system_metadata
SET value = jsonb_set(
  jsonb_set(value, '{oauth}', convert_from(decode('${oauth_base64}', 'base64'), 'UTF8')::jsonb, true),
  '{server}', COALESCE(value->'server', '{}'::jsonb) || convert_from(decode('${server_base64}', 'base64'), 'UTF8')::jsonb,
  true
)
WHERE key = 'system-config';"
printf '%s\n' "${sql}" | kubectl --context "${context}" exec --stdin \
  --namespace "${immich_namespace}" immich-cluster-1 -- \
  psql -v ON_ERROR_STOP=1 -U postgres -d immich >/dev/null

echo "Created matching Immich and Authelia OIDC credentials."
