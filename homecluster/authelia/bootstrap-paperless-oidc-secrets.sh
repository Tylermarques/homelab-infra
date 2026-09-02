#!/usr/bin/env bash

set -euo pipefail

context="${KUBE_CONTEXT:-k3s-homelab}"
authelia_namespace="authelia"
paperless_namespace="default"
authelia_secret="paperless-oidc"
paperless_secret="paperless-oidc"
client_id="paperless"
server_url="https://auth.local.tylermarques.com"
image="ghcr.io/authelia/authelia:4.39.20@sha256:b5f415d5f14b154c2aa2b186d9f329d879e223da36e115cd871db4c261d5af54"

secret_exists() {
  kubectl --context "${context}" get secret "$2" --namespace "$1" >/dev/null 2>&1
}

read_secret() {
  kubectl --context "${context}" get secret "$2" --namespace "$1" \
    -o go-template="{{index .data \"$3\" | base64decode}}"
}

authelia_exists=false
paperless_exists=false
secret_exists "${authelia_namespace}" "${authelia_secret}" && authelia_exists=true
secret_exists "${paperless_namespace}" "${paperless_secret}" && paperless_exists=true

if ${authelia_exists} && ${paperless_exists}; then
  providers_json="$(read_secret "${paperless_namespace}" "${paperless_secret}" providers-json)"
  existing_client_id="$(jq -r '.openid_connect.APPS[0].client_id' <<<"${providers_json}")"
  existing_server_url="$(jq -r '.openid_connect.APPS[0].settings.server_url' <<<"${providers_json}")"
  client_secret="$(jq -r '.openid_connect.APPS[0].secret' <<<"${providers_json}")"
  client_secret_digest="$(read_secret "${authelia_namespace}" "${authelia_secret}" \
    client-secret-digest.txt)"

  if [[ "${existing_client_id}" != "${client_id}" || "${existing_server_url}" != "${server_url}" ]]; then
    echo "Existing Paperless OIDC metadata does not match this deployment; refusing to change it." >&2
    exit 1
  fi

  docker run --rm "${image}" authelia crypto hash validate \
    --password "${client_secret}" -- "${client_secret_digest}" >/dev/null
  echo "Paperless OIDC secrets already exist and match; no changes made."
  exit 0
fi

if ${authelia_exists} || ${paperless_exists}; then
  echo "Only one Paperless OIDC secret exists; refusing to replace or rotate credentials." >&2
  exit 1
fi

client_secret="$(openssl rand -hex 32)"
providers_json="$(jq -cn \
  --arg client_id "${client_id}" \
  --arg client_secret "${client_secret}" \
  --arg server_url "${server_url}" \
  '{openid_connect: {
    OAUTH_PKCE_ENABLED: true,
    EMAIL_AUTHENTICATION: true,
    EMAIL_AUTHENTICATION_AUTO_CONNECT: true,
    SCOPE: ["openid", "profile", "email", "groups"],
    APPS: [{
      provider_id: "authelia",
      name: "Authelia",
      client_id: $client_id,
      secret: $client_secret,
      settings: {
        server_url: $server_url,
        oauth_pkce_enabled: true,
        token_auth_method: "client_secret_basic"
      }
    }]
  }}')"
hash_output="$(docker run --rm "${image}" authelia crypto hash generate argon2 \
  --password "${client_secret}")"
client_secret_digest="${hash_output#Digest: }"

created_authelia=false
cleanup() {
  if ${created_authelia}; then
    kubectl --context "${context}" delete secret "${authelia_secret}" \
      --namespace "${authelia_namespace}" >/dev/null
  fi
}
trap cleanup ERR

kubectl --context "${context}" create secret generic "${authelia_secret}" \
  --namespace "${authelia_namespace}" \
  --from-literal=client-secret-digest.txt="${client_secret_digest}"
created_authelia=true
kubectl --context "${context}" create secret generic "${paperless_secret}" \
  --namespace "${paperless_namespace}" \
  --from-literal=providers-json="${providers_json}"

trap - ERR
echo "Created matching Paperless and Authelia OIDC secrets."
