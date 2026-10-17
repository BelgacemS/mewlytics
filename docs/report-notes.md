# Notes pour le rapport

Journal tenu à chaque palier, avant le tag. Il sert de base à la rédaction du rapport (étape 43 du plan). Les captures sont dans `captures/`, qui n'est pas versionné.

Pour chaque palier : ce qui est atteint, les preuves (commande et capture), les choix à justifier, les mesures, et ce qui reste à reprendre pour le rapport.

## Palier 10 : un service conteneurisé et déployé

Tag `v0.10.0`, 16/10/2026.

Atteint : le service `catalog` (FastAPI, lecture des tournois, SQLite en mémoire) est conteneurisé, publié sur Docker Hub en amd64 et arm64 par la CI, et déployé dans minikube avec un pod durci.

| Preuve | Commande | Capture |
|---|---|---|
| Image publiée, deux architectures | `docker buildx imagetools inspect belgacems/mewlytics-catalog:0.10.0` | `etape-07-dockerhub.png` (tags `0.10.0` et `0.12.0`), `etape-05-dockerhub.png` (premier tag publié, `0.10.0-rc.1`) |
| Deployment, pod Running avec l'image `0.10.0`, Service | `kubectl -n mewlytics get deploy,pods,svc -o wide` | `etape-06-pods.png` |
| Le pod respecte la PSA `restricted` | `kubectl label --dry-run=server --overwrite ns mewlytics pod-security.kubernetes.io/enforce=restricted` | `etape-06-pods.png` |
| Le service répond | `kubectl -n mewlytics port-forward svc/catalog 8000:8000`, puis `curl` sur `/healthz`, `/api/catalog/tournaments` et `/api/catalog/tournaments/1` | `etape-06-curl.png` |
| Documentation OpenAPI | `/api/catalog/docs` dans le navigateur, via le port-forward | `etape-06-docs.png` |

Choix à justifier :
- FastAPI : validation des entrées et OpenAPI intégrées, peu de code.
- Base « en mémoire d'abord », comme le demande l'énoncé : SQLite en mémoire via SQLAlchemy, avec `StaticPool` et un verrou global. Le même code passera sur MySQL en changeant `DATABASE_URL`.
- Image : Dockerfile multi-stage avec uv, utilisateur non root, lancement direct du Python du venv. Le conteneur démarre avec le système de fichiers en lecture seule.
- Pod durci : seccomp `RuntimeDefault` au niveau du pod (il couvre aussi les conteneurs injectés par Istio), `runAsNonRoot`, `readOnlyRootFilesystem` avec un `emptyDir` sur `/tmp`, `capabilities: drop [ALL]`, requests, limits et probes.
- PSA `restricted` d'abord en `warn` et `audit`. Le mode `enforce` arrive à l'étape 25, une fois tous les workloads vérifiés.
- Chaîne d'approvisionnement : actions GitHub épinglées par SHA, images de base épinglées par digest et tenues à jour par Dependabot, permissions minimales. Le token Docker Hub est dans un environnement GitHub réservé aux tags `v*`.
- Tags d'image immuables, jamais `latest`.
- Cluster : minikube à 4 Go, Istio en mode sidecar plutôt qu'ambient, d'après les mesures de l'étape 2 (voir le README, section Memory).

Mesures : `catalog` utilisait 75 Mi à l'étape 6.

À reprendre pour le rapport : les captures de l'étape 6 datent d'avant Istio (pod en 1/1, sans sidecar). C'est l'état du palier 10, à préciser dans la légende.

## Palier 12 : gateway

Tag `v0.12.0`, 17/10/2026.

Atteint : chaque pod du namespace reçoit un sidecar Istio. Une `Gateway` (Gateway API, classe `istio`) écoute en HTTP sur le port 80, et une `HTTPRoute` envoie `/api/catalog` vers `catalog`. En local, on y accède par `minikube tunnel` à l'adresse `127.0.0.1`.

| Preuve | Commande | Capture |
|---|---|---|
| Requête à travers la gateway : 200 et `server: istio-envoy` | `curl -i http://127.0.0.1/api/catalog/tournaments` | `etape-07-curl.png` |
| `catalog` en 2/2 (application et sidecar), Service `gateway-istio` en LoadBalancer, Gateway `PROGRAMMED True` | `kubectl -n mewlytics get pods,svc,gateway,httproute` | `etape-07-ressources.png` |
| Configuration Istio valide | `istioctl analyze -n mewlytics` | `etape-07-analyze.png` |
| Gateway et sidecars respectent la PSA `restricted` | `kubectl label --dry-run=server --overwrite ns mewlytics pod-security.kubernetes.io/enforce=restricted` | `etape-07-psa.png` |
| Image `0.12.0` publiée, deux architectures | `docker buildx imagetools inspect belgacems/mewlytics-catalog:0.12.0`, run CI 39031694728 | `etape-07-dockerhub.png` |

Choix à justifier :
- Gateway API plutôt que `VirtualService` et `Gateway` d'Istio : c'est l'API standard de Kubernetes, qui succède à Ingress (Ingress NGINX est retiré), et Istio compte en faire son API de trafic par défaut.
- Istio déploie lui-même le proxy de la gateway à partir de l'objet `Gateway`. Son seccomp `RuntimeDefault`, réglé à l'installation, lui permet de passer la PSA `restricted`.
- Sidecars natifs et CNI d'Istio : pas de conteneur `istio-init` privilégié (`NET_ADMIN`), donc des pods compatibles avec la PSA `restricted`, et des Jobs qui se terminent.
- La gateway n'accepte que les routes de son namespace (`from: Same`).
- `PathPrefix /api/catalog` sans réécriture, car `catalog` sert déjà ses routes sous ce préfixe. Une `HTTPRoute` par service.

Audit du diff `v0.10.0..v0.12.0` :
- Aucun bug trouvé.
- Envoy normalise les chemins avant le routage : `/api/catalog/../healthz` et `/api/catalog/%2e%2e/healthz` renvoient 404 sans atteindre `catalog`, et `/api/catalogx` n'est pas routé.
- Les points de durcissement trouvés sont reportés dans le plan : en-têtes Envoy et doc Swagger publique à l'étape 24, port 15021 exposé à l'étape 29.
- `scripts/deploy.sh` attend désormais la création de `gateway-istio` par istiod. Sans ce correctif, le script pouvait réussir sans gateway.

Mesures (17/10/2026, Docker Desktop à 4,5 Go) :

| Composant | Mémoire |
|---|---|
| Proxy de la gateway | 137 Mi |
| Sidecar de `catalog` | 34 Mi |
| istiod juste après un redémarrage | 43 Mi |
| istiod après plusieurs jours de fonctionnement | 165 Mi |
| Conteneur minikube | 2,46 GiB sur 4, cache de fichiers compris |

À reprendre pour le rapport :
- `etape-07-curl.png` contient du texte parasite à droite de la ligne `[]%` : recadrer l'image.
- `kubectl port-forward` contourne le mesh : le préciser quand on l'utilise comme preuve.
