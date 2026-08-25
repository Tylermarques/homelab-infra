#!/usr/bin/env bash

set -euo pipefail

context="${KUBE_CONTEXT:-k3s-homelab}"
namespace="authelia"
username="tyler"
email="me@tylermarques.com"
image="ghcr.io/authelia/authelia:4.39.20@sha256:b5f415d5f14b154c2aa2b186d9f329d879e223da36e115cd871db4c261d5af54"

kubectl --context "${context}" create namespace "${namespace}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -

if kubectl --context "${context}" get secret authelia-secrets \
  --namespace "${namespace}" >/dev/null 2>&1; then
  echo "secret/${namespace}/authelia-secrets already exists; refusing to rotate encryption keys."
  exit 1
fi

password="$(openssl rand -base64 24 | tr -d '\n')"
database_password="$(openssl rand -base64 32 | tr -d '\n')"
hash_output="$(docker run --rm "${image}" authelia crypto hash generate argon2 --password "${password}")"
password_hash="${hash_output#Digest: }"

users_database="$(printf '%s\n' \
  'users:' \
  "  ${username}:" \
  '    disabled: false' \
  '    displayname: "Tyler Marques"' \
  "    password: \"${password_hash}\"" \
  "    email: ${email}" \
  '    groups:' \
  '      - admins' \
  '      - users')"

kubectl --context "${context}" create secret generic authelia-secrets \
  --namespace "${namespace}" \
  --from-literal=identity_validation.reset_password.jwt.hmac.key="$(openssl rand -hex 64)" \
  --from-literal=session.encryption.key="$(openssl rand -hex 64)" \
  --from-literal=session.redis.password.txt="$(openssl rand -base64 32 | tr -d '\n')" \
  --from-literal=storage.encryption.key="$(openssl rand -hex 64)" \
  --from-literal=storage.postgres.password.txt="${database_password}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -

kubectl --context "${context}" create secret generic authelia-db-credentials \
  --namespace "${namespace}" \
  --type=kubernetes.io/basic-auth \
  --from-literal=username=authelia \
  --from-literal=password="${database_password}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -

kubectl --context "${context}" create secret generic authelia-users \
  --namespace "${namespace}" \
  --from-literal=users_database.yml="${users_database}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -

kubectl --context "${context}" create secret generic authelia-bootstrap-credentials \
  --namespace "${namespace}" \
  --from-literal=username="${username}" \
  --from-literal=password="${password}" \
  --dry-run=client -o yaml | kubectl --context "${context}" apply -f -

echo "Created Authelia secrets and stored the initial login in secret/${namespace}/authelia-bootstrap-credentials."
