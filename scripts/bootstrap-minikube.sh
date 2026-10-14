#!/usr/bin/env bash
# Create the local cluster: minikube with metrics-server, the Gateway API CRDs,
# and Istio (minimal profile, sidecar mode, CNI) with reduced resource requests.
# Safe to run again on an existing cluster.
set -euo pipefail

source "$(dirname "$0")/versions.sh"

PROFILE="${MINIKUBE_PROFILE:-minikube}"
MEMORY_MB="${MINIKUBE_MEMORY:-4096}"
CPUS="${MINIKUBE_CPUS:-4}"
# The Docker VM needs some headroom above the minikube node. The kernel reports
# a bit less than the value set in Docker Desktop, hence 4400 for a 4.5 GB setting.
MIN_DOCKER_MEMORY_MB=4400

die() {
  echo "error: $*" >&2
  exit 1
}

check_tools() {
  local tool
  for tool in docker minikube kubectl istioctl; do
    command -v "$tool" >/dev/null || die "$tool not found"
  done

  local version
  version="$(minikube version --short)"
  [[ "$version" == "$MINIKUBE_VERSION" ]] ||
    echo "warning: minikube $version found, the project uses $MINIKUBE_VERSION" >&2

  # istioctl installs the control plane of its own version, so it must match.
  istioctl version --remote=false 2>/dev/null | grep -qF "$ISTIO_VERSION" ||
    die "istioctl $ISTIO_VERSION required: curl -L https://istio.io/downloadIstio | ISTIO_VERSION=$ISTIO_VERSION sh -"
}

check_docker_memory() {
  local total_mb
  total_mb=$(($(docker info --format '{{.MemTotal}}') / 1024 / 1024))
  ((total_mb >= MIN_DOCKER_MEMORY_MB)) ||
    die "Docker has ${total_mb} MiB, set at least 4.5 GB in Docker Desktop > Settings > Resources"
}

start_minikube() {
  # The bridge CNI is set explicitly because istio-cni chains onto an existing CNI config.
  minikube start -p "$PROFILE" \
    --driver=docker \
    --container-runtime=docker \
    --cni=bridge \
    --kubernetes-version="$KUBERNETES_VERSION" \
    --memory="$MEMORY_MB" \
    --cpus="$CPUS" \
    --addons=metrics-server
  kubectl config use-context "$PROFILE"
}

install_gateway_api() {
  kubectl apply --server-side \
    -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml"
}

install_istio() {
  # Default requests are 500m/2Gi for istiod and 100m/128Mi per sidecar, too much for 4 GB.
  # The gateway seccomp profile lets Gateway API deployments pass PSA restricted.
  istioctl install -y \
    --set profile=minimal \
    --set components.cni.enabled=true \
    --set components.cni.namespace=istio-system \
    --set values.pilot.env.ENABLE_NATIVE_SIDECARS=true \
    --set values.pilot.autoscaleEnabled=false \
    --set values.pilot.resources.requests.cpu=100m \
    --set values.pilot.resources.requests.memory=256Mi \
    --set values.global.proxy.resources.requests.cpu=10m \
    --set values.global.proxy.resources.requests.memory=48Mi \
    --set values.global.proxy.resources.limits.memory=256Mi \
    --set values.gateways.seccompProfile.type=RuntimeDefault
}

main() {
  check_tools
  check_docker_memory
  start_minikube
  install_gateway_api
  install_istio
  kubectl -n istio-system rollout status deploy/istiod --timeout=300s
  kubectl -n istio-system rollout status ds/istio-cni-node --timeout=300s
  kubectl -n kube-system rollout status deploy/metrics-server --timeout=300s
  kubectl get pods -A
}

main "$@"
