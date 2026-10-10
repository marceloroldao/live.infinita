extends RefCounted
# Experimental consumer of eye observations; no wildlife registry or core writes.
const MAX_MS:=5000
const MAX_DISTANCE_M:=12.0
var _eyes=preload("res://nov_animal_approach.gd").new()
var _active:Dictionary={}
var _used:Array=[]
var _previous:=Vector3(INF,INF,INF)
var _distance:=0.0
var _last_ms:=-1
var result:Dictionary={}
func _init()->void:_eyes.enabled=true
func observe(value:Dictionary)->void:_eyes.observe(value)
func begin(outcome:Dictionary,current:Vector3,now:int,resolve:Callable)->bool:
    if _used.size()>=32 or not _active.is_empty() or not current.is_finite() or not resolve.is_valid() or now<_last_ms:return false
    if outcome.get("result")!="contact_lost" or outcome.get("censored")!=false or outcome.get("capture")!=false or outcome.get("world_write_authority")!=false:return false
    var ended=outcome.get("ended_ms")
    if typeof(ended) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(ended)) or float(ended)!=floorf(float(ended)) or ended>now or now-int(ended)>300:return false
    var id=outcome.get("id");var entity=outcome.get("entity_id");var world=outcome.get("world_id")
    if typeof(id)!=TYPE_STRING or id.is_empty() or _used.has(id) or typeof(entity)!=TYPE_STRING or typeof(world)!=TYPE_STRING:return false
    if not _eyes._seen.has(entity):return false
    var seen:Dictionary=_eyes._seen[entity]
    if seen.world!=world or seen.stamp>now or now-int(seen.stamp)>6000 or Time.get_ticks_msec()-int(seen.received)>6000:return false
    var point:Vector3=seen.point
    var offset:=Vector2(point.x-current.x,point.z-current.z)
    if offset.length()>18.0:return false
    var direction:=offset.normalized()
    var requested:=current+Vector3(direction.x,0,direction.y)*minf(MAX_DISTANCE_M,maxf(0.0,offset.length()-3.0))
    var resolved:Dictionary=resolve.call(requested)
    var goal:Vector3=resolved.get("position",Vector3(INF,INF,INF))
    if not bool(resolved.get("allowed",false)) or not goal.is_finite() or goal.distance_to(requested)>2.0 or Vector2(goal.x-current.x,goal.z-current.z).length()>MAX_DISTANCE_M:return false
    _eyes._world=world
    _active={"phase":"contact_search","source":"last_eye_observation_hypothesis","entity_id":entity,"world_id":world,"approach_id":id,
        "started_ms":now,"deadline_ms":now+MAX_MS,"wall_started":Time.get_ticks_msec(),"seed_observed_ms":seen.stamp,
        "last_observed_point":[point.x,point.y,point.z],"goal":[goal.x,goal.y,goal.z],"contains_prediction":true,"capture":false,"world_write_authority":false}
    _used.append(id)
    _previous=current;_distance=0.0;_last_ms=now;result={}
    return true
func _finish(reason:String,now:int,seen:Dictionary={})->void:
    result={"approach_id":_active.approach_id,"entity_id":_active.entity_id,"world_id":_active.world_id,
        "started_ms":_active.started_ms,"ended_ms":now,"result":reason,"distance_m":_distance,
        "seed_observed_ms":_active.seed_observed_ms,"reacquired_observed_ms":seen.get("stamp",null),
        "observed_position_m":[seen.point.x,seen.point.y,seen.point.z] if seen.has("point") else null,
        "capture":false,"absence_claim":false,"approach_confirmed":false,"learning_eligible":false,"world_write_authority":false}
    _active.clear()
func choose(current:Vector3,world:String,now:int)->Dictionary:
    if _active.is_empty():return {}
    if not current.is_finite() or world!=_active.world_id or now<_last_ms:
        _finish("invalid_context",maxi(now,_last_ms));return {}
    _distance+=Vector2(current.x-_previous.x,current.z-_previous.z).length()
    _previous=current;_last_ms=now
    if now-int(_active.started_ms)>=MAX_MS or Time.get_ticks_msec()-int(_active.wall_started)>=MAX_MS or _distance>=MAX_DISTANCE_M:
        _finish("search_budget_exhausted",now);return {}
    var seen:Dictionary=_eyes._seen.get(_active.entity_id,{})
    if not seen.is_empty() and seen.world==world and int(seen.stamp)>int(_active.seed_observed_ms) and seen.stamp<=now and now-int(seen.stamp)<=300 and Time.get_ticks_msec()-int(seen.received)<=500:
        _finish("reacquired",now,seen);return {}
    var selection:=_active.duplicate(true)
    selection["distance_m"]=_distance
    return selection
