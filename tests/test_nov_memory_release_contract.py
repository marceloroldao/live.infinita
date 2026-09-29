"""MVP-018N: immutable flat-module bundle and hardening template preflight."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_release_contract import MODULES, ReleaseBlocked, render_unit


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "release"
        self.root.mkdir(mode=0o755)
        for module in MODULES:
            file = self.root / (module + ".py")
            file.write_text("# public source\n")
            file.chmod(0o644)
        self.core = Path(self.tmp.name) / "core"
        (self.core / "memoria_resolutiva").mkdir(parents=True)
        (self.core / "memoria_resolutiva/external_episode_incremental.py").write_text("")
        self.python = Path(self.tmp.name) / "python"
        self.python.write_text("#!/bin/sh\n")
        self.python.chmod(0o755)
        self.template = (ROOT / "deploy/live-infinita-nov-memory-prepare.service").read_text()

    def render(self):
        return render_unit(self.template, self.root, core=self.core, python=self.python)

    def test_release_unit_resolves_restricted_executable_paths(self):
        unit = self.render()
        self.assertIn("User=liveinfinita", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ReadOnlyPaths=/var/lib/live-infinita/memoria-local", unit)
        self.assertIn("ReadOnlyPaths=/var/lib/live-infinita/autonomous-world", unit)
        self.assertIn("ReadWritePaths=/run/live-infinita-nov-preparer", unit)
        self.assertIn("RuntimeDirectory=live-infinita-nov-preparer", unit)
        self.assertIn("RuntimeDirectoryMode=0700", unit)
        self.assertIn(" --scratch-root /run/live-infinita-nov-preparer", unit)
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("StartLimitBurst=3", unit)
        self.assertIn("ExecStart=" + str(self.python) + " " +
                      str(self.root) + "/nov_memory_continuous.py", unit)
        self.assertNotIn("ReadWritePaths=/var/lib/live-infinita/memoria-local", unit)
        self.assertNotIn("@NOV_RELEASE_ROOT@", unit)
        self.assertNotIn("@PINNED_CORE_ROOT@", unit)
        self.assertNotIn("@VENV_PYTHON@", unit)
        self.assertNotIn("/home/etbra", unit)

    def test_bad_release_permissions_missing_module_and_symlink_block(self):
        victim = self.root / "nov_memory_continuous.py"
        victim.chmod(0o666)
        with self.assertRaises(ReleaseBlocked):
            self.render()
        victim.chmod(0o644)
        victim.unlink()
        with self.assertRaises(ReleaseBlocked):
            self.render()
        victim.symlink_to(self.python)
        with self.assertRaises(ReleaseBlocked):
            self.render()

    def test_root_and_template_tampering_block(self):
        self.root.chmod(0o777)
        with self.assertRaises(ReleaseBlocked):
            self.render()
        self.root.chmod(0o755)
        with self.assertRaises(ReleaseBlocked):
            render_unit(self.template.replace("ProtectSystem=strict", ""),
                        self.root, core=self.core, python=self.python)
        with self.assertRaises(ReleaseBlocked):
            render_unit(self.template.replace("@NOV_RELEASE_ROOT@", "/unknown"),
                        self.root, core=self.core, python=self.python)
        with self.assertRaises(ReleaseBlocked):
            render_unit(self.template.replace("ReadWritePaths=/run/live-infinita-nov-preparer",
                                              "ReadWritePaths=/var/lib/live-infinita/memoria-local"),
                        self.root, core=self.core, python=self.python)
        with self.assertRaises(ReleaseBlocked):
            render_unit(self.template.replace("RuntimeDirectoryMode=0700",
                                              "RuntimeDirectoryMode=0755"),
                        self.root, core=self.core, python=self.python)
        with self.assertRaises(ReleaseBlocked):
            render_unit(self.template.replace("ReadOnlyPaths=/var/lib/live-infinita/memoria-local",
                                              "ReadWritePaths=/var/lib/live-infinita/memoria-local"),
                        self.root, core=self.core, python=self.python)

    def test_no_automatic_install_or_world_wiring(self):
        script = (ROOT / "deploy/mvp018n-nov-lifecycle-preflight.sh").read_text()
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertIn("systemd-analyze verify", script)
        self.assertIn("cmp -s", script)
        self.assertNotIn("sudo ", script)
        self.assertNotIn("systemctl enable ", script)
        self.assertNotIn("systemctl start ", script)
        self.assertNotIn("systemctl restart ", script)
        self.assertNotIn("memory_recall_provider=", runtime)
        self.assertNotIn("prepared_memory_provider=", runtime)


if __name__ == "__main__":
    unittest.main()
