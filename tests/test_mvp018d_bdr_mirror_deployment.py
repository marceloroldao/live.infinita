from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


class BdrMirrorDeployContractTests(unittest.TestCase):
    def test_only_auxiliary_code_and_private_mirror(self):
        script = (DEPLOY / "mvp018d-bdr-read-only-mirror.sh").read_text()
        self.assertIn("MEMORIA_SHA=cf699e2daf8f91a97f05892abd58890f11c4acbe", script)
        self.assertIn("BDR_SHA=317882a00f041fc1568ff986af8016b09453f21a", script)
        self.assertIn("apt-get download zlib1g-dev", script)
        self.assertIn('dpkg-deb -x "$deb" extracted', script)
        self.assertNotIn("apt-get install", script)
        self.assertNotIn("pip install", script)
        self.assertIn("MVP018D_REAL_NATIVE_SCRATCH_PREFLIGHT_OK", (
            DEPLOY / "mvp018d-bdr-native-preflight.py"
        ).read_text())
        self.assertIn("MVP018D_BDR_READ_ONLY_MIRROR_OK", script)
        self.assertIn("MVP018D_NO_CUTOVER", script)
        self.assertIn("--max-records 10000", script)

    def test_never_restart_core_world_or_advance_checkpoint(self):
        script = (DEPLOY / "mvp018d-bdr-read-only-mirror.sh").read_text()
        for forbidden in (
            "systemctl restart", "systemctl stop", "systemctl enable",
            "systemctl disable", "nov-ingest.checkpoint.json",
            "sudo rm", "sudo mv", "sudo apt", "MEMORIA_EXTERNAL_EPISODE_PERSISTENCE=bdr",
        ):
            self.assertNotIn(forbidden, script)
        self.assertIn("sudo -u liveinfinita env", script)
        self.assertIn("bdr-mirror-runs", script)
        self.assertIn("--source-sqlite", script)
        self.assertIn("MVP018D_LIVE_SQLITE_STILL_AUTHORITATIVE", script)
        self.assertIn('check_pid "$WORLD" "$world_pid"', script)
        self.assertIn('check_pid "$MEMORY" "$memory_pid"', script)
        self.assertIn('check_pid "$RENDERER" "$renderer_pid"', script)

    def test_native_preflight_is_real_and_synthetic(self):
        file = DEPLOY / "mvp018d-bdr-native-preflight.py"
        ast.parse(file.read_text(), filename=str(file))
        code = file.read_text()
        self.assertIn("AtomicBDR.open", code)
        self.assertIn("create_verified_mirror", code)
        self.assertIn("IncrementalExternalEpisodeStore", code)
        self.assertIn('"preflight-world"', code)
        self.assertNotIn("/var/lib/live-infinita", code)


if __name__ == "__main__":
    unittest.main()
