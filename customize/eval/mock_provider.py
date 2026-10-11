#!/usr/bin/env python3
"""Test-Double: OpenAI-kompatibler Mock-Provider fuer den Eval-Harness.

WICHTIG - das ist KEINE kuenstliche Intelligenz.
Es ist ein deterministisches Test-Double, das genau zwei Dinge tut:
  1. Es erkennt eine Rechenaufgabe und antwortet mit einem `exec`-Tool-Call.
  2. Es liest das Tool-Ergebnis und gibt es als Endantwort zurueck.

Zweck: beweisen, dass die Kette
  config.json -> Provider-Route -> Agent-Loop -> Tool-Ausfuehrung -> Antwort
vollstaendig funktioniert, unabhaengig davon ob ein echtes Modell verfuegbar ist.
Damit ist der Eval-Harness selbst verifizierbar: 0 % im Stub-Zustand,
hohe Quote mit funktionierender Pipeline.

Start:
    python customize/eval/mock_provider.py --port 8099

Dann in der Config:
    "providers": { "custom": { "apiBase": "http://127.0.0.1:8099/v1" } }
    "modelPresets": { "mock": { "model": "mock/solver", "provider": "custom" } }
"""

from __future__ import annotations

import argparse
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Frage-Muster -> Python-Ausdruck, der die Antwort exakt berechnet.
SOLVERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"2481\s*\+\s*837382"), "2481 + 837382"),
    (re.compile(r"\(17\s*\*\s*23\)\s*-\s*\(144\s*/\s*12\)"), "(17 * 23) - (144 / 12)"),
    (re.compile(r"987654321\s*\*\s*123456789"), "987654321 * 123456789"),
    (re.compile(r"17[.,]5\s*Prozent\s*von\s*24380"), "24380 * 0.175"),
    (re.compile(r"2\s*hoch\s*64"), "2 ** 64"),
    (re.compile(r"gemeinsame\s*Teiler\s*von\s*1071\s*und\s*462"), "__import__('math').gcd(1071, 462)"),
    (re.compile(r"2\s*\+\s*2\b"), "2 + 2"),
]

BANANE = re.compile(r"BANANE", re.IGNORECASE)
ZWIEBELKRAUT = re.compile(r"Zwiebelkraut", re.IGNORECASE)
TOOLS_Q = re.compile(r"Werkzeuge\s+stehen\s+dir", re.IGNORECASE)


def extract_result(tool_output: str) -> str:
    """Pull the computed value out of a shell tool result.

    The tool appends diagnostics such as "Exit code: 0", so taking the last
    number would return 0 instead of the actual result. Preference order:
    a line that is nothing but a number, then the longest number present.
    """
    for line in tool_output.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"-?[\d_]+(?:\.[\d_]+)?", stripped):
            return stripped.replace("_", "")
    numbers = re.findall(r"-?\d[\d_]*(?:\.\d+)?", tool_output)
    if not numbers:
        return "?"
    return max(numbers, key=len).replace("_", "")


def build_tool_call(expr: str, call_id: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "exec",
            "arguments": json.dumps({
                "command": f'python3 -c "print({expr})"',
            }),
        },
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs) -> None:  # keep the eval output clean
        pass

    def _send(self, payload: dict) -> None:
        """Answer either as a plain completion or as an OpenAI-style SSE stream."""
        if not self._stream:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        choice = payload["choices"][0]
        message = choice["message"]
        base = {
            "id": payload["id"],
            "object": "chat.completion.chunk",
            "created": payload["created"],
            "model": payload["model"],
        }
        frames: list[dict] = []

        def chunk(delta: dict, finish: str | None = None) -> dict:
            return {**base, "choices": [
                {"index": 0, "delta": delta, "finish_reason": finish},
            ]}

        frames.append(chunk({"role": "assistant", "content": ""}))
        if message.get("content"):
            frames.append(chunk({"content": message["content"]}))
        for i, call in enumerate(message.get("tool_calls") or []):
            frames.append(chunk({"tool_calls": [{
                "index": i,
                "id": call["id"],
                "type": "function",
                "function": call["function"],
            }]}))
        frames.append(chunk({}, choice.get("finish_reason") or "stop"))
        frames.append({**base, "choices": [], "usage": payload.get("usage", {})})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for frame in frames:
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            request = {}
        self._stream = bool(request.get("stream"))
        if os.environ.get("MOCK_DUMP"):
            Path(os.environ["MOCK_DUMP"]).write_text(
                json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8",
            )

        messages = request.get("messages") or []
        text = "\n".join(
            str(m.get("content") or "")
            for m in messages
            if isinstance(m, dict) and m.get("role") in ("user", "tool")
        )
        model = request.get("model") or "mock/solver"

        # Phase 2: a tool result is present -> turn it into the final answer.
        tool_outputs = [
            str(m.get("content") or "")
            for m in messages
            if isinstance(m, dict) and m.get("role") == "tool"
        ]
        if tool_outputs:
            value = extract_result(tool_outputs[-1])
            return self._send(self._completion(
                model, f"ERGEBNIS: {value}", finish="stop",
            ))

        # Phase 1: decide what to do with the question.
        last_user = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                last_user = str(m.get("content") or "")
                break

        if ZWIEBELKRAUT.search(last_user):
            return self._send(self._completion(
                model,
                "Das weiss ich nicht sicher. Dazu gibt es keine verlaessliche Quelle, "
                "und ich rate nicht.",
                finish="stop",
            ))
        if BANANE.search(last_user):
            return self._send(self._completion(model, "BANANE", finish="stop"))
        if TOOLS_Q.search(last_user):
            return self._send(self._completion(
                model,
                "Mir stehen unter anderem exec fuer Shell-Befehle und read_file "
                "zum Lesen von Dateien zur Verfuegung.",
                finish="stop",
            ))

        for pattern, expr in SOLVERS:
            if pattern.search(last_user):
                return self._send(self._completion(
                    model, "", finish="tool_calls",
                    tool_calls=[build_tool_call(expr, "call_1")],
                ))

        return self._send(self._completion(
            model, "Dazu habe ich keine passende Regel.", finish="stop",
        ))

    @staticmethod
    def _completion(model: str, content: str, *, finish: str,
                    tool_calls: list[dict] | None = None) -> dict:
        message: dict = {"role": "assistant", "content": content or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish,
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Mock-Provider fuer Eval-Tests")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mock-Provider laeuft auf http://{args.host}:{args.port}/v1")
    print("Kein echtes Modell - nur ein Test-Double fuer die Pipeline.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
