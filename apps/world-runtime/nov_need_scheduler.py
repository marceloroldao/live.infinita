from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class NeedState:
    """Minimal agent-local pressure state.

    Needs are not facts about the world and are not stored as Memoria.ia knowledge.
    They are local autonomous state that evolves with logical time and is relieved
    only by actions the world explicitly exposes as capable of serving that need.
    """

    tick_id: int
    pressures: tuple[tuple[str, int], ...]

    def pressure(self, need_id: str) -> int:
        for stored_id, value in self.pressures:
            if stored_id == need_id:
                return value
        return 0


@dataclass(frozen=True, slots=True)
class NeedActionDecision:
    need_id: str
    pressure: int
    proposal: dict[str, Any]
    reason: str


def make_need_state(*, tick_id: int, pressures: Mapping[str, int]) -> NeedState:
    if tick_id < 0:
        raise ValueError("tick_id must be >= 0")
    normalized = []
    for need_id, pressure in pressures.items():
        if not need_id:
            raise ValueError("need_id must be non-empty")
        value = int(pressure)
        if value < 0:
            raise ValueError("pressure must be >= 0")
        normalized.append((str(need_id), value))
    normalized.sort(key=lambda item: item[0])
    return NeedState(tick_id=tick_id, pressures=tuple(normalized))


def advance_needs(
    state: NeedState,
    *,
    tick_id: int,
    growth_per_tick: Mapping[str, int] | None = None,
    cap: int = 1_000_000,
) -> NeedState:
    """Advance pressures using logical time only.

    Growth is explicit agent physiology/configuration, not a learned fact and not a
    semantic rule inside Memoria.ia. The default is +1 per tick for every known need.
    """
    if tick_id < state.tick_id:
        raise ValueError("tick_id cannot move backwards")
    if cap < 1:
        raise ValueError("cap must be >= 1")

    elapsed = tick_id - state.tick_id
    rates = growth_per_tick or {}
    values: dict[str, int] = {}
    for need_id, pressure in state.pressures:
        rate = int(rates.get(need_id, 1))
        if rate < 0:
            raise ValueError("growth rates must be >= 0")
        values[need_id] = min(cap, pressure + elapsed * rate)
    return make_need_state(tick_id=tick_id, pressures=values)


def relieve_need(
    state: NeedState,
    need_id: str,
    *,
    amount: int | None = None,
) -> NeedState:
    """Relieve one need after an actually committed action.

    amount=None resets that pressure. A finite amount subtracts without going below 0.
    """
    if not need_id:
        raise ValueError("need_id must be non-empty")
    values = dict(state.pressures)
    if need_id not in values:
        raise ValueError("unknown need_id")

    if amount is None:
        values[need_id] = 0
    else:
        amount = int(amount)
        if amount < 0:
            raise ValueError("amount must be >= 0")
        values[need_id] = max(0, values[need_id] - amount)
    return make_need_state(tick_id=state.tick_id, pressures=values)


def _rule_for_proposal(world: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any] | None:
    rule_id = str((proposal.get("parameters") or {}).get("rule_id") or "")
    if not rule_id:
        return None
    for rule in (world.get("rules") or {}).get("actions") or ():
        if str(rule.get("rule_id") or "") == rule_id:
            return rule
    return None


def proposal_need_affordances(
    world: dict[str, Any],
    proposal: dict[str, Any],
) -> tuple[str, ...]:
    """Read world-declared affordances without changing proposal validity."""
    rule = _rule_for_proposal(world, proposal)
    if not rule:
        return ()
    values = []
    seen = set()
    for value in rule.get("need_affordances") or ():
        need_id = str(value)
        if need_id and need_id not in seen:
            seen.add(need_id)
            values.append(need_id)
    return tuple(values)


def select_need_action(
    *,
    world: dict[str, Any],
    proposals: Iterable[dict[str, Any]],
    needs: NeedState,
) -> NeedActionDecision | None:
    """Select a valid world proposal for the strongest currently serviceable need.

    Selection is deterministic and ordinal. It never creates an action and never
    changes World State. Ties in pressure resolve by need_id, then action/proposal_id.
    """
    proposals = tuple(proposals)
    ranked_needs = sorted(
        ((need_id, pressure) for need_id, pressure in needs.pressures if pressure > 0),
        key=lambda item: (-item[1], item[0]),
    )

    for need_id, pressure in ranked_needs:
        candidates = [
            proposal
            for proposal in proposals
            if need_id in proposal_need_affordances(world, proposal)
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda item: (
                str(item.get("action") or ""),
                str(item.get("target") or ""),
                str(item.get("proposal_id") or ""),
            )
        )
        return NeedActionDecision(
            need_id=need_id,
            pressure=pressure,
            proposal=candidates[0],
            reason="highest-pressure-serviceable-need",
        )
    return None
