from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class RendererConfigError(ValueError):
    pass


@dataclass(frozen=True)
class HeadlessRendererConfig:
    project_dir: str = "/opt/live.infinita/apps/renderer-godot"
    godot_bin: str = "/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64"
    scene: str = ""
    display: str = ":99"
    width: int = 720
    height: int = 1280
    internal_width: int = 0
    internal_height: int = 0
    fps: int = 30
    godot_fps: int = 20
    minimum_godot_fps: int = 12
    cpu_governor_enabled: bool = False
    video_output: str = "udp://127.0.0.1:5600?pkt_size=1316"
    video_bitrate_kbps: int = 6000
    startup_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "HeadlessRendererConfig":
        return cls(
            project_dir=os.getenv("LIVE_INFINITA_RENDER_PROJECT", "/opt/live.infinita/apps/renderer-godot").strip(),
            godot_bin=os.getenv("LIVE_INFINITA_GODOT_BIN", "/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64").strip(),
            scene=os.getenv("LIVE_INFINITA_RENDER_SCENE", "").strip(),
            display=os.getenv("LIVE_INFINITA_RENDER_DISPLAY", ":99").strip(),
            width=int(os.getenv("LIVE_INFINITA_RENDER_WIDTH", "720")),
            height=int(os.getenv("LIVE_INFINITA_RENDER_HEIGHT", "1280")),
            internal_width=int(os.getenv("LIVE_INFINITA_RENDER_INTERNAL_WIDTH", "0")),
            internal_height=int(os.getenv("LIVE_INFINITA_RENDER_INTERNAL_HEIGHT", "0")),
            fps=int(os.getenv("LIVE_INFINITA_RENDER_FPS", "30")),
            godot_fps=int(os.getenv("LIVE_INFINITA_RENDER_GODOT_FPS", "20")),
            minimum_godot_fps=int(os.getenv("LIVE_INFINITA_RENDER_GODOT_MIN_FPS", "12")),
            cpu_governor_enabled=os.getenv("LIVE_INFINITA_RENDER_CPU_GOVERNOR", "0").strip().lower() in {"1", "true", "yes", "on"},
            video_output=os.getenv("LIVE_INFINITA_VIDEO_BUS", "udp://127.0.0.1:5600?pkt_size=1316").strip(),
            video_bitrate_kbps=int(os.getenv("LIVE_INFINITA_RENDER_BITRATE_KBPS", "6000")),
            startup_seconds=float(os.getenv("LIVE_INFINITA_RENDER_STARTUP_SECONDS", "2")),
        )

    @property
    def render_width(self) -> int:
        return self.internal_width if self.internal_width > 0 else self.width

    @property
    def render_height(self) -> int:
        return self.internal_height if self.internal_height > 0 else self.height

    def validate(self) -> None:
        if not self.project_dir:
            raise RendererConfigError("diretório do projeto Godot ausente")
        if not self.godot_bin:
            raise RendererConfigError("binário Godot ausente")
        if self.scene:
            if (
                not self.scene.startswith("res://")
                or not self.scene.endswith(".tscn")
                or ".." in self.scene
            ):
                raise RendererConfigError("cena Godot inválida")
        if not self.display.startswith(":"):
            raise RendererConfigError("display X11 inválido")
        if self.width < 320 or self.height < 240:
            raise RendererConfigError("resolução de saída inválida")
        if self.render_width < 320 or self.render_height < 240:
            raise RendererConfigError("resolução interna inválida")
        if self.render_width * self.height != self.render_height * self.width:
            raise RendererConfigError("resolução interna deve preservar a proporção da saída")
        if self.render_width > self.width or self.render_height > self.height:
            raise RendererConfigError("resolução interna não pode exceder a saída")
        if not 1 <= self.fps <= 60:
            raise RendererConfigError("FPS deve ficar entre 1 e 60")
        if not 8 <= self.minimum_godot_fps <= self.godot_fps <= 60:
            raise RendererConfigError("limites FPS Godot inválidos")
        if self.video_bitrate_kbps < 500:
            raise RendererConfigError("bitrate de vídeo muito baixo")
        if not self.video_output.startswith("udp://127.0.0.1:"):
            raise RendererConfigError("video bus deve ser UDP em loopback")

    def xvfb_command(self, xvfb_bin: str = "Xvfb") -> list[str]:
        self.validate()
        return [xvfb_bin, self.display, "-screen", "0", f"{self.render_width}x{self.render_height}x24", "-ac", "-nolisten", "tcp", "+extension", "GLX", "+render"]

    def godot_command(self) -> list[str]:
        self.validate()
        command = [
            self.godot_bin,
            "--path",
            self.project_dir,
            "--display-driver",
            "x11",
            "--resolution",
            f"{self.render_width}x{self.render_height}",
        ]
        if self.scene:
            command.append(self.scene)
        return command

    def capture_command(self, ffmpeg_bin: str = "ffmpeg") -> list[str]:
        self.validate()
        gop = self.fps * 2
        command = [
            ffmpeg_bin, "-hide_banner", "-loglevel", "warning", "-f", "x11grab", "-draw_mouse", "0",
            "-framerate", str(self.fps), "-video_size", f"{self.render_width}x{self.render_height}", "-i", f"{self.display}.0+0,0", "-an",
        ]
        if (self.render_width, self.render_height) != (self.width, self.height):
            command.extend([
                "-vf",
                f"scale={self.width}:{self.height}:flags=fast_bilinear",
            ])
        command.extend([
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-b:v", f"{self.video_bitrate_kbps}k",
            "-maxrate", f"{self.video_bitrate_kbps}k", "-bufsize", f"{self.video_bitrate_kbps}k", "-g", str(gop),
            "-keyint_min", str(gop), "-pix_fmt", "yuv420p", "-f", "mpegts", self.video_output,
        ])
        return command


