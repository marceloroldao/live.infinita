"""Static installer checks; never execute root deployment in tests."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RolloutTests(unittest.TestCase):
    def setUp(self):self.text=(ROOT/"deploy/apply-animal-context-008fg-root.sh").read_text()
    def test_stops_renderer_before_replacing_files(self):
        install=self.text.split("trap rollback ERR",1)[1]
        self.assertLess(install.index("systemctl stop live-infinita-renderer.service"),install.index('for f in "${FILES[@]}"'))
    def test_rollback_stops_services_before_restoring_modules(self):
        rollback=self.text.split("rollback() {",1)[1].split("trap rollback ERR",1)[0]
        self.assertLess(rollback.index("systemctl stop live-infinita-renderer.service"),rollback.index('for f in "${FILES[@]}"'))
        self.assertLess(rollback.index("systemctl stop live-infinita-animal-context.service"),rollback.index('for f in "${PYFILES[@]}"'))
        self.assertNotIn("rm -rf",rollback)
        self.assertNotIn("animal-context-checkpoint",rollback)
    def test_fresh_readiness_and_collection_only(self):
        for token in ("d['generated_at_unix']>=float(sys.argv[1])","c['collection_enabled'] is True",
                      "c['storage_ready'] is True","c['persistent'] is True","c['decision_use'] is False",
                      "c['last_error']==''","d['cached_recovered']>0","d['capture'] is False"):
            self.assertIn(token,self.text)
    def test_native_and_bridge_dependencies_shipped(self):
        for name in ("nov_animal_context_history.gd","nov_animal_approach_context.py","nov_animal_context_sync.py",
                     "nov_animal_search_intent.gd","world_map_local_motion.gd","world_map_preview.gd"):
            self.assertIn(name,self.text)
    def test_unit_local_only_and_privilege_limits(self):
        unit=(ROOT/"deploy/live-infinita-animal-context.service").read_text()
        for token in ("User=liveinfinita","NoNewPrivileges=true","ProtectSystem=strict","IPAddressDeny=any",
                      "IPAddressAllow=localhost","search-policy.json.approach.context","nov_animal_context_sync.py"):
            self.assertIn(token,unit)
    def test_live_selector_not_using_experimental_recommender(self):
        scene=(ROOT/"apps/renderer-godot/world_map_preview.gd").read_text()
        self.assertIn('Callable(_local_motion,"approach_context")',scene)
        self.assertNotIn("recovered-failure-reassessment",scene)
        self.assertNotIn("nov_animal_approach_context.py",scene)
if __name__=="__main__":unittest.main()
