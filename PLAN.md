# Mewlytics : plan

## Objectif

Une application en microservices sur les tournois Pokémon VGC, format M-C. Elle :
- recense les tournois Limitless ;
- offre un espace utilisateur pour saisir des tournois locaux ;
- affiche des statistiques et trois tier lists : brute, rétrécie, et corrigée du niveau des joueurs par un modèle de Bradley-Terry.

Objectif de notation : la grille du cours jusqu'au palier 18, puis le bonus cloud.

Critère de réussite global, depuis un clone neuf :
- La chaîne suivante déploie l'application à partir des images Docker Hub : `scripts/bootstrap-minikube.sh`, `scripts/create-secrets.sh`, `scripts/deploy.sh local`, puis `scripts/ingest.sh initial` (tournois, puis Pokédex).
- `https://<ip-gateway>/` affiche les tournois, les statistiques et les trois tier lists, et permet de s'inscrire et de saisir un tournoi.
- `scripts/check-security.sh` (contrôles des étapes 20 à 26) passe.
- `uv run --package analytics python -m analytics.export --until <date de gel>`, puis `uv run --package analytics python -m analytics.evaluate --until <date de gel>`, reproduisent le tableau de résultats du rapport, au hash du snapshot près.

## Contraintes

- Énoncé : microservices REST et/ou gRPC (gRPC en bonus), Docker, Kubernetes, images publiées sur Docker Hub.
- Paliers :
  - 10 : un service conteneurisé et déployé ;
  - 12 : gateway ;
  - 14 : un deuxième service relié au premier ;
  - 16 : base de données, d'abord en mémoire, sans Kubernetes ;
  - 18 : sécurité ;
  - 20 : cloud, en bonus.
- Critères de notation, par ordre d'importance : intégration des technologies, code, fonctionnalités, front.
- Rendu : mini rapport avec captures, envoyé par mail, et dépôt GitHub `git@github.com:BelgacemS/mewlytics.git`. Date limite : 27/12/2026. Pas de planning daté : on avance aussi vite que possible.
- Matériel : deux Mac de 8 Go. Le cluster local doit tenir dans environ 4 Go.
- Données :
  - API publique Limitless, sans scraping, en respectant les limites de débit ;
  - PokéAPI chargée une seule fois en base ;
  - pas d'image officielle, de secret ni de données dans git, sauf de petites fixtures de test anonymisées et le JSON des métriques agrégées.
- Hors périmètre : LLM, RL, réseaux de neurones, suggestion automatique d'équipe, temps réel.

## Choix techniques

| Sujet | Choix | Justification |
|---|---|---|
| Services | Python 3.12, FastAPI, uvicorn (un worker) | validation et OpenAPI intégrées, peu de code |
| Environnement | workspace uv : un `pyproject.toml` par service, un seul `uv.lock`. Commandes `uv sync --all-packages` et `uv run --package <svc> ...` | versions identiques entre services |
| Base | SQLAlchemy 2.0 et `DATABASE_URL`. SQLite en mémoire pour les tests et les paliers 10 à 14 (`StaticPool`, écritures sous un verrou global), puis MySQL 8.4 | même code ; c'est le « en mémoire d'abord » demandé par l'énoncé |
| Base par service | une instance MySQL, un schéma et un utilisateur par service | isolation sans trois serveurs en RAM |
| Liens internes | REST de `catalog` vers `auth` (JWKS) et d'`ingestion` vers `analytics` (refresh) ; gRPC (`grpc.server` synchrone) d'`ingestion` et d'`analytics` vers `catalog` | palier 14 atteint sans gRPC ; gRPC rapporte le bonus avec un contrat typé et du streaming |
| Stubs gRPC | générés par script, commités, contrôlés en CI | Dockerfiles simples |
| Sondes | HTTP `/healthz` | gRPC tourne dans le même processus |
| Auth | argon2-cffi, PyJWT en RS256 (`iss`, `kid`), JWKS publié par `auth` | standard ; passlib n'est plus maintenu |
| Gateway | Istio avec la Gateway API Kubernetes (`Gateway`, `HTTPRoute`) | successeur d'Ingress (Ingress NGINX est retiré) ; Istio compte en faire son API de trafic par défaut |
| Mesh | Istio en sidecar (sidecars natifs), version mineure supportée au moins égale à 1.27. CNI activé, profil minimal, `values.gateways.seccompProfile.type=RuntimeDefault` | mTLS, autorisations, Jobs qui se terminent. Le CNI et le seccomp rendent la PSA `restricted` possible |
| Cluster | minikube, 4 Go, sans l'addon `ingress` (c'est Ingress NGINX), avec `metrics-server`. Images de développement construites dans le cluster avec `minikube image build` | tenir dans 8 Go et mesurer la mémoire |
| Manifestes | Kustomize : `k8s/base` et `k8s/overlays/{local,gke}`, tags d'image immuables. Jobs manuels hors kustomization, lancés par `scripts/ingest.sh`. Manifestes générés dans `generated/` (non versionné) | intégré à kubectl ; les Jobs sont immuables |
| Front | Vue 3 + Vite, CSS écrit à la main, servi par `nginx-unprivileged` | framework cité par l'énoncé, le plus simple des trois |
| CI | GitHub Actions : ruff, pytest (avec MySQL en conteneur), build amd64 + arm64 sous QEMU pour chaque service, push Docker Hub sur tag. Trivy via l'image `aquasec/trivy` épinglée par digest, dans un job sans secrets. Actions épinglées par SHA, permissions minimales | qualité, images multi-architecture, chaîne d'approvisionnement protégée (trivy-action compromis en mars 2026, CVE-2026-33634) |
| Cloud | GKE Standard zonal, 2 nœuds `e2-medium`, crédit d'essai Google Cloud | le crédit mensuel GKE couvre les frais d'un cluster zonal ; cluster supprimé après les captures |

## Architecture

```
Navigateur --HTTPS--> Istio Gateway
   /            -> web        (SPA)
   /api/auth    -> auth       (REST)          -> MySQL schéma auth
   /api/catalog -> catalog    (REST + gRPC)   -> MySQL schéma catalog
                     catalog --REST JWKS--> auth
   /api/stats   -> analytics  (REST)          -> MySQL schéma analytics
                     analytics --gRPC StreamEntries/StreamMatches--> catalog
Job/CronJob ingestion tournaments --gRPC UpsertTournament--> catalog, puis --REST POST /internal/refresh--> analytics
Job ingestion pokedex             --gRPC StreamEntries puis UpsertSpecies--> catalog
```