class CpuPressureGovernor:
    """Bounded renderer-only FPS controller; never changes simulation-clock cadence."""

    def __init__(self, max_fps: int, min_fps: int, recovery_samples: int = 6) -> None:
        self.max_fps = max_fps
        self.min_fps = min_fps
        self.recovery_samples = recovery_samples
        self.current_fps = max_fps
        self.healthy_samples = 0

    @staticmethod
    def pressure_avg10(snapshot: str) -> float | None:
        for line in snapshot.splitlines():
            if not line.startswith("some "):
                continue
            match = re.search(r"(?:^|\s)avg10=([0-9]+(?:\.[0-9]+)?)", line)
            if match:
                return float(match.group(1))
        return None

    def update(self, cpu_pressure_avg10: float | None) -> int:
        if cpu_pressure_avg10 is None:
            return self.current_fps
        if cpu_pressure_avg10 >= 55.0:
            target = self.min_fps
        elif cpu_pressure_avg10 >= 30.0:
            target = max(self.min_fps, self.max_fps - 5)
        else:
            target = self.max_fps
        if target < self.current_fps:
            self.current_fps = target
            self.healthy_samples = 0
        elif target > self.current_fps:
            self.healthy_samples += 1
            if self.healthy_samples >= self.recovery_samples:
                self.current_fps = min(target, self.current_fps + 2)
                self.healthy_samples = 0
        else:
            self.healthy_samples = 0
        return self.current_fps


