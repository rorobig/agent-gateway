# agent-gateway

Demo infrastructure for a talk on **agentgateway**: LLM traffic, agents (kagent, A2A, MCP), and how it compares with LiteLLM.
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
| http://kagent.localhost, http://agents.localhost | demo 4: agents (kagent UI, A2A endpoints) |
| http://litellm.localhost | demo 5: LiteLLM, for comparison |
| http://shop.localhost | demo 6: the app the fixer agent repairs (after `demo.sh break`) |

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
API keys (`keys.yaml`): `sk-alice` and `sk-bob` (tier `pro`), `sk-intern` (tier `free`), `sk-kagent` (tier `agent`, demo 4).

```bash
./scripts/demo.sh nokey          # 401, before anything else happens
./scripts/demo.sh badkey         # 401, a key the gateway doesn't know
./scripts/demo.sh as alice       # asks for "gpt-5", gets qwen3.5:9b    (pro)
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
| Which model? | `backend.yaml`, `transformations` | pro -> `qwen3.5:9b`, agent -> `qwen2.5:7b`, free -> `qwen2.5:1.5b`, whatever the client asked; thinking off |
| Safe prompt? | `backend.yaml`, `promptGuard.request` | regex built-ins -> custom regex -> Llama Guard webhook; a reject means the model is never called |
| Safe answer? | `backend.yaml`, `promptGuard.response` | emails and phone numbers masked |
| Who spent what? | `platform/gateway/telemetry.yaml` | a `user` label on every metric, `user`/tokens on every access log line |

**Llama Guard** (`demos/guard/guard.py`) is ~80 lines of stdlib Python implementing agentgateway's webhook
contract (`POST /request` -> pass / reject). It runs `llama-guard3:1b` in the same Ollama. Watch it decide:
`./scripts/demo.sh guardlog`.

### 4. Agents (`demos/04-agents`, kagent)
```bash
./scripts/demo.sh agents         # each agent's A2A agent card: name, description, skills
./scripts/demo.sh agent          # tour-guide -> cluster-reader -> Kubernetes tools, every step printed
./scripts/demo.sh reader "Are there any pods that are not running?"
```
```
you ──A2A──▶ agents.localhost ─▶ tour-guide ──A2A──▶ cluster-reader ──MCP──▶ read-only k8s tools
                                     │                     │
                                     └──── LLM calls ──────┴──▶ api.ai.svc.cluster.local (= api.localhost)
```
Two agents, both just `Agent` resources. `tour-guide` has no tools; its only "tool" is the other agent,
called over **A2A** (agent-to-agent protocol). `cluster-reader` uses kagent's Kubernetes tools over **MCP**.
Both make their LLM calls through the company endpoint with key `sk-kagent`: the agents are just another
user, with a token budget, the guards, and their own `kagent` line on the dashboard. Chat with them in the
UI at http://kagent.localhost.

### 5. LiteLLM, for comparison (`demos/05-litellm`)
```bash
./scripts/demo.sh litellm        # the same question via agentgateway and via LiteLLM
```
LiteLLM does demo 1's job (`fast`/`smart` aliases in front of the same Ollama) from its own `config.yaml`.
Notice the `model` in the answer: agentgateway reports the real model (`qwen2.5:7b`), LiteLLM the alias
(`smart`). agentgateway only routes to LiteLLM here; it doesn't see tokens on this route.

### 6. An agent that fixes things (`demos/04-agents/fixer.yaml`, `demos/06-fix`)
```bash
./scripts/demo.sh break          # deploys the shop, then a typo in its image: ErrImagePull, shop.localhost 503
./scripts/demo.sh fix            # fixer: list pods -> describe -> patch the image -> check; shop.localhost 200
```
`fixer` has the same Kubernetes tools as `cluster-reader` plus `k8s_patch_resource` and `k8s_rollout`.
It has its own key (`sk-fixer`, tier `pro`, so `qwen3.5:9b`) and its own line on the dashboard. The shop is
applied by `demo.sh`, not Argo CD, because Argo would self-heal both the breakage and the fix.
Expect about a minute. The prompt tells it to stay in the `playground` namespace, but nothing enforces that:
its tool server could patch anything. That is the argument for putting MCP behind the gateway too.

## Changing things live

Everything is GitOps: edit, commit, push, then `./scripts/sync.sh` (Argo otherwise polls every 30 s).
Good live edits:
- the pirate persona (`demos/02-prompt/pirate.yaml`)
- the intern's budget (`demos/03-company/route.yaml`)
- `Mask` -> `Reject` on the response guard (`demos/03-company/backend.yaml`)
- point `smart` at `qwen3.5:9b` (`demos/01-chat/chat.yaml`), or pro at `qwen2.5:7b` (`demos/03-company/backend.yaml`)

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

- **`kubectl apply` doesn't stick.** Argo CD self-heals every app back to git within seconds. Commit and push.
- **Pods can't use `*.localhost`** (that's their own loopback). In-cluster callers use
  `api.ai.svc.cluster.local`: an ExternalName Service to the proxy plus a second hostname on the route.
- **qwen2.5:7b and A2A tool calls:** it sent `tour-guide`'s `request` argument as an object 9 times in 10.
  An example string in the system prompt made it 10 out of 10 (and 1.5 s per call). `qwen3.5:9b` gets it
  right without the hint but takes ~40 s per call while thinking (~3 s with `reasoning_effort: none`).
- **Llama Guard judged agents' own replies.** Sent the whole conversation, it classifies the *last* turn;
  in an agent loop that's the agent's own text ("I'll patch the deployment"), blocked as "specialized advice".
  `guard.py` now sends only the user's messages. And a blocked LLM call makes a kagent agent hang for minutes.
- **qwen2.5:7b can't reliably fix things:** in 5 break/fix runs it broke the patch JSON once and wandered
  off twice. `qwen3.5:9b` (thinking off) is slower but gets it right.
- **kagent agent cards are at `.well-known/agent-card.json`** (A2A 0.3/1.0), not `agent.json`.

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

- kagent's MCP tool calls through the gateway too (today only its LLM calls are), with per-agent tool
  access: cluster-reader read-only, fixer only in `playground`
- the A2A route as an A2A-aware agentgateway backend (today: plain HTTP routing)
- a chat UI (Open WebUI) pointed at `api.localhost`