- `catalog` est le seul propriétaire des tournois, des équipes, des matchs et du référentiel Pokémon.
- `analytics` recalcule ses statistiques et son modèle dans une tâche de fond, à chaque `POST /internal/refresh` (route non exposée par la gateway) et au démarrage si son schéma est vide. Il stocke les résultats dans son schéma et les sert depuis la base.
- `ingestion` calcule l'identifiant canonique d'espèce : `raichu` avec l'objet `Raichunite X` donne `raichu-mega-x`. La correspondance (objet vers forme méga, identifiant Limitless vers identifiant PokéAPI) est dans `services/ingestion/src/ingestion/species_map.csv`.

## Tenir dans 8 Go

- minikube avec `--memory=4096 --cpus=4`. La VM Docker Desktop doit avoir au moins 4,5 Go.
- En développement, les images sont construites dans le cluster avec `minikube image build`. On ne lance pas de `docker build` sur l'hôte en même temps.
- Ressources réduites :
  - requests réduites pour istiod et les sidecars ;
  - une réplique partout ;
  - MySQL avec `performance_schema=OFF` et un buffer pool de 64 Mo.
- Kiali et Prometheus ne sont installés que le temps des captures (`scripts/addons.sh install|remove`). `minikube stop` entre deux sessions.
- Mémoire mesurée à l'étape 2 sur des pods factices, puis aux étapes 17 et 37 sur l'application réelle (`kubectl top pods -A`, noté dans le README).
- Si ça ne tient pas, dans l'ordre :
  1. passer Istio en mode ambient avec `platform=minikube`. Les règles L7 des étapes 22 et 23 demandent alors un waypoint et des politiques en `targetRefs` ;
  2. faire la démo finale sur GKE.

## Workflow git

- Branches :
  - `main` : stable, mise à jour à chaque palier atteint et taguée (`v0.10.0`, `v0.12.0`, ..., `v1.0.0`) ;
  - `dev` : intégration ;
  - une branche par étape (`feat/<sujet>`, `fix/<sujet>`), créée depuis `dev` au début de l'étape, mergée dans `dev` avec `--no-ff`, puis supprimée.
  
  Exception : l'étape 1 commite directement sur `main`, puis crée `dev`.
- Commits : messages courts et concrets, en anglais, à l'impératif, sans préfixe de type.
  - Exemples : `Init repository`, `Skip pairings without opponent`.
  - Pas de corps de commit sans vrai besoin, pas de trailer.
- Fin d'étape vérifiée : on coche la case de l'étape dans `PLAN.md`, puis commit sur la branche de l'étape (le commit contient le plan à jour) et merge dans `dev`. Le push et le merge de `dev` dans `main` se font sur demande.
- On prévient l'autre avant de commencer une étape. Une étape dont toutes les dépendances sont cochées peut se faire en parallèle d'une autre.
- Ignorés par git :
  - `idee.md`, `sujet.pdf` ;
  - `.env`, `*.pem`, `*.key`, `*.crt`, `generated/`, `k8s/overlays/dev/` ;
  - `data/`, `runs/`, `node_modules/`, `dist/`, `.venv/`.

## Étapes

Légende : [cœur] = cœur de la méthode, à savoir défendre à l'oral. Sauf mention « Dépend de », chaque étape dépend de la précédente.

### A. Mise en place

