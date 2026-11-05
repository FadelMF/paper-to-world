"""An OpenAI-compatible Chat Completions / Responses endpoint that answers with ScriptedLLM replies.

    python tests/fake_llm_server.py PORT 2d|3d [FIXTURE_DIR]

FIXTURE_DIR holds replies written in advance, one file per call, named NN-Agent.txt (e.g. 01-Analyst.txt);
each agent's files are used in name order before ScriptedLLM's own replies.

Lets the real server, worker process and OpenAI client run unchanged, with LLM_BASE_URL (and VISION_MODEL,
for the image agents) pointing here.
"""

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_fixture import ScriptedLLM

port, modality = int(sys.argv[1]), sys.argv[2]
replies = {}
for path in sorted(Path(sys.argv[3]).glob("*.txt")) if len(sys.argv) > 3 else []:
    replies.setdefault(path.stem.split("-", 1)[1], []).append(path.read_text())
scripted = ScriptedLLM(modality, **replies)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        responses = "input" in body
        messages = {m["role"]: m["content"] for m in body["input"] if m.get("role")} if responses else {m["role"]: m["content"] for m in body["messages"]}
        if responses:
            messages["system"] = "".join(part["text"] for part in messages["system"])
            converted = [
                {"type": "text", "text": part["text"]} if part["type"] == "input_text" else {"type": "image_url", "image_url": {"url": part["image_url"]}}
                for part in messages["user"]
            ]
            messages["user"] = converted if any(part["type"] == "image_url" for part in converted) else "".join(part["text"] for part in converted)
        user = messages["user"]
        if isinstance(user, list):  # a vision request: text then base64 PNG images
            images = [base64.b64decode(part["image_url"]["url"].split(",", 1)[1]) for part in user if part["type"] == "image_url"]
            content = scripted(messages["system"], "".join(part["text"] for part in user if part["type"] == "text"), images)
        else:
            content = scripted(messages["system"], user)
        if responses:
            payload = {
                "id": "resp_fake",
                "object": "response",
                "created_at": 0,
                "model": body["model"],
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_fake",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": content, "annotations": []}],
                    }
                ],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
        else:
            payload = {
                "id": "fake",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        reply = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, format, *args):
        agent = scripted.calls[-1][0] if scripted.calls else "-"
        print(f"{agent} {format % args}", flush=True)


ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
