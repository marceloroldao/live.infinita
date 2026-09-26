from __future__ import annotations

import json
import sys
from pathlib import Path

WORLD_RUNTIME = Path(__file__).resolve().parents[1] / "apps" / "world-runtime"
sys.path.insert(0, str(WORLD_RUNTIME))

from plan_ledger import PlanLedger, PlanLedgerError


def _valid_row(plan_id: str) -> bytes:
    return (json.dumps({"plan_id": plan_id, "status": "planned"}) + "\n").encode()


def test_history_recovers_only_torn_final_record(tmp_path: Path) -> None:
    path = tmp_path / "plans.jsonl"
    good = _valid_row("p1")
    torn = b'{"plan_id":"p2","status":'
    path.write_bytes(good + torn)

    ledger = PlanLedger(path)

    assert ledger.history() == [{"plan_id": "p1", "status": "planned"}]
    assert path.read_bytes() == good
    assert (tmp_path / "plans.jsonl.torn-tail").read_bytes() == torn


def test_history_recovers_nul_tail_seen_in_production(tmp_path: Path) -> None:
    path = tmp_path / "plans.jsonl"
    good = _valid_row("p1")
    path.write_bytes(good + (b"\x00" * 940))

    assert PlanLedger(path).history() == [{"plan_id": "p1", "status": "planned"}]
    assert path.read_bytes() == good
    assert (tmp_path / "plans.jsonl.torn-tail").read_bytes() == b"\x00" * 940


def test_history_refuses_corruption_in_middle(tmp_path: Path) -> None:
    path = tmp_path / "plans.jsonl"
    path.write_bytes(_valid_row("p1") + b"not-json\n" + _valid_row("p2"))

    try:
        PlanLedger(path).history()
    except PlanLedgerError as exc:
        assert "corrupt plan ledger" in str(exc)
    else:
        raise AssertionError("middle corruption must fail closed")

    assert path.read_bytes().endswith(_valid_row("p2"))
    assert not (tmp_path / "plans.jsonl.torn-tail").exists()


def test_append_is_durable_and_jsonl_valid(tmp_path: Path) -> None:
    path = tmp_path / "plans.jsonl"
    ledger = PlanLedger(path)
    row = {"plan_id": "p1", "status": "planned", "text": "ação"}

    assert ledger._append(row) == row
    assert path.read_bytes().endswith(b"\n")
    assert ledger.history() == [row]
