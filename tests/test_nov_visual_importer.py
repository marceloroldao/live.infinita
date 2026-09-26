"""Nov vendor importer: deterministic selection, safety and honest animation contract."""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.import_nov_character import import_packs


def glb(animations: list[str]) -> bytes:
    doc = json.dumps({"asset": {"version": "2.0"}, "animations": [
        {"name": label, "channels": [], "samplers": []} for label in animations
    ]}).encode("utf-8")
    doc += b" " * (-len(doc) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(doc)) + struct.pack("<I4s", len(doc), b"JSON") + doc


class NovVisualImporterTests(unittest.TestCase):
    def make_body(self, path: Path) -> None:
        with ZipFile(path, "w") as archive:
            archive.writestr(
                "Base Characters/Godot - UE/Regular_Female_FullBody.gltf",
                json.dumps({
                    "asset": {"version": "2.0"},
                    "buffers": [{"uri": "Regular_Female_FullBody.bin", "byteLength": 4}],
                    "images": [{"uri": "../Textures/skin.png"}],
                }),
            )
            archive.writestr(
                "Base Characters/Godot - UE/Regular_Female_FullBody.bin", b"data"
            )
            archive.writestr("Base Characters/Textures/skin.png", b"image")
            archive.writestr("Base Characters/Godot - UE/Teen_Female_FullBody.gltf", b"{}")
            archive.writestr("Base Characters/FBX/Regular_Female_FullBody.fbx", b"unused")

    def test_selects_regular_female_gltf_and_exact_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.zip"
            anim = root / "animation.zip"
            self.make_body(body)
            with ZipFile(anim, "w") as zipfile:
                zipfile.writestr("Unreal-Godot/UAL_Standard_RM.glb", glb(["Idle"]))
                zipfile.writestr("Unreal-Godot/UAL_Standard.glb", glb(["Idle", "Walk", "Jog", "Wave"]))
                zipfile.writestr("Unity/UAL_Standard.fbx", b"unused")
            out = root / "nov"
            preview = import_packs(body, anim, out, dry_run=True)
            self.assertFalse(out.exists())
            result = import_packs(body, anim, out)
            self.assertEqual(preview, result)
            self.assertIn("Regular_Female_FullBody.gltf", result["body_scene"])
            self.assertEqual(result["semantic_clips"], {
                "idle": "Idle", "walk": "Walk", "run": "Jog", "interact": "Wave"
            })
            self.assertFalse(result["retarget_verified"])
            self.assertEqual(
                (out / "body/Base Characters/Textures/skin.png").read_bytes(), b"image"
            )
            self.assertFalse((out / "body/Base Characters/FBX").exists())
            self.assertTrue((out / "animations/UAL_Standard.glb").exists())
            self.assertFalse((out / "animations/UAL_Standard_RM.glb").exists())
            self.assertEqual(json.loads((out / "catalog.json").read_text()), result)

    def test_missing_dependency_blocks_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.zip"
            with ZipFile(body, "w") as z:
                z.writestr("Regular_Female_FullBody.gltf", json.dumps({
                    "buffers": [{"uri": "missing.bin"}]
                }))
            with self.assertRaisesRegex(ValueError, "Missing dependency"):
                import_packs(body, output=root / "nov")
            self.assertFalse((root / "nov").exists())

    def test_traversal_blocks_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.zip"
            with ZipFile(body, "w") as z:
                z.writestr("../escape.txt", "bad")
                z.writestr("Regular_Female_FullBody.gltf", "{}")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP path"):
                import_packs(body, output=root / "nov")
            self.assertFalse((root / "nov").exists())

    def test_animation_only_glb_without_required_clips_is_truthful(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.zip"
            anim = root / "animation.zip"
            self.make_body(body)
            with ZipFile(anim, "w") as z:
                z.writestr("Unreal-Godot/UAL_Standard.glb", glb(["Death", "Climb"]))
            data = import_packs(body, anim, root / "nov", dry_run=True)
            self.assertEqual(data["semantic_clips"]["walk"], "")
            self.assertEqual(data["animation_clips"], ["Death", "Climb"])


if __name__ == "__main__":
    unittest.main()
