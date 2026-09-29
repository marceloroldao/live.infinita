from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from packages.observability.nov_episode_sync import (
    EpisodeSyncContractError, observation_envelope, preview_episode_batch,
    world_identity,
)

ROOT = Path(__file__).resolve().parents[1]


def _episode(index: int, *, npc_id: str = 'nov') -> dict:
    plan_id = f'plan_{index}'
    return {
        'episode_schema': 'npc_episode_v1',
        'episode_id': 'plan:' + plan_id,
        'npc_id': npc_id,
        'logical_tick': 100 + index,
        'need': 'curiosity',
        'target_entity_id': 'ancient_tree',
        'strategy_id': 'via_shelter:shelter_marker',
        'context': {'period': 'night', 'weather': 'clear', 'region_id': 'clearing', 'danger_level': 0.35, 'free_text': 'DO_NOT_EXPORT'},
        'outcome': {'satisfaction': 0.3, 'observed_risk': 0.35, 'elapsed_ticks': 3, 'preemptions': 0, 'replans': 0, 'raw_comment': 'PRIVATE'},
        'source': {'kind': 'need_outcome', 'plan_id': plan_id, 'plan_revision': 0, 'proposal_id': f'pr_{index}', 'token': 'SECRET'},
    }


class NovEpisodeSyncPreviewTests(unittest.TestCase):
    def _fixture(self, directory: str, rows: list[dict], *, incomplete: bytes = b''):
        root = Path(directory)
        world = root / 'world.json'
        ledger = root / 'npc-episodes.jsonl'
        world.write_text(json.dumps({'world_id': 'nov-live-autonomous-001', 'version': 3}), encoding='utf-8')
        ledger.write_bytes(b''.join(json.dumps(r, ensure_ascii=False).encode() + b'\n' for r in rows) + incomplete)
        return ledger, world

    def test_typed_observation_is_stable_and_does_not_leak_untrusted_source_text(self):
        row = _episode(1)
        before = deepcopy(row)
        value = observation_envelope(row, world_id='nov-live-autonomous-001')
        self.assertEqual(row, before)
        self.assertEqual(value, observation_envelope(deepcopy(row), world_id='nov-live-autonomous-001'))
        self.assertEqual(value['schema'], 'live-infinita-npc-episode-observation/v1')
        self.assertEqual(value['source']['episode_id'], 'plan:plan_1')
        self.assertEqual(value['source']['source_kind'], 'need_outcome')
        self.assertEqual(value['observation']['outcome']['satisfaction'], 0.3)
        self.assertFalse(value['world_write_authority'])
        self.assertEqual(len(value['record_key']), 64)
        self.assertEqual(len(value['content_sha256']), 64)
        self.assertNotEqual(value['record_key'], value['content_sha256'])
        for secret in ('SECRET', 'DO_NOT_EXPORT', 'PRIVATE', 'role', 'text'):
            self.assertNotIn(secret, json.dumps(value))
        different = deepcopy(row)
        different['outcome']['satisfaction'] = 0.5
        changed = observation_envelope(different, world_id='nov-live-autonomous-001')
        self.assertEqual(changed['record_key'], value['record_key'])
        self.assertNotEqual(changed['content_sha256'], value['content_sha256'])
        self.assertNotEqual(observation_envelope(row, world_id='another-world')['record_key'], value['record_key'])

    def test_requires_confirmed_plan_outcome_not_narration_or_forecast(self):
        row = _episode(0)
        for change in ({'episode_schema': 'shadow_forecast_v1'}, {'role': 'assistant', 'source': {'kind': 'narration'}},
                       {'source': {'kind': 'need_outcome', 'plan_id': 'wrong', 'proposal_id': 'pr_0', 'plan_revision': 0}}):
            with self.subTest(change=change):
                candidate = deepcopy(row)
                candidate.update(change)
                with self.assertRaises(EpisodeSyncContractError):
                    observation_envelope(candidate, world_id='nov-live-autonomous-001')
        self.assertIsNone(observation_envelope(_episode(0, npc_id='other'), world_id='nov-live-autonomous-001'))

    def test_byte_cursor_is_stable_bounded_and_never_an_ack(self):
        with tempfile.TemporaryDirectory() as root:
            rows = [_episode(i) for i in range(3)]
            ledger, world = self._fixture(root, rows, incomplete=b'{"episode_id":"partial"')
            before = ledger.read_bytes()
            first = preview_episode_batch(ledger, world, cursor=0, limit=1)
            second = preview_episode_batch(ledger, world, cursor=first['candidate_next_cursor'], limit=1)
            third = preview_episode_batch(ledger, world, cursor=second['candidate_next_cursor'], limit=1)
            final = preview_episode_batch(ledger, world, cursor=third['candidate_next_cursor'], limit=1)
            self.assertEqual([x['episodes'][0]['source']['episode_id'] for x in (first, second, third)],
                             ['plan:plan_0', 'plan:plan_1', 'plan:plan_2'])
            self.assertEqual(final['episodes'], [])
            self.assertTrue(final['partial_tail'])
            self.assertEqual(final['candidate_next_cursor'], third['candidate_next_cursor'])
            self.assertEqual(ledger.read_bytes(), before)
            self.assertFalse(first['candidate_cursor_is_ack'])
            self.assertFalse(first['transport_enabled'])
            self.assertIsNone(first['central_receipt'])
            self.assertFalse(first['world_mutated'])
            self.assertFalse(first['selection_authority'])
            self.assertEqual(first['ledger_identity'], second['ledger_identity'])
            with self.assertRaisesRegex(EpisodeSyncContractError, 'cursor_not_line_boundary'):
                preview_episode_batch(ledger, world, cursor=1)

    def test_corrupted_records_and_conflicting_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            ledger, world = self._fixture(root, [_episode(0), {**_episode(1), 'source': {}}])
            with self.assertRaisesRegex(EpisodeSyncContractError, 'episode_provenance_not_confirmed'):
                preview_episode_batch(ledger, world)
            ledger.write_bytes(json.dumps(_episode(0)).encode() + b'\n{garbage}\n')
            with self.assertRaisesRegex(EpisodeSyncContractError, 'malformed_episode_record'):
                preview_episode_batch(ledger, world)
            different = _episode(0)
            different['outcome']['satisfaction'] = 0.8
            self._fixture(root, [_episode(0), different])
            with self.assertRaisesRegex(EpisodeSyncContractError, 'conflicting_episode_identity'):
                preview_episode_batch(ledger, world)

    def test_cursor_bounds_world_identity_and_partial_line(self):
        with tempfile.TemporaryDirectory() as root:
            ledger, world = self._fixture(root, [_episode(0)])
            with self.assertRaisesRegex(EpisodeSyncContractError, 'cursor_beyond_ledger'):
                preview_episode_batch(ledger, world, cursor=ledger.stat().st_size + 1)
            with self.assertRaisesRegex(EpisodeSyncContractError, 'invalid_cursor'):
                preview_episode_batch(ledger, world, cursor=-1)
            self.assertEqual(world_identity(world), 'nov-live-autonomous-001')
            world.write_text(json.dumps({'world_id': '../bad'}))
            with self.assertRaisesRegex(EpisodeSyncContractError, 'invalid_world_identity'):
                preview_episode_batch(ledger, world)


