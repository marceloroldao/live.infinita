from __future__ import annotations

import asyncio
import json
import math
import os
import random
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from array import array
from collections import deque
from pathlib import Path
from typing import Any

import websockets

SAMPLE_RATE = int(os.getenv("LIVE_INFINITA_AUDIO_SAMPLE_RATE", "48000"))
CHANNELS = 2
CHUNK_FRAMES = 960  # 20 ms at 48 kHz
UDP_OUTPUT = os.getenv("LIVE_INFINITA_AUDIO_UDP", "udp://127.0.0.1:5500?pkt_size=1316")
WORLD_WS = os.getenv("LIVE_INFINITA_WORLD_WS", "ws://127.0.0.1:8080/ws")
DATA_DIR = Path(os.getenv("LIVE_INFINITA_DATA_DIR", "/var/lib/live-infinita"))
INTEGRATIONS_FILE = DATA_DIR / "integrations.json"
AUDIO_DIR = DATA_DIR / "audio"
TTS_DIR = AUDIO_DIR / "tts"
STATUS_FILE = AUDIO_DIR / "status.json"
EVENT_LOG = AUDIO_DIR / "narration-events.jsonl"
TTS_MODEL = os.getenv("LIVE_INFINITA_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("LIVE_INFINITA_TTS_VOICE", "alloy")
TTS_INSTRUCTIONS = os.getenv(
    "LIVE_INFINITA_TTS_INSTRUCTIONS",
    "Fale em português brasileiro, como um narrador calmo, cinematográfico e natural."
)
AMBIENT_VOLUME = float(os.getenv("LIVE_INFINITA_AMBIENT_VOLUME", "0.075"))
DUCKED_AMBIENT_VOLUME = float(os.getenv("LIVE_INFINITA_DUCKED_AMBIENT_VOLUME", "0.025"))
NARRATION_VOLUME = float(os.getenv("LIVE_INFINITA_NARRATION_VOLUME", "0.95"))


class ProgramAudio:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.narration_queue: deque[array] = deque()
        self.queue_lock = threading.Lock()
        self.current: array | None = None
        self.current_offset = 0
        self.ffmpeg: subprocess.Popen[bytes] | None = None
        self.phase_a = 0.0
        self.phase_b = 0.0
        self.filtered_noise = 0.0
        self.thread = threading.Thread(target=self._run, name="program-audio", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=4)
        if self.ffmpeg and self.ffmpeg.poll() is None:
            self.ffmpeg.terminate()
            try:
                self.ffmpeg.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.ffmpeg.kill()

    def enqueue_pcm(self, pcm_bytes: bytes) -> None:
        samples = array("h")
        samples.frombytes(pcm_bytes)
        with self.queue_lock:
            self.narration_queue.append(samples)

    def _start_ffmpeg(self) -> subprocess.Popen[bytes]:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-c:a", "aac", "-b:a", "128k", "-f", "mpegts", UDP_OUTPUT,
        ]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def _next_narration_sample(self) -> tuple[int, int, bool]:
        if self.current is None:
            with self.queue_lock:
                if self.narration_queue:
                    self.current = self.narration_queue.popleft()
                    self.current_offset = 0
        if self.current is None:
            return 0, 0, False
        if self.current_offset + 1 >= len(self.current):
            self.current = None
            self.current_offset = 0
            return 0, 0, False
        left = int(self.current[self.current_offset] * NARRATION_VOLUME)
        right = int(self.current[self.current_offset + 1] * NARRATION_VOLUME)
        self.current_offset += 2
        if self.current_offset >= len(self.current):
            self.current = None
            self.current_offset = 0
        return left, right, True

    @staticmethod
    def _clip(value: int) -> int:
        return max(-32768, min(32767, value))

    def _ambient_sample(self, volume: float) -> int:
        # A subtle procedural bed: two slow tones plus low-pass noise.
        self.phase_a += 2 * math.pi * 73.0 / SAMPLE_RATE
        self.phase_b += 2 * math.pi * 109.0 / SAMPLE_RATE
        if self.phase_a > 2 * math.pi:
            self.phase_a -= 2 * math.pi
        if self.phase_b > 2 * math.pi:
            self.phase_b -= 2 * math.pi
        raw_noise = random.uniform(-1.0, 1.0)
        self.filtered_noise = (self.filtered_noise * 0.997) + (raw_noise * 0.003)
        signal_value = (
            math.sin(self.phase_a) * 0.24
            + math.sin(self.phase_b) * 0.16
            + self.filtered_noise * 0.55
        )
        return int(signal_value * 32767 * volume)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            if self.ffmpeg is None or self.ffmpeg.poll() is not None:
                try:
                    self.ffmpeg = self._start_ffmpeg()
                except OSError:
                    time.sleep(2)
                    continue
            output = array("h")
            for _ in range(CHUNK_FRAMES):
                voice_l, voice_r, speaking = self._next_narration_sample()
                ambient_volume = DUCKED_AMBIENT_VOLUME if speaking else AMBIENT_VOLUME
                ambient = self._ambient_sample(ambient_volume)
                output.append(self._clip(ambient + voice_l))
                output.append(self._clip(ambient + voice_r))
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
                time.sleep(0.5)


