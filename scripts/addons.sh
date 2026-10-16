#!/usr/bin/env bash
# Install or remove Kiali and Prometheus. They only run while taking screenshots,
# to keep the cluster within its memory budget.
set -euo pipefail

source "$(dirname "$0")/versions.sh"

ADDONS_URL="https://raw.githubusercontent.com/istio/istio/${ISTIO_VERSION}/samples/addons"
ADDONS=(prometheus kiali)

usage() {
  echo "usage: $0 install|remove" >&2
  exit 1
}

install_addons() {
  local addon
  for addon in "${ADDONS[@]}"; do
    kubectl apply -f "$ADDONS_URL/$addon.yaml"
  done
  for addon in "${ADDONS[@]}"; do
    kubectl -n istio-system rollout status "deploy/$addon" --timeout=300s
  done
  echo "Open Kiali with: istioctl dashboard kiali"
}

remove_addons() {
  local addon
  for addon in "${ADDONS[@]}"; do
    kubectl delete -f "$ADDONS_URL/$addon.yaml" --ignore-not-found
  done
}

case "${1:-}" in
  install) install_addons ;;
  remove) remove_addons ;;
  *) usage ;;
esac
