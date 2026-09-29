"""Render the Nov preparer unit for one immutable, public-code release.

This module is a packaging contract. It does not install/start/enable systemd
units or read private Memoria.ia data.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import stat

SCHEMA = "live-infinita-nov-release-contract/v1"
CORE = Path("/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src")
PYTHON = Path("/opt/live.infinita/.venv/bin/python")
MODULES = (
    "memoria_v2_adapter", "nov_memory_recall_shadow", "nov_memory_recall_cache",
    "nov_memory_context_shadow", "nov_trajectory_recall_shadow",
    "nov_memory_hybrid_shadow", "nov_memory_dual_lane_shadow",
    "nov_memory_async_prepare", "nov_memory_current_frame",
    "nov_memory_continuous", "nov_memory_release_contract",
)
TOKENS = {
    "@NOV_RELEASE_ROOT@": "release_root",
    "@PINNED_CORE_ROOT@": "core",
    "@VENV_PYTHON@": "python",
}


class ReleaseBlocked(ValueError):
    pass


def _simple_absolute(path: Path, *, allow_symlink: bool = False) -> str:
    raw = str(path)
    if (not path.is_absolute() or not raw.isascii()
            or re.fullmatch(r"/[A-Za-z0-9_./-]+", raw) is None
            or any(part in (".", "..") for part in path.parts)):
        raise ReleaseBlocked("release_path_invalid")
    if not allow_symlink and path.is_symlink():
        raise ReleaseBlocked("release_path_symlink")
    return raw


def validate_release(root: Path) -> None:
    _simple_absolute(root)
    if not root.is_dir():
        raise ReleaseBlocked("release_directory_missing")
    mode = root.stat(follow_symlinks=False).st_mode
    if not stat.S_ISDIR(mode) or mode & 0o022:
        raise ReleaseBlocked("release_root_permissions")
    for module in MODULES:
        file = root / (module + ".py")
        if file.is_symlink() or not file.is_file():
            raise ReleaseBlocked("release_module_missing")
        mode = file.stat(follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode) or mode & 0o022 or mode & 0o444 == 0:
            raise ReleaseBlocked("release_module_permissions")


def render_unit(template: str, root: Path, *, core: Path = CORE,
                python: Path = PYTHON) -> str:
    validate_release(root)
    values = {
        "@NOV_RELEASE_ROOT@": _simple_absolute(root),
        "@PINNED_CORE_ROOT@": _simple_absolute(core),
        "@VENV_PYTHON@": _simple_absolute(python, allow_symlink=True),
    }
    if not python.is_file() or not (core / "memoria_resolutiva/external_episode_incremental.py").is_file():
        raise ReleaseBlocked("pinned_runtime_missing")
    for token in TOKENS:
        if template.count(token) < 1:
            raise ReleaseBlocked("unit_template_incomplete")
    rendered = template
    for token, value in values.items():
        rendered = rendered.replace(token, value)
    if (re.search(r"@[A-Z][A-Z_]+@", rendered)
            or "User=liveinfinita" not in rendered
            or "Group=liveinfinita" not in rendered
            or "ProtectSystem=strict" not in rendered
            or "ReadOnlyPaths=/var/lib/live-infinita/memoria-local" not in rendered
            or "ReadOnlyPaths=/var/lib/live-infinita/autonomous-world" not in rendered
            or "NoNewPrivileges=true" not in rendered
            or "IPAddressDeny=any" not in rendered
            or "Restart=on-failure" not in rendered
            or "ExecStart=" + str(python) + " " + str(root) + "/nov_memory_continuous.py" not in rendered
            or "ReadWritePaths=/var/lib/live-infinita/memoria-local" in rendered):
        raise ReleaseBlocked("unsafe_unit_contract")
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        rendered = render_unit(args.template.read_text(encoding="utf-8"), args.root)
        if args.output.is_symlink() or args.output.parent != args.root:
            raise ReleaseBlocked("unit_output_invalid")
        args.output.write_text(rendered, encoding="utf-8")
        args.output.chmod(0o600)
    except (OSError, ReleaseBlocked) as exc:
        raise SystemExit("MVP018N_RELEASE_BLOCKED " + type(exc).__name__) from exc
    print("MVP018N_RENDERED_UNIT_OK " + SCHEMA)


if __name__ == "__main__":
    main()
