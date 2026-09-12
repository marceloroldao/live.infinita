from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GODOT_BIN = Path("/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def source_checks(root: Path = ROOT) -> list[Check]:
    required = [
        "apps/world-runtime/main.py",
        "apps/audio-service/server_audio.py",
        "apps/audio-web-bridge/audio_web_bridge.py",
        "apps/headless-renderer/headless_renderer.py",
        "apps/broadcaster/broadcaster.py",
        "apps/renderer-godot/project.godot",
        "apps/renderer-godot/main.tscn",
        "apps/renderer-godot/main.gd",
        "deploy/install-server-audio.sh",
        "deploy/install-browser-audio.sh",
        "deploy/install-headless-renderer.sh",
        "deploy/prepare-broadcaster.sh",
        "deploy/nginx_audio_patch.py",
        "deploy/install-godot-web.sh",
        "deploy/install-live-showcase.sh",
        "deploy/live-infinita-audio.service",
        "deploy/live-infinita-audio-web.service",
        "deploy/live-infinita-renderer.service",
        "deploy/live-infinita-broadcaster.service",
    ]
    checks = [
        Check(f"source:{path}", (root / path).is_file(), "arquivo obrigatório")
        for path in required
    ]

    project = root / "apps/renderer-godot/project.godot"
    if project.is_file():
        text = project.read_text(encoding="utf-8")
        checks.append(Check("godot:main_scene", 'run/main_scene="res://main.tscn"' in text, "main.tscn configurada"))

    showcase = root / "deploy/install-live-showcase.sh"
    if showcase.is_file():
        text = showcase.read_text(encoding="utf-8")
        checks.extend([
            Check("installer:server-audio", "install-server-audio.sh" in text, "Server Audio integrado"),
            Check("installer:browser-audio", "install-browser-audio.sh" in text, "Browser Audio integrado"),
            Check("installer:renderer", "install-headless-renderer.sh" in text, "renderer nativo integrado"),
            Check("installer:broadcaster-safe", "prepare-broadcaster.sh" in text and "Broadcaster não deveria estar ativo" in text, "Broadcaster preparado sem auto-start"),
            Check("installer:replay", "/api/replay/verify" in text, "replay verificado"),
        ])

    renderer = root / "apps/headless-renderer/headless_renderer.py"
    if renderer.is_file():
        text = renderer.read_text(encoding="utf-8")
        checks.extend([
            Check("renderer:xvfb", "x11grab" in text and "Xvfb" in text, "captura por framebuffer virtual"),
            Check("renderer:godot-native", "--display-driver" in text and "x11" in text, "Godot nativo no X11"),
            Check("renderer:video-bus", "udp://127.0.0.1:5600" in text, "bus de vídeo local"),
        ])

    broadcaster = root / "apps/broadcaster/broadcaster.py"
    if broadcaster.is_file():
        text = broadcaster.read_text(encoding="utf-8")
        checks.extend([
            Check("broadcaster:dry-run", "--dry-run" in text, "modo seguro sem transmissão"),
            Check("broadcaster:redaction", "redact_url" in text, "stream key mascarada em logs"),
            Check("broadcaster:audio-bus", "udp://127.0.0.1:5500" in text, "bus de áudio local"),
            Check("broadcaster:video-bus", "udp://127.0.0.1:5600" in text, "bus de vídeo local"),
        ])
    return checks


def _command_check(command: str) -> Check:
    resolved = shutil.which(command)
    return Check(f"host:command:{command}", resolved is not None, resolved or "não encontrado")


def _path_check(name: str, path: Path, executable: bool = False) -> Check:
    ok = path.is_file() and (not executable or bool(path.stat().st_mode & 0o111))
    return Check(name, ok, str(path))


def _service_check(service: str) -> Check:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(f"host:service:{service}", False, type(exc).__name__)
    detail = (result.stdout or result.stderr).strip() or f"exit={result.returncode}"
    return Check(f"host:service:{service}", result.returncode == 0, detail)


def _service_inactive_check(service: str) -> Check:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(f"host:service-inactive:{service}", False, type(exc).__name__)
    detail = (result.stdout or result.stderr).strip() or f"exit={result.returncode}"
    return Check(f"host:service-inactive:{service}", result.returncode != 0, detail)


def _json_endpoint(name: str, url: str, required_key: str) -> Check:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return Check(name, False, type(exc).__name__)
    ok = bool(payload.get(required_key)) if isinstance(payload, dict) else False
    return Check(name, ok, f"{required_key}={payload.get(required_key)!r}" if isinstance(payload, dict) else "JSON inválido")


def host_checks() -> list[Check]:
    checks = [_command_check(cmd) for cmd in ("python3", "ffmpeg", "nginx", "curl", "systemctl", "Xvfb")]
    checks.extend([
        _path_check("host:godot-native", GODOT_BIN, executable=True),
        _service_check("live-infinita.service"),
        _service_check("live-infinita-audio.service"),
        _service_check("live-infinita-audio-web.service"),
        _service_check("live-infinita-renderer.service"),
        _service_inactive_check("live-infinita-broadcaster.service"),
        _json_endpoint("host:runtime-health", "http://127.0.0.1:8080/api/health", "ok"),
        _json_endpoint("host:replay", "http://127.0.0.1:8080/api/replay/verify", "ok"),
        _json_endpoint("host:audio-web-health", "http://127.0.0.1:8092/health", "ok"),
    ])
    return checks


def render(checks: list[Check]) -> int:
    failed = 0
    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
        if not check.ok:
            failed += 1
    print(f"\nResumo: {len(checks) - failed}/{len(checks)} checks aprovados")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight somente leitura do Live Infinita Showcase")
    parser.add_argument("--host", action="store_true", help="inclui checks da VM, serviços e endpoints locais")
    args = parser.parse_args(argv)
    checks = source_checks()
    if args.host:
        checks.extend(host_checks())
    return render(checks)


if __name__ == "__main__":
    raise SystemExit(main())
