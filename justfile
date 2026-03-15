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
      --exclude='.omc' --exclude='test-results' \
      . {{server}}:~/narrative-network/

# Build frontend image on server
build-frontend:
    ssh {{server}} "cd ~/narrative-network && docker build --no-cache -f Dockerfile.frontend -t narrative-network-frontend:latest ."

# Import image into k3s containerd
import-frontend:
    ssh {{server}} "docker save narrative-network-frontend:latest | k3s ctr images import -"

# Restart frontend deployment
restart-frontend:
    kubectl -n {{namespace}} rollout restart deployment/frontend
    kubectl -n {{namespace}} rollout status deployment/frontend --timeout=90s

# ── Python Service Deploy ─────────────────────────────────────────────

# Deploy a Python service: just deploy-python gateway
deploy-python service: sync (build-python service) (import-python service) (restart-python service)

# Build a Python service image (gateway, validator, domain-miner, narrative-miner)
build-python service:
    ssh {{server}} "cd ~/narrative-network && docker build --no-cache -f Dockerfile.python --target {{service}} -t narrative-network-{{service}}:latest ."

# Import a Python service image
import-python service:
    ssh {{server}} "docker save narrative-network-{{service}}:latest | k3s ctr images import -"

# Restart a Python service
restart-python service:
    kubectl -n {{namespace}} rollout restart deployment/{{service}}
    kubectl -n {{namespace}} rollout status deployment/{{service}} --timeout=90s

# ── Local Dev ────────────────────────────────────────────────────────

# Run the Python gateway locally (no Bittensor, in-process miners)
gateway:
    AXON_NETWORK=local uv run uvicorn orchestrator.gateway:app --host 0.0.0.0 --port 8080 --reload

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
