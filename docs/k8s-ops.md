# Kubernetes Operations Guide

## Cluster

- **Server:** Hetzner VPS `bnn1` (8 CPU, 16GB RAM, Ubuntu 24.04)
- **IP:** 5.78.184.254
- **Runtime:** k3s v1.34.5 (single node, control-plane)
- **Namespace:** `narrative-network`

## Local kubectl Setup

The kubeconfig was created by merging the k3s config from the server:

```bash
# One-time setup (already done)
ssh bnn1 "cat /etc/rancher/k3s/k3s.yaml" | \
  sed 's|https://127.0.0.1:6443|https://5.78.184.254:6443|g' | \
  sed 's|name: default|name: bnn1|g' | \
  sed 's|cluster: default|cluster: bnn1|g' | \
  sed 's|user: default|user: bnn1|g' > /tmp/bnn1-kubeconfig.yaml

KUBECONFIG=~/.kube/config:/tmp/bnn1-kubeconfig.yaml kubectl config view --flatten > /tmp/merged.yaml
cp /tmp/merged.yaml ~/.kube/config

# Switch to bnn1 context
kubectl config use-context bnn1
```

Verify:
```bash
kubectl get nodes
# NAME   STATUS   ROLES           VERSION
# bnn1   Ready    control-plane   v1.34.5+k3s1
```

## Ingress Stack

**Traefik** (ingress controller) and **cert-manager** (TLS) are installed via Helm on the server.

```bash
# Helm on bnn1 requires explicit KUBECONFIG
ssh bnn1 "KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm list -A"
```

- **Traefik:** `kube-system` namespace, LoadBalancer on ports 80/443
- **cert-manager:** `cert-manager` namespace, ClusterIssuer `letsencrypt-prod`
- **TLS:** Auto-provisioned via Let's Encrypt ACME HTTP-01 challenges
- **Domain:** `futograph.online` + `www.futograph.online` (GoDaddy A record → 5.78.184.254)

## Deploying the Frontend

### Full deploy (code changed)

```bash
# 1. Rsync code to server
rsync -avz --delete \
  --exclude='node_modules' --exclude='.git' --exclude='docs/corpora/.cache' \
  --exclude='.env' --exclude='__pycache__' --exclude='.playwright-mcp' \
  . bnn1:~/narrative-network/

# 2. Build image on server
ssh bnn1 "cd ~/narrative-network && docker build --no-cache -f Dockerfile.frontend -t narrative-network-frontend:latest ."

# 3. Import into k3s containerd
ssh bnn1 "docker save narrative-network-frontend:latest | k3s ctr images import -"

# 4. Rollout
kubectl -n narrative-network rollout restart deployment/frontend
kubectl -n narrative-network rollout status deployment/frontend --timeout=90s
```

### Config-only change (no rebuild needed)

```bash
# Update env vars
kubectl -n narrative-network set env deployment/frontend KEY=value

# Apply manifest changes
kubectl apply -k k8s/
```

### Verify deployment

```bash
# Pods healthy?
kubectl -n narrative-network get pods -l app=frontend

# Logs
kubectl -n narrative-network logs deployment/frontend --tail=30

# TLS cert status
kubectl -n narrative-network get certificate

# Hit the site
curl -s -o /dev/null -w "%{http_code}" https://futograph.online/
```

## Deploying Python Services

Same pattern, using `Dockerfile.python` which has 4 build targets:

```bash
# Build (pick one target)
ssh bnn1 "cd ~/narrative-network && docker build --no-cache -f Dockerfile.python --target gateway -t narrative-network-gateway:latest ."
ssh bnn1 "cd ~/narrative-network && docker build --no-cache -f Dockerfile.python --target validator -t narrative-network-validator:latest ."
ssh bnn1 "cd ~/narrative-network && docker build --no-cache -f Dockerfile.python --target domain-miner -t narrative-network-domain-miner:latest ."
ssh bnn1 "cd ~/narrative-network && docker build --no-cache -f Dockerfile.python --target narrative-miner -t narrative-network-narrative-miner:latest ."

# Import + rollout
ssh bnn1 "docker save narrative-network-gateway:latest | k3s ctr images import -"
kubectl -n narrative-network rollout restart deployment/gateway
```

## Applying K8s Manifests

Always use kustomize:
```bash
kubectl apply -k k8s/
```

Direct `kubectl apply -f k8s/frontend.yaml` will fail because kustomize adds `commonLabels` to selectors. The deployed resources have these labels baked into their immutable selectors.

## Useful Commands

```bash
# All resources in namespace
kubectl -n narrative-network get all

# Describe a failing pod
kubectl -n narrative-network describe pod <pod-name>

# Exec into a pod
kubectl -n narrative-network exec -it deployment/frontend -- sh

# Port-forward for local debugging
kubectl -n narrative-network port-forward svc/frontend 3000:80

# Check ingress routing
kubectl -n narrative-network get ingress

# Check cert-manager
kubectl -n narrative-network get certificate,order,challenge

# Helm releases (must run ON server or with KUBECONFIG set)
ssh bnn1 "KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm list -A"

# k3s containerd images
ssh bnn1 "k3s crictl images"
```

## Architecture

```
Internet
  │
  ├─ futograph.online (GoDaddy A → 5.78.184.254)
  │
  ▼
[Traefik LB :80/:443]  (kube-system)
  │
  ├─ TLS termination (cert from cert-manager/Let's Encrypt)
  │
  ▼
[Ingress: narrative-network-ingress]
  │
  ├─ futograph.online     → svc/frontend :80 → pods :3000 (SvelteKit)
  └─ www.futograph.online → svc/frontend :80 → pods :3000 (SvelteKit)

[Other services in namespace]
  ├─ svc/gateway     → pods :8080 (FastAPI orchestrator)
  ├─ svc/redis       → pods :6379
  ├─ svc/validator   → pods :8091
  └─ svc/ipfs        → pods :5001
```

## Gotchas

- **Helm on bnn1** needs `KUBECONFIG=/etc/rancher/k3s/k3s.yaml` — k3s doesn't use the default kubeconfig path
- **kustomize commonLabels** get baked into deployment selectors — always `kubectl apply -k k8s/`, never apply individual files directly
- **Docker → k3s images** — k3s uses containerd, not Docker. After `docker build`, must `docker save | k3s ctr images import -` for k3s to see the image
- **Health checks** — Frontend probes hit `/healthz` (not `/`) to avoid slow SSR page loads timing out the probe
- **ORIGIN env var** — SvelteKit needs `ORIGIN=https://futograph.online` set on the deployment to accept requests from that domain
