#!/usr/bin/env bash
# Create the cluster, install Argo CD, hand it this repo. Everything after that is GitOps.
set -euo pipefail
cd "$(dirname "$0")/.."

curl -sf localhost:11434/api/version >/dev/null || { echo "Ollama isn't running on the Mac (open the Ollama app)"; exit 1; }
for m in qwen3.5:9b qwen2.5:7b qwen2.5:1.5b llama-guard3:1b; do
  ollama list | grep -q "^$m " || ollama pull "$m"
done

k3d cluster list talk >/dev/null 2>&1 || k3d cluster create --config k3d.yaml
kubectl config use-context k3d-talk >/dev/null

helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm upgrade --install argocd argo/argo-cd --version 10.9.6 -n argocd --create-namespace \
  -f bootstrap/argocd-values.yaml --wait
kubectl apply -f bootstrap/root.yaml

echo "Argo CD is deploying the rest (2-3 min). Watch: kubectl -n argocd get applications -w"
echo "Then open http://argocd.localhost  http://grafana.localhost  and run ./scripts/demo.sh"
