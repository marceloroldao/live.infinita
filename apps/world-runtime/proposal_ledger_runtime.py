from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mutation_decision_log import MutationDecisionLog
from proposal_ledger import ProposalLedger, ProposalLedgerError
from proposal_ledger_bridge import ProposalLedgerBridge


class DualWriteAIProposalStore:
    """Proxy preserving the legacy AI proposal API while mirroring to the ledger."""

    def __init__(self, legacy: Any, bridge: ProposalLedgerBridge, decisions: MutationDecisionLog) -> None:
        self.legacy = legacy
        self.bridge = bridge
        self.decisions = decisions

    def __getattr__(self, name: str) -> Any:
        return getattr(self.legacy, name)

    def create(self, **kwargs: Any) -> dict[str, Any]:
        row = self.legacy.create(**kwargs)
        if row.get("status") == "pending":
            self.bridge.mirror_ai(row)
        return row

    def mark_rejected(self, proposal_id: str, *, reason: str) -> dict[str, Any]:
        row = self.legacy.mark_rejected(proposal_id, reason=reason)
        try:
            self.bridge.reject_by_source("ai", proposal_id, decided_by="operator", reason=reason)
        except KeyError:
            pass
        return row

    def mark_committed(self, proposal_id: str, *, world_event_id: str | None = None) -> dict[str, Any]:
        row = self.legacy.mark_committed(proposal_id, world_event_id=world_event_id)
        if world_event_id:
            decision = _decision_for_event(self.decisions, world_event_id)
            if decision is not None:
                try:
                    self.bridge.commit_by_source(
                        "ai",
                        proposal_id,
                        decided_by="operator",
                        mutation_decision_id=str(decision.get("mutation_decision_id") or ""),
                        world_event_id=world_event_id,
                    )
                except KeyError:
                    pass
        return row


class AudienceProposalAppendMirror:
    """Mirrors legacy audience proposal append records to the unified ledger."""

    def __init__(
        self,
        *,
        append_fn: Callable[[Path, dict[str, Any]], None],
        audience_file: Path,
        bridge: ProposalLedgerBridge,
        decisions: MutationDecisionLog,
    ) -> None:
        self.append_fn = append_fn
        self.audience_file = Path(audience_file)
        self.bridge = bridge
        self.decisions = decisions

    def __call__(self, path: Path, record: dict[str, Any]) -> None:
        self.append_fn(path, record)
        if Path(path) != self.audience_file:
            return
        proposal_id = str(record.get("proposal_id") or "").strip()
        if not proposal_id:
            return
        status = str(record.get("status") or "pending").strip().lower()
        if status == "pending":
            self.bridge.mirror_audience(record)
            return
        if status == "rejected":
            try:
                self.bridge.reject_by_source(
                    "audience", proposal_id, decided_by="operator",
                    reason=str(record.get("rejection_reason") or "rejected"),
                )
            except KeyError:
                pass
            return
        if status == "committed":
            decision = _decision_for_context_proposal(self.decisions, proposal_id)
            if decision is None:
                return
            world_event_id = str(decision.get("world_event_id") or "").strip()
            mutation_decision_id = str(decision.get("mutation_decision_id") or "").strip()
            if not world_event_id or not mutation_decision_id:
                return
            try:
                self.bridge.commit_by_source(
                    "audience",
                    proposal_id,
                    decided_by="operator",
                    mutation_decision_id=mutation_decision_id,
                    world_event_id=world_event_id,
                )
            except KeyError:
                pass


def _decision_for_event(log: MutationDecisionLog, world_event_id: str) -> dict[str, Any] | None:
    for row in reversed(log.read_all()):
        if row.get("accepted") and row.get("world_event_id") == world_event_id:
            return row
    return None


def _decision_for_context_proposal(log: MutationDecisionLog, proposal_id: str) -> dict[str, Any] | None:
    for row in reversed(log.read_all()):
        if not row.get("accepted"):
            continue
        context = row.get("context") if isinstance(row.get("context"), dict) else {}
        metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        if str(metadata.get("proposal_id") or "") == proposal_id:
            return row
    return None


def install_runtime_proposal_ledger(core: Any, data_dir: Path) -> ProposalLedger:
    """Install compatibility dual-write adapters on an imported runtime module."""
    ledger = ProposalLedger(Path(data_dir) / "proposal-ledger.jsonl")
    bridge = ProposalLedgerBridge(ledger)
    decisions = MutationDecisionLog(Path(data_dir) / "mutation-decisions.jsonl")

    if not isinstance(core.ai_proposals, DualWriteAIProposalStore):
        core.ai_proposals = DualWriteAIProposalStore(core.ai_proposals, bridge, decisions)
    if not isinstance(core.append_jsonl, AudienceProposalAppendMirror):
        core.append_jsonl = AudienceProposalAppendMirror(
            append_fn=core.append_jsonl,
            audience_file=core.AUDIENCE_PROPOSALS_FILE,
            bridge=bridge,
            decisions=decisions,
        )
    return ledger
