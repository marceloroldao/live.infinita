from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import time
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE_BIN = Path(os.getenv(
    "LIVE_INFINITA_AUDIO_NATIVE_BIN",
    str(ROOT / "apps" / "audio-native" / "build" / "live-infinita-audio-native"),
))
NATIVE_AVAILABLE = NATIVE_BIN.is_file() and os.access(NATIVE_BIN, os.X_OK)

# Native DSP owns the realtime 48 kHz hot loop. If the binary is unavailable,
# retain the proven 16 kHz Python continuity fallback rather than returning to
# the expensive Python 48 kHz per-sample loop.
os.environ["LIVE_INFINITA_AUDIO_SAMPLE_RATE"] = "48000" if NATIVE_AVAILABLE else "16000"

import retro_audio
import server_audio


class StableRetroProgramAudio(retro_audio.RetroProgramAudio):
    """Python fallback mixer used only when the native engine is unavailable."""

    def __init__(self) -> None:
        super().__init__()
        self.audio_chunks = 0
        self.audio_deadline_misses = 0
        self.audio_ffmpeg_restarts = 0
        self.audio_last_chunk_render_ms = 0.0
        self.audio_max_chunk_render_ms = 0.0
        self.audio_max_late_ms = 0.0
        self.audio_voice_priority_chunks = 0

    def ambient_status(self) -> dict[str, object]:
        status = super().ambient_status()
        status["realtime_audio"] = {
            "engine": "python-fallback",
            "sample_rate": server_audio.SAMPLE_RATE,
            "chunk_frames": server_audio.CHUNK_FRAMES,
            "chunk_ms": round(server_audio.CHUNK_SECONDS * 1000.0, 2),
            "chunks": self.audio_chunks,
            "deadline_misses": self.audio_deadline_misses,
            "ffmpeg_restarts": self.audio_ffmpeg_restarts,
            "voice_priority_chunks": self.audio_voice_priority_chunks,
            "last_chunk_render_ms": round(self.audio_last_chunk_render_ms, 3),
            "max_chunk_render_ms": round(self.audio_max_chunk_render_ms, 3),
            "max_late_ms": round(self.audio_max_late_ms, 3),
            "narration_fast_path": True,
            "ambient_suspended_during_voice": True,
            "continuity_profile": "python-fallback-16k-to-48k",
        }
        return status

    def _run(self) -> None:
        next_deadline = time.monotonic()
        while not self.stop_event.is_set():
            if self.ffmpeg is None or self.ffmpeg.poll() is not None:
                try:
                    self.ffmpeg = self._start_ffmpeg()
                    self.audio_ffmpeg_restarts += 1
                except OSError:
                    time.sleep(2)
                    continue

            chunk_started = time.monotonic()
            output = array("h")
            voice_frames = 0
            for _ in range(server_audio.CHUNK_FRAMES):
                voice_l, voice_r, speaking = self._next_narration_sample()
                target_duck = (
                    server_audio.DUCKED_AMBIENT_VOLUME / max(server_audio.AMBIENT_VOLUME, 0.0001)
                    if speaking else 1.0
                )
                smoothing = 0.010 if speaking else 0.0017
                self.duck_gain += (target_duck - self.duck_gain) * smoothing
                if speaking:
                    ambient_l = ambient_r = 0
                    voice_frames += 1
                else:
                    ambient_l, ambient_r = self._ambient_sample(server_audio.AMBIENT_VOLUME * self.duck_gain)
                output.append(self._clip(ambient_l + voice_l))
                output.append(self._clip(ambient_r + voice_r))

            try:
                assert self.ffmpeg.stdin is not None
                self.ffmpeg.stdin.write(output.tobytes())
                self.ffmpeg.stdin.flush()
            except (BrokenPipeError, OSError):
                try:
                    self.ffmpeg.kill()
                except OSError:
                    pass
                self.ffmpeg = None
                self.audio_ffmpeg_restarts += 1
                time.sleep(0.25)
                next_deadline = time.monotonic()
                continue

            finished = time.monotonic()
            render_ms = (finished - chunk_started) * 1000.0
            self.audio_chunks += 1
            self.audio_last_chunk_render_ms = render_ms
            self.audio_max_chunk_render_ms = max(self.audio_max_chunk_render_ms, render_ms)
            if voice_frames:
                self.audio_voice_priority_chunks += 1
            if render_ms > server_audio.CHUNK_SECONDS * 1000.0:
                self.audio_deadline_misses += 1

            next_deadline += server_audio.CHUNK_SECONDS
            wait = next_deadline - finished
            if wait > 0:
                self.stop_event.wait(wait)
            else:
                late_ms = -wait * 1000.0
                self.audio_max_late_ms = max(self.audio_max_late_ms, late_ms)
                if late_ms >= server_audio.CHUNK_SECONDS * 1000.0:
                    self.audio_deadline_misses += 1
                if wait < -0.25:
                    next_deadline = time.monotonic()

            if self.audio_chunks % 250 == 0:
                print(
                    "[audio] realtime "
                    f"engine=python-fallback chunks={self.audio_chunks} misses={self.audio_deadline_misses} "
                    f"sample_rate={server_audio.SAMPLE_RATE} chunk_ms={server_audio.CHUNK_SECONDS * 1000.0:.1f} "
                    f"last_ms={self.audio_last_chunk_render_ms:.2f} max_ms={self.audio_max_chunk_render_ms:.2f} "
                    f"late_ms={self.audio_max_late_ms:.2f} voice_chunks={self.audio_voice_priority_chunks}",
                    flush=True,
                )


