"""Fail-closed outbound transport for typed, confirmed Nov episode observations.

Completely separate from the authoritative world process. A candidate byte
cursor becomes durable only after a verified central receipt. No generated
language, shadow records, or user/assistant turns can enter this path.
"""
from __future__ import annotations

import base64
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from packages.observability.nov_episode_sync import EpisodeSyncContractError, preview_episode_batch

CHECKPOINT_SCHEMA = "live-infinita-nov-device-sync/v1"
RECEIPT_SCHEMA = "memoria-server-npc-episode-receipt/v1"
OBSERVE_PATH = "/api/server/v1/device/observations/npc-episodes"
MAX_RESPONSE_BYTES = 32768
_ANCHOR_BYTES = 4096
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class DeliveryError(RuntimeError):
    """Never advance the checkpoint when a send or receipt is uncertain."""


def _canonical(row: object) -> bytes:
    return json.dumps(row, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _anchor(path: Path, cursor: int, expected_identity: str) -> str:
    with path.open("rb") as source:
        stat = os.fstat(source.fileno())
        identity = f"{stat.st_dev}:{stat.st_ino}"
        if identity != expected_identity or stat.st_size < cursor:
            raise DeliveryError("source ledger changed during delivery")
        if cursor:
            source.seek(cursor - 1)
            if source.read(1) != b"\n":
                raise DeliveryError("checkpoint is not on a complete line")
        start = max(0, cursor - _ANCHOR_BYTES)
        source.seek(start)
        chunk = source.read(cursor - start)
        if len(chunk) != cursor - start:
            raise DeliveryError("source ledger anchor incomplete")
        return sha256(chunk).hexdigest()


def _save_json_atomic(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = _canonical(row) + b"\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        temporary.unlink(missing_ok=True)


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise DeliveryError("invalid existing checkpoint") from exc
    if not isinstance(data, dict) or data.get("schema") != CHECKPOINT_SCHEMA:
        raise DeliveryError("unsupported checkpoint schema")
    if (
        isinstance(data.get("cursor"), bool) or not isinstance(data.get("cursor"), int)
        or data["cursor"] < 0
        or not isinstance(data.get("ledger_identity"), str)
        or not isinstance(data.get("world_id"), str)
        or not isinstance(data.get("anchor_sha256"), str)
        or not _HEX64.fullmatch(data["anchor_sha256"])
    ):
        raise DeliveryError("invalid existing checkpoint fields")
    return data


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise DeliveryError("remote redirect forbidden")


class DeviceSession:
    """Short-lived Ed25519 device session, with pinned server identity."""

    def __init__(
        self, *, server_url: str, server_id: str, device_id: str,
        key_path: Path | None = None,
        transport: Callable[[str, dict[str, Any], str | None], tuple[int, dict[str, Any]]] | None = None,
        signer: Callable[[bytes], bytes] | None = None,
    ) -> None:
        parsed = urlsplit(server_url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise DeliveryError("central server must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise DeliveryError("server URL must be an origin without credentials or path")
        if not server_id or not device_id:
            raise DeliveryError("pinned server_id and device_id required")
        self.server_url = server_url.rstrip("/")
        self.server_id = server_id
        self.device_id = device_id
        self.key_path = Path(key_path) if key_path is not None else None
        self.signer = signer or self._sign
        self.transport = transport or self._request
        self.token: str | None = None
        self.token_until = 0.0

    def _sign(self, message: bytes) -> bytes:
        if self.key_path is None:
            raise DeliveryError("Ed25519 private key path required")
        # Lazy dependency: live world and Manager never import a crypto runtime.
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise DeliveryError("device key must be Ed25519")
        return key.sign(message)

    def _request(self, path: str, payload: dict[str, Any], token: str | None) -> tuple[int, dict[str, Any]]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = "Device " + token
        req = Request(self.server_url + path, data=_canonical(payload), headers=headers, method="POST")
        opener = build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=8) as response:
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise DeliveryError("oversized central response")
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise DeliveryError("invalid central JSON response")
                return response.status, value
        except HTTPError as exc:
            # Never log request body, authorization token, or upstream response.
            return exc.code, {}
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise DeliveryError("central transport unavailable or invalid") from exc

    def _authenticate(self) -> None:
        path = "/api/server/v1/device-auth/"
        status, challenge = self.transport(path + "challenge", {"device_id": self.device_id}, None)
        if status != 200 or challenge.get("schema") != "memoria-server-device-challenge/v1":
            raise DeliveryError("device challenge rejected")
        if challenge.get("server_id") != self.server_id or challenge.get("device_id") != self.device_id:
            raise DeliveryError("server/device identity mismatch")
        message = challenge.get("signing_message")
        challenge_id = challenge.get("challenge_id")
        nonce = challenge.get("nonce")
        if not isinstance(message, str) or not isinstance(challenge_id, str) or not challenge_id or not isinstance(nonce, str):
            raise DeliveryError("invalid signed challenge")
        expected_message = (
            "memoria-server-device-auth/v1\n" + self.server_id + "\n"
            + self.device_id + "\n" + challenge_id + "\n" + nonce
        )
        if message != expected_message:
            raise DeliveryError("unexpected device challenge signing message")
        signature = base64.urlsafe_b64encode(self.signer(expected_message.encode("utf-8"))).decode("ascii").rstrip("=")
        status, result = self.transport(path + "verify", {
            "device_id": self.device_id,
            "challenge_id": challenge_id,
            "signature": signature,
        }, None)
        if status != 200 or result.get("schema") != "memoria-server-device-token/v1":
            raise DeliveryError("device challenge verification rejected")
        if result.get("device_id") != self.device_id or result.get("token_type") != "Device":
            raise DeliveryError("device token identity mismatch")
        token = result.get("token")
        expires_in = result.get("expires_in")
        if not isinstance(token, str) or len(token) < 20 or isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in < 60:
            raise DeliveryError("invalid device session")
        self.token = token
        self.token_until = time.monotonic() + expires_in - 20

    def send(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if self.token is None or time.monotonic() >= self.token_until:
            self._authenticate()
        status, receipt = self.transport(OBSERVE_PATH, envelope, self.token)
        if status == 401:
            self.token = None
            self._authenticate()
            status, receipt = self.transport(OBSERVE_PATH, envelope, self.token)
        if status != 201 or receipt.get("schema") != RECEIPT_SCHEMA:
            raise DeliveryError(f"central observation not acknowledged (HTTP {status})")
        if not (
            receipt.get("status") in {"stored", "duplicate"}
            and receipt.get("record_key") == envelope["record_key"]
            and receipt.get("content_sha256") == envelope["content_sha256"]
            and receipt.get("episode_id") == envelope["source"]["episode_id"]
            and receipt.get("server_id") == self.server_id
            and receipt.get("device_id") == self.device_id
            and receipt.get("namespace") == "live:" + envelope["source"]["world_id"]
            and receipt.get("world_mutated") is False
            and receipt.get("selection_authority") is False
            and isinstance(receipt.get("evidence_id"), str)
            and receipt["evidence_id"] == "live-obs:" + envelope["record_key"][:40]
        ):
            raise DeliveryError("central receipt identity or authority mismatch")
        persistence = receipt.get("persistence")
        if not isinstance(persistence, dict) or not all(
            isinstance(persistence.get(k), str) and persistence[k]
            for k in ("backend", "state_id", "sha256")
        ) or not _HEX64.fullmatch(persistence["sha256"]):
            raise DeliveryError("central durable persistence receipt missing")
        return receipt


def deliver_next(
    *, episode_file: Path, world_file: Path, checkpoint_file: Path,
    device: DeviceSession,
) -> dict[str, Any]:
    """Process at most one source event; checkpoint after validated ACK only."""
    checkpoint_file = Path(checkpoint_file)
    ledger = Path(episode_file)
    lock_file = checkpoint_file.with_suffix(".lock")
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DeliveryError("another sync process already owns this cursor") from exc
        saved = _read_checkpoint(checkpoint_file)
        cursor = saved["cursor"] if saved else 0
        preview = preview_episode_batch(ledger, Path(world_file), cursor=cursor, limit=1)
        identity = preview["ledger_identity"]
        world_id = preview["world_id"]
        if saved:
            if saved["ledger_identity"] != identity or saved["world_id"] != world_id:
                raise DeliveryError("ledger identity/world changed; manual reconciliation required")
            if _anchor(ledger, cursor, identity) != saved["anchor_sha256"]:
                raise DeliveryError("ledger checkpoint anchor changed")
        next_cursor = preview["candidate_next_cursor"]
        if next_cursor == cursor:
            return {"status": "waiting_complete_record", "cursor": cursor, "ack": False}
        rows = preview["episodes"]
        receipt = device.send(rows[0]) if rows else None
        anchor = _anchor(ledger, next_cursor, identity)
        state = {
            "schema": CHECKPOINT_SCHEMA,
            "cursor": next_cursor,
            "ledger_identity": identity,
            "world_id": world_id,
            "anchor_sha256": anchor,
            "last_record_key": rows[0]["record_key"] if rows else (saved or {}).get("last_record_key"),
            "last_content_sha256": rows[0]["content_sha256"] if rows else (saved or {}).get("last_content_sha256"),
            "acknowledged": ((saved or {}).get("acknowledged") or 0) + int(receipt is not None),
            "updated_at_unix": time.time(),
        }
        _save_json_atomic(checkpoint_file, state)
        return {
            "status": "acknowledged" if receipt else "filtered_non_nov_record",
            "cursor": next_cursor, "ack": bool(receipt),
            "record_key": state["last_record_key"],
        }
