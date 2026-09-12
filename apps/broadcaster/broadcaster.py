from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class BroadcasterConfigError(ValueError):
    pass


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted>"
    if not parts.scheme:
        return "<redacted>"
    path = parts.path
    if path and path != "/":
        segments = path.rstrip("/").split("/")
        if segments:
            segments[-1] = "***"
            path = "/".join(segments)
    query = "***" if parts.query else ""
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


@dataclass(frozen=True)
class BroadcasterConfig:
    video_input: str
    audio_input: str
    output_url: str
    width: int = 720
    height: int = 1280
    fps: int = 30
    video_bitrate_kbps: int = 3500
    audio_bitrate_kbps: int = 128
    keyframe_seconds: int = 2

    @classmethod
    def from_env(cls) -> "BroadcasterConfig":
        return cls(
            video_input=os.getenv("LIVE_INFINITA_VIDEO_INPUT", "udp://127.0.0.1:5600?fifo_size=2000000&overrun_nonfatal=1").strip(),
            audio_input=os.getenv("LIVE_INFINITA_AUDIO_INPUT", "udp://127.0.0.1:5500?fifo_size=1000000&overrun_nonfatal=1").strip(),
            output_url=os.getenv("LIVE_INFINITA_STREAM_OUTPUT", "").strip(),
            width=int(os.getenv("LIVE_INFINITA_STREAM_WIDTH", "720")),
            height=int(os.getenv("LIVE_INFINITA_STREAM_HEIGHT", "1280")),
            fps=int(os.getenv("LIVE_INFINITA_STREAM_FPS", "30")),
            video_bitrate_kbps=int(os.getenv("LIVE_INFINITA_VIDEO_BITRATE_KBPS", "3500")),
            audio_bitrate_kbps=int(os.getenv("LIVE_INFINITA_AUDIO_BITRATE_KBPS", "128")),
            keyframe_seconds=int(os.getenv("LIVE_INFINITA_KEYFRAME_SECONDS", "2")),
        )

    def validate(self, require_output: bool = True) -> None:
        if not self.video_input:
            raise BroadcasterConfigError("LIVE_INFINITA_VIDEO_INPUT não configurado")
        if not self.audio_input:
            raise BroadcasterConfigError("LIVE_INFINITA_AUDIO_INPUT não configurado")
        if require_output and not self.output_url:
            raise BroadcasterConfigError("LIVE_INFINITA_STREAM_OUTPUT não configurado")
        if self.width < 320 or self.height < 240:
            raise BroadcasterConfigError("resolução inválida")
        if not 1 <= self.fps <= 60:
            raise BroadcasterConfigError("FPS deve ficar entre 1 e 60")
        if self.video_bitrate_kbps < 250:
            raise BroadcasterConfigError("bitrate de vídeo muito baixo")
        if self.audio_bitrate_kbps < 32:
            raise BroadcasterConfigError("bitrate de áudio muito baixo")
        if not 1 <= self.keyframe_seconds <= 10:
            raise BroadcasterConfigError("intervalo de keyframe inválido")

    def command(self, include_output: bool = True, duration_seconds: float | None = None) -> list[str]:
        self.validate(require_output=include_output)
        if duration_seconds is not None and duration_seconds <= 0:
            raise BroadcasterConfigError("duração de probe deve ser positiva")
        gop = self.fps * self.keyframe_seconds
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-thread_queue_size", "1024", "-fflags", "+genpts+nobuffer", "-i", self.video_input,
            "-thread_queue_size", "1024", "-fflags", "+genpts+nobuffer", "-i", self.audio_input,
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2",
            "-r", str(self.fps),
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", f"{self.video_bitrate_kbps}k", "-maxrate", f"{self.video_bitrate_kbps}k",
            "-bufsize", f"{self.video_bitrate_kbps * 2}k", "-g", str(gop), "-keyint_min", str(gop),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", f"{self.audio_bitrate_kbps}k", "-ar", "48000", "-ac", "2",
            "-shortest",
        ]
        if duration_seconds is not None:
            cmd.extend(["-t", f"{duration_seconds:g}"])
        if include_output:
            cmd.extend(["-f", "flv", self.output_url])
        else:
            cmd.extend(["-f", "null", "-"])
        return cmd

    def safe_command_text(self, include_output: bool = True, duration_seconds: float | None = None) -> str:
        command = self.command(include_output=include_output, duration_seconds=duration_seconds)
        if include_output and self.output_url:
            command[-1] = redact_url(self.output_url)
        return shlex.join(command)


def status_path() -> Path:
    return Path(os.getenv("LIVE_INFINITA_BROADCAST_STATUS", "/var/lib/live-infinita/broadcaster-status.json"))


def write_status(state: str, config: BroadcasterConfig, *, mode: str, pid: int | None = None, returncode: int | None = None, detail: str | None = None) -> None:
    path = status_path()
    payload = {
        "state": state,
        "mode": mode,
        "updated_at_unix": time.time(),
        "pid": pid,
        "returncode": returncode,
        "detail": detail,
        "video": {"width": config.width, "height": config.height, "fps": config.fps, "bitrate_kbps": config.video_bitrate_kbps},
        "audio": {"bitrate_kbps": config.audio_bitrate_kbps, "sample_rate": 48000, "channels": 2},
        "destination": redact_url(config.output_url) if config.output_url else None,
        "output_configured": bool(config.output_url),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Infinita provider-neutral broadcaster")
    parser.add_argument("--dry-run", action="store_true", help="valida configuração e imprime comando sem transmitir")
    parser.add_argument("--probe", action="store_true", help="valida inputs com saída descartada; não transmite")
    parser.add_argument("--probe-seconds", type=float, default=5.0, help="duração do probe local (padrão: 5s)")
    args = parser.parse_args(argv)

    if shutil.which("ffmpeg") is None:
        print("[broadcaster] ffmpeg não encontrado", file=sys.stderr)
        return 2

    config = BroadcasterConfig.from_env()
    duration = args.probe_seconds if args.probe else None
    mode = "probe" if args.probe else "live"
    try:
        command = config.command(include_output=not args.probe, duration_seconds=duration)
    except (BroadcasterConfigError, ValueError) as exc:
        print(f"[broadcaster] configuração inválida: {exc}", file=sys.stderr)
        return 2

    print(f"[broadcaster] {config.safe_command_text(include_output=not args.probe, duration_seconds=duration)}", flush=True)
    if args.dry_run:
        return 0

    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(command)
        write_status("probing" if args.probe else "live", config, mode=mode, pid=process.pid)
        while True:
            code = process.poll()
            if code is not None:
                final_state = "probe_ok" if args.probe and code == 0 else ("stopped" if code == 0 else "error")
                write_status(final_state, config, mode=mode, pid=process.pid, returncode=int(code))
                return int(code)
            write_status("probing" if args.probe else "live", config, mode=mode, pid=process.pid)
            time.sleep(1.0)
    except KeyboardInterrupt:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        write_status("stopped", config, mode=mode, pid=process.pid if process else None, detail="interrompido pelo operador")
        return 130
    except Exception as exc:
        write_status("error", config, mode=mode, pid=process.pid if process else None, detail=type(exc).__name__)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
