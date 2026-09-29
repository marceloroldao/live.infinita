"""Static deployment safety gate for experimental BDR mirror operator script."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/mvp018d-bdr-shadow-mirror.sh"


class BdrShadowOperatorContractTests(unittest.TestCase):
    def test_version_pin_source_isolation_and_private_output(self):
        s = SCRIPT.read_text()
        self.assertIn("MEMORIA_PIN=4f40da7876ecece3ce30f743d1b7a8382213aaf1", s)
        self.assertIn("BDR_PIN=317882a00f041fc1568ff986af8016b09453f21a", s)
        self.assertIn("git -C \"$stage/memoria\" checkout -q --detach \"$MEMORIA_PIN\"", s)
        self.assertIn("bdr_atomic_c_api_shared", s)
        self.assertIn("bdr_atomic_c_abi_version()==2", s)
        self.assertIn("external-episodes-incremental/external-episodes.sqlite3", s)
        self.assertIn("nov-ingest.checkpoint.json", s)
        self.assertIn('sudo -u liveinfinita env', s)
        self.assertIn('sudo install -d -o liveinfinita -g liveinfinita -m 0700 "$MIRRORS"', s)
        self.assertIn('test -s "$output/report.json"', s)
        self.assertIn('MVP018D_BDR_MIRROR_OK', s)

    def test_no_world_restart_no_backend_switch_no_checkpoint_write(self):
        s = SCRIPT.read_text()
        self.assertIn("live-infinita-memoria-local.service", s)
        self.assertIn('systemctl show "$WORLD" -p MainPID --value', s)
        self.assertIn('systemctl show "$CORE" -p MainPID --value', s)
        self.assertIn('systemctl show "$RENDERER" -p MainPID --value', s)
        self.assertIn('systemctl is-active --quiet "$TIMER"', s)
        self.assertIn('"external_episode_persistence"]=="sqlite-incremental"', s)
        self.assertIn('--checkpoint "$CHECKPOINT"', s)
        self.assertIn('--max-records 100000', s)
        for snippet in (
            'systemctl stop "$WORLD"', 'systemctl restart "$WORLD"',
            'systemctl stop "$CORE"', 'systemctl restart "$CORE"',
            'systemctl stop "$TIMER"', 'systemctl restart "$TIMER"',
            'sqlite3 "$SOURCE"', 'rm -f "$CHECKPOINT"',
            'chown liveinfinita "$SOURCE"', 'chmod 777',
            'MEMORIA_EXTERNAL_EPISODE_PERSISTENCE=bdr',
            'sudo apt install', 'sudo apt-get install',
        ):
            self.assertNotIn(snippet, s)


if __name__ == "__main__":
    unittest.main()
