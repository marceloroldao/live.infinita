import unittest,tempfile,json,time,sys,copy
from pathlib import Path
from unittest.mock import patch
import nov_animal_memory_sync as m
from nov_spatial_memory_sync import _canonical,_observation_id
from hashlib import sha256
SDK='/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src'
def row(seq=1):
    return dict(sequence=seq,entity_id='test:rabbit:0',kind='rabbit',first_seen_ms=1000,last_seen_ms=1250,first_observer_eye_m=[0,1.55,0],last_observer_eye_m=[0,1.55,0],first_target_m=[0,0.55,8],last_target_m=[0,0.55,8],sample_count=2,min_distance_m=65**0.5,max_distance_m=65**0.5,first_range_m=24,last_range_m=24,closed_reason='lost_visual_contact')
class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'source';self.ack=self.root/'ack';self.public=self.root/'public';self.world=self.root/'world';self.world.write_text('{"world_id":"test"}')
        self.data=dict(schema=m.SCHEMA,world_id='test',session_id='a'*32,next_sequence=2,acknowledged_sequence=0,logical_time_ms=4500,generated_at_unix=time.time(),pending=[row()],active={},dropped_samples=0,source='local_physics_eye_sensor',world_write_authority=False,contains_prediction=False,absence_claim=False)
        self.rows={};self.posts=[];self.source_write()
    def tearDown(self):self.tmp.cleanup()
    def source_write(self):
        raw=json.dumps(self.data);self.source.write_text(json.dumps(dict(payload=raw,sha256=sha256(raw.encode()).hexdigest())))
    def api(self,path,payload=None):
        if payload is None:return dict(semantic_projection=False,items=list(self.rows.values()))
        id=_observation_id(payload['event']);duplicate=id in self.rows;self.rows[id]=dict(**payload,observation_id=id);self.posts.append(id)
        return dict(observation_id=id,stored=not duplicate,duplicate=duplicate,association_sync_deferred=True,semantic_projection=False,backend='sqlite')
    def sync(self,api=None):return m.sync_once(self.source,self.ack,self.public,self.world,api or self.api)
    def test_store_recover_ack_and_no_repost_on_idle(self):
        result=self.sync();self.assertEqual(result['stored_and_recovered_encounters'],1);self.assertEqual(result['pending'],0)
        self.assertFalse(result['decision_use']);self.assertFalse(result['learning_improvement_measured']);self.sync();self.assertEqual(len(self.posts),1)
    def test_post_timeout_retry_uses_same_event(self):
        def failure(path,payload=None):
            if payload:self.api(path,payload);raise TimeoutError()
            return self.api(path)
        with self.assertRaises(TimeoutError):self.sync(failure)
        self.assertFalse(self.ack.exists());self.sync();self.assertEqual(len(self.rows),1);self.assertEqual(self.posts[0],self.posts[1])
    def test_fetch_failure_does_not_ack_stored_event(self):
        def failure(path,payload=None):
            if payload is None:raise TimeoutError()
            return self.api(path,payload)
        with self.assertRaises(TimeoutError):self.sync(failure)
        self.assertFalse(self.ack.exists());self.sync();self.assertEqual(len(self.rows),1)
    def test_wrong_ack_never_releases_source(self):
        def wrong(path,payload=None):
            result=self.api(path,payload)
            if payload:result['observation_id']='forged'
            return result
        with self.assertRaises(Exception):self.sync(wrong)
        self.assertFalse(self.ack.exists())
    def test_unstored_ack_is_rejected(self):
        def wrong(path,payload=None):
            result=self.api(path,payload)
            if payload:result.update(stored=False,duplicate=False)
            return result
        with self.assertRaises(ValueError):self.sync(wrong)
        self.assertFalse(self.ack.exists())
    def test_recall_content_must_match_record(self):
        def wrong(path,payload=None):
            result=self.api(path,payload)
            if payload is None:
                result=copy.deepcopy(result);result['items'][0]['provenance']['contains_prediction']=True
            return result
        with self.assertRaises(ValueError):self.sync(wrong)
        self.assertFalse(self.ack.exists())
    def test_world_predictions_absence_and_global_source_rejected(self):
        for key,value in [('world_id','other'),('contains_prediction',True),('absence_claim',True),('source','global_animal_projection')]:
            with self.subTest(key=key):
                old=self.data[key];self.data[key]=value;self.source_write()
                with self.assertRaises(ValueError):self.sync()
                self.data[key]=old
        self.assertFalse(self.posts)
    def test_geometry_future_time_sequence_and_nan_rejected(self):
        for mutate in [lambda r:r.update(first_target_m=[0,0,100]),lambda r:r.update(last_seen_ms=5000),lambda r:r.update(sequence=2),lambda r:r.update(first_range_m=float('nan')),lambda r:r.update(sample_count=201)]:
            with self.subTest(mutate=mutate):
                self.data['pending']=[row()];mutate(self.data['pending'][0]);self.source_write()
                with self.assertRaises(ValueError):self.sync()
        self.assertFalse(self.posts)
    def test_checksum_source_and_ack_corruption_rejected(self):
        self.source.write_text('{}')
        with self.assertRaises(ValueError):self.sync()
        self.source_write();self.sync();value=json.loads(self.ack.read_text());value['cursor']=2;self.ack.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.sync()
    def test_float_json_reload_keeps_event_identity(self):
        original=row();floats=copy.deepcopy(original)
        for key in ('sequence','first_seen_ms','last_seen_ms','sample_count','first_range_m','last_range_m'):floats[key]=float(floats[key])
        self.assertEqual(m.payload('test','a'*32,original),m.payload('test','a'*32,floats))
    def test_cursor_requires_contiguous_pending_and_one_per_run(self):
        self.data['pending'].append(row(2));self.data['next_sequence']=3;self.source_write()
        self.assertEqual(self.sync()['stored_and_recovered_encounters'],1);self.assertEqual(len(self.posts),1)
        self.assertEqual(self.sync()['stored_and_recovered_encounters'],2);self.assertEqual(len(self.posts),2)
    def test_stale_source_and_damaged_session_rejected(self):
        self.data['generated_at_unix']-=181;self.source_write()
        with self.assertRaises(ValueError):self.sync()
        self.data['generated_at_unix']=time.time();self.data['session_id']='bad';self.source_write()
        with self.assertRaises(ValueError):self.sync()
    def test_missing_recent_recall_preserves_unacknowledged_encounter(self):
        def empty(path,payload=None):
            return self.api(path,payload) if payload else dict(semantic_projection=False,items=[])
        with self.assertRaisesRegex(ValueError,'animal_memory_recall_not_found'):self.sync(empty)
        self.assertFalse(self.ack.exists());self.assertEqual(len(self.rows),1)
        self.assertEqual(m.read_source(self.source,'test')['pending'][0]['sequence'],1)
    def test_pending_budget_is_bounded(self):
        self.data['pending']=[row(i+1) for i in range(129)];self.data['next_sequence']=130;self.source_write()
        with self.assertRaisesRegex(ValueError,'animal_memory_source_pending'):self.sync()
        self.assertFalse(self.posts)
    def test_actual_frozen_core_and_godot_eye_fixture(self):
        sys.path.insert(0,SDK)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
        fixture=Path('/home/etbra/008dt-eye-fixture.json')
        self.assertTrue(fixture.exists(),'Run real Godot eye sensor smoke first')
        self.source.write_bytes(fixture.read_bytes())
        def connection():
            service=ProductStructuralObservationService.open(self.root/'core',backend='sqlite',allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key='isolated-animal-test-key-'+'x'*32,service=service);client=TestClient(app)
            def api(path,payload=None):
                response=client.post(path,json=payload,headers={'X-Memoria-Key':'isolated-animal-test-key-'+'x'*32}) if payload else client.get(path,headers={'X-Memoria-Key':'isolated-animal-test-key-'+'x'*32})
                self.assertEqual(response.status_code,201 if payload else 200);return response.json()
            return service,client,api
        service,client,api=connection()
        original=m.write_checkpoint
        def crash(path,value,mode=0o600):
            if path==self.ack:raise OSError('crash after core store and retrieval')
            original(path,value,mode)
        with patch.object(m,'write_checkpoint',side_effect=crash):
            with self.assertRaises(OSError):self.sync(api)
        self.assertEqual(service.store.count,1);self.assertFalse(self.ack.exists());client.close()
        service2,client2,api2=connection();result=self.sync(api2)
        self.assertEqual(service2.store.count,1);self.assertEqual(result['stored_and_recovered_encounters'],1)
        self.assertEqual(result['verified_history'][0]['encounter']['sample_count'],2)
        self.assertFalse(result['decision_use']);client2.close()
if __name__=='__main__':unittest.main()
