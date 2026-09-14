from __future__ import annotations

import asyncio
import json
import math
import os
import random
import signal
import subprocess
import threading
import time
from array import array
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets

SAMPLE_RATE = int(os.getenv("LIVE_INFINITA_AUDIO_SAMPLE_RATE", "48000"))
CHANNELS = 2
CHUNK_FRAMES = 960  # 20 ms at 48 kHz
CHUNK_SECONDS = CHUNK_FRAMES / SAMPLE_RATE
UDP_OUTPUT = os.getenv("LIVE_INFINITA_AUDIO_UDP", "udp://127.0.0.1:5500?pkt_size=1316")
WORLD_WS = os.getenv("LIVE_INFINITA_WORLD_WS", "ws://127.0.0.1:8080/ws")
DATA_DIR = Path(os.getenv("LIVE_INFINITA_DATA_DIR", "/var/lib/live-infinita"))
AUDIO_DIR = DATA_DIR / "audio"
TTS_DIR = AUDIO_DIR / "tts"
STATUS_FILE = AUDIO_DIR / "status.json"
EVENT_LOG = AUDIO_DIR / "narration-events.jsonl"
LAST_EVENT_FILE = AUDIO_DIR / "last-narrated-event.txt"
PIPER_BIN = os.getenv("LIVE_INFINITA_PIPER_BIN", "/opt/live.infinita/.venv/bin/piper")
PIPER_MODEL = os.getenv("LIVE_INFINITA_PIPER_MODEL", "/var/lib/live-infinita/audio/models/pt_BR-faber-medium.onnx")
AMBIENT_VOLUME = float(os.getenv("LIVE_INFINITA_AMBIENT_VOLUME", "0.105"))
DUCKED_AMBIENT_VOLUME = float(os.getenv("LIVE_INFINITA_DUCKED_AMBIENT_VOLUME", "0.030"))
NARRATION_VOLUME = float(os.getenv("LIVE_INFINITA_NARRATION_VOLUME", "0.95"))
WORLD_WALK_SPEED = float(os.getenv("LIVE_INFINITA_WORLD_WALK_SPEED", "62.0"))


@dataclass(frozen=True)
class WorldAudioState:
    biome: str = "forest"
    period: str = "day"
    weather: str = "clear"
    fire_lit: bool = False
    fire_distance: float | None = None
    walking: bool = False
    walk_duration: float = 0.0

    def layers(self) -> list[str]:
        result = ["wind"]
        if self.biome in {"forest", "field"}:
            result.append("forest")
        if self.period == "night":
            result.append("night-insects")
        else:
            result.append("day-birds")
        if self.fire_lit:
            result.append("campfire")
        if self.walking:
            result.append("footsteps")
        if self.weather in {"rain", "storm", "drizzle"}:
            result.append("rain")
        return result


