#!/usr/bin/env python3
"""Import only the glTF models needed from Quaternius Stylized Nature MegaKit Standard.

The vendor ZIP is obtained by the operator from the official Quaternius/itch.io page.
This command does not scrape a download endpoint or require paid Source files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import stat
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "apps/renderer-godot/assets/quaternius/stylized_nature_megakit"
)
RES_PREFIX = "res://assets/quaternius/stylized_nature_megakit/models/"
SOURCE_URL = "https://quaternius.com/packs/stylizednaturemegakit.html"
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 20000

KINDS = {
    "tree": ("tree", "pine", "oak", "birch", "willow", "palm", "fir"),
    "rock": ("rock", "stone", "boulder", "cliff"),
    "plant": ("grass", "plant", "flower", "bush", "shrub", "mushroom", "fern", "reed"),
}


def safe_name(name: str) -> str:
    """Prevent absolute paths, traversal, drive prefixes and ambiguous separators."""
    if not name or "\\" in name or name.startswith("/"):
        raise ValueError(f"Unsafe ZIP path: {name!r}")
    parts = PurePosixPath(name).parts
    if any(p in ("", ".", "..") or ":" in p for p in parts):
        raise ValueError(f"Unsafe ZIP path: {name!r}")
    normalized = "/".join(parts)
    if normalized != name.rstrip("/"):
        raise ValueError(f"Unsafe ZIP path: {name!r}")
    return normalized


def classify(name: str) -> str:
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", Path(name).stem)
    words = re.sub(r"[^a-zA-Z]+", " ", words).lower().split()
    for kind, keywords in KINDS.items():
        if any(any(w.startswith(k) for k in keywords) for w in words):
            return kind
    return "nature"


def collect(archive: ZipFile) -> tuple[dict[str, object], list[str], list[str]]:
    members: dict[str, object] = {}
    for info in archive.infolist():
        path = safe_name(info.filename)
        if info.is_dir():
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"ZIP symlink not permitted: {path}")
        if path in members:
            raise ValueError(f"Duplicate ZIP path: {path}")
        members[path] = info
    if len(members) > MAX_ENTRIES:
        raise ValueError("ZIP contains too many files")

    glb = sorted(p for p in members if p.lower().endswith(".glb"))
    gltf = sorted(p for p in members if p.lower().endswith(".gltf"))
    models = glb if glb else gltf
    if not models:
        raise ValueError("No .glb or .gltf models found in this ZIP")
    needed = set(models)
    if not glb:
        for model in models:
            document = json.loads(archive.read(members[model]).decode("utf-8"))
            for record in list(document.get("buffers", [])) + list(document.get("images", [])):
                uri = record.get("uri", "")
                if not isinstance(uri, str) or not uri or uri.startswith("data:"):
                    continue
                parsed = urlsplit(uri)
                if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                    raise ValueError(f"External/unsupported glTF URI in {model}: {uri}")
                # POSIX resolution is relative to the glTF file inside the ZIP.
                dependency = posixpath.normpath(
                    posixpath.join(posixpath.dirname(model), unquote(parsed.path))
                )
                safe_name(dependency)
                if dependency not in members:
                    raise ValueError(f"Missing glTF dependency: {model} -> {dependency}")
                needed.add(dependency)

    size = sum(members[p].file_size for p in needed)
    if size > MAX_EXPANDED_BYTES:
        raise ValueError("Expanded glTF selection exceeds 2 GiB")
    return members, models, sorted(needed)


def manifest_for(models: list[str]) -> dict:
    assets = []
    for model in models:
        normalized = re.sub(r"[^a-z0-9]+", "-", Path(model).stem.lower()).strip("-")
        digest = hashlib.sha256(model.encode("utf-8")).hexdigest()[:8]
        kind = classify(Path(model).stem)
        assets.append({
            "id": f"{kind}/{normalized or 'asset'}-{digest}",
            "kind": kind,
            "label": Path(model).stem,
            "path": RES_PREFIX + model,
        })
    return {
        "schema_version": 1,
        "pack": "Quaternius Stylized Nature MegaKit",
        "edition": "Standard",
        "license": "CC0-1.0",
        "source": SOURCE_URL,
        "assets": assets,
    }


def import_zip(zip_path: Path, output: Path, dry_run: bool = False) -> dict:
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    with ZipFile(zip_path) as archive:
        members, models, needed = collect(archive)
        manifest = manifest_for(models)
        if dry_run:
            return manifest
        output.parent.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=".quaternius-stage-", dir=output.parent))
        try:
            for name in needed:
                target = staged / "models" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(members[name]) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            (staged / "catalog.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            backup = output.with_name(output.name + ".backup")
            if backup.exists():
                raise FileExistsError(f"Remove prior interrupted backup first: {backup}")
            if output.exists():
                output.rename(backup)
            try:
                staged.rename(output)
            except Exception:
                if backup.exists():
                    backup.rename(output)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if staged.exists():
                shutil.rmtree(staged)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, help="Official Standard edition ZIP")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true", help="Inspect without extracting")
    args = parser.parse_args()
    manifest = import_zip(args.zip, args.output, args.dry_run)
    totals = Counter(asset["kind"] for asset in manifest["assets"])
    print(f"{'Would import' if args.dry_run else 'Imported'} {len(manifest['assets'])} models: {dict(totals)}")
    print(f"Catalog: {args.output / 'catalog.json'}")
    print("Existing 2D live scene was not modified.")


if __name__ == "__main__":
    main()
