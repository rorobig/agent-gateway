"""Generates platform/dashboards/agentgateway-talk.yaml. Run: python3 scripts/make-dashboard.py"""
import json, os
# Reference palette, dark-mode steps (Grafana runs in its dark theme on stage).
S1, S2, S3, S4, S5 = "#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
DS = {"type": "prometheus", "uid": "prometheus"}
T = 'agentgateway_gen_ai_client_token_usage'
panels, pid = [], 0

def panel(kind, title, x, y, w, h, targets, desc="", **kw):
    global pid; pid += 1
    p = {"id": pid, "type": kind, "title": title, "description": desc, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": chr(65 + i), "datasource": DS, "expr": e, "legendFormat": l,
                      **({"instant": True, "range": False} if kind in ("stat", "bargauge") else {})}
                     for i, (e, l) in enumerate(targets)]}
    p.update(kw); panels.append(p)

def fixed(name, color):  # color follows the entity, never its rank
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]}

def stat(title, expr, x, desc):
    panel("stat", title, x, 0, 4, 4, [(f"round(sum({expr}) or vector(0))", "")], desc,
          options={"colorMode": "none", "graphMode": "none", "textMode": "value", "justifyMode": "center",
                   "reduceOptions": {"calcs": ["lastNotNull"]}},
          fieldConfig={"defaults": {"decimals": 0, "unit": "locale"}, "overrides": []})

R = "[$__range]"
stat("Tokens", f'increase({T}_sum{R})', 0, "All input + output tokens through the gateway in the selected time range.")
stat("LLM requests", f'increase(agentgateway_requests_total{{route=~"ai/.*"}}{R})', 4, "Requests to the AI routes.")
stat("Blocked by guards (403)", f'increase(agentgateway_requests_total{{route=~"ai/.*",status="403"}}{R})', 8, "Prompt guards said no: regex, prompt injection, Llama Guard. The model was never called.")
stat("Over token budget (429)", f'increase(agentgateway_requests_total{{route=~"ai/.*",status="429"}}{R})', 12, "Token budget used up for this user.")
stat("No / bad API key (401)", f'increase(agentgateway_requests_total{{route=~"ai/.*",status="401"}}{R})', 16, "Rejected before anything else happened.")
stat("Masked responses", f'increase(agentgateway_guardrail_checks_total{{action="Mask"}}{R})', 20, "Answers where the gateway masked emails/phone numbers before the caller saw them.")

users = [("alice", S1), ("bob", S2), ("intern", S3), ("anonymous", S4)]
line = {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 8, "showPoints": "never", "spanNulls": True}
panel("timeseries", "Tokens per minute, by user", 0, 4, 14, 10,
      [(f'sum by (user) (rate({T}_sum[1m])) * 60', "{{user}}")],
      "Who is spending tokens. The user comes from the API key (apiKey.user_id), added as a metric label by the gateway.",
      fieldConfig={"defaults": {"custom": line, "unit": "short", "decimals": 0, "min": 0},
                   "overrides": [fixed(u, c) for u, c in users]},
      options={"legend": {"displayMode": "list", "placement": "right"},
               "tooltip": {"mode": "multi", "sort": "desc"}})
panel("bargauge", "Avg output tokens per answer, by route", 14, 4, 10, 10,
      [(f'sum by (route) (increase({T}_sum{{gen_ai_token_type="output"}}{R})) / sum by (route) (increase({T}_count{{gen_ai_token_type="output"}}{R}))', "{{route}}")],
      "brief.localhost appends 'be brief' and caps max_tokens: compare it with llm.localhost.",
      options={"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True, "valueMode": "text",
               "reduceOptions": {"calcs": ["lastNotNull"]}, "namePlacement": "top", "text": {"titleSize": 16, "valueSize": 26}},
      fieldConfig={"defaults": {"decimals": 0, "min": 0, "color": {"mode": "fixed", "fixedColor": S1}}, "overrides": []})

codes = [("200", GOOD, "200 ok"), ("401", SERIOUS, "401 no key"), ("403", CRIT, "403 blocked"), ("429", WARN, "429 over budget")]
panel("timeseries", "Request outcomes per minute", 0, 14, 10, 9,
      [(f'sum by (status) (rate(agentgateway_requests_total{{route=~"ai/.*"}}[1m])) * 60', "{{status}}")],
      "Every AI request by HTTP status. Status colors are paired with the code in the legend.",
      fieldConfig={"defaults": {"custom": {**line, "drawStyle": "bars", "fillOpacity": 80, "lineWidth": 1,
                                           "stacking": {"mode": "normal"}}, "unit": "short", "decimals": 1, "min": 0},
                   "overrides": [{**fixed(c, col), "properties": fixed(c, col)["properties"] + [{"id": "displayName", "value": n}]}
                                 for c, col, n in codes]},
      options={"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi", "sort": "desc"}})
panel("bargauge", "Guardrail decisions", 10, 14, 7, 9,
      [(f'round(sum by (phase, action) (increase(agentgateway_guardrail_checks_total{R})))', "{{phase}} · {{action}}")],
      "Each guard check: on the prompt (Request) or the answer (Response).",
      options={"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True, "valueMode": "text",
               "reduceOptions": {"calcs": ["lastNotNull"]}, "namePlacement": "top", "text": {"titleSize": 16, "valueSize": 26}},
      fieldConfig={"defaults": {"decimals": 0, "min": 0, "color": {"mode": "fixed", "fixedColor": S1}}, "overrides": []})
panel("bargauge", "Tokens by model", 17, 14, 7, 9,
      [(f'round(sum by (gen_ai_response_model) (increase({T}_sum{R})))', "{{gen_ai_response_model}}")],
      "Which model actually served the tokens (after aliases and tier routing).",
      options={"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True, "valueMode": "text",
               "reduceOptions": {"calcs": ["lastNotNull"]}, "namePlacement": "top", "text": {"titleSize": 16, "valueSize": 26}},
      fieldConfig={"defaults": {"decimals": 0, "min": 0, "color": {"mode": "fixed", "fixedColor": S1}}, "overrides": []})
panel("timeseries", "p95 answer time, by model", 0, 23, 24, 8,
      [('histogram_quantile(0.95, sum by (le, gen_ai_response_model) (rate(agentgateway_gen_ai_server_request_duration_bucket[2m])))', "{{gen_ai_response_model}}")],
      "How long the model took to answer, measured at the gateway.",
      fieldConfig={"defaults": {"custom": line, "unit": "s", "min": 0},
                   "overrides": [fixed("qwen2.5:7b", S1), fixed("qwen2.5:1.5b", S2)]},
      options={"legend": {"displayMode": "list", "placement": "right"}, "tooltip": {"mode": "multi", "sort": "desc"}})

dash = {"uid": "agentgateway-talk", "title": "agentgateway: the talk", "editable": True, "refresh": "5s",
        "time": {"from": "now-15m", "to": "now"}, "timepicker": {"refresh_intervals": ["5s", "10s", "30s"]},
        "schemaVersion": 39, "tags": ["agentgateway"], "panels": panels}
body = json.dumps(dash, indent=1).replace("\n", "\n    ")
out = f"""# Generated by scripts/make-dashboard.py; edit that, not this.
# The Grafana sidecar loads ConfigMaps labelled grafana_dashboard=1.
apiVersion: v1
kind: ConfigMap
metadata:
  name: agentgateway-talk-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  agentgateway-talk.json: |
    {body}
"""
path = os.path.join(os.path.dirname(__file__), "..", "platform", "dashboards", "agentgateway-talk.yaml")
open(path, "w").write(out)
print(len(panels), "panels ->", os.path.normpath(path))
