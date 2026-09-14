from __future__ import annotations

import json
import math
import os
import re
import time
import unicodedata
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any


# Closed scene vocabulary. This layer extracts only preferences that can safely
# map to scenery the current renderer/world evolver already understands. General
# questions remain conversation-only and therefore cannot accidentally mutate the
# world. Multi-word phrases are intentionally supported for natural questions.
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "forest": (
        "floresta", "mata", "mata fechada", "arvore", "arvores", "bosque",
        "selva", "vegetacao", "folhagem", "trilha na mata", "trilha na floresta",
        "entre as arvores", "animais da floresta",
    ),
    "river": (
        "rio", "rios", "agua", "aguas", "cachoeira", "cachoeiras", "lago", "lagos",
        "ponte", "pontes", "margem", "margens", "riacho", "corrego", "nascente",
        "beira do rio", "pescar", "atravessar o rio", "travessia", "correnteza",
        "barco", "ilha",
    ),
    "village": (
        "vila", "aldeia", "cidade", "casa", "casas", "comunidade", "morador",
        "moradores", "praca", "mercado", "rua", "ruas", "construcao", "construcoes",
        "outras pessoas", "alguem morando", "tem alguem por perto", "encontrar gente",
        "luzes de casas",
    ),
    "field": (
        "campo", "campo aberto", "campina", "planicie", "horizonte", "flores", "grama",
        "prado", "clareira", "clareiras", "ceu aberto", "vale", "colina", "colinas",
        "espaco aberto",
    ),
}


