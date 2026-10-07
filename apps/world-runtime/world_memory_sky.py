"""Celestial projection of confirmed aggregate memories, not primitive symbols."""
from pathlib import Path
import json, math, time
from hashlib import sha256, blake2b
from cognitive_terrain_projection import DEFAULT_DB, _readonly_sqlite, _canonical, _read_json
from nov_navigation_memory_sync import write_checkpoint
from nov_spatial_memory_sync import _post_local, _validate_ack
from world_sky_clock import sky_clock
SCHEMA="live-infinita-memory-sky/v1"
WORLD=Path("/var/lib/live-infinita/autonomous-world/world.json")
CLOCK=WORLD.with_name("simulation-clock.json")
REGISTRY=Path("/var/lib/live-infinita/memoria-local/celestial-anchors.json")
OUTPUT=Path("/var/lib/live-infinita/cognitive-terrain/sky.json")
LIMIT=256

def anchor_payload(body, world_id, birth_tick):
    definition={"body":body,"world_id":world_id,"birth_tick":birth_tick,
                "role":"world_celestial_definition","orbit":"shared_clock_opposition"}
    raw=_canonical(definition)
    event={"version":1,"source_id":f"live.infinita:{world_id}:celestial:{body}",
           "sequence":0,"byte_offset":0,"byte_length":len(raw),
           "trail":[int.from_bytes(blake2b(body.encode(),digest_size=8).digest(),"big")],
           "relation_ids":[],"signature":blake2b(raw,digest_size=8).hexdigest(),"resolution":1}
    return {"event":event,"provenance":{"hierarchy_id":f"live:celestial:{world_id}",
        "source_kind":"world_celestial_definition","world_id":world_id,
        "definition":definition,"world_write_authority":False,
        "selection_authority":False,"chronological_episode":False}}

def ensure_anchors(world_id, tick, registry=REGISTRY, send=_post_local):
    if registry.exists():
        saved=_read_json(registry,16384,"celestial_registry")
        if saved.get("world_id")!=world_id or saved.get("schema")!=SCHEMA:
            raise ValueError("celestial_registry_identity")
        payloads=saved.get("payloads")
        if not isinstance(payloads,list) or len(payloads)!=2:
            raise ValueError("celestial_registry_contract")
    else:
        payloads=[anchor_payload(b,world_id,tick) for b in ["sun","moon"]]
        write_checkpoint(registry,{"schema":SCHEMA,"world_id":world_id,"payloads":payloads})
    bodies=[]
    for body,payload in zip(["sun","moon"],payloads):
        birth=payload.get("provenance",{}).get("definition",{}).get("birth_tick")
        if type(birth) is not int or birth<0 or payload!=anchor_payload(body,world_id,birth):
            raise ValueError("celestial_anchor_changed")
        response=send(payload)
        # Duplicate append in the actual core reconstructs existing durable content.
        _validate_ack(response,payload)
        bodies.append({"body":body,"memory_id":response["observation_id"],
                       "payload_bytes":payload["event"]["byte_length"],"birth_tick":birth,
                       "provenance":"world_celestial_definition","confirmed":True})
    return bodies

def brightness(payload_bytes, age_ticks, tick_ms):
    age_hours=max(0,age_ticks)*tick_ms/3600000.0
    distance=1.0+math.log1p(age_hours)
    luminosity=math.log1p(payload_bytes)/8.0
    return distance,min(1.0,luminosity/(distance*distance))

def memory_rows(db_path,world_id,tick,tick_ms):
    if db_path.is_symlink() or not db_path.is_file() or db_path.stat().st_size>256*1024*1024:
        raise ValueError("sky_memory_database")
    db=_readonly_sqlite(db_path)
    try:
        db.execute("BEGIN")
        total=db.execute("SELECT COUNT(*) FROM observations WHERE world_id=?",(world_id,)).fetchone()[0]
        # Explicit bounded recent subset, not a claim to cover every primitive node.
        rows=db.execute("SELECT record_key,content_sha256,source_json,episode_id,logical_tick FROM observations WHERE world_id=? ORDER BY logical_tick DESC,record_key DESC LIMIT 8192",(world_id,)).fetchall()
    finally: db.close()
    stars=[]
    for key,digest,source_json,episode_id,birth in rows:
        raw=source_json.encode("utf-8")
        if len(raw)>262144 or sha256(raw).hexdigest()!=digest:
            raise ValueError("sky_memory_digest")
        p=json.loads(raw);source=p.get("source",{});obs=p.get("observation",{})
        identity={k:source.get(k) for k in ["system","world_id","entity_id","episode_id"]}
        if (sha256(_canonical(identity)).hexdigest()!=key or p.get("record_key")!=key
            or source.get("system")!="live.infinita" or source.get("world_id")!=world_id
            or source.get("entity_id")!="nov" or source.get("episode_id")!=episode_id
            or p.get("schema")!="live-infinita-npc-episode-observation/v1"
            or p.get("authority")!="observed-outcome-only" or p.get("world_write_authority") is not False
            or type(birth) is not int or birth<0 or obs.get("logical_tick")!=birth):
            raise ValueError("sky_memory_provenance")
        if birth>tick: continue
        distance,apparent=brightness(len(raw),tick-birth,tick_ms)
        stars.append({"memory_id":"external-episode:"+key,"birth_tick":birth,
            "time_basis":"experience_logical_tick","payload_bytes":len(raw),
            "payload_sha256":digest,"distance":distance,"brightness":apparent,
            "confirmed":True})
    stars.sort(key=lambda row:(-row["brightness"],row["memory_id"]))
    return stars[:LIMIT],total,len(rows)

def publish(world=WORLD,clock=CLOCK,db_path=DEFAULT_DB,registry=REGISTRY,output=OUTPUT,send=_post_local,now=time.time):
    world_id=_read_json(world,2*1024*1024,"sky_world").get("world_id")
    c=sky_clock(clock,world_id)
    if c is None:raise ValueError("sky_clock_missing")
    stars,total,scanned=memory_rows(db_path,world_id,c["tick"],c["tick_duration_ms"])
    bodies=ensure_anchors(world_id,c["tick"],registry,send)
    out={"schema":SCHEMA,"world_id":world_id,"generated_at_unix":int(now()),
         "source":"confirmed_local_memoria_aggregate_records",
         "unit":"persisted_aggregate_memory","time_basis":"experience_logical_tick",
         "tick_duration_ms":c["tick_duration_ms"],"stars":stars,"bodies":bodies,
         "total_aggregate_memories":total,"scanned_memories":scanned,
         "display_budget":LIMIT,"primitive_node_catalog":False,
         "telescope":False,"world_write_authority":False}
    write_checkpoint(output,out,mode=0o644)
    return {"stars":len(stars),"bodies":len(bodies),"total_memories":total}

def read_sky(path,world_id,now=time.time):
    try:
        p=_read_json(path,256*1024,"sky")
        if p.get("schema")!=SCHEMA or p.get("world_id")!=world_id or p.get("source")!="confirmed_local_memoria_aggregate_records":
            return None
        stamp=p.get("generated_at_unix")
        if type(stamp) is not int or not -30<=now()-stamp<=180:return None
        if not isinstance(p.get("stars"),list) or len(p["stars"])>LIMIT:return None
        if not isinstance(p.get("bodies"),list) or len(p["bodies"])!=2:return None
        return p
    except (OSError,ValueError,TypeError,RuntimeError):return None

if __name__=="__main__":
    print(json.dumps(publish(),sort_keys=True))