class HeadlessRenderer:
    def __init__(self, config: HeadlessRendererConfig) -> None:
        self.config = config
        self.processes: list[subprocess.Popen[bytes]] = []
        self.stop_requested = False
        self._fps_governor = CpuPressureGovernor(config.godot_fps, config.minimum_godot_fps)
        self._control_dir: tempfile.TemporaryDirectory[str] | None = None
        self._control_file: Path | None = None
        self._status_file = Path(os.getenv("LIVE_INFINITA_RENDER_STATUS_FILE", "/var/lib/live-infinita/render-runtime-status.json"))

    def _publish_fps(self, value: int) -> None:
        path = self._control_file
        if path is None:
            return
        temporary = path.with_suffix(".tmp")
        temporary.write_text(f"{value}\n", encoding="ascii")
        os.replace(temporary, path)

    def _start_governor(self, env: dict[str, str]) -> None:
        if not self.config.cpu_governor_enabled:
            return
        self._control_dir = tempfile.TemporaryDirectory(prefix="live-infinita-fps-")
        self._control_file = Path(self._control_dir.name) / "fps"
        self._publish_fps(self.config.godot_fps)
        env["LIVE_INFINITA_RENDER_CONTROL_FILE"] = str(self._control_file)

    def _publish_status(self, pressure: float | None) -> None:
        if not self.config.cpu_governor_enabled:
            return
        payload = {
            "updated_at_unix": time.time(),
            "godot_fps": self._fps_governor.current_fps,
            "capture_fps": self.config.fps,
            "render_width": self.config.render_width,
            "render_height": self.config.render_height,
            "output_width": self.config.width,
            "output_height": self.config.height,
            "governor_enabled": True,
            "cpu_pressure_avg10_pct": pressure,
            "scene": self.config.scene or "project-default",
        }
        try:
            self._status_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._status_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(self._status_file)
        except OSError as exc:
            print(f"[renderer] telemetry unavailable: {type(exc).__name__}", flush=True)

    def _poll_governor(self) -> None:
        if self._control_file is None:
            return
        try:
            snapshot = Path("/proc/pressure/cpu").read_text(encoding="ascii")
        except OSError:
            self._publish_status(None)
            return
        pressure = CpuPressureGovernor.pressure_avg10(snapshot)
        before = self._fps_governor.current_fps
        after = self._fps_governor.update(pressure)
        if after != before:
            self._publish_fps(after)
            print(f"[renderer] CPU pressure: Godot FPS {before} -> {after}", flush=True)
        self._publish_status(pressure)

    def _spawn(self, command: list[str], env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(command, env=env)
        self.processes.append(process)
        return process

    def stop(self) -> None:
        self.stop_requested = True
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 3.0
        for process in reversed(self.processes):
            if process.poll() is not None:
                continue
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes.clear()
        if self._control_dir is not None:
            self._control_dir.cleanup()
            self._control_dir = None
            self._control_file = None

    def run(self, xvfb_bin: str, ffmpeg_bin: str) -> int:
        self.config.validate()
        xvfb = self._spawn(self.config.xvfb_command(xvfb_bin))
        time.sleep(0.5)
        if xvfb.poll() is not None:
            return int(xvfb.returncode or 1)
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        self._start_governor(env)
        godot = self._spawn(self.config.godot_command(), env=env)
        time.sleep(max(0.0, self.config.startup_seconds))
        if godot.poll() is not None:
            return int(godot.returncode or 1)
        capture = self._spawn(self.config.capture_command(ffmpeg_bin), env=env)
        next_pressure_poll = 0.0
        while not self.stop_requested:
            now = time.monotonic()
            if now >= next_pressure_poll:
                self._poll_governor()
                next_pressure_poll = now + 10.0
            for process in (xvfb, godot, capture):
                code = process.poll()
                if code is not None:
                    return int(code or 1)
            time.sleep(0.5)
        return 0


def safe_commands(config: HeadlessRendererConfig, xvfb_bin: str, ffmpeg_bin: str) -> str:
    return "\n".join(shlex.join(command) for command in [config.xvfb_command(xvfb_bin), config.godot_command(), config.capture_command(ffmpeg_bin)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Infinita native Godot renderer on virtual X11 display")
    parser.add_argument("--dry-run", action="store_true", help="valida configuração e imprime processos sem iniciar")
    args = parser.parse_args(argv)
    xvfb_bin = shutil.which("Xvfb")
    ffmpeg_bin = shutil.which("ffmpeg")
    config = HeadlessRendererConfig.from_env()
    missing: list[str] = []
    if xvfb_bin is None: missing.append("Xvfb")
    if ffmpeg_bin is None: missing.append("ffmpeg")
    if not Path(config.godot_bin).is_file(): missing.append("Godot")
    if not Path(config.project_dir, "project.godot").is_file(): missing.append("renderer project")
    if config.scene:
        scene_relative = config.scene.removeprefix("res://")
        if not Path(config.project_dir, scene_relative).is_file():
            missing.append("renderer scene")
    if missing:
        print(f"[renderer] dependências ausentes: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        config.validate()
    except (RendererConfigError, ValueError) as exc:
        print(f"[renderer] configuração inválida: {exc}", file=sys.stderr)
        return 2
    assert xvfb_bin and ffmpeg_bin
    print("[renderer] pipeline:\n" + safe_commands(config, xvfb_bin, ffmpeg_bin), flush=True)
    if args.dry_run:
        return 0
    renderer = HeadlessRenderer(config)
    def request_stop(_signum: int, _frame: object) -> None:
        renderer.stop_requested = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        return renderer.run(xvfb_bin, ffmpeg_bin)
    finally:
        renderer.stop()


if __name__ == "__main__":
    raise SystemExit(main())