def load_integrations() -> dict[str, Any]:
    try:
        with INTEGRATIONS_FILE.open(encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_status(**updates: Any) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    try:
        with STATUS_FILE.open(encoding="utf-8") as fh:
            value = json.load(fh)
            if isinstance(value, dict):
                current = value
    except (OSError, json.JSONDecodeError):
        pass
    current.update(updates)
    current["updated_at_unix"] = time.time()
    tmp = STATUS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(current, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    tmp.replace(STATUS_FILE)


def append_event(record: dict[str, Any]) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def openai_tts(text: str, target: Path) -> bool:
    integrations = load_integrations()
    api_key = str(integrations.get("openai_api_key") or "").strip()
    if not api_key:
        return False
    payload = json.dumps({
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": text,
        "instructions": TTS_INSTRUCTIONS,
        "response_format": "mp3",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            target.write_bytes(response.read())
        return target.stat().st_size > 0
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def local_tts(text: str, target: Path) -> bool:
    wav_target = target.with_suffix(".wav")
    try:
        subprocess.run(
            ["espeak-ng", "-v", "pt-br", "-s", "160", "-w", str(wav_target), text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_target), str(target)],
            check=True,
            timeout=30,
        )
        return target.exists() and target.stat().st_size > 0
    except (subprocess.SubprocessError, OSError):
        return False
    finally:
        try:
            wav_target.unlink(missing_ok=True)
        except OSError:
            pass


def decode_to_pcm(source: Path) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(source),
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(CHANNELS),
            "-ar", str(SAMPLE_RATE), "pipe:1",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return result.stdout


class NarrationService:
    def __init__(self, audio: ProgramAudio) -> None:
        self.audio = audio
        self.last_identity = ""
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=64)
        self.stop = asyncio.Event()

    @staticmethod
    def narration_from_world(world: dict[str, Any]) -> tuple[str, str]:
        narration = world.get("narration") or {}
        text = str(narration.get("text") or "").strip()
        last_event = world.get("last_event") or {}
        identity = str(last_event.get("event_id") or "")
        if not identity:
            identity = f"v{world.get('version')}:{text}"
        return identity, text

    async def submit_world(self, world: dict[str, Any]) -> None:
        identity, text = self.narration_from_world(world)
        if not text or identity == self.last_identity:
            return
        self.last_identity = identity
        try:
            self.queue.put_nowait((identity, text))
        except asyncio.QueueFull:
            _ = self.queue.get_nowait()
            self.queue.task_done()
            self.queue.put_nowait((identity, text))

    async def synthesis_worker(self) -> None:
        TTS_DIR.mkdir(parents=True, exist_ok=True)
        while not self.stop.is_set():
            try:
                identity, text = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            started = time.time()
            safe_identity = "".join(c if c.isalnum() or c in "-_" else "_" for c in identity)[:100]
            target = TTS_DIR / f"{safe_identity or int(started * 1000)}.mp3"
            provider = "openai"
            ok = await asyncio.to_thread(openai_tts, text, target)
            if not ok:
                provider = "espeak-ng"
                ok = await asyncio.to_thread(local_tts, text, target)
            record = {
                "event_identity": identity,
                "text": text,
                "provider": provider,
                "ok": ok,
                "created_at_unix": started,
            }
            if ok:
                try:
                    pcm = await asyncio.to_thread(decode_to_pcm, target)
                    self.audio.enqueue_pcm(pcm)
                    record["queued_pcm_bytes"] = len(pcm)
                    write_status(
                        state="running",
                        last_narration=text,
                        last_event_identity=identity,
                        tts_provider=provider,
                        tts_model=TTS_MODEL if provider == "openai" else None,
                        udp_output=UDP_OUTPUT,
                    )
                except (subprocess.SubprocessError, OSError) as exc:
                    record["ok"] = False
                    record["decode_error"] = type(exc).__name__
            else:
                write_status(state="tts_error", last_narration=text, last_event_identity=identity)
            record["finished_at_unix"] = time.time()
            append_event(record)
            self.queue.task_done()

    async def world_listener(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            write_status(state="connecting", world_ws=WORLD_WS, udp_output=UDP_OUTPUT)
            try:
                async with websockets.connect(WORLD_WS, ping_interval=20, ping_timeout=20) as websocket:
                    write_status(state="connected", world_ws=WORLD_WS, udp_output=UDP_OUTPUT)
                    backoff = 1.0
                    async for raw in websocket:
                        try:
                            message = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(message, dict):
                            continue
                        if message.get("type") == "world_state" and isinstance(message.get("world"), dict):
                            await self.submit_world(message["world"])
                        if self.stop.is_set():
                            break
            except Exception as exc:  # connector boundary; reconnect instead of killing audio
                write_status(state="reconnecting", connector_error=type(exc).__name__)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)


async def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio = ProgramAudio()
    service = NarrationService(audio)
    audio.start()
    write_status(
        state="starting",
        world_ws=WORLD_WS,
        udp_output=UDP_OUTPUT,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        ambient_enabled=True,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, service.stop.set)
        except NotImplementedError:
            pass

    worker = asyncio.create_task(service.synthesis_worker())
    listener = asyncio.create_task(service.world_listener())
    await service.stop.wait()
    listener.cancel()
    worker.cancel()
    await asyncio.gather(listener, worker, return_exceptions=True)
    audio.stop()
    write_status(state="stopped")


if __name__ == "__main__":
    asyncio.run(main())
