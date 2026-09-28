from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from packages.observability.nov_life import nov_life_snapshot


ROOT = Path(__file__).resolve().parents[1]


def _episode(
    episode_id: str, tick: int, *,
    npc_id: str = "nov",
    source: dict | None = None,
    need: str = "curiosity",
) -> dict:
    return {
        "episode_schema": "npc_episode_v1",
        "episode_id": episode_id,
        "npc_id": npc_id,
        "logical_tick": tick,
        "need": need,
        "strategy_id": "via_shelter:shelter_marker",
        "target_entity_id": "ancient_tree",
        "context": {
            "period": "night",
            "weather": "clear",
            "region_id": "clearing",
            "danger_level": 0.35,
            "free_text": "PRIVATE_CONTEXT",
        },
        "outcome": {
            "satisfaction": 0.3,
            "elapsed_ticks": 3,
            "observed_risk": 0.35,
            "preemptions": 0,
            "replans": 0,
            "raw_comment": "PRIVATE_OUTCOME",
        },
        "source": source or {"raw_comment": "PRIVATE_SOURCE", "token": "SECRET_TOKEN"},
    }


class NovLifeProjectionTests(unittest.TestCase):
    def test_filters_ledger_by_schema_observer_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npc-episodes.jsonl"
            rows = [
                _episode("plan:one", 10),
                _episode("plan:other", 12, npc_id="another"),
                _episode("plan:two", 20),
                {**_episode("plan:shadow", 30), "episode_schema": "forecast_v1"},
                _episode("plan:two", 20),
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            before = path.read_bytes()
            result = nov_life_snapshot(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([x["episode_id"] for x in result["episodes"]], ["plan:two", "plan:one"])
            self.assertEqual(result["latest_episode_tick"], 20)
            self.assertEqual(result["window_records_examined"], 5)
            self.assertEqual(result["episodes"][0]["provenance"], "npc_episode_v1")
            self.assertEqual(result["episodes"][0]["need"], "curiosity")
            self.assertEqual(result["episodes"][0]["outcome"]["satisfaction"], 0.3)
            self.assertFalse(result["world_mutated"])
            self.assertFalse(result["selection_authority"])
            self.assertFalse(result["central_memoria_sync"])
            raw = json.dumps(result)
            for secret in ("PRIVATE_SOURCE", "SECRET_TOKEN", "PRIVATE_CONTEXT", "PRIVATE_OUTCOME", "another"):
                self.assertNotIn(secret, raw)

    def test_bounded_tail_skips_partial_and_huge_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npc-episodes.jsonl"
            rows = [json.dumps(_episode(f"plan:e{i}", i)) + "\n" for i in range(1000)]
            path.write_text("".join(rows) + '{"episode_id":"partial"', encoding="utf-8")
            result = nov_life_snapshot(path, max_bytes=2048, window_records=5, limit=3)
            self.assertEqual([x["logical_tick"] for x in result["episodes"]], [999, 998, 997])
            self.assertEqual(result["max_window_bytes"], 2048)
            self.assertEqual(result["window_records_examined"], 5)
            self.assertEqual(len(result["episodes"]), 3)

    def test_empty_and_malformed_entries_are_not_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npc-episodes.jsonl"
            self.assertEqual(nov_life_snapshot(path)["episodes"], [])
            self.assertFalse(nov_life_snapshot(path)["ledger_available"])
            malformed = _episode("plan:one", 1)
            malformed["episode_id"] = "line\nINJECTION"
            malformed["outcome"]["satisfaction"] = float("nan")
            path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
            self.assertEqual(nov_life_snapshot(path)["episodes"], [])
            valid = _episode("plan:valid", 4, need="invented_future_need")
            valid["outcome"]["satisfaction"] = float("nan")
            with path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(valid) + "\n")
            episode = nov_life_snapshot(path)["episodes"][0]
            self.assertEqual(episode["need"], "invented_future_need")
            self.assertIsNone(episode["outcome"]["satisfaction"])

    def test_caps_requested_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npc-episodes.jsonl"
            path.write_text("".join(json.dumps(_episode(f"plan:{n}", n)) + "\n" for n in range(40)))
            result = nov_life_snapshot(path, max_bytes=10_000_000, window_records=1000, limit=1000)
            self.assertEqual(result["max_window_bytes"], 262_144)
            self.assertEqual(len(result["episodes"]), 8)


class NovLifeRuntimeContractTests(unittest.TestCase):
    def test_actual_story_app_protected_route_is_read_only(self):
        probe = """
import os, json
from pathlib import Path
from fastapi.testclient import TestClient
import main_story_live
import main as core
root = Path(os.environ['LIVE_INFINITA_WORLD_DATA_DIR'])
root.joinpath('npc-episodes.jsonl').write_text(json.dumps({
    'episode_schema':'npc_episode_v1','episode_id':'plan:verified','npc_id':'nov',
    'logical_tick':23,'need':'curiosity','strategy_id':'direct','target_entity_id':'ancient_tree',
    'context':{},'outcome':{'satisfaction':0.5},'source':{'secret':'NEVER_LEAK'}
})+'\\n')
before=root.joinpath('npc-episodes.jsonl').read_bytes()
with TestClient(main_story_live.app) as client:
    unauth=client.get('/api/manage/nov/life')
    assert unauth.status_code==503,unauth.status_code
    main_story_live.app.dependency_overrides[core.require_operator]=lambda:None
    result=client.get('/api/manage/nov/life')
    assert result.status_code==200,result.text
    value=result.json()
    assert value['episodes'][0]['episode_id']=='plan:verified',value
    assert 'NEVER_LEAK' not in result.text
    assert value['world_mutated'] is False
    assert root.joinpath('npc-episodes.jsonl').read_bytes()==before
print('ISOLATED_NOV_LIFE_ENDPOINT_OK')
"""
        with tempfile.TemporaryDirectory(prefix="nov-life-contract-") as directory:
            env = os.environ.copy()
            env.update({
                "LIVE_INFINITA_DATA_DIR": directory,
                "LIVE_INFINITA_WORLD_DATA_DIR": directory,
                "LIVE_INFINITA_COLD_ENGINE": "0",
                "PYTHONPATH": os.pathsep.join((
                    str(ROOT), str(ROOT / "apps/world-runtime"), str(ROOT / "apps/audio-service"),
                    str(ROOT / "apps/audience"),
                )),
            })
            env.pop("LIVE_INFINITA_COLD_STORE_DIR", None)
            env.pop("LIVE_INFINITA_OPERATOR_TOKEN", None)
            run = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                                 env=env, text=True, capture_output=True, timeout=45)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertIn("ISOLATED_NOV_LIFE_ENDPOINT_OK", run.stdout)

    def test_manager_visualization_and_route_precedence(self):
        api = (ROOT / "apps/world-runtime/main_cognitive_live.py").read_text(encoding="utf-8")
        html = (ROOT / "apps/manager/index.html").read_text(encoding="utf-8")
        js = (ROOT / "apps/manager/app.js").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/manage/nov/life", dependencies=[Depends(core.require_operator)])', api)
        self.assertIn('promote_api_route_before_root(app, "/api/manage/nov/life")', api)
        self.assertIn('data-page="nov"', html)
        self.assertIn('id="nov-life-episodes"', html)
        self.assertIn("api('/api/manage/nov/life')", js)
        self.assertIn("setTimeout(loadNovLife, 15000)", js)
        self.assertIn("list.replaceChildren()", js)
        self.assertNotIn("li.innerHTML", js)


if __name__ == "__main__":
    unittest.main()
