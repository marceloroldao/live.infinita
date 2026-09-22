from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from urllib.parse import parse_qs, urlsplit

from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime


class RuntimeController:
    def __init__(
        self,
        *,
        episode_id: int = 1,
        state_path: str | None = None,
    ):
        self._lock = RLock()
        self._state_path = Path(state_path).resolve() if state_path else None
        if self._state_path is not None and self._state_path.exists():
            self.runtime = ServerCognitiveRC1Runtime.load_checkpoint(
                self._state_path
            )
        else:
            self.runtime = ServerCognitiveRC1Runtime.create(
                episode_id=episode_id
            )

        self._auto_stop = Event()
        self._auto_thread: Thread | None = None
        self._auto_interval: float | None = None
        self._last_auto_error: str | None = None

    def _checkpoint_unlocked(self):
        if self._state_path is None:
            return None
        return str(self.runtime.save_checkpoint(self._state_path))

    def _service_state(self):
        running = (
            self._auto_thread is not None
            and self._auto_thread.is_alive()
            and not self._auto_stop.is_set()
        )
        return {
            "auto_running": running,
            "auto_interval": self._auto_interval,
            "checkpoint_path": (
                str(self._state_path)
                if self._state_path is not None
                else None
            ),
            "last_auto_error": self._last_auto_error,
        }

    def status(self):
        with self._lock:
            payload = self.runtime.status()
            payload["service"] = self._service_state()
            return payload

    def inspect(self):
        with self._lock:
            payload = self.runtime.inspect()
            payload["service"] = self._service_state()
            return payload

    def step(self):
        with self._lock:
            payload = self.runtime.step()
            self._checkpoint_unlocked()
            payload["service"] = self._service_state()
            return payload

    def run(self, cycles: int):
        if cycles < 1 or cycles > 1000:
            raise ValueError("cycles must be between 1 and 1000")
        with self._lock:
            samples = self.runtime.run(cycles)
            self._checkpoint_unlocked()
            status = self.runtime.status()
            status["service"] = self._service_state()
            return {
                "cycles_requested": cycles,
                "samples": samples,
                "status": status,
            }

    def checkpoint(self):
        with self._lock:
            path = self._checkpoint_unlocked()
            if path is None:
                raise ValueError("checkpoint path is not configured")
            return {
                "status": "saved",
                "path": path,
                "cycles": self.runtime.cycles,
            }

    def _auto_worker(self):
        assert self._auto_interval is not None
        while not self._auto_stop.wait(self._auto_interval):
            try:
                self.step()
            except Exception as exc:  # surfaced in status instead of silent death
                with self._lock:
                    self._last_auto_error = (
                        f"{type(exc).__name__}: {exc}"
                    )
                self._auto_stop.set()
                break

    def start_auto(self, interval: float):
        interval = float(interval)
        if interval <= 0:
            raise ValueError("auto interval must be > 0")
        with self._lock:
            if (
                self._auto_thread is not None
                and self._auto_thread.is_alive()
            ):
                raise ValueError("automatic runtime is already running")
            self._auto_interval = interval
            self._last_auto_error = None
            self._auto_stop.clear()
            self._auto_thread = Thread(
                target=self._auto_worker,
                name="server-cognitive-rc1-auto",
                daemon=True,
            )
            self._auto_thread.start()
            return self._service_state()

    def stop_auto(self):
        with self._lock:
            thread = self._auto_thread
            self._auto_stop.set()
        if (
            thread is not None
            and thread.is_alive()
            and thread is not current_thread()
        ):
            thread.join(timeout=5.0)
        with self._lock:
            self._checkpoint_unlocked()
            return self._service_state()


def make_handler(controller: RuntimeController):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LiveInfinitaServerCognitiveRC1/0.2"

        def _json(self, status: int, payload):
            body = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _request(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            return parsed.path, query

        def _error(self, exc):
            status = 400 if isinstance(exc, ValueError) else 500
            self._json(
                status,
                {
                    "error": type(exc).__name__,
                    "detail": str(exc),
                },
            )

        def do_GET(self):
            path, _query = self._request()
            try:
                if path == "/health":
                    self._json(
                        200,
                        {
                            "status": "ok",
                            "profile": "server-cognitive-rc1",
                        },
                    )
                    return
                if path == "/api/v1/status":
                    self._json(200, controller.status())
                    return
                if path == "/api/v1/inspect":
                    self._json(200, controller.inspect())
                    return
                self._json(404, {"error": "not-found"})
            except Exception as exc:
                self._error(exc)

        def do_POST(self):
            path, query = self._request()
            try:
                if path == "/api/v1/step":
                    self._json(200, controller.step())
                    return
                if path == "/api/v1/run":
                    cycles = int(query.get("cycles", ["1"])[0])
                    self._json(200, controller.run(cycles))
                    return
                if path == "/api/v1/checkpoint":
                    self._json(200, controller.checkpoint())
                    return
                if path == "/api/v1/auto/start":
                    interval = float(query.get("interval", ["1.0"])[0])
                    self._json(200, controller.start_auto(interval))
                    return
                if path == "/api/v1/auto/stop":
                    self._json(200, controller.stop_auto())
                    return
                self._json(404, {"error": "not-found"})
            except Exception as exc:
                self._error(exc)

        def log_message(self, format, *args):
            return

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--episode-id", type=int, default=1)
    parser.add_argument("--state-path")
    parser.add_argument(
        "--auto-interval",
        type=float,
        default=0.0,
        help="run one cognitive cycle every N seconds; 0 disables auto-run",
    )
    args = parser.parse_args()

    controller = RuntimeController(
        episode_id=args.episode_id,
        state_path=args.state_path,
    )
    if args.auto_interval > 0:
        controller.start_auto(args.auto_interval)

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
                "auto_interval": args.auto_interval,
                "state_path": args.state_path,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        controller.stop_auto()
        server.server_close()


if __name__ == "__main__":
    main()
