#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

BASE_ENDPOINT = "http://127.0.0.1:8788/api/v1/structural/associations/sync"
DEFAULT_MAX_OBSERVATIONS = 2
MAX_OBSERVATIONS_PER_RUN = 16


class ConsolidationError(RuntimeError):
    pass


def _endpoint(max_observations: int) -> str:
    return f"{BASE_ENDPOINT}?max_observations={max_observations}"


def _post_local(max_observations: int) -> dict[str, Any]:
    api_key = os.environ.get("MEMORIA_API_KEY", "")
    if len(api_key) < 32:
        raise ConsolidationError("local_api_key_unconfigured")
    request = Request(
        _endpoint(max_observations),
        data=b"",
        method="POST",
        headers={"Accept": "application/json", "X-Memoria-Key": api_key},
    )
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=60) as response:
            raw = response.read(16385)
            if response.status != 200 or len(raw) > 16384:
                raise ConsolidationError("invalid_sync_response")
        value = json.loads(raw)
    except HTTPError as exc:
        raise ConsolidationError(f"sync_http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise ConsolidationError("sync_endpoint_unavailable") from exc
    if not isinstance(value, dict):
        raise ConsolidationError("invalid_sync_response")
    return value


def _validate_response(value: dict[str, Any], max_observations: int) -> dict[str, int]:
    replayed = value.get("association_sync_observations")
    declared_max = value.get("max_observations")
    associations = value.get("associations")
    if (
        type(replayed) is not int
        or replayed < 0
        or replayed > max_observations
        or declared_max != max_observations
        or not isinstance(associations, dict)
    ):
        raise ConsolidationError("sync_ack_mismatch")
    pending = associations.get("pending_observations")
    raw = associations.get("raw_observations")
    derived = associations.get("derived_observations")
    if any(type(item) is not int or item < 0 for item in (pending, raw, derived)):
        raise ConsolidationError("sync_status_invalid")
    if raw - derived != pending:
        raise ConsolidationError("sync_cursor_inconsistent")
    return {
        "replayed": replayed,
        "pending": pending,
        "raw": raw,
        "derived": derived,
    }


def consolidate_once(
    max_observations: int = DEFAULT_MAX_OBSERVATIONS,
    *,
    send: Callable[[int], dict[str, Any]] = _post_local,
) -> dict[str, int]:
    if not 1 <= int(max_observations) <= MAX_OBSERVATIONS_PER_RUN:
        raise ConsolidationError("max_observations_out_of_range")
    return _validate_response(send(int(max_observations)), int(max_observations))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-observations", type=int, default=DEFAULT_MAX_OBSERVATIONS)
    args = parser.parse_args()
    try:
        result = consolidate_once(args.max_observations)
    except ConsolidationError as exc:
        print(f"STRUCTURAL_ASSOCIATION_CONSOLIDATION_BLOCKED {exc}")
        return 1
    print(
        "STRUCTURAL_ASSOCIATION_CONSOLIDATION_OK "
        + json.dumps(
            {
                "max_observations": args.max_observations,
                **result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
