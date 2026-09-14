from __future__ import annotations

import asyncio
import math
import os
import random
from typing import Any

import server_audio


RETRO_SCORE_ENABLED = str(os.getenv("LIVE_INFINITA_RETRO_SCORE_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}
RETRO_SCORE_VOLUME = float(os.getenv("LIVE_INFINITA_RETRO_SCORE_VOLUME", "0.36"))
TAU = math.tau


# Original procedural themes. They intentionally use tiny, generic interval
# vocabularies rather than reproducing melodies from existing games.
RETRO_THEMES: dict[str, dict[str, Any]] = {
    "forest": {
        "label": "mysterious-woodland",
        "root_midi": 62,  # D4
        "bpm": 84.0,
        "lead": (0, None, 5, 7, 10, 7, 5, None, 3, None, 5, 7, 12, 10, 7, None),
        "arp": (0, 3, 7, 10),
        "bass": (0, 0, 3, 3, 5, 5, 3, 3),
        "duty": 0.25,
        "air": 0.82,
    },
    "river": {
        "label": "flowing-waterway",
        "root_midi": 64,  # E4
        "bpm": 98.0,
        "lead": (0, 4, 7, 9, 12, 9, 7, 4, 2, 4, 7, 11, 9, 7, 4, None),
        "arp": (0, 4, 7, 11),
        "bass": (0, 0, 5, 5, 7, 7, 5, 5),
        "duty": 0.25,
        "air": 0.94,
    },
    "village": {
        "label": "warm-settlement",
        "root_midi": 60,  # C4
        "bpm": 106.0,
        "lead": (0, 4, 7, None, 9, 7, 4, None, 5, 9, 12, 9, 7, 5, 4, None),
        "arp": (0, 4, 7, 9),
        "bass": (0, 0, 5, 5, 9, 9, 7, 7),
        "duty": 0.375,
        "air": 1.0,
    },
    "field": {
        "label": "open-horizon",
        "root_midi": 67,  # G4
        "bpm": 92.0,
        "lead": (0, None, 4, 7, 9, 7, 4, 2, 0, 2, 4, 9, 7, 4, 2, None),
        "arp": (0, 4, 7, 9),
        "bass": (0, 0, 7, 7, 5, 5, 7, 7),
        "duty": 0.25,
        "air": 0.90,
    },
}


def midi_frequency(note: float) -> float:
    return 440.0 * (2.0 ** ((float(note) - 69.0) / 12.0))


def pulse_wave(phase: float, duty: float) -> float:
    return 1.0 if (phase / TAU) < duty else -1.0


def triangle_wave(phase: float) -> float:
    # Console-like triangle without expensive harmonics.
    return (2.0 / math.pi) * math.asin(math.sin(phase))


class RetroProgramAudio(server_audio.ProgramAudio):
    """Server audio with a low-volume procedural retro game score.

    Environmental layers remain intact. This adds a deterministic musical layer
    whose tempo, register and interval vocabulary follow the current biome and
    day/night period. No copyrighted melody or external music asset is used.
    """

    def __init__(self) -> None:
        super().__init__()
        self.retro_step = -1
        self.retro_samples_to_step = 0
        self.retro_signature = ""

        self.retro_lead_phase = 0.0
        self.retro_arp_phase = 0.0
        self.retro_bass_phase = 0.0
        self.retro_kick_phase = 0.0
        self.retro_lead_frequency = 0.0
        self.retro_arp_frequency = 0.0
        self.retro_bass_frequency = 0.0
        self.retro_kick_frequency = 70.0

        self.retro_lead_env = 0.0
        self.retro_arp_env = 0.0
        self.retro_bass_env = 0.0
        self.retro_kick_env = 0.0
        self.retro_noise_env = 0.0

        # Two gentle one-pole stages remove the hard square-wave edge that would
        # otherwise be perceived as a sequence of isolated beeps.
        self.retro_filter_l = 0.0
        self.retro_filter_r = 0.0
        self.retro_filter2_l = 0.0
        self.retro_filter2_r = 0.0

    @staticmethod
    def retro_profile(state: server_audio.WorldAudioState) -> dict[str, Any]:
        base = RETRO_THEMES.get(state.biome, RETRO_THEMES["forest"])
        night = state.period == "night"
        bpm = float(base["bpm"]) * (0.78 if night else 1.0)
        transpose = -12 if night else 0
        return {
            **base,
            "bpm": bpm,
            "transpose": transpose,
            "period": state.period,
            "biome": state.biome,
        }

    def ambient_status(self) -> dict[str, Any]:
        status = super().ambient_status()
        scene = status.get("ambient_scene") if isinstance(status.get("ambient_scene"), dict) else {}
        layers = list(scene.get("layers") or [])
        if RETRO_SCORE_ENABLED and "retro-score" not in layers:
            layers.append("retro-score")
        with self.state_lock:
            state = self.world_state
        profile = self.retro_profile(state)
        scene.update({
            "layers": layers,
            "music_style": "procedural-retro-game",
            "music_theme": profile["label"],
            "music_bpm": round(float(profile["bpm"]), 1),
        })
        status["ambient_scene"] = scene
        status["ambient_provider"] = "local-procedural-retro-world-reactive"
        status["retro_score"] = {
            "enabled": RETRO_SCORE_ENABLED,
            "volume": RETRO_SCORE_VOLUME,
            "synthesis": ["pulse-lead", "pulse-arpeggio", "triangle-bass", "noise-percussion"],
            "copyrighted_music": False,
        }
        return status

    @staticmethod
    def _advance_retro_phase(phase: float, frequency: float) -> float:
        phase += TAU * frequency / server_audio.SAMPLE_RATE
        if phase >= TAU:
            phase -= TAU
        return phase

    def _trigger_retro_step(self, state: server_audio.WorldAudioState) -> None:
        profile = self.retro_profile(state)
        signature = f"{state.biome}:{state.period}"
        if signature != self.retro_signature:
            self.retro_signature = signature
            self.retro_step = -1
            # Cross-scene changes start softly instead of clicking into a new key.
            self.retro_lead_env *= 0.30
            self.retro_arp_env *= 0.30
            self.retro_bass_env *= 0.55

        self.retro_step = (self.retro_step + 1) % 16
        step_seconds = (60.0 / max(40.0, float(profile["bpm"]))) / 4.0
        self.retro_samples_to_step = max(1, int(server_audio.SAMPLE_RATE * step_seconds))
        transpose = int(profile["transpose"])
        root = int(profile["root_midi"]) + transpose

        lead_pattern = profile["lead"]
        lead_offset = lead_pattern[self.retro_step]
        if lead_offset is not None:
            self.retro_lead_frequency = midi_frequency(root + int(lead_offset))
            self.retro_lead_env = 0.82 if state.period != "night" else 0.60

        arp = profile["arp"]
        arp_offset = int(arp[self.retro_step % len(arp)])
        # The arpeggio sits one octave above the root but is intentionally quiet.
        self.retro_arp_frequency = midi_frequency(root + 12 + arp_offset)
        self.retro_arp_env = 0.44 if state.period != "night" else 0.30

        if self.retro_step % 4 == 0:
            bass_pattern = profile["bass"]
            bass_slot = (self.retro_step // 2) % len(bass_pattern)
            bass_offset = int(bass_pattern[bass_slot])
            self.retro_bass_frequency = midi_frequency(root - 24 + bass_offset)
            self.retro_bass_env = 0.92

        # Sparse retro percussion: low thump on the downbeat, short noise on the
        # backbeat. River/village get a little more motion than forest/field.
        if self.retro_step in {0, 8}:
            self.retro_kick_env = 0.82
            self.retro_kick_frequency = 86.0
            self.retro_kick_phase = 0.0
        elif self.retro_step in {4, 12}:
            self.retro_noise_env = 0.24 if state.period != "night" else 0.14
        elif state.biome in {"river", "village"} and self.retro_step % 2 == 1:
            self.retro_noise_env = max(self.retro_noise_env, 0.065)

    def _retro_sample(self, state: server_audio.WorldAudioState) -> tuple[float, float]:
        if not RETRO_SCORE_ENABLED:
            return 0.0, 0.0
        if self.retro_samples_to_step <= 0:
            self._trigger_retro_step(state)
        self.retro_samples_to_step -= 1

        profile = self.retro_profile(state)
        duty = float(profile["duty"])
        air = float(profile["air"])

        self.retro_lead_phase = self._advance_retro_phase(self.retro_lead_phase, self.retro_lead_frequency)
        self.retro_arp_phase = self._advance_retro_phase(self.retro_arp_phase, self.retro_arp_frequency)
        self.retro_bass_phase = self._advance_retro_phase(self.retro_bass_phase, self.retro_bass_frequency)

        lead = pulse_wave(self.retro_lead_phase, duty) * self.retro_lead_env * 0.18
        arp = pulse_wave(self.retro_arp_phase, 0.125) * self.retro_arp_env * 0.085
        bass = triangle_wave(self.retro_bass_phase) * self.retro_bass_env * 0.26

        self.retro_lead_env *= 0.99988
        self.retro_arp_env *= 0.99958
        self.retro_bass_env *= 0.999965

        kick = 0.0
        if self.retro_kick_env > 0.0005:
            self.retro_kick_phase = self._advance_retro_phase(self.retro_kick_phase, self.retro_kick_frequency)
            kick = math.sin(self.retro_kick_phase) * self.retro_kick_env * 0.18
            self.retro_kick_frequency = max(42.0, self.retro_kick_frequency * 0.99972)
            self.retro_kick_env *= 0.9986

        noise = 0.0
        if self.retro_noise_env > 0.0005:
            noise = random.uniform(-1.0, 1.0) * self.retro_noise_env * 0.12
            self.retro_noise_env *= 0.9962

        # Small stereo movement makes it feel like a score instead of one tone in
        # the middle. Bass stays centered; lead and arpeggio gently oppose.
        pan = 0.20 if (self.retro_step // 4) % 2 == 0 else -0.20
        raw_l = bass + kick + noise + lead * (1.0 - pan) + arp * (1.0 + pan)
        raw_r = bass + kick + noise + lead * (1.0 + pan) + arp * (1.0 - pan)
        raw_l *= air
        raw_r *= air

        # Gentle double low-pass: keeps the characteristic pulse texture while
        # removing the piercing edge that caused the old "bip" impression.
        self.retro_filter_l += (raw_l - self.retro_filter_l) * 0.22
        self.retro_filter_r += (raw_r - self.retro_filter_r) * 0.22
        self.retro_filter2_l += (self.retro_filter_l - self.retro_filter2_l) * 0.34
        self.retro_filter2_r += (self.retro_filter_r - self.retro_filter2_r) * 0.34
        return self.retro_filter2_l, self.retro_filter2_r

    def _ambient_sample(self, master_volume: float) -> tuple[int, int]:
        # Preserve wind/birds/fire/rain/footsteps from the original engine.
        base_l, base_r = super()._ambient_sample(master_volume)
        with self.state_lock:
            state = self.world_state
        retro_l, retro_r = self._retro_sample(state)
        music_gain = master_volume * RETRO_SCORE_VOLUME
        left = base_l + int(retro_l * 32767 * music_gain)
        right = base_r + int(retro_r * 32767 * music_gain)
        return self._clip(left), self._clip(right)


async def main() -> None:
    # server_audio.main resolves ProgramAudio from its module globals at runtime.
    # Replace it only for the production entry point; the original engine remains
    # importable and independently testable.
    server_audio.ProgramAudio = RetroProgramAudio  # type: ignore[assignment]
    await server_audio.main()


if __name__ == "__main__":
    asyncio.run(main())
