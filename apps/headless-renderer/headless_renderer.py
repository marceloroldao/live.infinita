from __future__ import annotations

import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


class RendererConfigError(ValueError):
    pass


@dataclass(frozen=True)
class HeadlessRendererConfig:
    project_dir: str = "/opt/live.infinita/apps/renderer-godot"
    godot_bin: str = "/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64"
    display: str = ":99"
    width: int = 720
    height: int = 1280
    fps: int = 30
    video_output: str = "udp://127.0.0.1:5600?pkt_size=1316"
    video_bitrate_kbps: int = 6000
    startup_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "HeadlessRendererConfig":
        return cls(
            project_dir=os.getenv("LIVE_INFINITA_RENDER_PROJECT", "/opt/live.infinita/apps/renderer-godot").strip(),
            godot_bin=os.getenv("LIVE_INFINITA_GODOT_BIN", "/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64").strip(),
            display=os.getenv("LIVE_INFINITA_RENDER_DISPLAY", ":99").strip(),
            width=int(os.getenv("LIVE_INFINITA_RENDER_WIDTH", "720")),
            height=int(os.getenv("LIVE_INFINITA_RENDER_HEIGHT", "1280")),
            fps=int(os.getenv("LIVE_INFINITA_RENDER_FPS", "30")),
            video_output=os.getenv("LIVE_INFINITA_VIDEO_BUS", "udp://127.0.0.1:5600?pkt_size=1316").strip(),
            video_bitrate_kbps=int(os.getenv("LIVE_INFINITA_RENDER_BITRATE_KBPS", "6000")),
            startup_seconds=float(os.getenv("LIVE_INFINITA_RENDER_STARTUP_SECONDS", "2")),
        )

    def validate(self) -> None:
        if not self.project_dir:
            raise RendererConfigError("diretório do projeto Godot ausente")
        if not self.godot_bin:
            raise RendererConfigError("binário Godot ausente")
        if not self.display.startswith(":"):
            raise RendererConfigError("display X11 inválido")
        if self.width < 320 or self.height < 240:
            raise RendererConfigError("resolução inválida")
        if not 1 <= self.fps <= 60:
            raise RendererConfigError("FPS deve ficar entre 1 e 60")
        if self.video_bitrate_kbps < 500:
            raise RendererConfigError("bitrate de vídeo muito baixo")
        if not self.video_output.startswith("udp://127.0.0.1:"):
            raise RendererConfigError("video bus deve ser UDP em loopback")

    def xvfb_command(self, xvfb_bin: str = "Xvfb") -> list[str]:
        self.validate()
        return [xvfb_bin, self.display, "-screen", "0", f"{self.width}x{self.height}x24", "-ac", "-nolisten", "tcp", "+extension", "GLX", "+render"]

    def godot_command(self) -> list[str]:
        self.validate()
        return [self.godot_bin, "--path", self.project_dir, "--display-driver", "x11", "--resolution", f"{self.width}x{self.height}"]

    def capture_command(self, ffmpeg_bin: str = "ffmpeg") -> list[str]:
        self.validate()
        gop = self.fps * 2
        return [
            ffmpeg_bin, "-hide_banner", "-loglevel", "warning", "-f", "x11grab", "-draw_mouse", "0",
            "-framerate", str(self.fps), "-video_size", f"{self.width}x{self.height}", "-i", f"{self.display}.0+0,0", "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-b:v", f"{self.video_bitrate_kbps}k",
            "-maxrate", f"{self.video_bitrate_kbps}k", "-bufsize", f"{self.video_bitrate_kbps}k", "-g", str(gop),
            "-keyint_min", str(gop), "-pix_fmt", "yuv420p", "-f", "mpegts", self.video_output,
        ]


class HeadlessRenderer:
    def __init__(self, config: HeadlessRendererConfig) -> None:
        self.config = config
        self.processes: list[subprocess.Popen[bytes]] = []
        self.stop_requested = False

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

    def run(self, xvfb_bin: str, ffmpeg_bin: str) -> int:
        self.config.validate()
        xvfb = self._spawn(self.config.xvfb_command(xvfb_bin))
        time.sleep(0.5)
        if xvfb.poll() is not None:
            return int(xvfb.returncode or 1)
        env = os.environ.copy()
        env["DISPLAY"] = self.config.display
        godot = self._spawn(self.config.godot_command(), env=env)
        time.sleep(max(0.0, self.config.startup_seconds))
        if godot.poll() is not None:
            return int(godot.returncode or 1)
        capture = self._spawn(self.config.capture_command(ffmpeg_bin), env=env)
        while not self.stop_requested:
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