- [x] 1. Dépôt
  - Objectif :
    - `git init`, remote GitHub, `.gitignore` ;
    - commit sur `main`, puis création de `dev` ;
    - workspace uv racine, avec ruff et pytest en dépendances de dev ;
    - `README.md` minimal : description, non-affiliation à Nintendo et à The Pokémon Company, attribution de Limitless et de PokéAPI ;
    - `CONTRIBUTING.md` : workflow git et commandes uv exactes.
  - Fichiers : `.gitignore`, `pyproject.toml`, `uv.lock`, `README.md`, `CONTRIBUTING.md`, `PLAN.md` (versionné, case de l'étape 1 cochée).
  - Vérification :
    - `git check-ignore idee.md sujet.pdf .env` liste les 3 fichiers ;
    - `uv sync --all-packages` passe ;
    - `git log` montre un seul commit, d'auteur BelgacemS, sans trailer ;
    - `git ls-files` contient `PLAN.md` et `git status` est propre ;
    - la branche `dev` existe.
  - Hors périmètre : tout code de service.

- [x] 2. Cluster local et mémoire
  - Objectif :
    - `scripts/bootstrap-minikube.sh` : minikube avec `metrics-server`, CRD Gateway API, Istio en profil minimal avec CNI, ressources réduites et `values.gateways.seccompProfile.type=RuntimeDefault` ;
    - `scripts/addons.sh install|remove` pour Kiali et Prometheus ;
    - 3 pods de test avec sidecar ;
    - mesurer la mémoire, puis trancher entre sidecar et ambient ;
    - épingler dans le README les versions de minikube, de Kubernetes et d'Istio (une mineure supportée selon la matrice de support).
    
    Le script dure plus de quelques minutes : c'est nous qui le lançons.
  - Fichiers : `scripts/bootstrap-minikube.sh`, `scripts/addons.sh`, `k8s/spike/` (supprimé à la fin de l'étape), `README.md`.
  - Vérification :
    - `kubectl get pods -A` : tout est Running ;
    - un pod de test a l'init container `istio-validation` et pas d'`istio-init`, ce qui prouve que le CNI est actif ;
    - `kubectl top node` ;
    - un `minikube image build` pendant que les pods de test tournent, sans OOM ;
    - le Moniteur d'activité n'affiche pas de pression mémoire rouge avec le navigateur et l'éditeur ouverts ;
    - la décision et les mesures sont notées dans le README.
  - Hors périmètre : nos services.

### B. Palier 10 : un service conteneurisé et déployé

- [x] 3. Service `catalog` en lecture
  - Objectif :
    - modèles SQLAlchemy : tournoi, joueur, participation, membre d'équipe, match ;
    - `db.py` : en SQLite mémoire, `StaticPool` et sessions prises sous un `threading.Lock` global. C'est le seul usage que `StaticPool` supporte ;
    - endpoints en `def` : `GET /api/catalog/tournaments`, `GET /api/catalog/tournaments/{id}`, `/healthz`.
  - Fichiers : `services/catalog/`.
  - Vérification : `uv run --package catalog pytest services/catalog` ; `uv run --package catalog uvicorn catalog.main:app` puis `curl` sur chaque endpoint.
  - Hors périmètre : écritures, gRPC.

- [ ] 4. Image Docker
  - Objectif : Dockerfile multi-stage avec uv, utilisateur non root, image slim. Le conteneur lance directement le Python du venv, pas `uv run`.
  - Fichiers : `services/catalog/Dockerfile`, `.dockerignore`.
  - Vérification :
    - `minikube image build` réussit ;
    - le conteneur démarre et répond sur `/healthz`, y compris avec le système de fichiers en lecture seule et `/tmp` en tmpfs.

- [ ] 5. CI et publication sur Docker Hub
  - Objectif :
    - workflow : ruff et pytest à chaque push ;
    - sur tag, une matrice par service : build `linux/amd64,linux/arm64` sous QEMU et push vers `<user>/mewlytics-<svc>` (images publiques). Pour commencer, `catalog` seulement ;
    - actions épinglées par SHA complet, `permissions:` au minimum ;
    - compte Docker Hub avec 2FA, token d'accès dédié stocké dans les secrets GitHub.
  - Fichiers : `.github/workflows/ci.yml`.
  - Vérification :
    - run vert ;
    - `docker buildx imagetools inspect <image>` montre les deux architectures ;
    - capture de la page Docker Hub.
    
    L'étape suppose un push, donc notre accord.

- [ ] 6. Déploiement Kubernetes
  - Objectif :
    - namespace avec les labels `pod-security.kubernetes.io/warn=restricted` et `audit=restricted` ;
    - Deployment et Service de `catalog`, sur un gabarit durci :
      - seccomp `RuntimeDefault` dans `spec.securityContext` du pod, pour couvrir aussi les conteneurs injectés ;
      - `runAsNonRoot` ;
      - `readOnlyRootFilesystem` avec un `emptyDir` sur `/tmp` ;
      - `capabilities: drop [ALL]` ;
      - requests, limits et probes ;
    - Kustomize, base et overlay local, avec un tag d'image immuable ;
    - `scripts/deploy.sh local` déploie les images Docker Hub, et `scripts/deploy.sh local --dev <svc>` lance `minikube image build -t <user>/mewlytics-<svc>:dev-<sha>` puis `kustomize edit set image` dans `k8s/overlays/dev/`, qui n'est pas versionné.
  - Fichiers : `k8s/base/`, `k8s/overlays/local/`, `scripts/deploy.sh`.
  - Vérification :
    - le pod est Running ;
    - `kubectl label --dry-run=server --overwrite ns <ns> pod-security.kubernetes.io/enforce=restricted` ne renvoie aucun avertissement ;
    - `kubectl port-forward` puis `curl` répond ;
    - captures prises.
    
    Merge dans `main` et tag `v0.10.0` sur demande.

### C. Palier 12 : gateway

- [ ] 7. Gateway Istio
  - Objectif : injection des sidecars dans le namespace, `Gateway` et `HTTPRoute` pour `/api/catalog`, `minikube tunnel`.
  - Fichiers : `k8s/base/istio/`.
  - Vérification :
    - `curl http://<ip>/api/catalog/tournaments` passe par la gateway ;
    - le pod de gateway a le seccomp `RuntimeDefault` (réglé à l'installation d'Istio, étape 2) ;
    - le dry-run du label `enforce` (voir l'étape 6) ne renvoie aucun avertissement ;
    - `istioctl analyze` ne signale aucune erreur ;
    - captures prises.
    
    Tag `v0.12.0`.

### D. Palier 14 : deux services reliés

- [ ] 8. Service `auth` en local
  - Objectif :
    - `POST /api/auth/register` ;
    - `POST /api/auth/login`, qui renvoie un JWT RS256 avec `iss`, `kid` et une expiration ;
    - `GET /api/auth/.well-known/jwks.json` ;
    - table des utilisateurs : nom d'utilisateur et hash argon2, pas d'email.
  - Fichiers : `services/auth/`.
  - Vérification : tests (mot de passe faux, doublon, jeton expiré, JWKS lisible par `jwt.PyJWKClient`) ; `curl` en local.
  - Dépend de : 3.

- [ ] 9. `auth` dans le cluster
  - Objectif :
    - `scripts/gen-jwt-keys.sh` génère les clés. `scripts/create-secrets.sh` les range dans un Secret et reste idempotent : il ne régénère pas une clé déjà présente. Le Secret du cluster est la source de vérité ;
    - image ajoutée à la CI ;
    - Deployment avec une limite mémoire de 256 Mi, parce qu'argon2 est gourmand ;
    - route `/api/auth`.
  - Fichiers : `scripts/gen-jwt-keys.sh`, `scripts/create-secrets.sh`, `.env.example`, `services/auth/Dockerfile`, `k8s/base/auth/`.
  - Vérification :
    - via la gateway, `curl` register puis login renvoie un jeton ;
    - la clé ne change ni après un redémarrage du pod, ni après une deuxième exécution de `create-secrets.sh` ;
    - le dry-run du label `enforce` ne renvoie aucun avertissement.
  - Dépend de : 7, 8.

- [ ] 10. Tournois saisis par les utilisateurs
  - Objectif :
    - `POST /api/catalog/me/tournaments` (vainqueur et son équipe, ou top 16) et `GET /api/catalog/me/tournaments`, en `def` parce que `PyJWKClient` est synchrone ;
    - `catalog` récupère le JWKS chez `auth` en REST interne et le garde en cache ;
    - les tournois saisis portent `source=user` et `verified=false`.
  - Fichiers : `services/catalog/`.
  - Vérification :
    - tests : 401 sans jeton, 201 avec un jeton valide ;
    - même chose via la gateway ;
    - capture Kiali du graphe gateway -> catalog -> auth, après un redémarrage de `catalog` pour vider le cache.
    
    Tag `v0.14.0`.

### E. Ingestion et gRPC (bonus gRPC)

- [ ] 11. Contrat gRPC et serveur dans `catalog`
  - Objectif :
    - `proto/mewlytics/v1/catalog.proto` : package `mewlytics.v1`, service `Catalog`, méthodes `UpsertTournament`, `UpsertSpecies`, `StreamEntries` et `StreamMatches` ;
    - `scripts/gen-proto.sh` et le paquet `libs/proto` ;
    - un `grpc.server` synchrone avec `ThreadPoolExecutor`, à l'écoute sur `[::]` : `start()` dans le lifespan de FastAPI, jamais `wait_for_termination()`, et `stop(grace).wait()` à l'arrêt ;
    - une session par appel, sous le verrou en mode SQLite ;
    - le port `grpc` du Service avec `appProtocol: grpc` ;
    - un job CI qui vérifie que les stubs sont à jour.
  - Fichiers : `proto/`, `libs/proto/`, `scripts/gen-proto.sh`, `services/catalog/`, `k8s/base/catalog/`.
  - Vérification :
    - test avec un serveur dans le même processus : un upsert puis un stream rendent les données envoyées ;
    - la CI échoue si on modifie le proto sans régénérer les stubs.
  - Dépend de : 6.

- [ ] 12. Client et parsing Limitless
  - Objectif :
    - client httpx : pagination, une requête par seconde, retries ;
    - fonctions de parsing pures :
      - calcul de l'identifiant canonique avec `species_map.csv` ;
      - exclusion des égalités, des doubles défaites, des byes et des `winner = -1` sans adversaire ;
      - lecture du mode par phase ;
      - tournois mixtes BO1/BO3 marqués comme tels ;
      - seuls les tournois terminés sont retenus.
  - Fichiers : `services/ingestion/`, dont `src/ingestion/species_map.csv`.
  - Vérification : tests sur de petites fixtures anonymisées tirées de vraies réponses, avec au moins un cas par règle d'exclusion.
  - Hors périmètre : l'envoi vers `catalog`.
  - Dépend de : 1.

- [ ] 13. Envoi vers `catalog` et CLI
  - Objectif :
    - conversion en messages proto et upsert idempotent ;
    - `python -m ingestion tournaments --format M-C --since <date>` ;
    - si `ANALYTICS_URL` est défini, appel final à `POST <ANALYTICS_URL>/internal/refresh`. Un échec est journalisé et fait échouer le Job, ce qui est sans risque puisque l'upsert est idempotent.
  - Vérification : contre un `catalog` local, deux exécutions consécutives donnent les mêmes nombres de tournois et de matchs.
  - Dépend de : 11, 12.

- [ ] 14. CronJob et Jobs d'ingestion
  - Objectif :
    - image ajoutée à la CI ;
    - ServiceAccount dédié ;
    - CronJob quotidien sur une fenêtre glissante (`--since` à J-3), avec `concurrencyPolicy: Forbid` ;
    - les Jobs manuels restent hors de `k8s/base`. `scripts/ingest.sh initial|pokedex` fait `kubectl delete job <nom> --ignore-not-found`, puis `kubectl create -f` sur le manifeste rendu par `kubectl kustomize k8s/jobs/<env>` avec le tag courant. Le mode `initial` charge les tournois depuis le 12/09/2026.
  - Fichiers : `services/ingestion/Dockerfile`, `k8s/base/ingestion/`, `k8s/jobs/`, `scripts/ingest.sh`, `README.md`.
  - Vérification :
    - `scripts/ingest.sh initial` se termine en Completed (le sidecar s'arrête) ;
    - les tournois sont visibles via la gateway ;
    - la durée du chargement initial (environ 30 min attendues) est notée dans le README.
    
    Jusqu'à l'étape 18, les données sont perdues à chaque redémarrage de `catalog`.
  - Dépend de : 7, 13.

- [ ] 15. Statistiques descriptives dans `analytics`
  - Objectif :
    - une tâche de fond, déclenchée par `POST /internal/refresh` et au démarrage, lit `catalog` en gRPC. Au démarrage, elle réessaie tant que `catalog` ne répond pas. Le calcul se fait hors session : seule l'écriture est faite sous le verrou SQLite ;
    - elle calcule l'usage, le win rate brut par espèce, par paire et par matchup, et les fréquences d'objets, de talents, d'attaques et de tera par espèce, avec un filtre `source=official|all`. Les matchs miroirs sont exclus du win rate d'une espèce ;
    - les résultats sont enregistrés en base ;
    - API : `GET /api/stats/pokemon`, `/pairs`, `/matchups`.
  - Fichiers : `services/analytics/`.
  - Vérification : tests sur un petit jeu synthétique aux valeurs calculées à la main.
  - Dépend de : 11.

- [ ] 16. Déploiement d'`analytics`
  - Objectif : image ajoutée à la CI, Deployment, route `/api/stats`, et `ANALYTICS_URL` passé au CronJob et aux Jobs d'ingestion.
  - Fichiers : `k8s/base/analytics/`, `k8s/base/ingestion/`, `k8s/jobs/`.
  - Vérification :
    - après `scripts/ingest.sh initial`, `curl /api/stats/pokemon` via la gateway renvoie des données, sans redémarrer `analytics` ;
    - le graphe Kiali montre analytics -> catalog (gRPC) et ingestion -> analytics.
  - Dépend de : 7, 14, 15.

### F. Palier 16 : base de données

- [ ] 17. MySQL dans le cluster
  - Objectif :
    - StatefulSet `mysql:8.4` avec PVC ;
    - `runAsUser` et `fsGroup` 999 ; `emptyDir` sur `/var/run/mysqld` et `/tmp`, et sur `/var/lib/mysql-files` si le démarrage l'exige ;
    - port du Service nommé `tcp-mysql`, et `PeerAuthentication` STRICT sur `app: mysql`, ce que la doc Istio recommande pour un protocole où le serveur parle en premier ;
    - ConfigMap `my.cnf` réglée pour la mémoire ;
    - script d'init qui crée les schémas et un utilisateur par service ;
    - `create-secrets.sh` complété.
  - Fichiers : `k8s/base/mysql/`, `scripts/create-secrets.sh`, `.env.example`.
  - Vérification :
    - `SHOW DATABASES` liste les schémas ;
    - l'utilisateur `catalog` ne peut pas lire le schéma `auth` ;
    - `kubectl exec mysql-0 -- ls -ld /var/lib/mysql` montre le bon propriétaire ;
    - le dry-run du label `enforce` ne renvoie aucun avertissement ;
    - `kubectl top pods -A` est noté dans le README.
  - Dépend de : 16.

- [ ] 18. Bascule des services sur MySQL
  - Objectif :
    - `DATABASE_URL` lue depuis un Secret, avec PyMySQL ;
    - un helper d'upsert qui gère les deux dialectes ;
    - `analytics` sert ses résultats depuis son schéma, et ne recalcule au démarrage que si ce schéma est vide ;
    - un job CI avec MySQL (`pytest -m mysql`).
  - Fichiers : `services/*/src/*/db.py`, `k8s/base/*/`, `.github/workflows/ci.yml`.
  - Vérification :
    - après suppression du pod `catalog`, puis du pod `mysql`, les données sont toujours là ;
    - après un redémarrage d'`analytics`, les statistiques répondent immédiatement ;
    - CI verte.

- [ ] 19. Référentiel Pokémon
  - Objectif :
    - `python -m ingestion pokedex` lit les espèces vues via `StreamEntries`, récupère leurs données sur PokéAPI (types, statistiques de base, talents, table des types) et les envoie via `UpsertSpecies`. L'opération est idempotente ;
    - lancement par `scripts/ingest.sh pokedex` après le chargement initial (`scripts/ingest.sh initial` enchaîne les deux), puis à la main si `species_map.csv` change ;
    - endpoints `GET /api/catalog/pokemon` et `/pokemon/{id}`.
  - Fichiers : `services/ingestion/`, `services/catalog/`, `k8s/jobs/`, `scripts/ingest.sh`.
  - Vérification :
    - le Job se termine en Completed ;
    - chaque espèce vue a des types ;
    - les identifiants non résolus sont listés puis ajoutés à `species_map.csv`.
    
    Tag `v0.16.0`.

### G. Palier 18 : sécurité

Chaque étape de cette section ajoute ses contrôles à `scripts/check-security.sh`.

- [ ] 20. ServiceAccounts et RBAC
  - Objectif :
    - un ServiceAccount par workload, avec `automountServiceAccountToken: false` ;
    - un Role `viewer` en lecture seule et son RoleBinding vers un ServiceAccount `viewer` ;
    - création de `scripts/check-security.sh`.
  - Vérification : `scripts/check-security.sh` vérifie avec `kubectl auth can-i ... --as=system:serviceaccount:<ns>:viewer` :
    - `get pods` répond yes ;
    - `delete pods`, `get secrets`, `create pods/portforward` et `create pods/exec` répondent no.
    
    L'application fonctionne toujours.

- [ ] 21. mTLS strict
  - Objectif :
    - `PeerAuthentication` STRICT sur le namespace ;
    - pods de test :
      - un pod sans sidecar dans le namespace `default` (pas d'injection, pas d'`enforce`) ;
      - `k8s/tests/intruder.yaml`, conforme à `restricted`, avec son propre ServiceAccount, pour les tests de l'étape 22.
  - Vérification :
    - depuis le pod de `default`, l'appel à `catalog` échoue ;
    - l'application fonctionne via la gateway ;
    - capture du cadenas mTLS dans Kiali.

- [ ] 22. Autorisations par identité
  - Objectif :
    1. En même temps, poser une `AuthorizationPolicy` vide (tout refuser) et une règle `action: ALLOW` avec `rules: [{}]` sur le workload gateway (sélecteur `gateway.networking.k8s.io/gateway-name: <nom>`).
    2. Ajouter ensuite les règles une par une, chacune vérifiée par un `curl` avant la suivante. Les ports sont ceux des pods, pas ceux des Services. Le principal de la gateway est généré par Istio : on le relève avec `kubectl get sa`.
       - gateway vers auth, catalog, analytics et web. Une règle qui ne vise encore aucun pod ne gêne rien ;
       - catalog vers auth ;
       - ingestion vers `/mewlytics.v1.Catalog/Upsert*` et `/mewlytics.v1.Catalog/StreamEntries`, et vers `POST /internal/refresh` d'analytics ;
       - analytics vers `/mewlytics.v1.Catalog/Stream*` ;
       - services vers mysql.
    
    Si l'étape ne tient pas en une session, s'arrêter après le point 1 et la règle de la gateway, et faire les règles internes dans une seconde session.
  - Vérification, par `scripts/check-security.sh` :
    - chaque flux prévu passe ;
    - un appel d'`analytics` à `UpsertTournament` est refusé ;
    - un appel depuis le pod `intruder` est refusé.

- [ ] 23. JWT à la gateway
  - Objectif :
    - `gen-jwt-keys.sh` génère `k8s/overlays/<env>/generated/request-auth.yaml`, une `RequestAuthentication` avec JWKS inline et vérification de l'`issuer`. On passe par un JWKS inline parce que, dans la configuration par défaut, istiod ne peut pas lire un JWKS servi en mTLS STRICT ;
    - si ce fichier manque (nouveau clone, cluster existant), `create-secrets.sh` le régénère à partir de la clé publique du Secret ;
    - une politique DENY avec `notRequestPrincipals: ["*"]` sur `/api/catalog/me/*`, toutes méthodes. Elle cible la gateway avec le même sélecteur que la `RequestAuthentication`.
  - Vérification, par `scripts/check-security.sh` :
    - 403 sans jeton, en POST et en GET ;
    - 401 avec un jeton signé par une autre clé ;
    - 201 avec un jeton valide.

- [ ] 24. HTTPS
  - Objectif :
    - certificat auto-signé généré par `scripts/gen-certs.sh`, idempotent et appelé par `create-secrets.sh` ;
    - Secret TLS et listener `https` ;
    - les HTTPRoute de l'application passent en `sectionName: https` ;
    - une HTTPRoute séparée sur le listener `http` porte le filtre `RequestRedirect` (`scheme: https`, `statusCode: 301`).
  - Vérification, par `scripts/check-security.sh` : `curl -k https://<ip>/api/catalog/tournaments` répond ; `curl -I http://<ip>/api/catalog/tournaments` renvoie 301.

- [ ] 25. PSA en `enforce`
  - Objectif : namespace en `enforce=restricted`.
  - Vérification :
    - le dry-run du label ne renvoie aucun avertissement ;
    - après le label, `kubectl rollout restart` de tous les Deployments et StatefulSets, puis tous les pods sont Ready ;
    - `scripts/ingest.sh initial` se termine en Completed ;
    - un pod privilégié est rejeté ;
    - `scripts/check-security.sh` passe en entier.

- [ ] 26. Scan de sécurité
  - Objectif :
    - Trivy sur les images et sur les fichiers de `k8s/` (`trivy config` sur les fichiers bruts : `generated/` n'est pas versionné, donc `kustomize build` n'est pas possible en CI) ;
    - exécution via l'image `aquasec/trivy:<version>` épinglée par digest, dans un job CI sans accès aux secrets, avec `--ignore-unfixed` ;
    - version vérifiée non compromise : ni le binaire 0.69.4 à 0.69.6, ni trivy-action 0.34.2 ou antérieure, ni setup-trivy 0.2.0 à 0.2.6 avant sa recréation.
  - Vérification : run vert ; les HIGH et CRITICAL corrigeables sont corrigés, les autres justifiés dans le README.
    
    Tag `v0.18.0` une fois les étapes 20 à 25 cochées.
  - Dépend de : 5.

### H. Front minimal et cloud (bonus)

- [ ] 27. Squelette du front
  - Objectif :
    - Vue 3 + Vite, thème sombre défini par des variables CSS : couleurs des 18 types, couleurs des tiers, échelle de win rate centrée sur 50 % ;
    - navigation ;
    - Dockerfile nginx-unprivileged, image ajoutée à la CI ;
    - ServiceAccount, Deployment conforme à `restricted`, route `/`.
  - Vérification :
    - `npm run build` passe ;
    - la page d'accueil, vide, est servie via la gateway ;
    - le dry-run du label `enforce` ne renvoie aucun avertissement.
  - Dépend de : 7.

- [ ] 28. Page Tournois
  - Objectif : liste et détail des tournois (classement, équipes, matchs).
  - Vérification : un tournoi réel s'affiche via la gateway ; capture.
  - Dépend de : 14, 27.

- [ ] 29. GKE : cluster et Istio
  - Objectif :
    - script de création : cluster zonal Standard, 2 nœuds `e2-medium`, `--workload-pool=<projet>.svc.id.goog` (une des options qui activent le CNI sur GKE selon la doc Istio CNI) ;
    - CRD Gateway API de la même version qu'en local, ou `--gateway-api=standard` ;
    - Istio avec `values.global.platform=gke` et le même seccomp de gateway qu'en local ;
    - alerte budgétaire sur le coût avant crédits.
    
    L'essai Google Cloud n'est activé qu'à cette étape.
  - Vérification :
    - istiod est Running ;
    - un pod de test a `istio-validation` ;
    - `kubectl describe nodes` ne montre aucun pod Pending.
  - Dépend de : 25, 26, 28.

- [ ] 30. GKE : application, captures, suppression
  - Objectif :
    - overlay `gke` avec des requests CPU réduites ;
    - déploiement depuis Docker Hub, secrets, `scripts/ingest.sh initial`, IP publique, TLS ;
    - captures ;
    - suppression du cluster.
  - Vérification :
    - l'application répond sur l'IP publique ;
    - `gcloud container clusters list` est vide à la fin ;
    - le coût net est nul, vérifié dans Billing le lendemain.

### I. Analyse (on peut commencer dès que l'étape 18 est cochée)

- [ ] 31. [cœur] Export et jeu de données
  - Objectif :
    - `python -m analytics.export --until <date>` lit `StreamEntries` et `StreamMatches` via `kubectl port-forward` et écrit `data/snapshot-<date>.jsonl`. Le port-forward contourne le mesh, ce que le rapport mentionnera ;
    - les filtres de `dataset.py` prennent un itérable d'enregistrements, issu du snapshot ou du flux gRPC ;
    - filtres :
      - matchs BO3 des tournois officiels M-C ;
      - tournois mixtes exclus en entier ;
      - équipes complètes de 6 ;
      - exclusions de l'étape 12 ;
    - découpage chronologique par tournoi : 70/15/15 ;
    - hash et comptages du snapshot ;
    - diagnostics :
      - part des participations de joueurs revus ;
      - part des matchs avec un joueur vu avec au moins deux équipes ;
      - part des matchs dans la plus grande composante connexe du graphe des rencontres (les θ de deux composantes différentes ne sont pas comparables) ;
    - définition d'une « nouvelle équipe » : jamais vue pour ce joueur en entraînement et validation, avec la distribution du nombre d'espèces changées.
    
    Si l'étape ne tient pas en une session : export et hash d'abord, filtres et diagnostics ensuite.
  - Vérification :
    - tests : aucun tournoi à cheval sur deux splits, ordre chronologique respecté ;
    - comptages et diagnostics affichés ;
    - deux exports sans nouvelle donnée donnent le même hash.
  - Dépend de : 18.

- [ ] 32. [cœur] Baselines
  - Objectif :
    - tier list brute ;
    - tier list rétrécie, avec un prior Beta ajusté sur l'entraînement ;
    - versions prédictives : une régression logistique à une variable, l'écart de win rate moyen entre les deux équipes :
      - les win rates sont calculés sur l'entraînement et la pente est ajustée sur la validation (sinon chaque match prédit sa propre issue) ;
      - les matchs miroirs sont exclus ;
      - une espèce absente de l'entraînement reçoit 0,5 dans la baseline naïve et la moyenne du prior Beta dans la baseline rétrécie.
  - Vérification : tests sur des valeurs calculées à la main ; log-loss de validation affichée.

- [ ] 33. [cœur] Bradley-Terry
  - Objectif :
    - modèle : P(i bat j) = σ((θ_i + Σ_{p∈T_i} β_p) − (θ_j + Σ_{p∈T_j} β_p)) ;
    - matrice creuse : ±1 sur les colonnes joueurs, (1_{T_i} − 1_{T_j})·s sur les colonnes espèces ;
    - `LogisticRegression(fit_intercept=False)`, sans passer `penalty` ni `l1_ratio=None` (dépréciés depuis scikit-learn 1.8), avec un `max_iter` assez grand ;
    - sens de chaque match tiré au hasard ;
    - β = s·w, ce qui équivaut à des priors N(0, C) sur θ et N(0, C·s²) sur β ;
    - variantes : joueurs seuls et Pokémon seuls ;
    - au test, θ = 0 et β = 0 pour les joueurs et les espèces inconnus.
  - Vérification, tests à la tolérance du solveur, avec des équipes de 6 :
    - shapes ;
    - p(x) + p(−x) = 1 ;
    - une espèce présente dans les deux équipes s'annule ;
    - somme des β nulle, somme des θ nulle par composante connexe ;
    - même résultat quel que soit le seed d'orientation ;
    - biais de sélection synthétique, à seed fixé : au moins 30 % des joueurs changent d'équipe ; une espèce A a β_A < β_B mais est surtout choisie par des joueurs à θ élevé. On vérifie WR_brut(A) > WR_brut(B) et β̂_A < β̂_B ;
    - contrôle négatif : sans aucun changement d'équipe, l'ordre n'est pas retrouvé de façon fiable.
  - Dépend de : 31.

- [ ] 34. [cœur] Sélection et test
  - Objectif :
    - sur la validation, une grille choisit (C, s) pour le modèle complet et un C propre à chaque variante ;
    - réajustement des modèles Bradley-Terry sur entraînement + validation ;
    - baselines : win rates et prior recalculés sur entraînement + validation, pente conservée telle qu'apprise sur la validation ;
    - une seule évaluation sur le test, en log-loss et Brier, des six modèles : constante 0,5, naïf, rétréci, joueurs seuls, Pokémon seuls, complet ;
    - `services/analytics/src/analytics/evaluation.json`, versionné, contient les métriques agrégées, (C, s), le seuil d'usage, les seuils de tiers et le seuil k de « peu d'information », tous fixés à cette étape. Le service le lit avec `importlib.resources`.
  - Vérification : `uv run --package analytics python -m analytics.evaluate --until <date de gel>` produit le tableau et `evaluation.json` ; deux exécutions donnent les mêmes chiffres.
  - Dépend de : 32, 33.

- [ ] 35. [cœur] Intervalles et diagnostics
  - Objectif :
    - écarts entre modèles avec un intervalle à 95 %, par bootstrap apparié sur les tournois de test : un seul rééchantillonnage pour tous les modèles, ratio des sommes. Cet intervalle ne mesure que la variabilité du test et ignore les joueurs communs à plusieurs tournois, ce qui sera dit dans le rapport ;
    - sous-ensembles du test :
      - deux joueurs connus ;
      - un seul joueur connu ;
      - aucun joueur connu ;
      - « joueur connu, nouvelle équipe » : c'est là que la séparation entre θ et β est le plus sollicitée. Un gain sur ce sous-ensemble montre que la décomposition se généralise, sans prouver que β est débarrassé du biais de sélection ;
    - figure de la corrélation de Spearman des β sur la grille de s ;
    - log JSON dans `runs/` : config, seed, hash du commit, hash du snapshot, métriques, durée ;
    - figures en PDF.
  - Vérification : le JSON et les figures sont produits.
  - Critère d'échec : si le modèle complet ne bat ni « joueurs seuls » ni la baseline rétrécie au-delà de l'intervalle, le rapport le dit tel quel.

- [ ] 36. [cœur] Tier lists : calcul
  - Objectif : des fonctions pures qui :
    - réajustent le modèle sur toutes les données, avec les paramètres de `evaluation.json` ;
    - font un bootstrap par tournoi (B configurable) sur un ensemble fixe d'espèces, celles au-dessus du seuil d'usage. Une espèce absente d'une réplique est comptée comme manquante, pas à β = 0 ;
    - centrent sur la moyenne pondérée par l'usage, avec des poids calculés une fois sur toutes les données. C'est un choix de référence, sans effet sur les prédictions ;
    - fixent les tiers par les seuils sur σ(β) − 0,5, qui mesure un écart à l'espèce moyenne et non un win rate ;
    - marquent « incertain » si l'intervalle de variabilité à 90 % chevauche une frontière de tier ;
    - marquent « peu d'information » si moins de k joueurs distincts ont été vus avec et sans l'espèce.
  - Vérification : tests (tiers déterministes à seed fixé, centrage sans effet sur les prédictions, comptage « peu d'information » sur un cas fait à la main).
  - Dépend de : 34.

- [ ] 37. [cœur] Tier lists : API
  - Objectif :
    - calcul intégré au refresh d'`analytics` : B = 200 dans le cluster, B = 50 en local, un seul refresh à la fois, et une demande reçue pendant un calcul relance un calcul à la fin ;
    - résultats dans son schéma ;
    - `GET /api/stats/tierlist?kind=raw|shrunk|bt` ;
    - `GET /api/stats/evaluation`, qui sert `evaluation.json` ;
    - image reconstruite avec `evaluation.json`.
  - Vérification :
    - `evaluation.json` est présent dans le conteneur (`ls`) ;
    - l'endpoint répond via la gateway ;
    - le refresh tient sous la limite mémoire du pod ; sa durée et `kubectl top pods -A` sont notés dans le README.

### J. Front

- [ ] 38. Pages Pokémon et Méta
  - Objectif :
    - tableau triable des Pokémon ;
    - fiche : types, statistiques, objets, talents, attaques, partenaires, matchups ;
    - accueil avec les chiffres clés.
  - Vérification : `npm run build` ; via la gateway, la fiche d'une espèce affiche ses types et ses statistiques ; capture.
  - Dépend de : 16, 19, 28.

- [ ] 39. Page Tier list
  - Objectif : les trois tier lists côte à côte, avec les intervalles et les changements de rang, et un encart méthode qui reprend le tableau de `/api/stats/evaluation`.
  - Vérification : les trois listes s'affichent avec les mentions « incertain » et « peu d'information » ; capture.
  - Dépend de : 27, 37.

- [ ] 40. Compte et Mes tournois
  - Objectif : inscription, connexion, jeton gardé en mémoire, formulaire de saisie, filtre `source` sur les statistiques.
  - Vérification : via la gateway, inscription, connexion puis saisie, et le tournoi apparaît dans Mes tournois ; un rechargement de la page vide le jeton ; captures.
  - Dépend de : 10, 16, 27.

- [ ] 41. Créateur d'équipe
  - Objectif :
    - choix de 6 espèces distinctes parmi celles vues en M-C ;
    - couverture de types ;
    - score du modèle, présenté comme une estimation relative à une équipe moyenne.
  - Vérification :
    - on ne peut pas ajouter une 7e espèce ;
    - un doublon est refusé ;
    - le score affiché égale la somme des β renvoyés par `/api/stats/tierlist?kind=bt` ;
    - capture d'une équipe complète avec sa couverture de types et son score.
  - Dépend de : 19, 27, 37.

### K. Rendu

- [ ] 42. README final et v1.0
  - Objectif :
    - architecture, prérequis, versions, limites ;
    - commandes exactes : déploiement depuis Docker Hub, `scripts/ingest.sh initial`, `scripts/check-security.sh`, export et évaluation ;
    - merge dans `main`, tag `v1.0.0`.
  - Vérification : depuis un clone neuf dans un dossier temporaire, les commandes du README déploient l'application, et `scripts/check-security.sh` passe.
  - Dépend de : 25, 26, 38 à 41 (et 30 si le bonus cloud est fait).

- [ ] 43. Rapport
  - Objectif :
    - tableau « palier, preuve (commande, capture) » ;
    - schéma d'architecture ;
    - une phrase sur le choix de la Gateway API plutôt que `VirtualService` ;
    - captures Kiali (graphe, mTLS) et Docker Hub ;
    - sécurité, en précisant que `kubectl port-forward` contourne le mesh et n'est donc pas accordé au rôle `viewer` ;
    - résultats de l'analyse et leurs limites :
      - non-stationnarité ;
      - effets additifs, sans interactions ;
      - β mesure la présence dans l'équipe, pas le fait que le Pokémon soit joué ;
      - identifiabilité : les changements d'équipe échangent souvent plusieurs espèces à la fois, ce qui n'identifie que des différences de β ;
      - θ = 0 pour les nouveaux joueurs, probablement plus faibles que la moyenne ;
      - l'intervalle du bootstrap ne mesure que la variabilité du test ;
      - la pente des baselines est apprise sur des win rates d'entraînement, ce qui les désavantage légèrement au test : un petit écart en faveur de Bradley-Terry ne doit pas être surinterprété.
    
    Envoi par mail.
  - Vérification : chaque palier du tableau a une preuve (commande ou capture).

## Si le temps manque

À couper dans cet ordre :
1. Étape 41 : le créateur d'équipe.
2. Étape 35 : la figure de Spearman et les sous-ensembles. On garde le tableau de test et un intervalle apparié.
3. Étape 36 : le bootstrap et la mention « incertain ». On garde les estimations ponctuelles, les seuils et « peu d'information ».
4. Étape 15 : les fréquences d'attaques et de tera, et les matchups. On garde l'usage, le win rate et les paires.
5. Étape 38 : la fiche détaillée. On garde le tableau et les types.
6. Étape 40 : le filtre `source`. On garde l'inscription, la connexion et la saisie.
7. En dernier recours, les étapes 29 et 30 (GKE).

On ne coupe jamais l'étape 11 (gRPC), les étapes 20 à 26 (sécurité) ni les captures Kiali.

## Risques et détection

| Risque | Détection | Parade |
|---|---|---|
| 8 Go insuffisants | étapes 2, 17, 37 | mode ambient, puis démo sur GKE |
| Retard sur l'infrastructure | palier 18 non atteint début décembre | appliquer la liste « Si le temps manque » |
| Gateway bloquée par le refus total | étape 22 | règle ALLOW avec `rules: [{}]` sur la gateway, posée en même temps |
| Pods rejetés par la PSA `restricted` (sidecars, gateway, Jobs) | étapes 6, 7, 9, 17, 25, 27 | seccomp au niveau du pod et de la gateway ; dry-run serveur du label `enforce` à chaque nouveau workload ; Jobs relancés après l'étape 25 |
| JWKS illisible par istiod en mTLS STRICT | étape 23 | JWKS inline généré depuis le Secret |
| MySQL mal géré par la détection de protocole d'Istio | étape 17 | `tcp-mysql`, `PeerAuthentication` STRICT ciblée |
| Accès concurrents à SQLite en mémoire | étapes 3, 11, 15 | verrou global en mode SQLite |
| Jobs immuables | étape 14 | Jobs hors kustomization, supprimés puis recréés par `scripts/ingest.sh` |
| β fixés par le prior (joueurs qui gardent leur équipe) | diagnostics des étapes 31 et 35, contrôle négatif de l'étape 33 | le rapporter ; sensibilité à s ; mention « peu d'information » |
| Changement de format pendant le projet | nouveaux tournois sous un autre code | modèle figé sur M-C, ingestion paramétrée par le format |
| API Limitless modifiée ou débit limité | erreurs à l'ingestion, hash du snapshot modifié | une requête par seconde, retries, fenêtre glissante |
| Chaîne d'approvisionnement de la CI | revue du workflow | actions épinglées par SHA, image Trivy épinglée par digest, permissions minimales, Trivy sans secrets |
| Limites de pull de Docker Hub | `ErrImagePull` | images de développement construites dans le cluster |
| Crédit d'essai Google Cloud limité à 90 jours | | activer l'essai seulement à l'étape 29 |

## Références

- Bradley-Terry et modèles voisins :
  - Bradley et Terry (1952) ;
  - Agresti, *Categorical Data Analysis* (Bradley-Terry vu comme une régression logistique) ;
  - Huang, Weng et Lin, *Generalized Bradley-Terry Models and Multi-class Probability Estimates* (JMLR 2006), pour les comparaisons d'équipes ;
  - Herbrich, Minka et Graepel, *TrueSkill* (NIPS 2006) ;
  - Sill (2010), *Improved NBA Adjusted +/- Using Regularization and Out-of-Sample Testing* (même structure ±1 avec régularisation ridge).
- Rétrécissement : Efron et Morris (1975).
- Bootstrap : Efron et Tibshirani (1993).
- Documentation des API :
  - Limitless : https://docs.limitlesstcg.com/developer/tournaments
  - PokéAPI : https://pokeapi.co/docs/v2
