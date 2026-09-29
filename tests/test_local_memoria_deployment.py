from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
CORE_SHA = "3ea447c449349761215c43182ca54a0941b6e09b"


class LocalMemoriaDeploymentContractTests(unittest.TestCase):
    def test_real_v2_is_immutable_and_loopback_only(self):
        install = (DEPLOY / "mvp018c-memoria-local.sh").read_text()
        unit = (DEPLOY / "live-infinita-memoria-local.service").read_text()
        self.assertIn("CORE_SHA=" + CORE_SHA, install)
        self.assertIn('git -C "$stage/core" checkout -q --detach "$CORE_SHA"', install)
        self.assertIn("PYTHONPATH=/opt/live-infinita-memoria-core/" + CORE_SHA + "/src", unit)
        self.assertIn("memoria_resolutiva.product_server:app", unit)
        self.assertIn("--host 127.0.0.1 --port 8788 --workers 1", unit)
        self.assertIn("MEMORIA_CONVERSATION_RUNTIME=python", install)
        self.assertIn("MEMORIA_EPISODIC_RUNTIME=python", install)
        self.assertIn("MEMORIA_STORAGE_BACKEND=sqlite", install)
        self.assertIn("MEMORIA_STORAGE_ALLOW_FALLBACK=false", install)
        self.assertIn("MEMORIA_DATA_DIR=/var/lib/live-infinita/memoria-local", install)
        self.assertIn("secrets.token_hex(32)", install)
        self.assertIn("0o600", install)
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("IPAddressAllow=localhost", unit)
        self.assertNotIn("MEMORIA_LLM_PROVIDER=", install)

    def test_observer_cannot_run_world_tick_or_restart_live(self):
        worker = (DEPLOY / "live-infinita-memoria-nov-sync.service").read_text()
        timer = (DEPLOY / "live-infinita-memoria-nov-sync.timer").read_text()
        install = (DEPLOY / "mvp018c-memoria-local.sh").read_text()
        self.assertIn("ReadOnlyPaths=/var/lib/live-infinita/autonomous-world", worker)
        self.assertIn("ReadWritePaths=/var/lib/live-infinita/memoria-local", worker)
        self.assertIn("--max-episodes 2", worker)
        self.assertIn("OnUnitInactiveSec=2min", timer)
        self.assertIn("MemoryMax=256M", worker)
        self.assertIn('MVP018C_LOCAL_MEMORIA_DEPLOY_OK', install)
        self.assertIn('world_pid="$(systemctl show "$WORLD_UNIT" -p MainPID --value)"', install)
        self.assertIn("LOCAL_MEMORIA_SYNC_OK", install)
        for name in (
            "live-infinita-autonomous-world.service",
            "live-infinita-renderer.service",
            "live-infinita.service",
            "live-infinita-audio.service",
        ):
            self.assertNotRegex(install, r"systemctl (?:restart|stop|disable|enable)\s+(?:--now\s+)?[\"']?" + re.escape(name))

    def test_local_source_and_state_are_separate_from_live(self):
        unit = (DEPLOY / "live-infinita-memoria-local.service").read_text()
        install = (DEPLOY / "mvp018c-memoria-local.sh").read_text()
        self.assertIn("MemoryMax=768M", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("LOCAL_MEMORIA_ROUTE=127.0.0.1:8788", install)
        self.assertIn("CENTRAL_SYNC=false", install)
        self.assertNotIn("memoria.ia.server", unit)
        self.assertNotIn("sudo rm -rf \"$DATA_DIR\"", install)
        self.assertNotIn("sudo rm -f \"$ENV_FILE\"", install)


if __name__ == "__main__":
    unittest.main()
