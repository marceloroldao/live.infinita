"""MVP-018D unprivileged preflight: exact native BDR + real V2 mirror on scratch."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from bdr.atomic import AtomicBDR
from memoria_resolutiva.external_episode_contract import ExternalEpisodeRequest, FORMAT, canonical
from memoria_resolutiva.external_episode_incremental import IncrementalExternalEpisodeStore
from memoria_resolutiva.external_episode_bdr_mirror import create_verified_mirror


def main() -> None:
    lib = Path(os.environ["BDR_ATOMIC_LIBRARY"])
    scratch_parent = Path(os.environ["MVP018D_SCRATCH"])
    with tempfile.TemporaryDirectory(dir=scratch_parent) as scratch:
        root = Path(scratch)
        native = AtomicBDR.open(root / "abi-probe", library_path=lib)
        assert native._lib.bdr_atomic_c_abi_version() == 2
        native.close()
        store = IncrementalExternalEpisodeStore(root / "source")
        for i in range(3):
            plan = f"preflight_{i}"
            identity = {
                "system": "live.infinita", "world_id": "preflight-world",
                "entity_id": "nov", "episode_id": "plan:" + plan,
            }
            unsigned = {
                "schema": FORMAT,
                "record_key": sha256(canonical(identity)).hexdigest(),
                "source": {
                    **identity, "source_schema": "npc_episode_v1",
                    "source_kind": "need_outcome", "plan_id": plan,
                    "proposal_id": "proposal_" + plan, "plan_revision": 0,
                },
                "observation": {
                    "logical_tick": i, "need": "curiosity",
                    "target_entity_id": "ancient_tree", "strategy_id": "explore",
                    "context": {"period": "day", "weather": "clear",
                                "region_id": "clearing", "danger_level": 0.1},
                    "outcome": {"satisfaction": 0.5, "observed_risk": 0.1,
                                "elapsed_ticks": 3, "preemptions": 0, "replans": 0},
                },
                "authority": "observed-outcome-only",
                "world_write_authority": False,
            }
            request = ExternalEpisodeRequest.model_validate({
                **unsigned, "content_sha256": sha256(canonical(unsigned)).hexdigest(),
            })
            assert store.observe(request)["stored"] is True
        proof = create_verified_mirror(store.path, root / "mirror", library_path=lib)
        assert proof["source_snapshot_records"] == proof["inserted_into_bdr"] == 3
        assert proof["verified_cold_restart"] and proof["verified_idempotent_replay"]
        assert proof["bdr_durable_sequence"] == 3
        assert not proof["backend_cutover"] and not proof["production_checkpoint_advanced"]
        store.close()
    print("MVP018D_REAL_NATIVE_SCRATCH_PREFLIGHT_OK", flush=True)


if __name__ == "__main__":
    main()