class ProgramAudio:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.narration_queue: deque[array] = deque()
        self.queue_lock = threading.Lock()
        self.current: array | None = None
        self.current_offset = 0
        self.ffmpeg: subprocess.Popen[bytes] | None = None

        self.state_lock = threading.Lock()
        self.world_state = WorldAudioState()
        self.last_nov_position: tuple[float, float] | None = None
        self.walking_until = 0.0
        self.fire_pan = 0.0

        self.wind_noise = 0.0
        self.forest_noise = 0.0
        self.rain_noise = 0.0
        self.phase_hum_a = 0.0
        self.phase_hum_b = 0.0

        self.bird_phase = 0.0
        self.bird_envelope = 0.0
        self.bird_age = 0
        self.bird_next = int(SAMPLE_RATE * 1.2)

        self.cricket_phase = 0.0
        self.cricket_envelope = 0.0
        self.cricket_next = int(SAMPLE_RATE * 0.4)

        self.fire_envelope = 0.0
        self.fire_next = int(SAMPLE_RATE * 0.08)

        self.step_phase = 0.0
        self.step_envelope = 0.0
        self.step_next = 0

        self.duck_gain = 1.0
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

    @staticmethod
    def _entity(world: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
        for entity in world.get("entities", []):
            if isinstance(entity, dict) and str(entity.get("id", "")) == entity_id:
                return entity
        return None

    @staticmethod
    def _position(entity: dict[str, Any] | None) -> tuple[float, float] | None:
        if not entity or not isinstance(entity.get("position"), dict):
            return None
        position = entity["position"]
        try:
            return float(position.get("x", 0.0)), float(position.get("y", 0.0))
        except (TypeError, ValueError):
            return None

    def update_world(self, world: dict[str, Any]) -> WorldAudioState:
        environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
        biome = str(environment.get("biome") or "forest").strip().lower() or "forest"
        period = str(environment.get("period") or "day").strip().lower() or "day"
        weather = str(environment.get("weather") or "clear").strip().lower() or "clear"

        nov = self._entity(world, "nov")
        if nov is None:
            for entity in world.get("entities", []):
                if isinstance(entity, dict) and entity.get("type") == "human":
                    nov = entity
                    break
        nov_position = self._position(nov)

        fire = self._entity(world, "fire_01")
        if fire is None:
            for entity in world.get("entities", []):
                if isinstance(entity, dict) and entity.get("type") == "campfire":
                    fire = entity
                    break
        fire_position = self._position(fire)
        fire_properties = fire.get("properties", {}) if isinstance(fire, dict) and isinstance(fire.get("properties"), dict) else {}
        fire_lit = bool(fire_properties.get("lit", False)) if fire is not None else self.world_state.fire_lit

        now = time.monotonic()
        walk_duration = 0.0
        if nov_position is not None and self.last_nov_position is not None:
            distance = math.hypot(
                nov_position[0] - self.last_nov_position[0],
                nov_position[1] - self.last_nov_position[1],
            )
            if 3.0 <= distance <= 800.0:
                walk_duration = max(0.30, min(6.0, distance / max(1.0, WORLD_WALK_SPEED)))
                self.walking_until = max(self.walking_until, now + walk_duration)
        if nov_position is not None:
            self.last_nov_position = nov_position

        fire_distance: float | None = None
        fire_pan = self.fire_pan
        if nov_position is not None and fire_position is not None:
            dx = fire_position[0] - nov_position[0]
            dy = fire_position[1] - nov_position[1]
            fire_distance = math.hypot(dx, dy)
            fire_pan = max(-0.75, min(0.75, dx / 360.0))

        state = WorldAudioState(
            biome=biome,
            period=period,
            weather=weather,
            fire_lit=fire_lit,
            fire_distance=fire_distance,
            walking=now < self.walking_until,
            walk_duration=walk_duration,
        )
        with self.state_lock:
            self.world_state = state
            self.fire_pan = fire_pan
        return state

    def ambient_status(self) -> dict[str, Any]:
        with self.state_lock:
            state = self.world_state
        walking = time.monotonic() < self.walking_until
        live_state = WorldAudioState(
            biome=state.biome,
            period=state.period,
            weather=state.weather,
            fire_lit=state.fire_lit,
            fire_distance=state.fire_distance,
            walking=walking,
            walk_duration=state.walk_duration,
        )
        return {
            "ambient_scene": {
                "biome": live_state.biome,
                "period": live_state.period,
                "weather": live_state.weather,
                "fire_lit": live_state.fire_lit,
                "fire_distance": None if live_state.fire_distance is None else round(live_state.fire_distance, 1),
                "walking": live_state.walking,
                "layers": live_state.layers(),
            },
            "ambient_enabled": True,
            "ambient_provider": "local-procedural-world-reactive",
            "ambient_volume": AMBIENT_VOLUME,
            "ducked_ambient_volume": DUCKED_AMBIENT_VOLUME,
        }

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

    @staticmethod
    def _advance_phase(phase: float, frequency: float) -> float:
        phase += 2.0 * math.pi * frequency / SAMPLE_RATE
        if phase > 2.0 * math.pi:
            phase -= 2.0 * math.pi
        return phase

    def _wind_and_forest(self, state: WorldAudioState) -> float:
        raw = random.uniform(-1.0, 1.0)
        self.wind_noise = self.wind_noise * 0.9986 + raw * 0.0014
        self.forest_noise = self.forest_noise * 0.994 + raw * 0.006
        self.phase_hum_a = self._advance_phase(self.phase_hum_a, 48.0)
        self.phase_hum_b = self._advance_phase(self.phase_hum_b, 71.0)
        base = self.wind_noise * 1.7 + math.sin(self.phase_hum_a) * 0.045 + math.sin(self.phase_hum_b) * 0.025
        if state.biome == "forest":
            base += self.forest_noise * 0.46
        elif state.biome == "field":
            base += self.forest_noise * 0.26
        return base * 0.58

    def _birds(self, enabled: bool) -> float:
        if not enabled:
            self.bird_envelope *= 0.995
            return 0.0
        if self.bird_next <= 0:
            self.bird_envelope = random.uniform(0.35, 0.72)
            self.bird_age = 0
            self.bird_next = random.randint(int(SAMPLE_RATE * 1.7), int(SAMPLE_RATE * 4.2))
        self.bird_next -= 1
        if self.bird_envelope < 0.001:
            return 0.0
        sweep = min(1.0, self.bird_age / max(1.0, SAMPLE_RATE * 0.18))
        frequency = 1650.0 + 950.0 * sweep + 240.0 * math.sin(self.bird_age / 430.0)
        self.bird_phase = self._advance_phase(self.bird_phase, frequency)
        value = math.sin(self.bird_phase) * self.bird_envelope
        self.bird_envelope *= 0.99955
        self.bird_age += 1
        return value * 0.11

    def _night_insects(self, enabled: bool) -> float:
        if not enabled:
            self.cricket_envelope *= 0.995
            return 0.0
        if self.cricket_next <= 0:
            self.cricket_envelope = random.uniform(0.18, 0.42)
            self.cricket_next = random.randint(int(SAMPLE_RATE * 0.10), int(SAMPLE_RATE * 0.55))
        self.cricket_next -= 1
        if self.cricket_envelope < 0.001:
            return 0.0
        self.cricket_phase = self._advance_phase(self.cricket_phase, 3650.0 + random.uniform(-18.0, 18.0))
        gate = 1.0 if math.sin(self.cricket_phase * 0.075) > -0.1 else 0.20
        value = math.sin(self.cricket_phase) * self.cricket_envelope * gate
        self.cricket_envelope *= 0.99972
        return value * 0.10

    def _campfire(self, state: WorldAudioState) -> tuple[float, float]:
        if not state.fire_lit:
            self.fire_envelope *= 0.97
            return 0.0, 0.0
        if self.fire_next <= 0:
            self.fire_envelope = random.uniform(0.35, 1.0)
            self.fire_next = random.randint(int(SAMPLE_RATE * 0.025), int(SAMPLE_RATE * 0.16))
        self.fire_next -= 1
        crack = random.uniform(-1.0, 1.0) * self.fire_envelope
        self.fire_envelope *= 0.9981
        bed = random.uniform(-1.0, 1.0) * 0.035

        distance_gain = 1.0
        if state.fire_distance is not None:
            distance_gain = max(0.12, min(1.0, 1.0 - state.fire_distance / 420.0))
        value = (crack * 0.15 + bed) * distance_gain
        pan = self.fire_pan
        left = value * (1.0 - max(0.0, pan) * 0.55)
        right = value * (1.0 + min(0.0, pan) * 0.55)
        return left, right

    def _footsteps(self, walking: bool) -> float:
        if not walking:
            self.step_envelope *= 0.96
            self.step_next = 0
            return 0.0
        if self.step_next <= 0:
            self.step_envelope = random.uniform(0.60, 0.92)
            self.step_next = random.randint(int(SAMPLE_RATE * 0.39), int(SAMPLE_RATE * 0.48))
            self.step_phase = 0.0
        self.step_next -= 1
        if self.step_envelope < 0.001:
            return 0.0
        self.step_phase = self._advance_phase(self.step_phase, 82.0)
        thump = math.sin(self.step_phase) * self.step_envelope
        grit = random.uniform(-1.0, 1.0) * self.step_envelope * 0.20
        self.step_envelope *= 0.9987
        return (thump * 0.18 + grit * 0.08)

    def _rain(self, enabled: bool) -> float:
        if not enabled:
            self.rain_noise *= 0.985
            return 0.0
        raw = random.uniform(-1.0, 1.0)
        self.rain_noise = self.rain_noise * 0.78 + raw * 0.22
        return self.rain_noise * 0.16

    def _ambient_sample(self, master_volume: float) -> tuple[int, int]:
        with self.state_lock:
            state = self.world_state
        walking = time.monotonic() < self.walking_until

        common = self._wind_and_forest(state)
        common += self._birds(state.period != "night" and state.biome in {"forest", "field"})
        common += self._night_insects(state.period == "night" and state.biome in {"forest", "field"})
        common += self._rain(state.weather in {"rain", "storm", "drizzle"})
        common += self._footsteps(walking)
        fire_l, fire_r = self._campfire(state)

        left = int((common + fire_l) * 32767 * master_volume)
        right = int((common + fire_r) * 32767 * master_volume)
        return left, right

    def _run(self) -> None:
        next_deadline = time.monotonic()
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
                target_duck = DUCKED_AMBIENT_VOLUME / max(AMBIENT_VOLUME, 0.0001) if speaking else 1.0
                smoothing = 0.008 if speaking else 0.0017
                self.duck_gain += (target_duck - self.duck_gain) * smoothing
                ambient_l, ambient_r = self._ambient_sample(AMBIENT_VOLUME * self.duck_gain)
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
                time.sleep(0.5)
                next_deadline = time.monotonic()
                continue

            next_deadline += CHUNK_SECONDS
            wait = next_deadline - time.monotonic()
            if wait > 0:
                self.stop_event.wait(wait)
            elif wait < -0.25:
                next_deadline = time.monotonic()


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


def load_last_identity() -> str:
    try:
        return LAST_EVENT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def persist_last_identity(identity: str) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LAST_EVENT_FILE.with_suffix(".tmp")
    tmp.write_text(identity + "\n", encoding="utf-8")
    tmp.replace(LAST_EVENT_FILE)


def piper_tts(text: str, target: Path) -> bool:
    model = Path(PIPER_MODEL)
    binary = Path(PIPER_BIN)
    if not binary.exists() or not model.exists() or not model.with_suffix(model.suffix + ".json").exists():
        return False
    wav_target = target.with_suffix(".wav")
    try:
        subprocess.run(
            [str(binary), "--model", str(model), "--output_file", str(wav_target)],
            input=(text + "\n").encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=45,
        )
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_target), str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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


