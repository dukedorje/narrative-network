# Narrative Network — deployment recipes
# Usage: just <recipe>

set dotenv-load := false

server := "bnn1"
namespace := "narrative-network"
domain := "futograph.online"

# ── Secrets ───────────────────────────────────────────────────────────

# Push .env secrets to K8s (dedupes, strips comments)
secrets:
    @grep -v '^#' .env | grep -v '^\s*$' | \
      awk -F= '!seen[$1]++ || 1 { last[$1]=$0 } END { for (k in last) print last[k] }' > /tmp/clean.env
    kubectl -n {{namespace}} create secret generic narrative-network-secrets \
      --from-env-file=/tmp/clean.env \
      --dry-run=client -o yaml | kubectl apply -f -
    @rm /tmp/clean.env
    @echo "✓ Secrets applied. Run 'just restart frontend' to pick up changes."

# Show which secret keys are stored
secrets-list:
    @kubectl -n {{namespace}} get secret narrative-network-secrets -o json | \
      python3 -c "import json,sys; print('\n'.join(sorted(json.load(sys.stdin)['data'].keys())))"

# ── Frontend Deploy ───────────────────────────────────────────────────

# Full frontend deploy: rsync → build → import → rollout
deploy-frontend: sync build-frontend import-frontend restart-frontend

# Rsync code to server
sync:
    rsync -avz --delete \
      --exclude='node_modules' --exclude='.git' --exclude='docs/corpora/.cache' \
      --exclude='.env' --exclude='__pycache__' --exclude='.playwright-mcp' \
      --exclude='.omc' --exclude='test-results' --exclude='.venv' \
      . {{server}}:~/narrative-network/

# Build frontend image on server
build-frontend:
    ssh {{server}} "cd ~/narrative-network && docker build --no-cache -f Dockerfile.frontend -t narrative-network-frontend:latest ."

# Import image into k3s containerd (force replace)
import-frontend:
    ssh {{server}} "k3s crictl rmi docker.io/library/narrative-network-frontend:latest 2>/dev/null || true; \
        docker save narrative-network-frontend:latest | k3s ctr images import -"

# Restart frontend deployment
restart-frontend:
    kubectl -n {{namespace}} rollout restart deployment/frontend
    kubectl -n {{namespace}} rollout status deployment/frontend --timeout=90s

# ── Python Service Deploy ─────────────────────────────────────────────

# Deploy a Python service: just deploy-python gateway
deploy-python service: sync (build-python service) (import-python service) (restart-python service)

# Build a Python service image (gateway, validator, miner)
build-python service:
    ssh {{server}} "cd ~/narrative-network && docker build --no-cache -f Dockerfile.python --target {{service}} -t narrative-network-{{service}}:latest ."

# Import a Python service image (force replace)
import-python service:
    ssh {{server}} "k3s crictl rmi docker.io/library/narrative-network-{{service}}:latest 2>/dev/null || true; \
        docker save narrative-network-{{service}}:latest | k3s ctr images import -"

# Restart a Python service
restart-python service:
    kubectl -n {{namespace}} rollout restart deployment/{{service}}
    kubectl -n {{namespace}} rollout status deployment/{{service}} --timeout=90s

# ── Full Deploy ──────────────────────────────────────────────────────

# Deploy everything to prod: sync, parallel builds, import, apply, restart
deploy-all: sync _build-all _import-all apply _restart-all
    @echo "✓ All services deployed."

# Build all images on server (sequential — parallel docker builds contend on build context)
_build-all:
    #!/usr/bin/env bash
    set -e
    echo "Building all images on {{server}}..."
    ssh {{server}} "cd ~/narrative-network && \
        docker build --no-cache -f Dockerfile.python --target gateway -t narrative-network-gateway:latest . && \
        docker build --no-cache -f Dockerfile.python --target validator -t narrative-network-validator:latest . && \
        docker build --no-cache -f Dockerfile.python --target miner -t narrative-network-miner:latest . && \
        docker build --no-cache -f Dockerfile.frontend -t narrative-network-frontend:latest ."
    echo "All images built."

# Import all images into k3s (force replace stale images)
_import-all:
    #!/usr/bin/env bash
    set -e
    echo "Importing images into k3s..."
    for svc in gateway validator miner frontend; do
        ssh {{server}} "k3s crictl rmi docker.io/library/narrative-network-${svc}:latest 2>/dev/null || true; \
            docker save narrative-network-${svc}:latest | k3s ctr images import -"
    done
    echo "All images imported."

# Restart all deployments
_restart-all:
    #!/usr/bin/env bash
    set -e
    for svc in frontend gateway miner; do
        kubectl -n {{namespace}} rollout restart deployment/${svc}
    done
    kubectl -n {{namespace}} rollout restart statefulset/validator
    echo "Waiting for rollouts..."
    for svc in frontend gateway miner; do
        kubectl -n {{namespace}} rollout status deployment/${svc} --timeout=120s
    done
    kubectl -n {{namespace}} rollout status statefulset/validator --timeout=120s
    echo "All services restarted."

# ── Local Dev ────────────────────────────────────────────────────────

# Run the Python gateway locally (no Bittensor, in-process miners)
gateway:
    AXON_NETWORK=local uv run uvicorn orchestrator.gateway:app --host 0.0.0.0 --port 8080 --reload

