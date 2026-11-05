"""Exercise the real SDK against a local Responses endpoint; no provider credentials."""

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from app import llm


class ResponsesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.requests = []
        self.response = {
            "id": "resp_test",
            "object": "response",
            "created_at": 0,
            "model": "muse-wonder-1.0",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_test",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "hello", "annotations": []}],
                }
            ],
            "usage": {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, self.headers.get("Authorization"), body))
                data = json.dumps(owner.response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)
        env = {
            "LLM_BASE_URL": f"http://127.0.0.1:{self.server.server_port}/v1",
            "LLM_API_KEY": "test-key",
            "PAPER_RUNS_DIR": temporary.name,
            "LLM_MODEL": "muse-wonder-1.0",
            "LLM_API": "responses",
            "VISION_MODEL": "test-vision",
        }
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_text_request_and_usage(self):
        self.assertEqual(llm.chat("system prompt", "user prompt"), "hello")
        path, auth, body = self.requests[-1]
        self.assertEqual(path, "/v1/responses")
        self.assertEqual(auth, "Bearer test-key")
        self.assertEqual(body["model"], "muse-wonder-1.0")
        self.assertEqual(body["input"][0]["content"][0]["text"], "system prompt")
        self.assertEqual(body["input"][1]["content"], [{"type": "input_text", "text": "user prompt"}])
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_output_tokens"], 16000)
        self.assertNotIn("max_tokens", body)
        self.assertEqual(llm.USAGE[-1]["prompt_tokens"], 12)
        self.assertEqual(llm.USAGE[-1]["completion_tokens"], 3)

    def test_image_request(self):
        self.assertEqual(llm.chat_vision("system", "look", [b"png"]), "hello")
        body = self.requests[-1][2]
        self.assertEqual(body["model"], "test-vision")
        self.assertEqual(body["input"][1]["content"][1], {"type": "input_image", "image_url": "data:image/png;base64,cG5n", "detail": "auto"})
        self.assertEqual(llm.USAGE[-1]["images"], 1)

    def test_unsuccessful_responses_are_rejected(self):
        for status in ("incomplete", "failed", "in_progress"):
            with self.subTest(status=status):
                self.response["status"] = status
                with self.assertRaises(RuntimeError):
                    llm.chat("system", "user")
        self.response["status"] = "completed"
        self.response["output"] = []
        with self.assertRaisesRegex(RuntimeError, "empty"):
            llm.chat("system", "user")
