from __future__ import annotations

from typing import Any

from cognitive_shadow import CognitiveShadowRecorder


class ShadowWorldTickRunner:
    """Passive wrapper around the authoritative runner.

    Shadow failures are contained and never block, retry, or roll back the world tick.
    The wrapper exposes ``clock`` for compatibility with ``WorldTickDriver`` and does
    not intercept any other authority-bearing component.
    """

    def __init__(self, runner: Any, recorder: CognitiveShadowRecorder) -> None:
        self.runner = runner
        self.recorder = recorder
        self.clock = runner.clock

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runner, name)

    def tick(self) -> dict[str, Any]:
        token = None
        begin_error: str | None = None
        try:
            token = self.recorder.begin_tick()
        except Exception as exc:  # shadow must never affect world authority
            begin_error = type(exc).__name__

        result = self.runner.tick()
        if not isinstance(result, dict):
            return result

        shadow: dict[str, Any] = {
            "enabled": self.recorder.enabled,
            "recorded": False,
            "world_mutated_by_shadow": False,
        }
        if begin_error is not None:
            shadow["status"] = "begin_error"
            shadow["error_type"] = begin_error
            result["cognitive_shadow"] = shadow
            return result

        try:
            record = self.recorder.complete_tick(token, result)
        except Exception as exc:  # observational persistence is fail-open
            shadow["status"] = "complete_error"
            shadow["error_type"] = type(exc).__name__
        else:
            shadow["recorded"] = record is not None
            shadow["status"] = "recorded" if record is not None else "skipped"
            if isinstance(record, dict):
                shadow["shadow_id"] = record.get("shadow_id")
                shadow["frame_id"] = record.get("frame_id")
                best = record.get("best_candidate") if isinstance(record.get("best_candidate"), dict) else {}
                shadow["best_candidate_action"] = best.get("action")
                shadow["exact_structural_match"] = best.get("exact_structural_match")
        result["cognitive_shadow"] = shadow
        return result