class CollectiveIntentEngine:
    """Bounded, deterministic aggregation of crowd preference over time.

    Conversation and world intent are deliberately separate: every comment may be
    answered by the conversational host, but only text that maps to the closed
    scene vocabulary becomes a collective world signal. Telemetry only amplifies
    an existing semantic direction and never chooses one by itself.
    """

    def __init__(self, state_file: Path) -> None:
        self.state_file = Path(state_file)
        self.window_seconds = float(os.getenv("LIVE_INFINITA_COLLECTIVE_WINDOW_SECONDS", "120"))
        self.min_score = float(os.getenv("LIVE_INFINITA_COLLECTIVE_MIN_SCORE", "2.8"))
        self.min_contributors = int(os.getenv("LIVE_INFINITA_COLLECTIVE_MIN_CONTRIBUTORS", "2"))
        self.min_dominance = float(os.getenv("LIVE_INFINITA_COLLECTIVE_MIN_DOMINANCE", "0.55"))
        self.cooldown_seconds = float(os.getenv("LIVE_INFINITA_COLLECTIVE_COOLDOWN_SECONDS", "75"))
        self.max_comment_signals = int(os.getenv("LIVE_INFINITA_COLLECTIVE_MAX_SIGNALS", "256"))
        self.comments: deque[dict[str, Any]] = deque(maxlen=max(32, self.max_comment_signals))
        self.telemetry: deque[dict[str, Any]] = deque(maxlen=512)
        self._last_actor_theme: dict[tuple[str, str], float] = {}
        self.chapter = 0
        self.last_applied_unix = 0.0
        self.evolutions: list[dict[str, Any]] = []
        self.last_failure: dict[str, Any] | None = None
        self._load()

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFKD", str(text or "").lower())
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    @staticmethod
    def _contains_term(normalized: str, term: str) -> bool:
        """Match complete words/phrases so `rio` does not match `curioso`."""
        normalized_term = " ".join(str(term).split())
        if not normalized_term:
            return False
        pattern = r"(?<![a-z0-9])" + r"\s+".join(
            re.escape(piece) for piece in normalized_term.split()
        ) + r"(?![a-z0-9])"
        return re.search(pattern, normalized) is not None

    @classmethod
    def classify_text(cls, text: str) -> tuple[str | None, float, list[str]]:
        normalized = cls._normalize(text)
        if not normalized:
            return None, 0.0, []
        scored: list[tuple[int, int, str, list[str]]] = []
        for theme, terms in THEME_KEYWORDS.items():
            matches = [term for term in terms if cls._contains_term(normalized, term)]
            if matches:
                # Prefer more evidence; when counts tie, specific multi-word
                # phrases beat a generic single word before deterministic theme id.
                phrase_specificity = sum(term.count(" ") for term in matches)
                scored.append((len(matches), phrase_specificity, theme, matches))
        if not scored:
            return None, 0.0, []
        scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
        count, _specificity, theme, matches = scored[0]
        weight = min(1.75, 1.0 + max(0, count - 1) * 0.25)
        return theme, weight, matches

    def _load(self) -> None:
        try:
            with self.state_file.open(encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        self.chapter = max(0, int(payload.get("chapter", 0)))
        self.last_applied_unix = float(payload.get("last_applied_unix", 0.0) or 0.0)
        rows = payload.get("evolutions")
        if isinstance(rows, list):
            self.evolutions = [deepcopy(row) for row in rows[-40:] if isinstance(row, dict)]

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "chapter": self.chapter,
            "last_applied_unix": self.last_applied_unix,
            "evolutions": self.evolutions[-40:],
            "last_failure": self.last_failure,
        }
        tmp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
        tmp.replace(self.state_file)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.comments and float(self.comments[0]["at_unix"]) < cutoff:
            self.comments.popleft()
        while self.telemetry and float(self.telemetry[0]["at_unix"]) < cutoff:
            self.telemetry.popleft()
        stale_keys = [key for key, ts in self._last_actor_theme.items() if ts < cutoff]
        for key in stale_keys:
            self._last_actor_theme.pop(key, None)

    def ingest_comment(
        self,
        *,
        source: str,
        actor_id: str,
        text: str,
        display_name: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        at = float(now if now is not None else time.time())
        self._prune(at)
        theme, weight, matches = self.classify_text(text)
        if theme is None:
            return None
        actor_key = f"{str(source).strip().lower()}:{str(actor_id).strip()}"
        repeat_key = (actor_key, theme)
        previous = self._last_actor_theme.get(repeat_key, 0.0)
        if at - previous < 12.0:
            return None
        self._last_actor_theme[repeat_key] = at
        signal = {
            "at_unix": at,
            "theme": theme,
            "weight": float(weight),
            "actor_key": actor_key,
            "display_name": display_name,
            "matches": matches,
            "text": str(text)[:280],
        }
        self.comments.append(signal)
        return deepcopy(signal)

    def ingest_telemetry(self, event: dict[str, Any], now: float | None = None) -> None:
        at = float(now if now is not None else event.get("received_at_unix", time.time()))
        self._prune(at)
        kind = str(event.get("kind") or "").strip().lower()
        if kind not in {"join", "like", "gift"}:
            return
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        if kind == "gift":
            weight = 0.70
        elif kind == "join":
            weight = 0.08
        else:
            count = metadata.get("count", metadata.get("like_count", 1))
            try:
                amount = max(1.0, min(100.0, float(count)))
            except (TypeError, ValueError):
                amount = 1.0
            weight = min(0.30, 0.025 * math.sqrt(amount))
        self.telemetry.append({"at_unix": at, "kind": kind, "weight": weight})

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        at = float(now if now is not None else time.time())
        self._prune(at)
        scores = {theme: 0.0 for theme in THEME_KEYWORDS}
        contributors: dict[str, set[str]] = {theme: set() for theme in THEME_KEYWORDS}
        for row in self.comments:
            age = max(0.0, at - float(row["at_unix"]))
            decay = max(0.15, 1.0 - (age / max(self.window_seconds, 1.0)) * 0.85)
            theme = str(row["theme"])
            if theme not in scores:
                continue
            scores[theme] += float(row["weight"]) * decay
            contributors[theme].add(str(row["actor_key"]))

        engagement = 0.0
        for row in self.telemetry:
            age = max(0.0, at - float(row["at_unix"]))
            decay = max(0.10, 1.0 - age / max(self.window_seconds, 1.0))
            engagement += float(row["weight"]) * decay
        confidence_gain = 1.0 + min(0.35, engagement * 0.025)
        boosted = {theme: value * confidence_gain for theme, value in scores.items()}
        ordered = sorted(boosted.items(), key=lambda pair: (-pair[1], pair[0]))
        if ordered and ordered[0][1] > 0.0:
            dominant, dominant_score = ordered[0]
        else:
            dominant, dominant_score = None, 0.0
        total = sum(boosted.values())
        dominance = (dominant_score / total) if total > 0 else 0.0
        dominant_contributors = len(contributors.get(str(dominant), set())) if dominant else 0
        cooldown_remaining = max(0.0, self.cooldown_seconds - (at - self.last_applied_unix))
        ready = bool(
            dominant
            and dominant_score >= self.min_score
            and dominant_contributors >= self.min_contributors
            and dominance >= self.min_dominance
            and cooldown_remaining <= 0.0
        )
        return {
            "dominant": dominant,
            "dominant_score": round(dominant_score, 4),
            "dominance": round(dominance, 4),
            "contributors": dominant_contributors,
            "scores": {key: round(value, 4) for key, value in boosted.items()},
            "engagement": round(engagement, 4),
            "comment_signals": len(self.comments),
            "telemetry_signals": len(self.telemetry),
            "window_seconds": self.window_seconds,
            "min_score": self.min_score,
            "min_contributors": self.min_contributors,
            "min_dominance": self.min_dominance,
            "cooldown_remaining_seconds": round(cooldown_remaining, 2),
            "chapter": self.chapter,
            "ready": ready,
        }

    def next_evolution(self, now: float | None = None) -> dict[str, Any] | None:
        at = float(now if now is not None else time.time())
        state = self.snapshot(at)
        if not state["ready"]:
            return None
        return {**state, "chapter": self.chapter + 1, "decided_at_unix": at}

    def mark_applied(self, decision: dict[str, Any], *, event_id: str, region_id: str | None) -> None:
        self.chapter = max(self.chapter, int(decision.get("chapter", self.chapter + 1)))
        self.last_applied_unix = float(decision.get("decided_at_unix", time.time()))
        self.evolutions.append({
            "chapter": self.chapter,
            "theme": decision.get("dominant"),
            "score": decision.get("dominant_score"),
            "dominance": decision.get("dominance"),
            "contributors": decision.get("contributors"),
            "event_id": event_id,
            "region_id": region_id,
            "applied_at_unix": self.last_applied_unix,
        })
        self.comments.clear()
        self.telemetry.clear()
        self._last_actor_theme.clear()
        self.last_failure = None
        self._save()

    def mark_failed(self, decision: dict[str, Any], reason: str) -> None:
        self.last_failure = {
            "theme": decision.get("dominant"),
            "chapter": decision.get("chapter"),
            "reason": str(reason)[:500],
            "at_unix": time.time(),
        }
        self._save()
