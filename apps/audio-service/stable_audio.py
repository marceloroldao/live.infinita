from __future__ import annotations

import asyncio
import os
import subprocess
import time
from array import array

# The procedural mixer is intentionally rendered at 24 kHz and resampled by the
# downstream relays to 48 kHz. Speech and the current ambience contain no useful
# energy near the 12 kHz Nyquist limit, while halving the Python sample workload
# gives the realtime loop substantially more scheduling headroom.
os.environ.setdefault("LIVE_INFINITA_AUDIO_SAMPLE_RATE", "24000")

import retro_audio
import server_audio


class StableRetroProgramAudio(retro_audio.RetroProgramAudio):
    """Retro program audio with a speech-priority realtime mixer.

    The original mixer evaluates every procedural ambience layer for every PCM
    frame, even while narration is active. On a shared server that can miss its
    20/40 ms delivery deadline and starve the local UDP transport. Narration is
    more important than decorative ambience, so this mixer suspends expensive
    procedural synthesis while voice PCM is active and exposes deadline metrics
    for the Manager diagnostic report.
    """

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
                    # Voice is already a complete decoded PCM stream. Do not spend
                    # the narration deadline synthesizing decorative ambience.
                    ambient_l = 0
                    ambient_r = 0
                    voice_frames += 1
                else:
                    ambient_l, ambient_r = self._ambient_sample(
                        server_audio.AMBIENT_VOLUME * self.duck_gain
                    )

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

            # This line is intentionally sparse (~10 s at the production 40 ms
            # chunk). It becomes visible in Manager -> Relatório without flooding
            # journalctl and lets us distinguish TTS quality from transport xruns.
            if self.audio_chunks % 250 == 0:
                print(
                    "[audio] realtime "
                    f"chunks={self.audio_chunks} misses={self.audio_deadline_misses} "
                    f"last_ms={self.audio_last_chunk_render_ms:.2f} "
                    f"max_ms={self.audio_max_chunk_render_ms:.2f} "
                    f"late_ms={self.audio_max_late_ms:.2f} "
                    f"voice_chunks={self.audio_voice_priority_chunks}",
                    flush=True,
                )


async def main() -> None:
    server_audio.ProgramAudio = StableRetroProgramAudio  # type: ignore[assignment]
    server_audio.NarrationService = retro_audio.InteractionNarrationService  # type: ignore[assignment]
    await server_audio.main()


if __name__ == "__main__":
    asyncio.run(main())
