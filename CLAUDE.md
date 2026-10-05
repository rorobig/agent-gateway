# CLAUDE.md

Demo repo for a conference talk on agentgateway. README.md has the demos, URLs and layout; read it first.

## How changes reach the cluster

- GitOps only. Argo CD (k3d cluster `talk`) syncs `main` of github.com/rorobig/agent-gateway with
  self-heal on, so a `kubectl apply` or `kubectl edit` is reverted within seconds. Test a live change only
  for a few seconds, or not at all: commit, push, then `./scripts/sync.sh`.
- The user pushes; ask before pushing.
- Before committing manifests, validate them: `kubectl apply --dry-run=server -n <ns> -f <file>`.
- Check sync after a push: `kubectl get applications -n argocd` should be all `Synced  Healthy`.

## Conventions

- Write the defaults the API server would add into Gateway API resources (`parentRefs` group/kind,
  `backendRefs` group/kind/weight, a `PathPrefix /` match). Leave them out and Argo shows OutOfSync forever.
- One AgentgatewayPolicy per section (`traffic`, `backend`, ...) per target; a second one silently wins.
- New component = one file in `apps/` (an Argo Application; `sync-wave` sets boot order) + its manifests.
  Helm charts are pinned to exact versions and configured with inline `valuesObject`.
- `platform/dashboards/agentgateway-talk.yaml` is generated: edit `scripts/make-dashboard.py` and run it.
- `scripts/demo.sh` is what runs on stage. Every demo prints the exact request it sends; keep that.
- Demo keys and passwords are plain text on purpose (laptop-only cluster, no logins).
- Comments explain *why* for an audience reading the YAML on a projector. Keep them short.

## Environment facts

- Ollama runs natively on the Mac (Apple GPU), not in Docker. Pods reach it at `host.k3d.internal:11434`.
- Pods can't use `*.localhost`; the company endpoint is `api.ai.svc.cluster.local` from inside the cluster.
- Models: `qwen3.5:9b` (pro tier, thinking off via `reasoning_effort`), `qwen2.5:7b` (smart, agent tier),
  `qwen2.5:1.5b` (fast, free tier), `llama-guard3:1b` (guard webhook).
  The 7B model needs explicit examples in agent prompts to make correct tool calls (see README gotchas).
- Useful checks: gateway access log `./scripts/demo.sh logs` (has `user=` and token counts per request);
  agent logs `kubectl -n kagent logs deploy/<agent>`.
