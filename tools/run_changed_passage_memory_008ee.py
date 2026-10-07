#!/usr/bin/env python3
"""Reuse the pinned real-core transport for a physically changed passage."""
import argparse
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("physical_memory_transport", ROOT / "tools/run_physical_memory_comparison_008ed.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=pathlib.Path, default=pathlib.Path("/home/etbra/008bz-godot-test"))
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    transport.SCRIPT = ROOT / "tests/godot_changed_passage_memory_008ee.gd"
    result, first, second = transport.compare(args.project)
    result["schema"] = "live-infinita-changed-passage-memory-comparison/v1"
    result["scope"] = "isolated_real_capsule_changed_passage_with_real_pinned_core"
    result["training_opening_z"] = -30.0
    result["comparison_opening_z"] = -130.0
    result["limitations"][0] = "One deterministic changed wall/gap; not statistical generalization."
    result["limitations"].append("Reaching a free wall end is distinct from discovering the moved gap.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "CHANGED_PASSAGE_MEMORY_COMPARISON_008EE.json").write_text(json.dumps(result, indent=2)+"\n")
    (args.output_dir / "CHANGED_PASSAGE_MEMORY_COLD_008EE.txt").write_text(first)
    (args.output_dir / "CHANGED_PASSAGE_MEMORY_CORE_008EE.txt").write_text(second)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
