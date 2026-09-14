from __future__ import annotations

import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 8091
SERVICES = {
    "tiktok": "live-infinita-tiktok.service",
    "audio": "live-infinita-audio.service",
}
MAX_LINES = 300
REDACTIONS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "sk-***REDACTED***"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{12,}"), r"\1***REDACTED***"),
    (re.compile(r"(?i)((?:api[_-]?key|token|secret|sessionid|sign[_-]?api[_-]?key)\s*[=:]\s*)[^\s,;]+"), r"\1***REDACTED***"),
]


def sanitize(text: str) -> str:
    value = text
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def read_logs(service: str, lines: int) -> dict:
    unit = SERVICES[service]
    count = max(20, min(lines, MAX_LINES))
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(count), "--no-pager", "--output=short-iso", "--quiet"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "service": service, "unit": unit, "lines": [], "error": type(exc).__name__}
    stdout = sanitize(result.stdout)
    stderr = sanitize(result.stderr.strip())
    records = stdout.splitlines()[-count:] if stdout else []
    return {"ok": result.returncode == 0, "service": service, "unit": unit, "lines": records,
            "error": None if result.returncode == 0 else (stderr or f"journalctl exit={result.returncode}")}


class Handler(BaseHTTPRequestHandler):
    server_version = "LiveInfinitaOpsLogs/1.1"
    def log_message(self, _format: str, *_args) -> None: return
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(body)
    def do_GET(self) -> None:
        parsed = urlparse(self.path); prefix = "/api/ops/logs/"
        if not parsed.path.startswith(prefix): self._json(404, {"ok": False, "error": "not_found"}); return
        service = parsed.path[len(prefix):].strip("/")
        if service not in SERVICES: self._json(404, {"ok": False, "error": "service_not_allowed"}); return
        try: lines = int(parse_qs(parsed.query).get("lines", ["140"])[0])
        except ValueError: lines = 140
        self._json(200, read_logs(service, lines))


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