# ── Docker Compose (local, no bittensor) ──────────────────────────────
# Quick local dev: gateway + local-validator + frontend + redis
# No Kind cluster, no bittensor dependency
compose:
    docker compose -f docker-compose.local.yml up --build

compose-down:
    docker compose -f docker-compose.local.yml down -v

compose-logs service="gateway":
    docker compose -f docker-compose.local.yml logs -f {{service}}

# ── Local K8s (kind) ────────────────────────────────────────────────

kind_cluster := "narrative-network"

# Full local K8s stack: create cluster, build images, load, deploy
# Access at http://localhost:3000 (frontend) and http://localhost:8080 (gateway API)
local: _local-cluster _local-build _local-load _local-secrets _local-deploy
    @echo ""
    @echo "Local K8s stack is up!"
    @echo "  Frontend: http://localhost:3000"
    @echo "  Gateway:  http://localhost:8080"
    @echo "  Status:   just local-status"
    @echo "  Logs:     just local-logs <service>"
    @echo "  Teardown: just local-down"

# Rebuild and redeploy (skip cluster creation)
local-redeploy: _local-build _local-load _local-deploy

# Create kind cluster (idempotent)
_local-cluster:
    #!/usr/bin/env bash
    if kind get clusters 2>/dev/null | grep -q "^{{kind_cluster}}$"; then
        echo "Kind cluster '{{kind_cluster}}' already exists"
    else
        kind create cluster --name {{kind_cluster}} --config k8s/local/kind-config.yaml
    fi
    kubectl config use-context kind-{{kind_cluster}}

# Build all local images
_local-build:
    docker build -f Dockerfile.python --target gateway-local -t narrative-network-gateway-local:latest .
    docker build -f Dockerfile.python --target local-validator -t narrative-network-local-validator:latest .
    docker build -f Dockerfile.frontend -t narrative-network-frontend:latest .

# Load images into kind
_local-load:
    kind load docker-image --name {{kind_cluster}} \
        narrative-network-gateway-local:latest \
        narrative-network-local-validator:latest \
        narrative-network-frontend:latest

# Create secrets from .env (idempotent)
_local-secrets:
    #!/usr/bin/env bash
    kubectl config use-context kind-{{kind_cluster}}
    kubectl apply -f k8s/base/namespace.yaml
    if [ -f .env ]; then
        grep -v '^#' .env | grep -v '^\s*$' | \
            awk -F= '!seen[$1]++ || 1 { last[$1]=$0 } END { for (k in last) print last[k] }' > /tmp/clean.env
        kubectl -n {{namespace}} create secret generic narrative-network-secrets \
            --from-env-file=/tmp/clean.env \
            --dry-run=client -o yaml | kubectl apply -f -
        rm /tmp/clean.env
        echo "Secrets applied from .env"
    else
        echo "No .env file found — creating empty secret"
        kubectl -n {{namespace}} create secret generic narrative-network-secrets \
            --dry-run=client -o yaml | kubectl apply -f -
    fi

# Apply local kustomize overlay
_local-deploy:
    kubectl config use-context kind-{{kind_cluster}}
    kubectl apply -k k8s/local/
    @echo "Waiting for rollouts..."
    kubectl -n {{namespace}} rollout status deployment/frontend --timeout=120s
    kubectl -n {{namespace}} rollout status deployment/gateway --timeout=300s
    kubectl -n {{namespace}} rollout status deployment/local-validator --timeout=120s

# Show local cluster status
local-status:
    kubectl config use-context kind-{{kind_cluster}}
    kubectl -n {{namespace}} get pods,svc

# Show local logs
local-logs service="frontend":
    kubectl config use-context kind-{{kind_cluster}}
    kubectl -n {{namespace}} logs deployment/{{service}} -f

# Delete local kind cluster
local-down:
    kind delete cluster --name {{kind_cluster}}

# ── K8s Manifests ─────────────────────────────────────────────────────

# Apply all K8s manifests via kustomize
apply:
    kubectl apply -k k8s/

# ── Status & Debug ────────────────────────────────────────────────────

# Show all resources in namespace
status:
    kubectl -n {{namespace}} get pods,svc,ingress,certificate

# Show frontend logs
logs service="frontend":
    kubectl -n {{namespace}} logs deployment/{{service}} --tail=50

# Follow frontend logs
logs-follow service="frontend":
    kubectl -n {{namespace}} logs deployment/{{service}} -f

# Shell into a pod
shell service="frontend":
    kubectl -n {{namespace}} exec -it deployment/{{service}} -- sh

# Port-forward a service locally
forward service="frontend" port="3000":
    kubectl -n {{namespace}} port-forward svc/{{service}} {{port}}:80

# Check TLS cert status
cert:
    kubectl -n {{namespace}} get certificate,order,challenge

# Check site is up
ping:
    @curl -s -o /dev/null -w "%{http_code}" https://{{domain}}/ && echo " https://{{domain}}"

# List images on server
images:
    @ssh {{server}} "k3s crictl images | grep narrative"

# ── Shortcuts ─────────────────────────────────────────────────────────

# Restart any deployment
restart service:
    kubectl -n {{namespace}} rollout restart deployment/{{service}}
    kubectl -n {{namespace}} rollout status deployment/{{service}} --timeout=90s
