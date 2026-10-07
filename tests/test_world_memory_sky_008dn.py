import unittest,json,sqlite3,tempfile,time,sys
from pathlib import Path
from hashlib import sha256
from world_memory_sky import publish,memory_rows,ensure_anchors,brightness,read_sky,SCHEMA
from cognitive_terrain_projection import _canonical
from nov_spatial_memory_sync import _observation_id
SDK="/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src"

class MemorySkyTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.d=Path(self.temp.name)
        self.db=self.d/"episodes.sqlite3"
        db=sqlite3.connect(self.db)
        db.execute("CREATE TABLE observations(record_key TEXT,content_sha256 TEXT,source_json TEXT,episode_id TEXT,logical_tick INTEGER,world_id TEXT)")
        for episode,tick in [("a",10),("b",20)]:
            source={"system":"live.infinita","world_id":"test","entity_id":"nov","episode_id":episode}
            key=sha256(_canonical(source)).hexdigest()
            raw=_canonical({"schema":"live-infinita-npc-episode-observation/v1","record_key":key,"source":source,
                "authority":"observed-outcome-only","world_write_authority":False,"observation":{"logical_tick":tick}})
            db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?)",(key,sha256(raw).hexdigest(),raw.decode(),episode,tick,"test"))
        db.commit();db.close()
        self.world=self.d/"world.json";self.world.write_text('{"world_id":"test"}')
        self.clock=self.d/"clock.json";self.clock.write_text(json.dumps({"clock_schema":"simulation_clock_v1","tick":30,"tick_duration_ms":500,"paused":False}))
    def tearDown(self):self.temp.cleanup()
    def fake_ack(self,p):
        return {"observation_id":_observation_id(p["event"]),"stored":True,"duplicate":False,
            "association_sync_deferred":True,"semantic_projection":False,"backend":"sqlite"}
    def test_payload_identity_age_and_no_raw_content_export(self):
        rows,total,scanned=memory_rows(self.db,"test",30,500)
        self.assertEqual((len(rows),total,scanned),(2,2,2))
        self.assertTrue(all(row["payload_bytes"]>0 for row in rows))
        self.assertTrue(all(row["birth_tick"] in [10,20] for row in rows))
        self.assertFalse(any("source_json" in row for row in rows))
        newer,_,_=memory_rows(self.db,"test",30000,500)
        for a,b in zip(sorted(rows,key=lambda x:x["memory_id"]),sorted(newer,key=lambda x:x["memory_id"])):
            self.assertEqual(a["birth_tick"],b["birth_tick"])
            self.assertGreater(b["distance"],a["distance"])
            self.assertLess(b["brightness"],a["brightness"])
        self.assertGreater(brightness(2000,1000,500)[1],brightness(100,1000,500)[1])
    def test_corrupt_payload_rejected_and_previous_output_preserved(self):
        output=self.d/"sky.json"
        kwargs=dict(world=self.world,clock=self.clock,db_path=self.db,registry=self.d/"anchors.json",output=output,send=self.fake_ack)
        publish(**kwargs);prior=output.read_bytes()
        db=sqlite3.connect(self.db);db.execute("UPDATE observations SET content_sha256='broken'");db.commit();db.close()
        with self.assertRaises(ValueError):publish(**kwargs)
        self.assertEqual(prior,output.read_bytes())
    def test_fresh_world_and_future_filter(self):
        output=self.d/"sky.json"
        publish(world=self.world,clock=self.clock,db_path=self.db,registry=self.d/"anchors.json",output=output,send=self.fake_ack,now=lambda:1000)
        self.assertIsNotNone(read_sky(output,"test",now=lambda:1000))
        self.assertIsNone(read_sky(output,"other",now=lambda:1000))
        self.assertIsNone(read_sky(output,"test",now=lambda:1181))
        rows,_,_=memory_rows(self.db,"test",5,500);self.assertEqual(rows,[])
        self.assertEqual(output.stat().st_mode & 0o777,0o644)
    def test_real_core_api_ack_replay_restart_and_retrieval(self):
        sys.path.insert(0,SDK)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
        root=self.d/"core";key="test-key-"+"x"*40
        def connection():
            service=ProductStructuralObservationService.open(root,backend="sqlite",allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            client=TestClient(app)
            def send(p):
                response=client.post("/api/v1/structural/observations?defer_associations=true",json=p,headers={"X-Memoria-Key":key})
                self.assertEqual(response.status_code,201)
                return response.json()
            return service,client,send
        service,client,send=connection()
        registry=self.d/"anchors.json"
        first=ensure_anchors("test",30,registry,send)
        self.assertEqual(service.store.count,2)
        repeat=ensure_anchors("test",300,registry,send)
        self.assertEqual(first,repeat);self.assertEqual(service.store.count,2)
        service2,client2,send2=connection()
        restarted=ensure_anchors("test",500,registry,send2)
        self.assertEqual(first,restarted);self.assertEqual(service2.store.count,2)
        recovered=client2.get("/api/v1/structural/observations/recent?limit=2",headers={"X-Memoria-Key":key}).json()["items"]
        self.assertEqual({r["observation_id"] for r in recovered},{r["memory_id"] for r in first})
        self.assertTrue(all(row["birth_tick"]==30 for row in first))
        client.close();client2.close()

    def test_actual_incremental_episode_receipt_matches_star_after_restart(self):
        sys.path.insert(0,SDK)
        from memoria_resolutiva.external_episode_contract import ExternalEpisodeRequest
        from memoria_resolutiva.external_episode_incremental import IncrementalExternalEpisodeStore
        root=self.d/"genuine-episodes"
        store=IncrementalExternalEpisodeStore(root)
        source={"system":"live.infinita","world_id":"test","entity_id":"nov","episode_id":"plan:sky-test","source_schema":"npc_episode_v1","source_kind":"need_outcome","plan_id":"sky-test","proposal_id":"proposal-sky","plan_revision":1}
        identity={k:source[k] for k in ["system","world_id","entity_id","episode_id"]}
        unsigned={"schema":"live-infinita-npc-episode-observation/v1","record_key":sha256(_canonical(identity)).hexdigest(),"source":source,
            "observation":{"logical_tick":10,"need":"exploration","target_entity_id":None,"strategy_id":None,
                "context":{"period":"day","weather":"clear","region_id":"forest","danger_level":0.1},
                "outcome":{"satisfaction":0.8,"observed_risk":0.1,"elapsed_ticks":3,"preemptions":0,"replans":0}},
            "authority":"observed-outcome-only","world_write_authority":False}
        req=ExternalEpisodeRequest(**unsigned,content_sha256=sha256(_canonical(unsigned)).hexdigest())
        receipt=store.observe(req)
        self.assertTrue(receipt["ack"]);self.assertTrue(receipt["stored"])
        self.assertFalse(store.observe(req)["stored"])
        store.close()
        restarted=IncrementalExternalEpisodeStore(root)
        self.assertEqual(restarted.count,1);restarted.close()
        rows,total,_=memory_rows(root/"external-episodes.sqlite3","test",100,500)
        self.assertEqual(total,1)
        self.assertEqual(rows[0]["memory_id"],receipt["persistence"]["state_id"])
        self.assertEqual(rows[0]["payload_sha256"],receipt["content_sha256"])
        self.assertEqual(rows[0]["payload_bytes"],len(_canonical(unsigned)))
        self.assertEqual(rows[0]["birth_tick"],10)

    def test_paused_world_receives_changed_sky_without_world_mutation(self):
        import ast,asyncio,types
        source=Path(__file__).parents[1]/"apps/world-runtime/main_spatial.py"
        tree=ast.parse(source.read_text())
        fn=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=="_external_world_sync_loop")
        world={"world_id":"test","sequence":1}
        calls=[]
        async def broadcast(message):calls.append(message)
        async def stop(_):raise asyncio.CancelledError()
        class FakePath:
            def __init__(self,*args):pass
            def stat(self):return types.SimpleNamespace(st_mtime_ns=123,st_size=100)
        ns={"_last_world_marker":(1,""),"_last_sky_marker":None,"_last_weather_marker":None,"_external_world_sync_seconds":lambda:0.5,
            "core":types.SimpleNamespace(engine=types.SimpleNamespace(load_world=lambda:world)),
            "_world_marker":lambda w:(w["sequence"],""),"Path":FakePath,"session_views":{"client":{}},
            "spatial_broadcast":broadcast,"cold_store":None,
            "asyncio":types.SimpleNamespace(CancelledError=asyncio.CancelledError,sleep=stop)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),"exec"),ns)
        with self.assertRaises(asyncio.CancelledError):asyncio.run(ns["_external_world_sync_loop"]())
        self.assertEqual(calls,[{"type":"world_state","world":world}])
        self.assertEqual(world,{"world_id":"test","sequence":1})
        self.assertEqual(ns["_last_world_marker"],(1,""))
