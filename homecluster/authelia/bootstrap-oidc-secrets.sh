#!/usr/bin/env bash

set -euo pipefail

context="${KUBE_CONTEXT:-k3s-homelab}"
authelia_namespace="authelia"
mealie_namespace="mealie"
authelia_secret="authelia-oidc"
mealie_secret="mealie-oidc"
client_id="mealie"
configuration_url="https://auth.local.tylermarques.com/.well-known/openid-configuration"
image="ghcr.io/authelia/authelia:4.39.20@sha256:b5f415d5f14b154c2aa2b186d9f329d879e223da36e115cd871db4c261d5af54"

secret_exists() {
  kubectl --context "${context}" get secret "$2" --namespace "$1" >/dev/null 2>&1
}

secret_has_key() {
  test -n "$(kubectl --context "${context}" get secret "$2" --namespace "$1" \
    -o go-template="{{index .data \"$3\"}}")"
}

require_keys() {
  local namespace="$1"
  local secret="$2"
  shift 2

  for key in "$@"; do
    if ! secret_has_key "${namespace}" "${secret}" "${key}"; then
      echo "secret/${namespace}/${secret} is missing key ${key}; refusing to replace or rotate it." >&2
      exit 1
    fi
  done
}

read_secret() {
  kubectl --context "${context}" get secret "$2" --namespace "$1" \
    -o go-template="{{index .data \"$3\" | base64decode}}"
}

kubectl --context "${context}" create namespace "${authelia_namespace}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -
kubectl --context "${context}" create namespace "${mealie_namespace}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -

authelia_exists=false
mealie_exists=false
secret_exists "${authelia_namespace}" "${authelia_secret}" && authelia_exists=true
secret_exists "${mealie_namespace}" "${mealie_secret}" && mealie_exists=true

if ${authelia_exists}; then
  require_keys "${authelia_namespace}" "${authelia_secret}" \
    hmac.key jwks-rs256.pem mealie-client-secret-digest.txt
fi

if ${mealie_exists}; then
  require_keys "${mealie_namespace}" "${mealie_secret}" \
    configuration-url client-id client-secret
fi

if ${authelia_exists} && ${mealie_exists}; then
  existing_client_id="$(read_secret "${mealie_namespace}" "${mealie_secret}" client-id)"
  existing_configuration_url="$(read_secret "${mealie_namespace}" "${mealie_secret}" configuration-url)"
  client_secret="$(read_secret "${mealie_namespace}" "${mealie_secret}" client-secret)"
  client_secret_digest="$(read_secret "${authelia_namespace}" "${authelia_secret}" \
    mealie-client-secret-digest.txt)"
  if [[ "${existing_client_id}" != "${client_id}" || \
        "${existing_configuration_url}" != "${configuration_url}" ]]; then
    echo "Existing Mealie OIDC metadata does not match this deployment; refusing to change it." >&2
    exit 1
  fi
  docker run --rm "${image}" authelia crypto hash validate \
    --password "${client_secret}" -- "${client_secret_digest}" >/dev/null
  echo "OIDC secrets already exist and contain all required keys; no changes made."
  exit 0
fi

if ${authelia_exists} && ! ${mealie_exists}; then
  echo "secret/${authelia_namespace}/${authelia_secret} exists without the matching Mealie secret." >&2
  echo "The plaintext client secret cannot be recovered; refusing to rotate it." >&2
  exit 1
fi

if ${mealie_exists}; then
  existing_client_id="$(read_secret "${mealie_namespace}" "${mealie_secret}" client-id)"
  if [[ "${existing_client_id}" != "${client_id}" ]]; then
    echo "secret/${mealie_namespace}/${mealie_secret} has an unexpected client-id; refusing to change it." >&2
    exit 1
  fi
  client_secret="$(read_secret "${mealie_namespace}" "${mealie_secret}" client-secret)"
else
  client_secret="$(openssl rand -hex 32)"
  kubectl --context "${context}" create secret generic "${mealie_secret}" \
    --namespace "${mealie_namespace}" \
    --from-literal=configuration-url="${configuration_url}" \
    --from-literal=client-id="${client_id}" \
    --from-literal=client-secret="${client_secret}"
fi

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out "${workdir}/jwks-rs256.pem" 2>/dev/null
hash_output="$(docker run --rm "${image}" authelia crypto hash generate argon2 \
  --password "${client_secret}")"
client_secret_digest="${hash_output#Digest: }"

kubectl --context "${context}" create secret generic "${authelia_secret}" \
  --namespace "${authelia_namespace}" \
  --from-literal=hmac.key="$(openssl rand -hex 64)" \
  --from-file=jwks-rs256.pem="${workdir}/jwks-rs256.pem" \
  --from-literal=mealie-client-secret-digest.txt="${client_secret_digest}"

echo "Created OIDC secrets without modifying secret/${authelia_namespace}/authelia-secrets."