def espeak_tts(text: str, target: Path) -> bool:
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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
        self.last_identity = load_last_identity()
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
        state = self.audio.update_world(world)
        write_status(**self.audio.ambient_status())
        identity, text = self.narration_from_world(world)
        if not text or identity == self.last_identity:
            return
        self.last_identity = identity
        persist_last_identity(identity)
        try:
            self.queue.put_nowait((identity, text))
        except asyncio.QueueFull:
            _ = self.queue.get_nowait()
            self.queue.task_done()
            self.queue.put_nowait((identity, text))
        print(
            f"[audio] world ambience biome={state.biome} period={state.period} weather={state.weather} "
            f"fire={state.fire_lit} walking={state.walking}",
            flush=True,
        )

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

            provider = "piper-local"
            ok = await asyncio.to_thread(piper_tts, text, target)
            if not ok:
                provider = "espeak-ng-local"
                ok = await asyncio.to_thread(espeak_tts, text, target)

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
                        tts_model=Path(PIPER_MODEL).name if provider == "piper-local" else "espeak-ng pt-br",
                        tts_local=True,
                        openai_audio_enabled=False,
                        udp_output=UDP_OUTPUT,
                        **self.audio.ambient_status(),
                    )
                    print(f"[audio] narrativa {identity!s}: {text!r} provider={provider} queued_pcm={len(pcm)}", flush=True)
                except (subprocess.SubprocessError, OSError) as exc:
                    record["ok"] = False
                    record["decode_error"] = type(exc).__name__
                    print(f"[audio] falha ao decodificar {identity}: {type(exc).__name__}", flush=True)
            else:
                write_status(state="tts_error", last_narration=text, last_event_identity=identity, tts_local=True, openai_audio_enabled=False)
                print(f"[audio] TTS local falhou para {identity}", flush=True)
            record["finished_at_unix"] = time.time()
            append_event(record)
            self.queue.task_done()

    async def world_listener(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            write_status(
                state="connecting",
                world_ws=WORLD_WS,
                udp_output=UDP_OUTPUT,
                tts_local=True,
                openai_audio_enabled=False,
                **self.audio.ambient_status(),
            )
            try:
                async with websockets.connect(WORLD_WS, ping_interval=20, ping_timeout=20) as websocket:
                    write_status(
                        state="connected",
                        world_ws=WORLD_WS,
                        udp_output=UDP_OUTPUT,
                        tts_local=True,
                        openai_audio_enabled=False,
                        **self.audio.ambient_status(),
                    )
                    print(f"[audio] conectado ao World State {WORLD_WS}; saída {UDP_OUTPUT}", flush=True)
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
            except Exception as exc:
                write_status(
                    state="reconnecting",
                    connector_error=type(exc).__name__,
                    tts_local=True,
                    openai_audio_enabled=False,
                    **self.audio.ambient_status(),
                )
                print(f"[audio] WebSocket desconectado ({type(exc).__name__}); reconectando", flush=True)
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
        tts_local=True,
        openai_audio_enabled=False,
        tts_model=Path(PIPER_MODEL).name,
        **audio.ambient_status(),
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
