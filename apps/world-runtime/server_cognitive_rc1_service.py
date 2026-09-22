from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock

from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime


class RuntimeController:
    def __init__(self, *, episode_id: int = 1):
        self._lock = RLock()
        self.runtime = ServerCognitiveRC1Runtime.create(episode_id=episode_id)

    def status(self):
        with self._lock:
            return self.runtime.status()

    def step(self):
        with self._lock:
            return self.runtime.step()

    def run(self, cycles: int):
        with self._lock:
            return {
                "cycles_requested": cycles,
                "samples": self.runtime.run(cycles),
                "status": self.runtime.status(),
            }


def make_handler(controller: RuntimeController):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LiveInfinitaServerCognitiveRC1/0.1"

        def _json(self, status: int, payload):
            body = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._json(
                    200,
                    {
                        "status": "ok",
                        "profile": "server-cognitive-rc1",
                    },
                )
                return
            if self.path == "/api/v1/status":
                self._json(200, controller.status())
                return
            self._json(404, {"error": "not-found"})

        def do_POST(self):
            if self.path == "/api/v1/step":
                self._json(200, controller.step())
                return
            if self.path.startswith("/api/v1/run"):
                cycles = 1
                if "?" in self.path:
                    query = self.path.split("?", 1)[1]
                    for item in query.split("&"):
                        key, _, value = item.partition("=")
                        if key == "cycles":
                            cycles = int(value)
                if cycles < 1 or cycles > 1000:
                    self._json(
                        400,
                        {"error": "cycles must be between 1 and 1000"},
                    )
                    return
                self._json(200, controller.run(cycles))
                return
            self._json(404, {"error": "not-found"})

        def log_message(self, format, *args):
            return

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--episode-id", type=int, default=1)
    args = parser.parse_args()

    controller = RuntimeController(episode_id=args.episode_id)
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(controller),
    )
    print(
        json.dumps(
            {
                "status": "listening",
                "profile": "server-cognitive-rc1",
                "host": args.host,
                "port": args.port,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
