from __future__ import annotations

import os
import sys
from pathlib import Path


MEMORIA_COMMIT = "45fdbe5b2404e00d40f492c2e503172a8eb22433"
BIT_ANALYZE_COMMIT = "2192c61e514a7bb500500ab9fff63bd42940dc52"


def configure_runtime_paths() -> dict[str, str]:
    here = Path(__file__).resolve()
    repo_root = here.parents[2]

    memoria_root = Path(
        os.environ.get(
            "MEMORIA_IA_ROOT",
            repo_root / ".vendor" / "memoria.ia",
        )
    ).resolve()
    bit_root = Path(
        os.environ.get(
            "BIT_ANALYZE_ROOT",
            repo_root / ".vendor" / "bit.analyze",
        )
    ).resolve()

    paths = {
        "world_runtime": str((repo_root / "apps" / "world-runtime").resolve()),
        "memoria_src": str((memoria_root / "src").resolve()),
        "bit_temporal": str(
            (
                bit_root
                / "experiments"
                / "temporal_multimodal"
            ).resolve()
        ),
    }
    for value in reversed(tuple(paths.values())):
        if value not in sys.path:
            sys.path.insert(0, value)
    return paths
