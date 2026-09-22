from __future__ import annotations

from copy import deepcopy
from typing import Any

from npc_reordering_need_scheduler import NpcReorderingNeedScheduler


class NpcAuditedReorderingNeedScheduler(NpcReorderingNeedScheduler):
    """Add non-binding causal provenance to horizon goal reconsideration.

    This class does not change need selection, thresholding, cooldown, ranking,
    planning, approval or mutation authority. It only links a later scheduled
    decision back to the most recent horizon-reordered decision that deferred the
    same original need, provided that need has not already been reconsidered.
    """

    def _pending_reorder_for(self, npc_id: str, need: str) -> dict[str, Any] | None:
        npc_id = str(npc_id or "")
        need = str(need or "").strip().lower()
        if not npc_id or not need:
            return None
        for row in reversed(self.history()):
            if row.get("npc_id") != npc_id or row.get("status") != "scheduled":
                continue
            original_need = str(row.get("original_need") or row.get("need") or "").strip().lower()
            if original_need != need:
                continue
            if bool(row.get("horizon_reordered")):
                return deepcopy(row)
            # The latest scheduled decision for this original need was already a
            # normal reconsideration; do not link across multiple decision cycles.
            return None
        return None

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(row)
        if value.get("status") == "scheduled" and not bool(value.get("horizon_reordered")):
            npc_id = str(value.get("npc_id") or "")
            need = str(value.get("need") or "").strip().lower()
            original_need = str(value.get("original_need") or need).strip().lower()
            if need and need == original_need:
                source = self._pending_reorder_for(npc_id, need)
                if source is not None:
                    value["reconsidered_from_proposal_id"] = source.get("proposal_id")
                    value["reconsidered_from_tick"] = source.get("tick")
                    value["reconsidered_after_need"] = source.get("need")
                    value["reconsideration_schema"] = "npc_goal_reconsideration_v1"
        return super()._append(value)
