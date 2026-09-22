from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, RLock, Thread
from urllib.parse import parse_qs, urlparse

from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime


class RuntimeController:
    def __init__(
        self,
        *,
        episode_id: int = 1,
        checkpoint_path: str | None = None,
        autosave_every: int = 1,
        resume: bool = True,
    ):
        if autosave_every < 1:
            raise ValueError("autosave_every must be >= 1")
        self._lock = RLock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._interval_seconds = 1.0
        self._background_errors = 0
        self._last_background_error: str | None = None
        self._checkpoint_errors = 0
        self._last_checkpoint_error: str | None = None
        self._checkpoint_path = (
            str(Path(checkpoint_path))
            if checkpoint_path
            else None
        )
        self._autosave_every = int(autosave_every)
        self._last_checkpoint_cycle: int | None = None
        self._loaded_from_checkpoint = False

        if (
            resume
            and self._checkpoint_path
            and Path(self._checkpoint_path).is_file()
        ):
            self.runtime = ServerCognitiveRC1Runtime.load_checkpoint(
                self._checkpoint_path
            )
            self._loaded_from_checkpoint = True
            self._last_checkpoint_cycle = self.runtime.cycles
        else:
            self.runtime = ServerCognitiveRC1Runtime.create(
                episode_id=episode_id
            )

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive() and not self._stop.is_set())

    def _service_state(self) -> dict:
        return {
            "running": self.running,
            "interval_seconds": self._interval_seconds,
            "background_errors": self._background_errors,
            "last_background_error": self._last_background_error,
            "checkpoint_path": self._checkpoint_path,
            "autosave_every": self._autosave_every,
            "loaded_from_checkpoint": self._loaded_from_checkpoint,
            "last_checkpoint_cycle": self._last_checkpoint_cycle,
            "checkpoint_errors": self._checkpoint_errors,
            "last_checkpoint_error": self._last_checkpoint_error,
        }

    def _save_checkpoint_locked(self):
        if not self._checkpoint_path:
            return None
        try:
            target = self.runtime.save_checkpoint(self._checkpoint_path)
            self._last_checkpoint_cycle = self.runtime.cycles
            self._last_checkpoint_error = None
            return str(target)
        except Exception as exc:
            self._checkpoint_errors += 1
            self._last_checkpoint_error = f"{type(exc).__name__}: {exc}"
            raise

    def checkpoint(self):
        with self._lock:
            target = self._save_checkpoint_locked()
            return {
                "saved": target is not None,
                "path": target,
                "cycles": self.runtime.cycles,
                "service": self._service_state(),
            }

    def _autosave_locked(self):
        if not self._checkpoint_path:
            return
        if self.runtime.cycles % self._autosave_every != 0:
            return
        self._save_checkpoint_locked()

    def status(self):
        with self._lock:
            payload = self.runtime.status()
            payload["service"] = self._service_state()
            return payload

    def cognition(self):
        status = self.status()
        return {
            "profile": status["profile"],
            "cycles": status["cycles"],
            "simulation_time": status["simulation_time"],
            "cognition": status["cognition"],
            "event_time": status["event_time"],
        }

    def world_status(self):
        status = self.status()
        return {
            "profile": status["profile"],
            "cycles": status["cycles"],
            "world": status["world"],
            "nov": status["nov"],
            "environment": status["environment"],
            "sensors": status["sensors"],
        }

    def metrics(self):
        status = self.status()
        structural = status["cognition"]["structural"]
        event_time = status["event_time"]
        return {
            "cycles": status["cycles"],
            "world_tick": status["world"]["tick"],
            "world_events": status["world"]["events"],
            "causal_memory_episodes": status["cognition"]["causal"]["memory_episodes"],
            "pairwise_links": structural["pairwise_links"],
            "higher_order_links": structural["higher_order_links"],
            "historical_context_records": structural["historical_context_records"],
            "current_candidates": structural["current_candidates"],
            "resolved_contexts": structural["resolution_counts"].get("resolved", 0),
            "ambiguous_contexts": structural["resolution_counts"].get("ambiguous", 0),
            "unsupported_contexts": structural["resolution_counts"].get("unsupported", 0),
            "reality_slices_offered": event_time["slices_offered"],
            "reality_slices_ingested": event_time["slices_ingested"],
            "late_rejection_count": event_time["late_rejection_count"],
            "watermark": event_time["watermark"],
            "max_event_time": event_time["max_event_time"],
            "service_running": status["service"]["running"],
        }

    def step(self):
        with self._lock:
            payload = self.runtime.step()
            self._autosave_locked()
            payload["service"] = self._service_state()
            return payload

    def run(self, cycles: int):
        if cycles < 1:
            raise ValueError("cycles must be >= 1")
        with self._lock:
            samples = []
            for _ in range(cycles):
                samples.append(self.runtime.step())
                self._autosave_locked()
            status = self.runtime.status()
            status["service"] = self._service_state()
            return {
                "cycles_requested": cycles,
                "samples": tuple(samples),
                "status": status,
            }

    def _background_loop(self):
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.step()
                self._last_background_error = None
            except Exception as exc:
                self._background_errors += 1
                self._last_background_error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            remaining = max(0.0, self._interval_seconds - elapsed)
            self._stop.wait(remaining)

    def start(self, *, interval_seconds: float = 1.0):
        interval = float(interval_seconds)
        if interval < 0.01 or interval > 60.0:
            raise ValueError("interval_seconds must be between 0.01 and 60")
        with self._lock:
            if self.running:
                self._interval_seconds = interval
                return self.status()
            self._interval_seconds = interval
            self._stop.clear()
            self._thread = Thread(
                target=self._background_loop,
                name="server-cognitive-rc1-loop",
                daemon=True,
            )
            self._thread.start()
            return self.status()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        with self._lock:
            if self._checkpoint_path:
                self._save_checkpoint_locked()
            return self.status()

    def close(self):
        return self.stop()