class NovEpisodeSyncPreviewApiTests(unittest.TestCase):
    def test_route_is_protected_and_does_not_persist_or_send(self):
        script = '''
import json, os
from pathlib import Path
from fastapi.testclient import TestClient
import main_story_live
import main as core
root=Path(os.environ['LIVE_INFINITA_WORLD_DATA_DIR'])
root.joinpath('world.json').write_text(json.dumps({'world_id':'nov-live-autonomous-001'}))
row={'episode_schema':'npc_episode_v1','episode_id':'plan:plan_x','npc_id':'nov','logical_tick':4,
     'need':'curiosity','strategy_id':'direct','target_entity_id':'ancient_tree','context':{},
     'outcome':{'satisfaction':0.5},
     'source':{'kind':'need_outcome','plan_id':'plan_x','plan_revision':0,'proposal_id':'pr_x'}}
root.joinpath('npc-episodes.jsonl').write_text(json.dumps(row)+'\\n')
before=root.joinpath('npc-episodes.jsonl').read_bytes()
with TestClient(main_story_live.app) as client:
    assert client.get('/api/manage/nov/sync/preview').status_code == 503
    main_story_live.app.dependency_overrides[core.require_operator]=lambda:None
    response=client.get('/api/manage/nov/sync/preview?cursor=0')
    assert response.status_code == 200,response.text
    value=response.json()
    assert value['episodes'][0]['source']['episode_id']=='plan:plan_x',value
    assert not value['transport_enabled'] and value['central_receipt'] is None
    assert root.joinpath('npc-episodes.jsonl').read_bytes()==before
    assert client.get('/api/manage/nov/sync/preview?cursor=1').status_code==409
print('ISOLATED_NOV_SYNC_PREVIEW_OK')
'''
        with tempfile.TemporaryDirectory(prefix='nov-sync-preview-') as directory:
            env = os.environ.copy()
            env.update({
                'LIVE_INFINITA_DATA_DIR': directory,
                'LIVE_INFINITA_WORLD_DATA_DIR': directory,
                'LIVE_INFINITA_COLD_ENGINE': '0',
                'PYTHONPATH': os.pathsep.join((str(ROOT), str(ROOT / 'apps/world-runtime'),
                                               str(ROOT / 'apps/audio-service'), str(ROOT / 'apps/audience'))),
            })
            env.pop('LIVE_INFINITA_COLD_STORE_DIR', None)
            env.pop('LIVE_INFINITA_OPERATOR_TOKEN', None)
            run = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env,
                                 text=True, capture_output=True, timeout=45)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('ISOLATED_NOV_SYNC_PREVIEW_OK', run.stdout)

    def test_disabled_transport_contract_is_explicit(self):
        api = (ROOT / 'apps/world-runtime/main_cognitive_live.py').read_text()
        module = (ROOT / 'packages/observability/nov_episode_sync.py').read_text()
        self.assertIn('promote_api_route_before_root(app, "/api/manage/nov/sync/preview")', api)
        self.assertIn('dependencies=[Depends(core.require_operator)]', api)
        self.assertNotIn('urlopen(', module)
        self.assertNotIn('requests.post', module)
        self.assertNotIn('open("a"', module)


if __name__ == '__main__':
    unittest.main()
