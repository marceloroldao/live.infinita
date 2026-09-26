"""Offline tests: no vendor download or paid assets are needed in CI."""
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.import_quaternius_nature import classify, import_zip


class QuaterniusNatureImporterTests(unittest.TestCase):
    def test_semantic_categories(self):
        self.assertEqual(classify("PineTree_01"), "tree")
        self.assertEqual(classify("RockLarge"), "rock")
        self.assertEqual(classify("Flower_03"), "plant")
        self.assertEqual(classify("Unknown_Thing"), "nature")

    def test_import_gltf_and_only_referenced_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "standard.zip"
            document = {
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "TreeOak.bin", "byteLength": 4}],
                "images": [{"uri": "../textures/leaves.png"}],
            }
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("pack/glTF/TreeOak.gltf", json.dumps(document))
                archive.writestr("pack/glTF/TreeOak.bin", b"abcd")
                archive.writestr("pack/textures/leaves.png", b"png")
                archive.writestr("pack/FBX/TreeOak.fbx", b"unused")
                archive.writestr("pack/glTF/RockLarge.gltf", json.dumps({"asset": {"version": "2.0"}}))
            dest = root / "installed"
            preview = import_zip(archive_path, dest, dry_run=True)
            self.assertFalse(dest.exists())
            self.assertEqual([a["kind"] for a in preview["assets"]], ["rock", "tree"])
            result = import_zip(archive_path, dest)
            self.assertEqual(preview, result)
            self.assertEqual((dest / "models/pack/glTF/TreeOak.bin").read_bytes(), b"abcd")
            self.assertEqual((dest / "models/pack/textures/leaves.png").read_bytes(), b"png")
            self.assertFalse((dest / "models/pack/FBX/TreeOak.fbx").exists())
            self.assertEqual(json.loads((dest / "catalog.json").read_text()), result)

    def test_rejects_zip_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bad.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("../escape.glb", b"nope")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP path"):
                import_zip(path, root / "output")
            self.assertFalse((root / "output").exists())

    def test_rejects_missing_gltf_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bad.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr(
                    "models/Tree.gltf",
                    json.dumps({"buffers": [{"uri": "missing.bin"}]}),
                )
            with self.assertRaisesRegex(ValueError, "Missing glTF dependency"):
                import_zip(path, root / "output")
            self.assertFalse((root / "output").exists())

    def test_glb_priority_and_stable_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "standard.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("pack/glTF/PineTree.glb", b"fake glb for importer-only test")
                archive.writestr("pack/OBJ/PineTree.obj", b"unused")
            first = import_zip(path, root / "out", dry_run=True)
            second = import_zip(path, root / "out", dry_run=True)
            self.assertEqual(first, second)
            self.assertEqual(first["assets"][0]["kind"], "tree")
            self.assertTrue(first["assets"][0]["path"].endswith("PineTree.glb"))


if __name__ == "__main__":
    unittest.main()
