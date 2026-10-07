import unittest, tempfile, json, sys, copy, math
from pathlib import Path
import world_weather_control as control
import world_weather_memory_experiment as memory
from world_physical_weather import initial as physical_initial, snapshot
from nov_spatial_memory_sync import _observation_id, _validate_ack
SDK='/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src'


def sample(t, wind):
    return {'time_ms':t,'values':{'temperature_c':20.,'humidity':0.5,'cloud_coverage':0.3,'wind_x_mps':wind,'wind_z_mps':0.}}


def envelope(origin, observed, world='test'):
    p=memory.transition_payload(world,500,origin,observed)
    return {**p,'observation_id':_observation_id(p['event'])}


def recall(rows):return {'items':rows,'semantic_projection':False}


class RecallTest(unittest.TestCase):
    def past(self, sign=1):
        return [envelope(sample(i*60000,sign*i),sample((i+1)*60000,sign*(i+1))) for i in range(3)]

    def test_actual_recalled_ids_change_forecast_ablation_removes_it(self):
        rows=self.past();cache=memory.merge_recalled([],recall(rows),'test',500)
        forecast=memory.predict(sample(180000,3),cache)
        self.assertAlmostEqual(forecast['values']['wind_x_mps'],4)
        self.assertEqual({s['observation_id'] for s in forecast['supports']},{r['observation_id'] for r in rows})
        self.assertAlmostEqual(sum(s['weight'] for s in forecast['supports']),1)
        self.assertIsNone(memory.predict(sample(180000,3),[]))

    def test_future_memories_excluded_and_worlds_filtered(self):
        rows=self.past()+[envelope(sample(180000,3),sample(240000,7))]
        cache=memory.merge_recalled([],recall(rows),'test',500)
        forecast=memory.predict(sample(180000,3),cache)
        self.assertAlmostEqual(forecast['values']['wind_x_mps'],4)
        self.assertTrue(all(s['observed_end_ms']<=180000 for s in forecast['supports']))
        self.assertIsNone(memory.predict(sample(120000,2),cache))
        self.assertEqual(memory.merge_recalled([],recall(self.past()),'other',500),[])

    def test_envelope_digest_identity_and_raw_predictions_rejected(self):
        row=self.past()[0]
        for field in ['signature','sequence','byte_length']:
            bad=copy.deepcopy(row);bad['event'][field]='0'*16 if field=='signature' else 123
            with self.assertRaises(ValueError):memory.merge_recalled([],recall([bad]),'test',500)
        bad=copy.deepcopy(row);bad['provenance']['contains_prediction']=True
        with self.assertRaises(ValueError):memory.merge_recalled([],recall([bad]),'test',500)
        bad=copy.deepcopy(row);bad['observation_id']='forged'
        with self.assertRaises(ValueError):memory.merge_recalled([],recall([bad]),'test',500)
        bad=copy.deepcopy(row);bad['provenance']['observation']['observed']['values']['wind_x_mps']=float('nan')
        with self.assertRaises(ValueError):memory.merge_recalled([],recall([bad]),'test',500)

    def test_recall_bounds_dedup_and_elapsed_normalization(self):
        origin=sample(0,0);observed=sample(65000,1.0833333333333333)
        rows=[envelope(sample(i*65000,0),sample((i+1)*65000,1.0833333333333333)) for i in range(3)]
        cache=memory.merge_recalled([],recall(rows+rows),'test',500)
        self.assertEqual(len(cache),3)
        forecast=memory.predict(sample(195000,0),cache)
        self.assertAlmostEqual(forecast['values']['wind_x_mps'],1)
        with self.assertRaises(ValueError):memory.transition_payload('test',500,origin,sample(66000,1))
        with self.assertRaises(ValueError):memory.merge_recalled([],recall(rows*34),'test',500)

    def test_recalled_cache_is_bounded_as_observations_grow(self):
        cache=[]
        for start in range(0,400,80):
            rows=[envelope(sample(i*60000,0),sample((i+1)*60000,1)) for i in range(start,start+80)]
            cache=memory.merge_recalled(cache,recall(rows),'test',500)
        self.assertEqual(len(cache),memory.CACHE_LIMIT)
        self.assertEqual(len({r['observation_id'] for r in cache}),memory.CACHE_LIMIT)
        self.assertEqual(cache[0]['payload']['provenance']['observation']['observed']['time_ms'],17*60000)

    def test_forecast_respects_vector_and_field_limits(self):
        rows=[envelope(sample(i*60000,0),sample((i+1)*60000,8)) for i in range(3)]
        cache=memory.merge_recalled([],recall(rows),'test',500)
        origin=sample(180000,5);origin['values']['wind_z_mps']=5
        forecast=memory.predict(origin,cache)
        self.assertLessEqual(math.hypot(forecast['values']['wind_x_mps'],forecast['values']['wind_z_mps']),8.000001)
        control.validate_sample({'time_ms':240000,'values':forecast['values']})


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.world=self.root/'world';self.weather=self.root/'weather';self.clock=self.root/'clock'
        self.world.write_text('{"world_id":"test"}')
        self.rows=[envelope(sample(i*60000,i),sample((i+1)*60000,i+1)) for i in range(3)]
        self.sent=[];self.stamp=1000
        self.args=dict(world=self.world,weather=self.weather,clock=self.clock,
            base_state=self.root/'base-state',base_public=self.root/'base-public',state=self.root/'memory-state',public=self.root/'memory-public',
            send=self.send,fetch=lambda:recall(self.rows),now=lambda:self.stamp)
    def tearDown(self):self.temp.cleanup()
    def observation(self,t,wind):
        s=physical_initial({'world_id':'test','regions':[]},t,500)
        s['wind_x_mps']=wind;s['wind_z_mps']=0
        self.weather.write_text(json.dumps(snapshot(s,self.stamp)))
        self.clock.write_text(json.dumps({'clock_schema':'simulation_clock_v1','tick':t//500,'tick_duration_ms':500,'paused':False}))
    def send(self,p):
        self.sent.append(copy.deepcopy(p))
        row={**p,'observation_id':_observation_id(p['event'])};self.rows.append(row)
        return {'observation_id':row['observation_id'],'stored':True,'duplicate':False,'association_sync_deferred':True,'semantic_projection':False,'backend':'sqlite'}
    def publish(self):return memory.publish(**self.args)
    def read(self,key):return json.loads(self.args[key].read_text())

    def test_prospective_paired_score_restart_and_no_prediction_ingest(self):
        self.observation(180000,3);self.publish();pending=self.read('state')['pending']
        self.assertIsNotNone(pending)
        self.assertLess(pending['issued_logical_time_ms'],pending['control']['target_time_ms'])
        self.stamp=1060;self.observation(240000,4);self.publish()
        state=self.read('state');self.assertEqual(state['paired'],1)
        self.assertEqual(state['history'][0]['prediction'],pending)
        self.assertAlmostEqual(state['error_sums']['memory']['wind_vector_mps'],0)
        self.assertAlmostEqual(state['error_sums']['control']['wind_vector_mps'],1)
        self.assertEqual(state['memory_wins']['wind_vector_mps'],1)
        self.assertEqual(self.read('base_state')['evaluated'],1)
        self.publish();self.assertEqual(self.read('state')['paired'],1)
        self.assertEqual(len(self.sent),1)
        p=self.sent[0]['provenance'];self.assertFalse(p['contains_prediction'])
        self.assertEqual(p['observation']['observed']['values']['wind_x_mps'],4)
        self.assertNotIn('forecast',p)
        self.assertEqual(self.args['state'].stat().st_mode&0o777,0o600)
        self.assertEqual(self.args['public'].stat().st_mode&0o777,0o644)

    def test_wrong_memories_can_lose_against_control(self):
        self.rows=[envelope(sample(i*60000,3),sample((i+1)*60000,2)) for i in range(3)]
        self.observation(180000,3);self.publish()
        self.stamp=1060;self.observation(240000,4);self.publish()
        state=self.read('state')
        self.assertGreater(state['error_sums']['memory']['wind_vector_mps'],state['error_sums']['control']['wind_vector_mps'])
        self.assertEqual(state['memory_wins']['wind_vector_mps'],0)

    def test_api_failure_preserves_control_and_is_not_a_memory_trial(self):
        def unavailable():raise OSError('offline')
        self.args['fetch']=unavailable
        self.observation(180000,3);self.publish()
        self.assertIsNone(self.read('state')['pending'])
        self.assertEqual(self.read('state')['unavailable'],1)
        self.publish();self.assertEqual(self.read('state')['unavailable'],1)
        self.stamp=1060;self.observation(240000,4);self.publish()
        self.assertEqual(self.read('base_state')['evaluated'],1)
        self.assertEqual(self.read('state')['paired'],0)
        self.assertGreater(self.read('state')['api_failures'],0)

    def test_late_clock_check_prevents_retrospective_prediction(self):
        self.observation(180000,3)
        def fetch():
            self.clock.write_text(json.dumps({'clock_schema':'simulation_clock_v1','tick':480,'tick_duration_ms':500,'paused':False}))
            return recall(self.rows)
        self.args['fetch']=fetch;self.publish()
        self.assertIsNone(self.read('state')['pending'])
        self.assertEqual(self.read('state')['last_reason'],'issuance_window_unavailable')

    def test_missed_window_not_paired_and_future_restart_not_retrofit(self):
        self.observation(180000,3);self.publish()
        self.stamp=1070;self.observation(250000,4);self.publish()
        self.assertEqual(self.read('state')['paired'],0)
        self.assertEqual(self.read('state')['missed'],1)
        self.assertEqual(self.read('base_state')['missed'],1)

    def test_corruption_preserves_memory_public_but_control_keeps_running(self):
        self.observation(180000,3);self.publish()
        prior=self.args['public'].read_bytes();base=self.args['base_state'].read_bytes()
        state=self.read('state');state['paired']=9;self.args['state'].write_text(json.dumps(state))
        self.stamp=1060;self.observation(240000,4)
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(self.args['public'].read_bytes(),prior)
        self.assertNotEqual(self.args['base_state'].read_bytes(),base)
        self.assertEqual(self.read('base_state')['evaluated'],1)

    def test_failure_phase_is_safe_and_control_survives_timeout(self):
        def unavailable():raise TimeoutError('sensitive diagnostic text')
        self.args['fetch']=unavailable
        self.observation(180000,3);self.publish()
        failure=self.read('public')['last_api_failure']
        self.assertEqual(failure['phase'],'fetch_recent')
        self.assertEqual(failure['code'],'weather_memory_api_timeout')
        self.assertNotIn('sensitive',json.dumps(self.read('public')))
        self.assertEqual(self.read('base_state')['pending']['origin']['time_ms'],180000)
        self.publish();self.assertEqual(self.read('public')['last_api_failure'],failure)

    def test_legacy_checkpoint_without_failure_field_is_preserved(self):
        self.observation(180000,3);self.publish()
        state=self.read('state');state.pop('last_api_failure');state['checksum']=memory.checksum(state)
        self.args['state'].write_text(json.dumps(state))
        pending=copy.deepcopy(state['pending'])
        self.publish()
        self.assertEqual(self.read('state')['pending'],pending)
        self.assertEqual(self.read('state')['paired'],0)

    def test_real_frozen_core_ack_retrieval_restart_and_forecast(self):
        sys.path.insert(0,SDK)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
        key='isolated-weather-test-key-'+('x'*32)
        def connection():
            service=ProductStructuralObservationService.open(self.root/'actual-core',backend='sqlite',allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            client=TestClient(app)
            def send(p):
                result=client.post('/api/v1/structural/observations?defer_associations=true',json=p,headers={'X-Memoria-Key':key})
                self.assertEqual(result.status_code,201);return result.json()
            def fetch():return client.get('/api/v1/structural/observations/recent?limit=64',headers={'X-Memoria-Key':key}).json()
            return service,client,send,fetch
        service,client,send,fetch=connection()
        for row in self.rows:
            p={k:row[k] for k in ('event','provenance')};_validate_ack(send(p),p)
            self.assertTrue(send(p)['duplicate'])
        self.assertEqual(service.store.count,3)
        client.close()
        service2,client2,send2,fetch2=connection()
        self.assertEqual(service2.store.count,3)
        self.args.update(send=send2,fetch=fetch2)
        self.observation(180000,3);self.publish()
        pending=self.read('state')['pending']
        retrieved={r['observation_id'] for r in fetch2()['items']}
        self.assertTrue({r['observation_id'] for r in pending['forecast']['supports']}<=retrieved)
        self.assertAlmostEqual(pending['forecast']['values']['wind_x_mps'],4)
        self.stamp=1060;self.observation(240000,4)
        from unittest.mock import patch
        durable_write=memory.write_checkpoint
        def crash_before_checkpoint(path,payload,**kwargs):
            if path==self.args['state']:raise OSError('simulated crash after durable core ACK')
            return durable_write(path,payload,**kwargs)
        with patch.object(memory,'write_checkpoint',side_effect=crash_before_checkpoint):
            with self.assertRaises(OSError):self.publish()
        self.assertEqual(service2.store.count,4)
        self.assertEqual(self.read('state')['paired'],0)
        client2.close()
        service3,client3,send3,fetch3=connection()
        self.args.update(send=send3,fetch=fetch3)
        self.publish()
        self.assertEqual(self.read('state')['paired'],1)
        self.assertEqual(service3.store.count,4)
        self.publish();self.assertEqual(self.read('state')['paired'],1)
        client3.close()


class ConnectorBudgetTest(unittest.TestCase):
    def test_post_and_get_use_established_time_budgets(self):
        from unittest.mock import patch
        recorded=[]
        class Response:
            def __init__(self,status):self.status=status
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"ok":true}'
        class Opener:
            def open(self,req,timeout):
                recorded.append(timeout)
                # Simulate a request requiring more than the old five seconds.
                if timeout<7:raise TimeoutError('old budget too small')
                return Response(201 if req.data is not None else 200)
        with patch.dict(memory.os.environ,{'MEMORIA_API_KEY':'isolated-'+('x'*40)}):
            with patch.object(memory,'build_opener',return_value=Opener()):
                self.assertEqual(memory.request_api('/test',{'event':{}}),{'ok':True})
                self.assertEqual(memory.request_api('/test'),{'ok':True})
        self.assertEqual(recorded,[30,15])

    def test_http_and_wrapped_timeout_do_not_expose_response_or_key(self):
        from unittest.mock import patch
        from urllib.error import HTTPError,URLError
        class Opener:
            def __init__(self,exc):self.exc=exc
            def open(self,*args,**kwargs):raise self.exc
        for exc,expected in [(HTTPError('http://127.0.0.1:8788/test',401,'sensitive text',{},None),'weather_memory_api_http_401'),(URLError(TimeoutError('sensitive text')),'weather_memory_api_timeout')]:
            with patch.dict(memory.os.environ,{'MEMORIA_API_KEY':'isolated-'+('x'*40)}):
                with patch.object(memory,'build_opener',return_value=Opener(exc)):
                    with self.assertRaises(memory.WeatherMemoryAPIError) as result:memory.request_api('/test')
            self.assertEqual(str(result.exception),expected)
            self.assertNotIn('sensitive',str(result.exception))
