from __future__ import annotations

import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from bootstrap_paths import configure_runtime_paths

configure_runtime_paths()

from engine import ServerCognitiveEngine  # noqa: E402


DASHBOARD = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Infinita — Cognitive RC1</title>
<style>
body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:18px}
h1{font-size:22px;margin:0 0 12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.card{background:#1c1c1c;border:1px solid #333;border-radius:10px;padding:12px}
pre{white-space:pre-wrap;word-break:break-word;font-size:12px}.ok{color:#7ee787}.bad{color:#ff7b72}
button{margin:4px;padding:8px 12px;background:#2f81f7;color:white;border:0;border-radius:6px;cursor:pointer}
</style>
</head>
<body>
<h1>Live Infinita — Server Cognitive RC1</h1>
<div>
<button onclick="post('/step',{})">1 step</button>
<button onclick="post('/run',{count:10})">10 steps</button>
<button onclick="post('/control',{autorun:true})">Autorun ON</button>
<button onclick="post('/control',{autorun:false})">Autorun OFF</button>
</div>
<div class="grid">
<div class="card"><h3>Status</h3><pre id="status"></pre></div>
<div class="card"><h3>Nov</h3><pre id="nov"></pre></div>
<div class="card"><h3>Cognição</h3><pre id="cognition"></pre></div>
<div class="card"><h3>Event time</h3><pre id="eventtime"></pre></div>
<div class="card"><h3>Atividade recente</h3><pre id="activity"></pre></div>
</div>
<script>
async function getj(url){return (await fetch(url)).json()}
async function post(url,body){await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}); await refresh()}
async function refresh(){
  try{
    const s=await getj('/snapshot'); const a=await getj('/activity?limit=12'); const h=await getj('/health');
    status.textContent=JSON.stringify({health:h,world:s.world,environment:s.environment},null,2);
    nov.textContent=JSON.stringify(s.nov,null,2);
    cognition.textContent=JSON.stringify({bit_analyze:s.bit_analyze,memoria_v2:s.memoria_v2},null,2);
    eventtime.textContent=JSON.stringify(s.event_time,null,2);
    activity.textContent=JSON.stringify(a,null,2);
  }catch(e){status.textContent='erro: '+e}
}
refresh(); setInterval(refresh,1500);
</script>
</body>
</html>"""


class CognitiveService:
    def __init__(self, engine: ServerCognitiveEngine, *, interval: float, autorun: bool):
        self.engine = engine
        self.interval = max(0.05, float(interval))
        self.autorun = bool(autorun)
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop,
            name="cognitive-autorun",
            daemon=True,
        )
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            if self.autorun:
                try:
                    self.engine.step()
                    self.last_error = None
                except Exception as exc:  # service must remain observable after a failed cycle
                    self.last_error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.01, self.interval - elapsed))

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


SERVICE: CognitiveService | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "LiveInfinitaCognitiveRC1/0.1"

    def log_message(self, format: str, *args) -> None:
        print("[server-cognitive]", format % args)

    def _json(self, payload, *, status=HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:
        assert SERVICE is not None
        parsed = urlparse(self.path)
        if parsed.path == "/":
            raw = DASHBOARD.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(raw)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/health":
            self._json({
                "status": "ok" if SERVICE.last_error is None else "degraded",
                "profile": "server-cognitive-rc1",
                "autorun": SERVICE.autorun,
                "interval_seconds": SERVICE.interval,
                "last_error": SERVICE.last_error,
            })
            return
        if parsed.path == "/snapshot":
            self._json(SERVICE.engine.snapshot())
            return
        if parsed.path == "/activity":
            query = parse_qs(parsed.query)
            limit = int((query.get("limit") or ["50"])[0])
            self._json({"items": SERVICE.engine.activity_snapshot(limit)})
            return
        if parsed.path == "/debug/world":
            self._json(SERVICE.engine.debug_world())
            return
        if parsed.path == "/debug/memory":
            self._json(SERVICE.engine.debug_memory())
            return
        self._json({"error": "not-found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        assert SERVICE is not None
        try:
            body = self._body()
            if self.path == "/step":
                self._json(SERVICE.engine._jsonable(SERVICE.engine.step()))
                return
            if self.path == "/run":
                count = int(body.get("count", 1))
                result = SERVICE.engine.run_steps(count)
                self._json({
                    "count": len(result),
                    "last": SERVICE.engine._jsonable(result[-1]),
                })
                return
            if self.path == "/flush":
                self._json({
                    "ingested_slice_ids": SERVICE.engine.flush_event_time(),
                })
                return
            if self.path == "/control":
                if "autorun" in body:
                    SERVICE.autorun = bool(body["autorun"])
                if "interval_seconds" in body:
                    SERVICE.interval = max(0.05, float(body["interval_seconds"]))
                self._json({
                    "autorun": SERVICE.autorun,
                    "interval_seconds": SERVICE.interval,
                })
                return
            self._json({"error": "not-found"}, status=HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(
                {"error": type(exc).__name__, "detail": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:
            SERVICE.last_error = f"{type(exc).__name__}: {exc}"
            self._json(
                {"error": type(exc).__name__, "detail": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )


def main() -> None:
    global SERVICE
    host = os.environ.get("LIVE_COGNITIVE_HOST", "127.0.0.1")
    port = int(os.environ.get("LIVE_COGNITIVE_PORT", "8090"))
    interval = float(os.environ.get("LIVE_COGNITIVE_STEP_SECONDS", "1.0"))
    autorun = os.environ.get("LIVE_COGNITIVE_AUTORUN", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }

    SERVICE = CognitiveService(
        ServerCognitiveEngine(),
        interval=interval,
        autorun=autorun,
    )
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(
        f"[server-cognitive] listening on http://{host}:{port} "
        f"autorun={autorun} interval={interval}s"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        SERVICE.stop()


if __name__ == "__main__":
    main()
