#!/usr/bin/env bash

set -euo pipefail

context="${KUBE_CONTEXT:-k3s-homelab}"
authelia_namespace="authelia"
argocd_namespace="argocd"
authelia_secret="argocd-oidc"
argocd_secret="argocd-oidc"
image="ghcr.io/authelia/authelia:4.39.20@sha256:b5f415d5f14b154c2aa2b186d9f329d879e223da36e115cd871db4c261d5af54"

secret_exists() {
  kubectl --context "${context}" get secret "$2" --namespace "$1" >/dev/null 2>&1
}

read_secret() {
  kubectl --context "${context}" get secret "$2" --namespace "$1" \
    -o go-template="{{index .data \"$3\" | base64decode}}"
}

authelia_exists=false
argocd_exists=false
secret_exists "${authelia_namespace}" "${authelia_secret}" && authelia_exists=true
secret_exists "${argocd_namespace}" "${argocd_secret}" && argocd_exists=true

if ${authelia_exists} && ${argocd_exists}; then
  client_secret="$(read_secret "${argocd_namespace}" "${argocd_secret}" clientSecret)"
  client_secret_digest="$(read_secret "${authelia_namespace}" "${authelia_secret}" \
    client-secret-digest.txt)"

  docker run --rm "${image}" authelia crypto hash validate \
    --password "${client_secret}" -- "${client_secret_digest}" >/dev/null
  echo "Argo CD OIDC secrets already exist and match; no changes made."
  exit 0
fi

if ${authelia_exists} || ${argocd_exists}; then
  echo "Only one Argo CD OIDC secret exists; refusing to replace or rotate credentials." >&2
  exit 1
fi

client_secret="$(openssl rand -hex 32)"
hash_output="$(docker run --rm "${image}" authelia crypto hash generate argon2 \
  --password "${client_secret}")"
client_secret_digest="${hash_output#Digest: }"

created_authelia=false
created_argocd=false
cleanup() {
  if ${created_argocd}; then
    kubectl --context "${context}" delete secret "${argocd_secret}" \
      --namespace "${argocd_namespace}" >/dev/null
  fi
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
kubectl --context "${context}" create secret generic "${argocd_secret}" \
  --namespace "${argocd_namespace}" \
  --from-literal=clientSecret="${client_secret}"
created_argocd=true
# Argo CD only resolves `$argocd-oidc:clientSecret` from Secrets it is told
# belong to it.
kubectl --context "${context}" label secret "${argocd_secret}" \
  --namespace "${argocd_namespace}" app.kubernetes.io/part-of=argocd

trap - ERR
echo "Created matching Argo CD and Authelia OIDC secrets."
