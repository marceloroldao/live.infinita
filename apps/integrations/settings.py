from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SECRET_FIELDS = {"openai_api_key", "tiktok_sign_api_key"}


class IntegrationStore:
    """Small server-side secret store for the single-VM MVP."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}

    def update(self, values: dict[str, Any]) -> None:
        current = self.load()
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
            if key in SECRET_FIELDS and value == "":
                current.pop(key, None)
            elif key not in SECRET_FIELDS or value:
                current[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as fh:
            json.dump(current, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    def public_status(self) -> dict[str, Any]:
        value = self.load()
        return {
            "openai": {
                "configured": bool(value.get("openai_api_key")),
                "model": value.get("openai_model", "gpt-5-mini"),
                "key_hint": self._hint(value.get("openai_api_key")),
            },
            "tiktok": {
                "configured": bool(value.get("tiktok_unique_id")),
                "unique_id": value.get("tiktok_unique_id"),
                "sign_key_configured": bool(value.get("tiktok_sign_api_key")),
                "sign_key_hint": self._hint(value.get("tiktok_sign_api_key")),
                "apply_mode": "automatic-service-restart",
            },
        }

    @staticmethod
    def _hint(value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        return "••••" + value[-4:] if len(value) >= 4 else "••••"
