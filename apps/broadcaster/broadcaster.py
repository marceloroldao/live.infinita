from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class BroadcasterConfigError(ValueError):
    pass


def redact_url(value: str) -> str:
    """Redact path/query credentials while preserving enough destination context for logs."""
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
    width: int = 1280
    height: int = 720
    fps: int = 30
    video_bitrate_kbps: int = 3500
    audio_bitrate_kbps: int = 128
    keyframe_seconds: int = 2

    @classmethod
    def from_env(cls) -> "BroadcasterConfig":
        video_input = os.getenv(
            "LIVE_INFINITA_VIDEO_INPUT",
            "udp://127.0.0.1:5600?fifo_size=2000000&overrun_nonfatal=1",
        ).strip()
        audio_input = os.getenv(
            "LIVE_INFINITA_AUDIO_INPUT",
            "udp://127.0.0.1:5500?fifo_size=1000000&overrun_nonfatal=1",
        ).strip()
        output_url = os.getenv("LIVE_INFINITA_STREAM_OUTPUT", "").strip()
        return cls(
            video_input=video_input,
            audio_input=audio_input,
            output_url=output_url,
            width=int(os.getenv("LIVE_INFINITA_STREAM_WIDTH", "1280")),
            height=int(os.getenv("LIVE_INFINITA_STREAM_HEIGHT", "720")),
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

    def command(self, include_output: bool = True) -> list[str]:
        self.validate(require_output=include_output)
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
        if include_output:
            cmd.extend(["-f", "flv", self.output_url])
        else:
            cmd.extend(["-f", "null", "-"])
        return cmd

    def safe_command_text(self, include_output: bool = True) -> str:
        command = self.command(include_output=include_output)
        if include_output and self.output_url:
            command[-1] = redact_url(self.output_url)
        return shlex.join(command)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Infinita provider-neutral broadcaster")
    parser.add_argument("--dry-run", action="store_true", help="valida configuração e imprime comando sem transmitir")
    parser.add_argument("--probe", action="store_true", help="valida inputs com saída descartada; não transmite")
    args = parser.parse_args(argv)

    if shutil.which("ffmpeg") is None:
        print("[broadcaster] ffmpeg não encontrado", file=sys.stderr)
        return 2

    config = BroadcasterConfig.from_env()
    try:
        if args.probe:
            command = config.command(include_output=False)
        else:
            command = config.command(include_output=True)
    except (BroadcasterConfigError, ValueError) as exc:
        print(f"[broadcaster] configuração inválida: {exc}", file=sys.stderr)
        return 2

    print(f"[broadcaster] {config.safe_command_text(include_output=not args.probe)}", flush=True)
    if args.dry_run:
        return 0

    result = subprocess.run(command, check=False)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
