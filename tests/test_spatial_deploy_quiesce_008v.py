from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SpatialDeployQuiesce008VTests(unittest.TestCase):
    def test_deploy_quiesces_old_sync_before_install_and_start(self) -> None:
        source = (ROOT / "deploy" / "apply-spatial-deploy-quiesce-008v.sh").read_text(encoding="utf-8")
        disable = source.index("systemctl disable --now live-infinita-nov-spatial-memory-sync.timer")
        stop = source.index("systemctl stop live-infinita-nov-spatial-memory-sync.service")
        install = source.index('install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/world-runtime/nov_spatial_memory_sync.py"')
        start = source.index("systemctl start live-infinita-nov-spatial-memory-sync.service")
        self.assertLess(disable, install)
        self.assertLess(stop, install)
        self.assertLess(install, start)

    def test_deploy_verifies_exact_008u_runtime_before_start(self) -> None:
        source = (ROOT / "deploy" / "apply-spatial-deploy-quiesce-008v.sh").read_text(encoding="utf-8")
        self.assertIn("MAX_EVENTS_PER_RUN = 1", source)
        self.assertIn("SPATIAL_RECURRENCE_GRID_M = 64.0", source)
        self.assertIn("--max-events 1", source)
        verify = source.index("versão instalada confirmada")
        start = source.index("systemctl start live-infinita-nov-spatial-memory-sync.service")
        self.assertLess(verify, start)


if __name__ == "__main__":
    unittest.main()