def _query(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlparse(path)
    return parsed.path, parse_qs(parsed.query, keep_blank_values=True)


def _single_float(query: dict[str, list[str]], key: str, default: float) -> float:
    values = query.get(key)
    if not values:
        return default
    return float(values[-1])


def _single_int(query: dict[str, list[str]], key: str, default: int) -> int:
    values = query.get(key)
    if not values:
        return default
    return int(values[-1])


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
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path, _query_values = _query(self.path)
            if path == "/health":
                payload = controller.status()
                self._json(
                    200,
                    {
                        "status": "ok",
                        "profile": "server-cognitive-rc1",
                        "cycles": payload["cycles"],
                        "running": payload["service"]["running"],
                    },
                )
                return
            if path == "/api/v1/status":
                self._json(200, controller.status())
                return
            if path == "/api/v1/cognition":
                self._json(200, controller.cognition())
                return
            if path == "/api/v1/world":
                self._json(200, controller.world_status())
                return
            if path == "/api/v1/metrics":
                self._json(200, controller.metrics())
                return
            self._json(404, {"error": "not-found"})

        def do_POST(self):
            path, query = _query(self.path)
            try:
                if path == "/api/v1/step":
                    self._json(200, controller.step())
                    return
                if path == "/api/v1/run":
                    cycles = _single_int(query, "cycles", 1)
                    if cycles < 1 or cycles > 1000:
                        self._json(
                            400,
                            {"error": "cycles must be between 1 and 1000"},
                        )
                        return
                    self._json(200, controller.run(cycles))
                    return
                if path == "/api/v1/start":
                    interval = _single_float(query, "interval", 1.0)
                    self._json(
                        200,
                        controller.start(interval_seconds=interval),
                    )
                    return
                if path == "/api/v1/checkpoint":
                    self._json(200, controller.checkpoint())
                    return
                if path == "/api/v1/stop":
                    self._json(200, controller.stop())
                    return
            except (TypeError, ValueError) as exc:
                self._json(400, {"error": str(exc)})
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
    parser.add_argument("--autostart", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--checkpoint",
        default="var/server-cognitive-rc1/checkpoint.json",
    )
    parser.add_argument("--autosave-every", type=int, default=10)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    controller = RuntimeController(
        episode_id=args.episode_id,
        checkpoint_path=args.checkpoint,
        autosave_every=args.autosave_every,
        resume=not args.no_resume,
    )
    if args.autostart:
        controller.start(interval_seconds=args.interval)

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
                "autostart": bool(args.autostart),
                "interval": args.interval,
                "checkpoint": args.checkpoint,
                "autosave_every": args.autosave_every,
                "resume": not args.no_resume,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        controller.close()
        server.server_close()


if __name__ == "__main__":
    main()