class NativeProgramAudio:
    """Python control plane for the native C++ realtime audio engine.

    World State and Piper remain in Python. The C++ child owns continuous 48 kHz
    synthesis/mixing, ducking, clipping and the FFmpeg UDP feed. Control updates
    cross a Unix datagram socket only when state changes or a complete narration
    PCM file is ready; no Python call occurs in the per-sample hot path.
    """

    def __init__(self) -> None:
        self.state_model = retro_audio.RetroProgramAudio()
        self.process: subprocess.Popen[bytes] | None = None
        self.fallback: StableRetroProgramAudio | None = None
        self.socket_path = Path(os.getenv(
            "LIVE_INFINITA_AUDIO_NATIVE_SOCKET",
            str(server_audio.AUDIO_DIR / "native.sock"),
        ))
        self.metrics_path = Path(os.getenv(
            "LIVE_INFINITA_AUDIO_NATIVE_METRICS",
            str(server_audio.AUDIO_DIR / "native-metrics.txt"),
        ))
        self.voice_dir = server_audio.AUDIO_DIR / "native-voice"

    def _send(self, message: str) -> bool:
        if self.fallback is not None:
            return False
        for _ in range(4):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                    client.sendto(message.encode("utf-8"), str(self.socket_path))
                return True
            except OSError:
                time.sleep(0.025)
        return False

    def start(self) -> None:
        if not NATIVE_AVAILABLE:
            self._start_fallback("binary unavailable")
            return
        server_audio.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        self.metrics_path.unlink(missing_ok=True)
        command = [
            str(NATIVE_BIN),
            "--socket", str(self.socket_path),
            "--metrics", str(self.metrics_path),
            "--udp-output", server_audio.UDP_OUTPUT,
            "--ambient", str(server_audio.AMBIENT_VOLUME),
            "--ducked", str(server_audio.DUCKED_AMBIENT_VOLUME),
            "--narration", str(server_audio.NARRATION_VOLUME),
        ]
        try:
            self.process = subprocess.Popen(command)
        except OSError as exc:
            self._start_fallback(type(exc).__name__)
            return
        for _ in range(100):
            if self.socket_path.exists() and self.process.poll() is None:
                print(f"[audio] native C++ mixer ativo pid={self.process.pid} sample_rate=48000 chunk_ms=20", flush=True)
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self._start_fallback("native startup failed")

    def _start_fallback(self, reason: str) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self.fallback = StableRetroProgramAudio()
        self.fallback.start()
        print(f"[audio] native indisponível ({reason}); usando mixer Python fallback", flush=True)

    def stop(self) -> None:
        if self.fallback is not None:
            self.fallback.stop()
            return
        self._send("STOP")
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        self.socket_path.unlink(missing_ok=True)

    def update_world(self, world: dict) -> server_audio.WorldAudioState:
        if self.fallback is not None:
            return self.fallback.update_world(world)
        state = self.state_model.update_world(world)
        distance = state.fire_distance if state.fire_distance is not None else 999.0
        message = "|".join([
            "STATE",
            state.biome.replace("|", ""),
            state.period.replace("|", ""),
            state.weather.replace("|", ""),
            "1" if state.fire_lit else "0",
            f"{distance:.3f}",
            "1" if state.walking else "0",
        ])
        self._send(message)
        return state

    def enqueue_pcm(self, pcm_bytes: bytes) -> None:
        if self.fallback is not None:
            self.fallback.enqueue_pcm(pcm_bytes)
            return
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        target = self.voice_dir / f"voice-{time.time_ns()}.pcm"
        target.write_bytes(pcm_bytes)
        if not self._send(f"VOICE|{target}"):
            target.unlink(missing_ok=True)
            raise OSError("native audio control socket unavailable")

    def _native_metrics(self) -> dict[str, object]:
        values: dict[str, object] = {}
        try:
            for line in self.metrics_path.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if not sep:
                    continue
                if key in {"engine"}:
                    values[key] = value
                elif key in {"render_avg_ms", "render_max_ms", "max_late_ms", "chunk_ms"}:
                    values[key] = float(value)
                elif key == "voice_active":
                    values[key] = value == "1"
                else:
                    values[key] = int(value)
        except (OSError, ValueError):
            pass
        return values

    def ambient_status(self) -> dict[str, object]:
        if self.fallback is not None:
            return self.fallback.ambient_status()
        status = self.state_model.ambient_status()
        metrics = {
            "engine": "cpp-native",
            "sample_rate": 48000,
            "chunk_frames": 960,
            "chunk_ms": 20.0,
            "native_process_alive": bool(self.process and self.process.poll() is None),
            "narration_fast_path": True,
            "ambient_suspended_during_voice": True,
            "control_transport": "unix-datagram",
            "voice_transport": "pcm-file-handoff",
            "continuity_profile": "native-48k-realtime",
            **self._native_metrics(),
        }
        status["realtime_audio"] = metrics
        status["ambient_provider"] = "native-cpp-world-reactive"
        return status


async def main() -> None:
    server_audio.ProgramAudio = NativeProgramAudio if NATIVE_AVAILABLE else StableRetroProgramAudio  # type: ignore[assignment]
    server_audio.NarrationService = retro_audio.InteractionNarrationService  # type: ignore[assignment]
    await server_audio.main()


if __name__ == "__main__":
    asyncio.run(main())
