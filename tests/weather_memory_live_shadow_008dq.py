"""Read actual live weather, test the frozen SDK in an isolated temporary store.
No production memory credentials, core writes, world writes or installation.
Run with PYTHONPATH=apps/world-runtime:packages and the production venv.
"""
import json, sys, tempfile, time, math
from pathlib import Path
import world_weather_control as control
import world_weather_memory_experiment as memory
from nov_navigation_memory_sync import write_checkpoint
from nov_spatial_memory_sync import _validate_ack
SDK='/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src'
sys.path.insert(0,SDK)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
ROOT=Path(__file__).resolve().parents[1]
STATUS=Path('/var/www/live-infinita-godot/navigation-memory/weather-control.json')
RESULT=Path('/home/etbra/008dq-live-shadow-result.json')
PREDICTION=Path('/home/etbra/008dq-live-shadow-prediction.json')


def read_status():
    status=json.loads(STATUS.read_text())
    assert status['schema']==control.SCHEMA and -30<=time.time()-status['generated_at_unix']<=30
    return status


with tempfile.TemporaryDirectory(prefix='008dq-shadow-',dir='/home/etbra') as root:
    key='isolated-shadow-test-'+('x'*40)
    service=ProductStructuralObservationService.open(Path(root)/'core',backend='sqlite',allow_fallback=False)
    app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
    client=TestClient(app)
    # All seed rows are previously measured physical deliveries, never forecasts.
    seed1=json.loads((ROOT/'docs/WEATHER_CONTROL_RESULT_008DP.json').read_text())['real_websocket_isolated_probe']['last_evaluation']
    seed2=json.loads((ROOT/'docs/WEATHER_CONTROL_PRODUCTION_008DP.json').read_text())['status']['last_evaluation']
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        status=read_status();trial=status['pending']
        if status['last_evaluation'] and trial['origin']['time_ms']<=status['last_time_ms']<=trial['origin']['time_ms']+5000:break
        time.sleep(2)
    else:raise RuntimeError('No fresh live baseline trial')
    world=trial['world_id'];duration=trial['tick_duration_ms']
    control.validate_trial(trial,world,duration)
    seed3=status['last_evaluation']
    identities=set()
    for row in [seed1,seed2,seed3]:
        control.validate_trial(row['trial'],world,duration)
        assert row['observed']['time_ms']<=trial['origin']['time_ms']
        payload=memory.transition_payload(world,duration,row['trial']['origin'],row['observed'])
        response=client.post('/api/v1/structural/observations?defer_associations=true',json=payload,headers={'X-Memoria-Key':key})
        assert response.status_code==201
        ack=response.json();_validate_ack(ack,payload);identities.add(ack['observation_id'])
    assert len(identities)==3 and service.store.count==3
    response=client.get('/api/v1/structural/observations/recent?limit=64',headers={'X-Memoria-Key':key}).json()
    cache=memory.merge_recalled([],response,world,duration)
    forecast=memory.predict(trial['origin'],cache)
    assert forecast and {s['observation_id'] for s in forecast['supports']}==identities
    latest=read_status();assert latest['pending']['prediction_id']==trial['prediction_id']
    assert latest['last_time_ms']<trial['target_time_ms']
    prediction={'control':trial,'forecast':forecast,'issued_at_unix':time.time(),
                'issue_observed_logical_time_ms':latest['last_time_ms'],'production_memory':False}
    write_checkpoint(PREDICTION,prediction)
    print('008DQ_REAL_LIVE_SHADOW_PREDICTION_COMMITTED',trial['prediction_id'],flush=True)
    deadline=time.monotonic()+95
    while time.monotonic()<deadline:
        status=read_status();row=status['last_evaluation']
        if row and row['trial']['prediction_id']==trial['prediction_id']:
            observed=row['observed']
            assert trial['target_time_ms']<=observed['time_ms']<=trial['target_time_ms']+control.TOLERANCE_MS
            assert prediction['issued_at_unix']<status['generated_at_unix']
            errors={}
            for method,values in [('control',trial['prediction']),('memory',forecast['values'])]:
                errors[method]={k:abs(observed['values'][k]-values[k]) for k in control.FIELDS}
                errors[method]['wind_vector_mps']=math.hypot(errors[method]['wind_x_mps'],errors[method]['wind_z_mps'])
            result={'schema':'live-infinita-weather-memory-live-shadow/v1','source':'isolated_frozen_core_actual_live_weather',
                    'production_memory':False,'prediction':prediction,'observed':observed,'errors':errors,
                    'paired':1,'physical_influence':False,'general_improvement_claim':False}
            write_checkpoint(RESULT,result)
            print('008DQ_REAL_LIVE_SHADOW_PAIR_OK',json.dumps(errors),flush=True)
            break
        time.sleep(2)
    else:raise RuntimeError('Actual live target not observed')
    client.close()
