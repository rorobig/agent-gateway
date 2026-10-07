"""Llama Guard as an agentgateway prompt-guard webhook.

agentgateway POSTs {"body": {"messages": [{"role", "content"}, ...]}} to /request.
We ask Llama Guard 3 (running in Ollama) whether the user's messages are safe and answer:
  pass:   {"action": {"reason": "..."}}
  reject: {"action": {"body": "<message for the caller>", "status_code": 403, "reason": "..."}}
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLLAMA = os.environ.get("OLLAMA_URL", "http://host.k3d.internal:11434")
MODEL = os.environ.get("GUARD_MODEL", "llama-guard3:1b")

# Llama Guard 3 hazard categories
CATEGORIES = {
    "S1": "violent crimes", "S2": "non-violent crimes", "S3": "sex-related crimes",
    "S4": "child sexual exploitation", "S5": "defamation", "S6": "specialized advice",
    "S7": "privacy", "S8": "intellectual property", "S9": "indiscriminate weapons",
    "S10": "hate", "S11": "suicide & self-harm", "S12": "sexual content",
    "S13": "elections", "S14": "code interpreter abuse",
}


def text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # OpenAI content parts
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def classify(messages):
    # Only what the caller wrote (user messages), as one prompt. If the conversation ends with an
    # assistant turn, Llama Guard judges that answer instead of the prompt: agents' own replies
    # ("I'll patch the deployment...") then get blocked as "specialized advice".
    asked = "\n\n".join(t for m in messages if m.get("role") == "user" and (t := text(m.get("content"))))
    if not asked:
        return "safe"
    convo = [{"role": "user", "content": asked}]
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps({"model": MODEL, "messages": convo, "stream": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["message"]["content"].strip()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path != "/request":  # we only guard prompts; let responses through
            return self.reply({"action": {"reason": "not checked"}})
        verdict = classify(body.get("body", {}).get("messages", []))
        lines = verdict.split()
        if lines and lines[0] == "unsafe":
            codes = lines[1].split(",") if len(lines) > 1 else []
            why = ", ".join(CATEGORIES.get(c, c) for c in codes) or "unsafe"
            print(f"BLOCK  {why}", flush=True)
            return self.reply({"action": {
                "body": f"Blocked by Llama Guard: {why}.",
                "status_code": 403,
                "reason": why,
            }})
        print("PASS", flush=True)
        self.reply({"action": {"reason": "safe"}})

    def do_GET(self):  # readiness probe
        self.reply({"ok": True})

    def reply(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"llama-guard webhook on :8000 -> {OLLAMA} ({MODEL})", flush=True)
    ThreadingHTTPServer(("", 8000), Handler).serve_forever()
