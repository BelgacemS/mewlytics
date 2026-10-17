# Mewlytics

Pokémon VGC tournament results, teams and stats (format M-C). Follow the latest Limitless tournaments with their standings, teams and matches, see which Pokémon are used and how they perform, and add your own local tournaments. Pokémon are also ranked in three tier lists: raw win rates, shrunk win rates, and a Bradley-Terry model that corrects for player skill.

The application is built as microservices on Kubernetes.

Work in progress. Setup and development commands are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Local cluster

Pinned versions (also in `scripts/versions.sh`):

| Component | Version |
|---|---|
| minikube | v1.39.0 |
| Kubernetes | v1.36.5 |
| Istio | 1.31.1 (supports Kubernetes 1.32 to 1.37) |
| Gateway API CRDs | v1.6.3 |

Requirements: Docker Desktop with at least 4.5 GB of memory, minikube, kubectl, and istioctl at the pinned version:

```sh
brew install minikube
cd ~ && curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.31.1 sh -
echo 'export PATH="$HOME/istio-1.31.1/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Create the cluster (minikube with 4 GB and 4 CPUs, metrics-server, Gateway API CRDs, Istio in sidecar mode with the CNI):

```sh
scripts/bootstrap-minikube.sh
```

Kiali and Prometheus are only installed while taking screenshots:

```sh
scripts/addons.sh install
istioctl dashboard kiali
scripts/addons.sh remove
```

Stop the cluster between sessions with `minikube stop`. The first run of `scripts/bootstrap-minikube.sh` took 7 min 23 s, mostly image downloads.

### Deploy

Deploy the images published on Docker Hub, at the tags set in `k8s/overlays/local`:

```sh
scripts/deploy.sh local
```

To try local changes, build a service inside minikube and deploy that build instead:

```sh
scripts/deploy.sh local --dev catalog
```

All pods in the `mewlytics` namespace get an Istio sidecar. Pods created before injection was enabled only get it after `kubectl -n mewlytics rollout restart deploy`.

The application is reached through the Istio gateway, which gets an address once `minikube tunnel` runs. Keep it open in a separate terminal: it asks for the sudo password because the gateway listens on port 80. With the docker driver on macOS, the address is `127.0.0.1`:

```sh
minikube tunnel
curl http://127.0.0.1/api/catalog/tournaments
```

### Memory

Measured on a MacBook Air M1 with 8 GB, Docker Desktop at 4.5 GB, minikube at 4 GB, three test pods with a sidecar (Python `http.server`), and a browser and an editor open:

| | Memory |
|---|---|
| minikube node (`kubectl top node`) | 1602 Mi of 4 Gi |
| Kubernetes control plane and system pods | 888 Mi, of which kube-apiserver 460 Mi |
| istiod | 48 to 63 Mi |
| istio-cni-node | 49 Mi |
| Sidecar, per pod | 30 to 34 Mi |
| Kiali and Prometheus, while installed | 224 Mi |
| minikube container during `minikube image build` (`docker stats`) | 1.77 GiB peak |

No pod was OOM killed during the image build. macOS reported memory pressure at the warning level (yellow), never critical, with about 2.6 GB of swap in use.

Decision: Istio stays in sidecar mode. The three sidecars use about 100 Mi in total and the node keeps about 2.4 Gi free, so the ambient mode would save little and would require a waypoint for the L7 policies. Memory will be measured again on the real application.

## Data sources

- Tournament data comes from the public [Limitless API](https://docs.limitlesstcg.com/developer/tournaments). No scraping, and requests stay within the API rate limits.
- Species data (types, base stats, abilities) comes from [PokéAPI](https://pokeapi.co/). It is loaded once into our database and not requested again at runtime, following the PokéAPI fair use policy.

## Disclaimer

This is a student project for a Master's course at Université Paris Cité. It is not affiliated with, endorsed by or sponsored by Nintendo, Creatures, Game Freak, The Pokémon Company or Limitless. Pokémon and related names are trademarks of their respective owners. No official artwork is included in this repository.
