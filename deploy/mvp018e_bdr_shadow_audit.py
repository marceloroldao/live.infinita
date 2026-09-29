"""Owner-only audit of a completed MVP-018D BDR shadow report.

Print only booleans and counts. Do not expose observation contents, identities,
source JSON, full fingerprints or Nov's private checkpoint.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "memoria-v2-bdr-observed-episode-mirror-proof/v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class AuditError(ValueError):
    """Private mirror is absent, incomplete or fails the proof contract."""


def _private(path: Path, *, directory: bool) -> None:
    if path.is_symlink():
        raise AuditError("symlink_not_allowed")
    info = path.stat(follow_symlinks=False)
    if info.st_uid != os.geteuid():
        raise AuditError("owner_mismatch")
    expected = 0o700 if directory else 0o600
    if stat.S_IMODE(info.st_mode) != expected:
        raise AuditError("permissions_mismatch")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise AuditError("file_type_mismatch")


def audit(root: Path) -> dict[str, object]:
    _private(root, directory=True)
    runs = sorted(
        (entry for entry in root.iterdir() if entry.name[:1].isdigit()),
        key=lambda entry: entry.name, reverse=True,
    )
    if not runs:
        raise AuditError("no_bdr_runs")
    # Fail closed on newest run: never silently report an older successful run
    # after a newer attempted mirror failed.
    latest = runs[0]
    _private(latest, directory=True)
    report_path = latest / "report.json"
    _private(report_path, directory=False)
    if report_path.stat().st_size > 16384:
        raise AuditError("oversized_report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AuditError("invalid_report") from exc
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise AuditError("schema_mismatch")

    count = report.get("source_snapshot_records")
    inserted = report.get("inserted_into_bdr")
    sequence = report.get("bdr_durable_sequence")
    if (type(count) is not int or count <= 0 or type(inserted) is not int
            or inserted != count or type(sequence) is not int or sequence <= 0):
        raise AuditError("count_or_durability_mismatch")
    for name in ("record_manifest_sha256", "evidence_graph_sha256"):
        value = report.get(name)
        if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
            raise AuditError("fingerprint_invalid")
    for name in ("sqlite_snapshot_bytes", "bdr_candidate_bytes"):
        value = report.get(name)
        if type(value) is not int or value <= 0:
            raise AuditError("missing_snapshot_or_bdr")
    if report.get("source_mode") != "sqlite-online-backup-read-only":
        raise AuditError("source_mode_invalid")

    required_true = (
        "checkpoint_watermark_present", "sqlite_source_inode_unchanged",
        "verified_cold_restart", "verified_idempotent_replay",
    )
    required_false = (
        "backend_cutover", "production_checkpoint_advanced",
        "world_mutated", "central_sync",
    )
    for name in required_true:
        if report.get(name) is not True:
            raise AuditError("proof_failed_" + name)
    for name in required_false:
        if report.get(name) is not False:
            raise AuditError("unsafe_" + name)
    stable = report.get("checkpoint_unchanged_during_copy")
    if type(stable) is not bool:
        raise AuditError("checkpoint_stability_unknown")
    return {
        "snapshot_records": count,
        "bdr_durable_sequence": sequence,
        "checkpoint_unchanged_during_copy": stable,
        "snapshot_parity": True,
        "backend_cutover": False,
        "live_caught_up_claim": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirrors-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.mirrors_root)
    except (OSError, AuditError) as exc:
        raise SystemExit("MVP018E_BDR_AUDIT_BLOCKED " + (
            str(exc) if isinstance(exc, AuditError) else "private_report_inaccessible"
        )) from exc
    print("MVP018E_BDR_SHADOW_AUDIT_OK " +
          json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
