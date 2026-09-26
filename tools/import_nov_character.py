#!/usr/bin/env python3
"""Select a Nov body and optional animation clip library from Quaternius Standard ZIPs.

Only extracts glTF and its dependencies plus one non-root-motion Godot/Unreal
animation GLB. The Source/Pro editions are not needed and are never fetched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import stat
import struct
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from tools.import_quaternius_nature import safe_name

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "apps/renderer-godot/assets/quaternius/nov_character"
RES_BASE = "res://assets/quaternius/nov_character/"
MAX_EXPANDED = 300 * 1024 * 1024
MAX_MEMBER = 95 * 1024 * 1024
AUTHOR = "https://quaternius.com/packs/universalbasecharacters.html"
ANIMATIONS = "https://quaternius.com/packs/universalanimationlibrary.html"


def _members(z: ZipFile) -> dict[str, object]:
    found = {}
    for info in z.infolist():
        name = safe_name(info.filename)
        if info.is_dir():
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"ZIP symlink not permitted: {name}")
        if name in found:
            raise ValueError(f"Duplicate member: {name}")
        if info.file_size > MAX_MEMBER:
            raise ValueError(f"Oversized member: {name}")
        found[name] = info
    return found


def _body_candidates(names: list[str]) -> list[str]:
    options = []
    for name in names:
        if not name.lower().endswith((".gltf", ".glb")):
            continue
        label = Path(name).stem.lower()
        if "female" not in label or "male" in label.replace("female", ""):
            continue
        if not any(term in label for term in ("fullbody", "full_body", "full-body")):
            continue
        # The default Nov rig is the regular female humanoid, not teen/superhero.
        weight = 0 if "regular" in label else 1 if "teen" in label else 2
        # Favor the export prepared for Godot/UE, avoid Unity FBX/OBJ paths.
        environment = 0 if "godot" in name.lower() else 1
        options.append((weight, environment, 0 if name.lower().endswith(".gltf") else 1, name))
    return [v[-1] for v in sorted(options)]


def _dependency_set(z: ZipFile, members: dict, body: str) -> list[str]:
    if body.lower().endswith(".glb"):
        return [body]
    doc = json.loads(z.read(members[body]).decode("utf-8"))
    needed = {body}
    for obj in list(doc.get("buffers", [])) + list(doc.get("images", [])):
        uri = obj.get("uri")
        if uri is None or str(uri).startswith("data:"):
            continue
        if not isinstance(uri, str):
            raise ValueError("Invalid glTF dependency URI")
        split = urlsplit(uri)
        if split.scheme or split.netloc or split.query or split.fragment:
            raise ValueError(f"Remote/unsupported glTF dependency: {uri}")
        ref = posixpath.normpath(posixpath.join(posixpath.dirname(body), unquote(split.path)))
        safe_name(ref)
        if ref not in members:
            raise ValueError(f"Missing dependency: {body} -> {ref}")
        needed.add(ref)
    if sum(members[p].file_size for p in needed) > MAX_EXPANDED:
        raise ValueError("Body selection too large")
    return sorted(needed)


def _animation_candidates(names: list[str]) -> list[str]:
    opts = []
    for name in names:
        if not name.lower().endswith(".glb"):
            continue
        label = Path(name).stem.lower()
        if label.endswith("_rm") or "rootmotion" in label or "root_motion" in label:
            continue
        if not any(word in label for word in ("ual", "animation", "standard")):
            continue
        priority = 0 if ("godot" in name.lower() or "unreal" in name.lower()) else 1
        opts.append((priority, len(name), name))
    return [x[-1] for x in sorted(opts)]


def _animation_names_from_glb(payload: bytes) -> list[str]:
    """Read only GLB JSON: inspect clip names without requiring Blender or Godot."""
    if len(payload) < 20 or payload[:4] != b"glTF":
        raise ValueError("Animation file is not a GLB")
    declared = struct.unpack_from("<I", payload, 8)[0]
    if declared != len(payload):
        raise ValueError("Corrupt GLB byte length")
    length, chunk_type = struct.unpack_from("<I4s", payload, 12)
    if chunk_type != b"JSON" or 20 + length > len(payload):
        raise ValueError("Missing GLB JSON chunk")
    doc = json.loads(payload[20:20 + length].decode("utf-8").rstrip(" \t\r\n\0"))
    return [str(a.get("name", f"clip_{i}")) for i, a in enumerate(doc.get("animations", []))]


def _pick_clip(clips: list[str], terms: tuple[str, ...]) -> str:
    for clip in clips:
        normalized = re.sub(r"[^a-z0-9]+", "_", clip.lower())
        if any(re.search(rf"(?:^|_){re.escape(term)}(?:_|$)", normalized) for term in terms):
            return clip
    return ""


def import_packs(
    body_zip: Path,
    animation_zip: Path | None = None,
    output: Path = DEFAULT_OUTPUT,
    dry_run: bool = False,
) -> dict:
    """Return deterministic catalog, optionally publishing assets atomically."""
    body_zip = Path(body_zip)
    if not body_zip.is_file():
        raise FileNotFoundError(body_zip)
    with ZipFile(body_zip) as archive:
        members = _members(archive)
        candidates = _body_candidates(sorted(members))
        if not candidates:
            raise ValueError("No female full-body glTF in Standard pack; inspect the archive")
        body = candidates[0]
        needed = _dependency_set(archive, members, body)
        body_sha = hashlib.sha256(body_zip.read_bytes()).hexdigest()
        if not dry_run:
            output.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".nov-stage-", dir=output.parent))
        else:
            stage = None
        try:
            if stage:
                for name in needed:
                    target = stage / "body" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(members[name]) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            animation_source_sha = ""
            animation_path = ""
            clips: list[str] = []
            if animation_zip:
                animation_zip = Path(animation_zip)
                with ZipFile(animation_zip) as animations:
                    candidates = _animation_candidates(sorted(_members(animations)))
                    if not candidates:
                        raise ValueError("No non-root-motion GLB available in animation Standard ZIP")
                    chosen = candidates[0]
                    metadata = animations.getinfo(chosen)
                    if metadata.file_size > MAX_MEMBER:
                        raise ValueError("Animation GLB exceeds Git file limit")
                    payload = animations.read(chosen)
                    clips = _animation_names_from_glb(payload)
                    animation_path = RES_BASE + "animations/" + Path(chosen).name
                    if stage:
                        folder = stage / "animations"
                        folder.mkdir(parents=True, exist_ok=True)
                        (folder / Path(chosen).name).write_bytes(payload)
                animation_source_sha = hashlib.sha256(animation_zip.read_bytes()).hexdigest()

            catalog = {
                "schema_version": 1,
                "character_id": "nov",
                "identity": "quaternius_universal_base_regular_female",
                "body_scene": RES_BASE + "body/" + body,
                "body_archive_sha256": body_sha,
                "body_source": AUTHOR,
                "animation_scene": animation_path,
                "animation_archive_sha256": animation_source_sha,
                "animation_source": ANIMATIONS if animation_zip else "",
                "animation_clips": clips,
                "semantic_clips": {
                    "idle": _pick_clip(clips, ("idle",)),
                    "walk": _pick_clip(clips, ("walk", "walking")),
                    "run": _pick_clip(clips, ("run", "jog", "sprint")),
                    "interact": _pick_clip(clips, ("interact", "pickup", "pick_up", "wave")),
                },
                "retarget_verified": False,
                "license": "CC0-1.0",
            }
            if stage:
                (stage / "catalog.json").write_text(
                    json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                backup = output.with_name(output.name + ".backup")
                if backup.exists():
                    raise FileExistsError(f"Prior interrupted install: {backup}")
                if output.exists():
                    output.rename(backup)
                try:
                    stage.rename(output)
                except Exception:
                    if backup.exists():
                        backup.rename(output)
                    raise
                if backup.exists():
                    shutil.rmtree(backup)
            return catalog
        finally:
            if stage and stage.exists():
                shutil.rmtree(stage)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--body-zip", type=Path, required=True)
    p.add_argument("--animations-zip", type=Path)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    manifest = import_packs(args.body_zip, args.animations_zip, args.output, args.dry_run)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    if args.dry_run:
        print("DRY RUN: No files written")
    else:
        print("Installed Nov visual assets (not loaded into production live).")


if __name__ == "__main__":
    main()
