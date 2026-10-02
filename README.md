# agent-gateway

Demo infrastructure for a talk on **agentgateway** (and later, how it compares with LiteLLM).
Everything runs on one MacBook: a local Kubernetes cluster (k3d), deployed by Argo CD from this repo, with
AI models served by Ollama natively on the Mac (Apple GPU).

```
 curl / chat UI ──▶ http://*.localhost ──▶ agentgateway (in k3d) ──▶ Ollama on the Mac (host.k3d.internal:11434)
                                              │  API keys · token budgets · prompt rewrites · guards · model routing
                                              ▼
                                        Prometheus ──▶ Grafana (tokens per user / model, blocks, 429s, latency)
```

## Start

Needs: Docker (12 GB+ memory), k3d, helm, kubectl, jq, and the [Ollama app](https://ollama.com) running.

```bash
./scripts/up.sh          # pulls models, creates the cluster, installs Argo CD, hands it this repo (~3 min)
./scripts/demo.sh        # lists the demos
./scripts/down.sh        # deletes the cluster (models stay)
```

| URL | What |
|---|---|
| http://grafana.localhost | the talk dashboard (opens by default, no login) |
| http://argocd.localhost | Argo CD (no login, laptop only) |
| http://prometheus.localhost | raw metrics |
| http://llm.localhost | demo 1: an AI behind the gateway |
| http://pirate.localhost, http://brief.localhost | demo 2: prompt rewrites |
| http://api.localhost | demo 3: the company endpoint (API key needed) |

All of them are OpenAI-compatible: `POST /v1/chat/completions`. Any OpenAI SDK or chat UI works with
`base_url=http://api.localhost/v1` and `api_key=sk-alice`.

## The demos

### 1. An AI behind a gateway (`demos/01-chat`)
```bash
./scripts/demo.sh chat
./scripts/demo.sh aliases        # "fast" -> qwen2.5:1.5b, "smart" -> qwen2.5:7b
```
The client asks for `smart`; the gateway maps it to a real model (`modelAliases`). The platform team can swap
the model behind `smart` without any client changing. Token counts come from the gateway reading the response.

### 2. The gateway rewrites prompts (`demos/02-prompt`)
```bash
./scripts/demo.sh pirate         # a hidden system prompt, prepended
./scripts/demo.sh brief          # the same question on llm.localhost vs brief.localhost
```
`pirate`: the caller sent one message; the model received two. `brief`: the gateway *appends* "two sentences
max" and *overrides* `max_tokens` and `temperature`. In testing, "How does DNS work?" cost **786 output tokens**
plain and **23** through `brief`. That is cost control without touching a single client.

### 3. The company endpoint (`demos/03-company`, `demos/guard`)
Three API keys (`keys.yaml`): `sk-alice` and `sk-bob` (tier `pro`), `sk-intern` (tier `free`).

```bash
./scripts/demo.sh nokey          # 401, before anything else happens
./scripts/demo.sh as alice       # asks for "gpt-5", gets qwen2.5:7b    (pro)
./scripts/demo.sh as intern      # asks for "gpt-5", gets qwen2.5:1.5b  (free)
./scripts/demo.sh burn intern    # 400 tokens/min budget -> 429 after ~2 answers
./scripts/demo.sh card           # 403: credit card number (built-in regex)
./scripts/demo.sh inject         # 403: "ignore all previous instructions" (custom regex)
./scripts/demo.sh unsafe         # 403: Llama Guard says "violent crimes" (webhook)
./scripts/demo.sh mask           # 200, but emails/phones in the ANSWER are <MASKED>
./scripts/demo.sh load           # background traffic from all three users, for the dashboard
```

What's going on, in request order:

| Step | Where | How |
|---|---|---|
| Who are you? | `route.yaml`, `apiKeyAuthentication` | key -> `apiKey.user_id`, `apiKey.tier` (CEL), available to every later step |
| Budget left? | `route.yaml`, `rateLimit.conditional` | counted in **tokens**, per tier; first matching `condition` wins |
| Which model? | `backend.yaml`, `transformations` | `apiKey.tier == "pro" ? "qwen2.5:7b" : "qwen2.5:1.5b"`, whatever the client asked |
| Safe prompt? | `backend.yaml`, `promptGuard.request` | regex built-ins -> custom regex -> Llama Guard webhook; a reject means the model is never called |
| Safe answer? | `backend.yaml`, `promptGuard.response` | emails and phone numbers masked |
| Who spent what? | `platform/gateway/telemetry.yaml` | a `user` label on every metric, `user`/tokens on every access log line |

**Llama Guard** (`demos/guard/guard.py`) is ~80 lines of stdlib Python implementing agentgateway's webhook
contract (`POST /request` -> pass / reject). It runs `llama-guard3:1b` in the same Ollama. Watch it decide:
`./scripts/demo.sh guardlog`.

## Changing things live

Everything is GitOps: edit, commit, push, then `./scripts/sync.sh` (Argo otherwise polls every 30 s).
Good live edits:
- the pirate persona (`demos/02-prompt/pirate.yaml`)
- the intern's budget (`demos/03-company/route.yaml`)
- `Mask` -> `Reject` on the response guard (`demos/03-company/backend.yaml`)
- point `smart` at `qwen3.5:9b` (`demos/01-chat/chat.yaml`)

The dashboard is generated: edit `scripts/make-dashboard.py`, run it, push. (Argo reverts edits made in the Grafana UI.)

## Layout

```
k3d.yaml                 the cluster (1 node, port 80, no Traefik)
bootstrap/               Argo CD install values + the root app (the only things applied by hand)
apps/                    one Argo CD Application per component; sync-wave = boot order
platform/gateway/        the Gateway + gateway-wide telemetry policy
platform/routes/         argocd/grafana/prometheus.localhost
platform/dashboards/     the Grafana dashboard
demos/                   one folder per demo
scripts/                 up, down, sync, demo, make-dashboard
```

## Gotchas found while building this

- **Ollama in Docker on a Mac is CPU-only.** So Ollama runs natively and the cluster reaches it at
  `host.k3d.internal`.
- **Only one AgentgatewayPolicy per section per target.** Two `traffic` policies on the same route: one silently
  wins (both report Accepted). Combine them.
- **The Grafana chart generates a new admin password on every render**, so under Argo it restarts forever.
  Pinned in `apps/grafana.yaml`.
- **The Prometheus chart's default jobs scrape the proxy twice** (via its `prometheus.io/scrape` annotation),
  doubling every number. All default jobs are off; there is one `agentgateway` job.
- **Local rate limits are per proxy replica.** Fine with one replica; for real use, the global rate limiter.

## Next

- kagent: an agent whose LLM *and* tools (MCP) go through this gateway
- LiteLLM next to it, in front of the same Ollama, for the comparison
- a chat UI (Open WebUI) pointed at `api.localhost`
